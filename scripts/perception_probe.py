#!/usr/bin/env python3
"""End-to-end acceptance probe for the image-based trash detector.

Two modes:
  --expect detections: trash world. Requires camera frames, detection
      messages, at least one detection of a class that actually exists in
      the scene ground truth (ground truth used for EVALUATION only),
      sane bboxes/confidences, and a debug image that carries real drawn
      annotations.
  --expect empty: empty world. Requires camera frames and detection
      messages that all report zero detections (no false positives).

The probe also re-checks that the detector source never reads the Gazebo
ground truth: detection logic must be pure image pixels.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image

from smartclean_interfaces.msg import TrashDetectionArray

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = PROJECT_ROOT / "configs" / "gazebo_scene.json"
CORE_PATH = (
    PROJECT_ROOT
    / "ros2_ws/src/smartclean_perception/smartclean_perception/detector_core.py"
)
NODE_PATH = (
    PROJECT_ROOT
    / "ros2_ws/src/smartclean_perception/smartclean_perception/trash_detector_node.py"
)
DRAW_COLORS_BGR = [(255, 128, 0), (0, 0, 255), (0, 200, 0),
                   (255, 255, 0), (0, 255, 255)]
TRASH_CLASSES = (
    "fallen_leaves",
    "plastic_bottle",
    "paper_scrap",
    "paper_cup",
    "aluminum_can",
)


class PerceptionProbe(Node):
    def __init__(self, expect_empty: bool, timeout_s: float) -> None:
        super().__init__("smartclean_perception_probe")
        self.expect_empty = expect_empty
        self.timeout_s = timeout_s
        self.images = []
        self.detection_arrays = []
        self.debug_images = []
        image_qos = QoSProfile(depth=10)
        image_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        self.create_subscription(
            Image, "/camera/image_raw", self._on_image, image_qos
        )
        self.create_subscription(
            TrashDetectionArray,
            "/smartclean/detections",
            self._on_detections,
            10,
        )
        self.create_subscription(
            Image,
            "/smartclean/debug/detection_image",
            self._on_debug,
            image_qos,
        )

    def _on_image(self, message: Image) -> None:
        if len(self.images) < 16:
            self.images.append(message)

    def _on_detections(self, message: TrashDetectionArray) -> None:
        if len(self.detection_arrays) < 24:
            self.detection_arrays.append(message)

    def _on_debug(self, message: Image) -> None:
        if len(self.debug_images) < 16:
            self.debug_images.append(message)

    def _collect(self, minimum_frames: int) -> bool:
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            if len(self.images) >= minimum_frames:
                return True
        return False

    @staticmethod
    def _assert_source_is_pixel_pure() -> None:
        for path in (CORE_PATH, NODE_PATH):
            text = path.read_text(encoding="utf-8")
            for forbidden in ("gazebo_scene", "configs/", "model://",
                              "subprocess", "ign ", "ignition"):
                if forbidden in text:
                    raise AssertionError(
                        "{} 包含禁止的真值读取标记：{}".format(path, forbidden)
                    )

    def _check_debug_annotations(self) -> None:
        if not self.debug_images:
            raise AssertionError("未收到 /smartclean/debug/detection_image")
        raw = np.frombuffer(self.images[-1].data, dtype=np.uint8)
        debug = np.frombuffer(self.debug_images[-1].data, dtype=np.uint8)
        if raw.shape != debug.shape:
            raise AssertionError("调试图尺寸与原始图不一致")
        if np.array_equal(raw, debug):
            raise AssertionError("调试图与原始图完全相同：未发生标注")
        debug_bgr = debug.reshape(self.debug_images[-1].height,
                                  self.debug_images[-1].width, 3)
        drawn = 0
        for color in DRAW_COLORS_BGR:
            match = np.all(
                np.abs(debug_bgr.astype(np.int16) - np.array(color)) < 25,
                axis=2,
            )
            drawn += int(np.count_nonzero(match))
        if drawn < 60:
            raise AssertionError("调试图未发现标注框颜色（draw={}）".format(drawn))

    def run_detections(self) -> int:
        if not self._collect(3):
            print("[perception-probe] FAIL 未收到足够相机图像帧")
            return 1
        self._assert_source_is_pixel_pure()
        scene = json.loads(SCENE_PATH.read_text(encoding="utf-8"))
        scene_classes = {item["class_name"] for item in scene["trash"]}

        deadline = time.monotonic() + self.timeout_s
        valid_detections = []
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            if self.detection_arrays and self.debug_images:
                break
        if not self.detection_arrays:
            print("[perception-probe] FAIL 未收到 /smartclean/detections")
            return 1
        for array in self.detection_arrays:
            for detection in array.detections:
                if detection.class_name not in TRASH_CLASSES:
                    raise AssertionError(
                        "非法类别：{}".format(detection.class_name)
                    )
                if not 0.0 <= detection.confidence <= 1.0:
                    raise AssertionError("confidence 越界")
                x_min, y_min, x_max, y_max = detection.bbox_xyxy
                if not (0 <= x_min < x_max <= 640):
                    raise AssertionError("bbox x 越界：{}".format(
                        detection.bbox_xyxy))
                if not (0 <= y_min < y_max <= 480):
                    raise AssertionError("bbox y 越界：{}".format(
                        detection.bbox_xyxy))
                valid_detections.append(detection)
        detected_classes = {d.class_name for d in valid_detections}
        if not (detected_classes & scene_classes):
            print(
                "[perception-probe] FAIL 检测类别 {} 与场景真值 {} 无交集".format(
                    sorted(detected_classes), sorted(scene_classes)
                )
            )
            return 1
        self._check_debug_annotations()
        print(
            "[perception-probe] OK 相机图像 {} 帧，检测消息 {} 条".format(
                len(self.images), len(self.detection_arrays)
            )
        )
        print(
            "[perception-probe] OK 识别到真实存在的垃圾类别：{}".format(
                sorted(detected_classes & scene_classes)
            )
        )
        print(
            "[perception-probe] OK 检测数 {}，全部 bbox/类别/置信度合法".format(
                len(valid_detections)
            )
        )
        print("[perception-probe] OK 调试图包含真实标注")
        print("[perception-probe] PASS")
        return 0

    def run_empty(self) -> int:
        if not self._collect(3):
            print("[perception-probe] FAIL 空场景未收到足够相机图像帧")
            return 1
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            if len(self.detection_arrays) >= 5:
                break
        if len(self.detection_arrays) < 5:
            print("[perception-probe] FAIL 空场景检测消息不足")
            return 1
        false_detections = []
        for array in self.detection_arrays:
            false_detections.extend(array.detections)
        if false_detections:
            print(
                "[perception-probe] FAIL 空场景出现虚假检测：{}".format(
                    [(d.class_name, d.bbox_xyxy) for d in false_detections]
                )
            )
            return 1
        print(
            "[perception-probe] OK 空场景 {} 条检测消息全部为空（无虚假检测）".format(
                len(self.detection_arrays)
            )
        )
        print("[perception-probe] PASS")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expect",
        choices=("detections", "empty"),
        default="detections",
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()
    rclpy.init()
    try:
        probe = PerceptionProbe(args.expect == "empty", args.timeout)
        if args.expect == "empty":
            return probe.run_empty()
        return probe.run_detections()
    finally:
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
