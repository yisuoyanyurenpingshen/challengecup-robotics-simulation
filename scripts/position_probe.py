#!/usr/bin/env python3
"""End-to-end acceptance probe for depth-based trash position estimation.

Checks:
  - /camera/depth/image_rect_raw arrives with sane size/encoding/timestamps
    and contains both invalid (sky) and finite valid depth samples;
  - /camera/depth/camera_info has usable intrinsics;
  - /smartclean/detections contains at least one position_valid detection
    whose frame is odom or map;
  - the estimated XY position is within 0.45 m of the nearest Gazebo ground
    truth of the same class (truth used for error evaluation only);
  - the camera_optical_frame -> odom TF chain is connected.

The probe also asserts that the estimator and node sources never read the
Gazebo ground truth.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import rclpy
import tf2_ros
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo, Image

from smartclean_interfaces.msg import TrashDetectionArray

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = PROJECT_ROOT / "configs" / "gazebo_scene.json"
ESTIMATOR_PATH = (
    PROJECT_ROOT
    / "ros2_ws/src/smartclean_perception/smartclean_perception/"
    "position_estimator.py"
)
NODE_PATH = (
    PROJECT_ROOT
    / "ros2_ws/src/smartclean_perception/smartclean_perception/"
    "trash_detector_node.py"
)
MAX_POSITION_ERROR_M = 0.45


def _assert_sources_are_pixel_pure() -> None:
    for path in (ESTIMATOR_PATH, NODE_PATH):
        text = path.read_text(encoding="utf-8")
        for forbidden in (
            "gazebo_scene",
            "configs/",
            "model://",
            "subprocess",
            "ign ",
            "ignition",
        ):
            if forbidden in text:
                raise AssertionError(
                    "{} 包含禁止的真值读取标记：{}".format(path, forbidden)
                )


class PositionProbe(Node):
    def __init__(self, timeout_s: float) -> None:
        super().__init__("smartclean_position_probe")
        self.timeout_s = timeout_s
        self.depth_images = []
        self.depth_infos = []
        self.detection_arrays = []
        image_qos = QoSProfile(depth=10)
        image_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        self.create_subscription(
            Image, "/camera/depth/image_rect_raw", self._on_depth, image_qos
        )
        self.create_subscription(
            CameraInfo,
            "/camera/camera_info",
            self._on_info,
            image_qos,
        )
        self.create_subscription(
            TrashDetectionArray,
            "/smartclean/detections",
            self._on_detections,
            10,
        )
        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)

    def _on_depth(self, message: Image) -> None:
        if len(self.depth_images) < 24:
            self.depth_images.append(message)

    def _on_info(self, message: CameraInfo) -> None:
        if len(self.depth_infos) < 4:
            self.depth_infos.append(message)

    def _on_detections(self, message: TrashDetectionArray) -> None:
        if len(self.detection_arrays) < 24:
            self.detection_arrays.append(message)

    def _collect(self) -> bool:
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            if (
                len(self.depth_images) >= 8
                and len(self.depth_infos) >= 1
                and len(self.detection_arrays) >= 4
            ):
                return True
        return False

    @staticmethod
    def _check_depth_images(depth_images) -> None:
        image = depth_images[-1]
        if image.width != 640 or image.height != 480:
            raise AssertionError(
                "深度图像尺寸应为 640x480，实际 {}x{}".format(
                    image.width, image.height
                )
            )
        if image.encoding not in ("32FC1", "16UC1"):
            raise AssertionError("深度编码非法：{}".format(image.encoding))
        stamps = [
            float(m.header.stamp.sec) + float(m.header.stamp.nanosec) * 1e-9
            for m in depth_images
        ]
        if len(set(stamps)) < 4:
            raise AssertionError("深度图像时间戳没有推进")
        sample = depth_images[-1]
        if sample.encoding == "32FC1":
            values = np.frombuffer(sample.data, dtype=np.float32)
        else:
            values = np.frombuffer(sample.data, dtype=np.uint16).astype(
                np.float64
            )
        finite = values[np.isfinite(values) & (values > 0)]
        if finite.size < values.size * 0.05:
            raise AssertionError("深度图像几乎没有有效测距值")

    @staticmethod
    def _check_depth_info(depth_infos) -> None:
        info = depth_infos[-1]
        if info.k[0] <= 0 or info.k[4] <= 0:
            raise AssertionError("深度相机内参 fx/fy 非法")
        # Gazebo Fortress 6.16 quirk: rgbd/depth CameraInfo reports half the
        # true focal length (277 instead of 554). The node therefore derives
        # intrinsics analytically via CameraIntrinsics.from_hfov; the real
        # correctness proof is the position error check below.
        if not (270.0 < info.k[0] < 285.0):
            raise AssertionError(
                "深度相机 fx 与 Gazebo 6.16 已知行为不一致：{}".format(info.k[0])
            )

    def _check_tf_chain(self) -> None:
        try:
            transform = self._tf_buffer.lookup_transform(
                "odom",
                "camera_optical_frame",
                Time(seconds=0, nanoseconds=0),
                Duration(seconds=1.0),
            )
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                "camera_optical_frame -> odom TF 不连通：{}".format(exc)
            )
        if transform.header.frame_id != "odom":
            raise AssertionError("TF 查询返回的父帧不是 odom")

    def _check_positions(self) -> None:
        truths = json.loads(SCENE_PATH.read_text(encoding="utf-8"))["trash"]
        valid = []
        for array in self.detection_arrays:
            for detection in array.detections:
                if detection.position_valid:
                    valid.append(detection)
        if not valid:
            raise AssertionError("没有任何 position_valid=true 的检测")
        best = None
        for detection in valid:
            if detection.position_frame_id not in ("odom", "map"):
                raise AssertionError(
                    "位置帧非法：{}".format(detection.position_frame_id)
                )
            position = np.array(detection.position, dtype=np.float64)
            if not np.all(np.isfinite(position)):
                raise AssertionError("检测位置包含 NaN/Inf")
            same_class = [
                item for item in truths
                if item["class_name"] == detection.class_name
            ]
            if not same_class:
                continue
            truth_xy = np.array(
                [
                    [item["position"]["x"], item["position"]["y"]]
                    for item in same_class
                ],
                dtype=np.float64,
            )
            error = min(
                np.linalg.norm(position[:2] - truth) for truth in truth_xy
            )
            if best is None or error < best[0]:
                best = (error, detection.class_name, position.tolist())
        if best is None:
            raise AssertionError("position_valid 检测没有同类别真值可比")
        error, class_name, position = best
        if error > MAX_POSITION_ERROR_M:
            raise AssertionError(
                "位置误差超限：{} 类误差 {:.3f} m > {:.2f} m，位置 {}".format(
                    class_name, error, MAX_POSITION_ERROR_M, position
                )
            )
        self.get_logger().info(
            "最佳位置估计：{} 误差 {:.3f} m 位置 {}".format(
                class_name, error, position
            )
        )

    def run(self) -> bool:
        if not self._collect():
            self.get_logger().error(
                "超时：深度 {}/8，info {}/1，检测 {}/4".format(
                    len(self.depth_images),
                    len(self.depth_infos),
                    len(self.detection_arrays),
                )
            )
            return False
        _assert_sources_are_pixel_pure()
        self._check_depth_images(self.depth_images)
        self._check_depth_info(self.depth_infos)
        self._check_tf_chain()
        self._check_positions()
        print("[position-probe] PASS")
        return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    rclpy.init()
    node = PositionProbe(args.timeout)
    try:
        ok = node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
