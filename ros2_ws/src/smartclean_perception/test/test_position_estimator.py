"""Unit tests for depth-based position estimation.

Covers the required edge cases: normal depth, zero depth, NaN/Inf depth,
image edges, unusable intrinsics, missing transform, rigid transform math
and the position error against a known ground truth (pure math, no Gazebo).
"""

import numpy as np
import pytest

from smartclean_perception.position_estimator import (
    CameraIntrinsics,
    PositionConfig,
    RigidTransform,
    backproject_optical,
    depth_to_meters,
    estimate_position,
    patch_median_depth,
    transform_point,
)


INTRINSICS = CameraIntrinsics(fx=554.3, fy=554.3, cx=320.0, cy=240.0)
IDENTITY = RigidTransform(
    translation=(0.0, 0.0, 0.0), rotation_xyzw=(0.0, 0.0, 0.0, 1.0)
)


def _flat_depth(rows=480, cols=640, value=2.0):
    return np.full((rows, cols), value, dtype=np.float64)


def test_depth_to_meters_converts_millimeters_and_passthrough() -> None:
    raw = np.array([[1000, 2500]], dtype=np.uint16)
    meters = depth_to_meters(raw, "16UC1")
    assert meters[0, 0] == pytest.approx(1.0)
    assert meters[0, 1] == pytest.approx(2.5)
    raw32 = np.array([[1.5]], dtype=np.float32)
    assert depth_to_meters(raw32, "32FC1")[0, 0] == pytest.approx(1.5)
    with pytest.raises(ValueError):
        depth_to_meters(np.zeros((2, 2)), "bgr8")


def test_intrinsics_from_hfov_match_verified_calibration() -> None:
    intrinsics = CameraIntrinsics.from_hfov(640, 480, 60.0)
    # 640/(2*tan(30 deg)) matches the independently verified RGB value.
    assert intrinsics.fx == pytest.approx(554.26, abs=0.1)
    assert intrinsics.fy == pytest.approx(554.26, abs=0.1)
    assert intrinsics.cx == pytest.approx(320.0)
    assert intrinsics.cy == pytest.approx(240.0)


def test_backprojection_uses_pinhole_model() -> None:
    point = backproject_optical(430.0, 340.0, 2.0, INTRINSICS)
    assert point is not None
    x, y, z = point
    assert z == pytest.approx(2.0)
    assert x == pytest.approx((430.0 - 320.0) * 2.0 / 554.3)
    assert y == pytest.approx((340.0 - 240.0) * 2.0 / 554.3)


def test_backprojection_rejects_zero_and_invalid_depth() -> None:
    assert backproject_optical(320.0, 240.0, 0.0, INTRINSICS) is None
    assert backproject_optical(320.0, 240.0, float("nan"), INTRINSICS) is None
    assert backproject_optical(320.0, 240.0, float("inf"), INTRINSICS) is None
    assert backproject_optical(320.0, 240.0, -1.0, INTRINSICS) is None


def test_backprojection_rejects_unusable_intrinsics() -> None:
    zero_focal = CameraIntrinsics(fx=0.0, fy=554.3, cx=320.0, cy=240.0)
    assert backproject_optical(320.0, 240.0, 2.0, zero_focal) is None
    nan_focal = CameraIntrinsics(fx=float("nan"), fy=554.3, cx=320.0, cy=240.0)
    assert backproject_optical(320.0, 240.0, 2.0, nan_focal) is None


def test_patch_median_ignores_zero_nan_and_inf() -> None:
    depth = _flat_depth(20, 20, 2.0)
    depth[8:13, 8:13] = 0.0
    depth[9, 9] = float("nan")
    depth[10, 10] = float("inf")
    depth[11, 11] = 4.0
    median = patch_median_depth(depth, 10, 10, radius=4)
    assert median == pytest.approx(2.0)


def test_patch_median_returns_none_when_all_samples_invalid() -> None:
    depth = np.zeros((20, 20), dtype=np.float64)
    assert patch_median_depth(depth, 10, 10, radius=4) is None
    nan_depth = np.full((20, 20), float("nan"), dtype=np.float64)
    assert patch_median_depth(nan_depth, 10, 10, radius=4) is None


def test_patch_median_clips_at_image_edges() -> None:
    depth = _flat_depth(20, 20, 3.0)
    assert patch_median_depth(depth, 0, 0, radius=4) == pytest.approx(3.0)
    assert patch_median_depth(depth, 19, 19, radius=4) == pytest.approx(3.0)
    depth[0, 0] = 5.0
    assert patch_median_depth(depth, 0, 0, radius=4) == pytest.approx(3.0)


def test_transform_point_translation_and_rotation() -> None:
    translate = RigidTransform(
        translation=(1.0, 2.0, 3.0), rotation_xyzw=(0.0, 0.0, 0.0, 1.0)
    )
    assert transform_point((1.0, 1.0, 1.0), translate) == pytest.approx(
        (2.0, 3.0, 4.0)
    )
    yaw_90 = RigidTransform(
        translation=(0.0, 0.0, 0.0),
        rotation_xyzw=(0.0, 0.0, np.sin(np.pi / 4.0), np.cos(np.pi / 4.0)),
    )
    x, y, z = transform_point((1.0, 0.0, 0.0), yaw_90)
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(1.0, abs=1e-9)
    assert z == pytest.approx(0.0, abs=1e-9)


def test_estimate_position_full_pipeline_and_error_bound() -> None:
    # Ground truth: object surface point 2.0 m in front of the optical
    # origin, at pixel (430, 340). The pipeline must recover the 3D point
    # within a few millimetres (pure math, no sensor noise).
    truth = (2.0 * (430.0 - 320.0) / 554.3, 2.0 * (340.0 - 240.0) / 554.3, 2.0)
    estimated = estimate_position(
        (420.0, 330.0, 440.0, 350.0),
        _flat_depth(value=2.0),
        INTRINSICS,
        IDENTITY,
        "odom",
    )
    assert estimated is not None
    assert estimated.frame_id == "odom"
    assert estimated.depth_m == pytest.approx(2.0)
    error = np.linalg.norm(np.array(estimated.xyz) - np.array(truth))
    assert error < 0.01


def test_estimate_position_none_when_depth_unreliable() -> None:
    zeros = np.zeros((480, 640), dtype=np.float64)
    assert (
        estimate_position(
            (0, 0, 10, 10), zeros, INTRINSICS, IDENTITY, "odom"
        )
        is None
    )


def test_estimate_position_none_when_transform_missing() -> None:
    estimated = estimate_position(
        (0, 0, 10, 10),
        _flat_depth(value=2.0),
        INTRINSICS,
        None,
        "odom",
    )
    assert estimated is None


def test_estimate_position_rejects_non_finite_result() -> None:
    # A transform producing NaN output must not be marked position_valid.
    broken = RigidTransform(
        translation=(float("nan"), 0.0, 0.0),
        rotation_xyzw=(0.0, 0.0, 0.0, 1.0),
    )
    assert (
        estimate_position(
            (0, 0, 10, 10), _flat_depth(value=2.0), INTRINSICS, broken, "odom"
        )
        is None
    )


def test_position_config_defaults_are_sane() -> None:
    config = PositionConfig()
    assert config.use_depth is True
    assert config.depth_topic == "/camera/depth/image_rect_raw"
    assert config.camera_info_topic == "/camera/camera_info"
    assert "map" in config.position_frame_ids
    assert "odom" in config.position_frame_ids
    assert config.depth_max_stamp_delta_s > 0
    assert config.depth_patch_radius >= 1
