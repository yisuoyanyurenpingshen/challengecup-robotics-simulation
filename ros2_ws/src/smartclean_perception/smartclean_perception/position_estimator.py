"""Depth-based position estimation for detections.

Inputs are pixels and the aligned depth image plus camera intrinsics; the
module never reads Gazebo ground truth. A detection bbox center is
back-projected with the pinhole model, then mapped into the target frame
with a caller-supplied rigid transform (TF lookup happens in the ROS node).

Depth reliability rules:
  - zero, negative, NaN and Inf depth samples are ignored;
  - a median over a small patch around the bbox center is used so a single
    noisy pixel cannot corrupt the estimate;
  - when too few valid samples or no transform is available, the caller
    must mark the detection position_valid=false.
"""

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import numpy as np


@dataclass(frozen=True)
class CameraIntrinsics:
    """Pinhole intrinsics used for back-projection (focal in pixels)."""

    fx: float
    fy: float
    cx: float
    cy: float

    @classmethod
    def from_camera_info(cls, camera_info) -> "CameraIntrinsics":
        return cls(
            fx=float(camera_info.k[0]),
            fy=float(camera_info.k[4]),
            cx=float(camera_info.k[2]),
            cy=float(camera_info.k[5]),
        )

    @classmethod
    def from_hfov(
        cls, width: int, height: int, hfov_deg: float
    ) -> "CameraIntrinsics":
        """Pinhole intrinsics from image size and horizontal FOV.

        Gazebo Fortress 6.16 publishes a wrong focal length (half the true
        value) in the rgbd/depth CameraInfo, so the node derives the focal
        length analytically from the sensor's documented FOV and resolution
        instead of trusting that message.
        """

        focal = (float(width) / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
        return cls(
            fx=focal,
            fy=focal,
            cx=float(width) / 2.0,
            cy=float(height) / 2.0,
        )


@dataclass(frozen=True)
class PositionConfig:
    """Node-level knobs for the depth-based position pipeline."""

    use_depth: bool = True
    depth_topic: str = "/camera/depth/image_rect_raw"
    camera_info_topic: str = "/camera/camera_info"
    position_frame_ids: Sequence[str] = ("map", "odom")
    depth_max_stamp_delta_s: float = 0.5
    depth_patch_radius: int = 4
    camera_hfov_deg: float = 60.0


@dataclass(frozen=True)
class RigidTransform:
    """Translation plus xyzw quaternion rotation (TF convention)."""

    translation: Tuple[float, float, float]
    rotation_xyzw: Tuple[float, float, float, float]


@dataclass(frozen=True)
class EstimatedPosition:
    xyz: Tuple[float, float, float]
    depth_m: float
    frame_id: str


_METER_ENCODINGS = ("32fc1", "32FC1", "mono16")
_MILLIMETER_ENCODINGS = ("16uc1", "16UC1")


def depth_to_meters(depth: np.ndarray, encoding: str) -> np.ndarray:
    """Normalize a depth image to meters.

    ``16UC1`` images are millimetres, ``32FC1`` are already metres. The
    function returns float64 copy so NaN/Inf masking is always possible.
    """

    normalized = depth.astype(np.float64, copy=False)
    if encoding in _MILLIMETER_ENCODINGS:
        return normalized * 1e-3
    if encoding in _METER_ENCODINGS:
        return normalized
    raise ValueError("不支持的深度编码：{}".format(encoding))


def patch_median_depth(
    depth_m: np.ndarray,
    center_x: float,
    center_y: float,
    radius: int = 4,
    min_valid: int = 3,
) -> Optional[float]:
    """Median of valid depth samples around a pixel; None when unreliable."""

    rows, cols = depth_m.shape[:2]
    column = int(round(float(center_x)))
    row = int(round(float(center_y)))
    top = max(0, row - radius)
    bottom = min(rows, row + radius + 1)
    left = max(0, column - radius)
    right = min(cols, column + radius + 1)
    patch = depth_m[top:bottom, left:right]
    valid = patch[np.isfinite(patch) & (patch > 0.0)]
    if valid.size < min_valid:
        return None
    return float(np.median(valid))


def backproject_optical(
    center_x: float,
    center_y: float,
    depth_m: float,
    intrinsics: CameraIntrinsics,
) -> Optional[Tuple[float, float, float]]:
    """Back-project one pixel into the optical frame (x right, y down, z fwd)."""

    if not (np.isfinite(depth_m) and depth_m > 0.0):
        return None
    if not (
        np.isfinite(intrinsics.fx)
        and intrinsics.fx > 0.0
        and np.isfinite(intrinsics.fy)
        and intrinsics.fy > 0.0
    ):
        return None
    x = (float(center_x) - intrinsics.cx) * depth_m / intrinsics.fx
    y = (float(center_y) - intrinsics.cy) * depth_m / intrinsics.fy
    return (x, y, float(depth_m))


def transform_point(
    xyz: Sequence[float], transform: RigidTransform
) -> Tuple[float, float, float]:
    """Rotate then translate one point with a TF-style rigid transform."""

    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    qx, qy, qz, qw = (float(v) for v in transform.rotation_xyzw)
    # Standard xyzw quaternion rotation matrix.
    xx, yy, zz = qx * qx, qy * qy, qz * qz
    xy, xz, yz = qx * qy, qx * qz, qy * qz
    wx, wy, wz = qw * qx, qw * qy, qw * qz
    rotated = (
        2.0 * ((0.5 - yy - zz) * x + (xy - wz) * y + (xz + wy) * z),
        2.0 * ((xy + wz) * x + (0.5 - xx - zz) * y + (yz - wx) * z),
        2.0 * ((xz - wy) * x + (yz + wx) * y + (0.5 - xx - yy) * z),
    )
    tx, ty, tz = transform.translation
    return (rotated[0] + tx, rotated[1] + ty, rotated[2] + tz)


def estimate_position(
    bbox_xyxy: Sequence[float],
    depth_m: np.ndarray,
    intrinsics: CameraIntrinsics,
    transform: Optional[RigidTransform],
    frame_id: str,
    patch_radius: int = 4,
) -> Optional[EstimatedPosition]:
    """Full pipeline: bbox center -> patch depth -> back-project -> transform.

    Returns None (caller marks position_valid=false) when the depth patch
    is unreliable, the intrinsics are unusable, or no transform is given.
    """

    center_x = (float(bbox_xyxy[0]) + float(bbox_xyxy[2])) / 2.0
    center_y = (float(bbox_xyxy[1]) + float(bbox_xyxy[3])) / 2.0
    depth = patch_median_depth(
        depth_m, center_x, center_y, radius=patch_radius
    )
    if depth is None:
        return None
    point = backproject_optical(center_x, center_y, depth, intrinsics)
    if point is None:
        return None
    if transform is None:
        return None
    xyz = transform_point(point, transform)
    if not all(np.isfinite(v) for v in xyz):
        return None
    return EstimatedPosition(xyz=xyz, depth_m=depth, frame_id=frame_id)
