#!/usr/bin/env python3
"""Verify the Gazebo RGB camera end to end through the ROS bridge.

Checks: image arrival, geometry, encoding, advancing timestamps, non-black
pixels, consecutive valid frames, CameraInfo consistency, and the camera TF
chain from base_footprint to camera_optical_frame.
"""

import sys
import time
from typing import List, Optional

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from geometry_msgs.msg import Twist
from sensor_msgs.msg import CameraInfo, Image
from tf2_msgs.msg import TFMessage

EXPECTED_WIDTH = 640
EXPECTED_HEIGHT = 480
EXPECTED_ENCODING = "rgb8"
MIN_FRAMES = 3
MIN_MEAN = 5.0
TIMEOUT_S = 45.0


class CameraProbe(Node):
    """Collect camera evidence and run the acceptance checks."""

    def __init__(self) -> None:
        super().__init__("smartclean_camera_probe")
        self.images: List[Image] = []
        self.infos: List[CameraInfo] = []
        self.tf_ok = False
        self.static_frames = {}  # /tf_static: child -> parent
        self.dynamic_frames = {}  # /tf: child -> parent
        self.command_publisher = self.create_publisher(Twist, "/cmd_vel", 10)

        sensor_qos = QoSProfile(depth=50)
        sensor_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        sensor_qos.durability = DurabilityPolicy.VOLATILE
        self.create_subscription(
            Image, "/camera/image_raw", self._on_image, sensor_qos
        )
        self.create_subscription(
            CameraInfo, "/camera/camera_info", self._on_info, sensor_qos
        )

        self.create_subscription(TFMessage, "/tf", self._on_tf, 20)
        static_qos = QoSProfile(depth=20)
        static_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.create_subscription(
            TFMessage, "/tf_static", self._on_tf_static, static_qos
        )

    def _on_image(self, message: Image) -> None:
        if len(self.images) < 32:
            self.images.append(message)

    def _on_info(self, message: CameraInfo) -> None:
        if len(self.infos) < 8:
            self.infos.append(message)

    def _on_tf(self, message: TFMessage) -> None:
        for transform in message.transforms:
            self.dynamic_frames[transform.child_frame_id] = (
                transform.header.frame_id
            )

    def _on_tf_static(self, message: TFMessage) -> None:
        for transform in message.transforms:
            self.static_frames[transform.child_frame_id] = (
                transform.header.frame_id
            )

    def _spin_once(self, timeout_s: float) -> bool:
        """Return False when the deadline has passed with too few frames."""

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            if len(self.images) >= MIN_FRAMES and self.infos:
                return True
        return False

    def _publish_turn(self, duration_s: float, angular: float) -> None:
        """让清扫车原地旋转，证明相机画面跟随世界真实变化。

        同时经过 /cmd_vel 看门狗、桥接与 Gazebo DiffDrive，因此旋转期间
        以 5Hz 持续发指令，避免看门狗超时停车。
        """

        deadline = time.monotonic() + duration_s
        command = Twist()
        command.angular.z = angular
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            self.command_publisher.publish(command)
            time.sleep(0.1)

    def _image_mean(self, image: Image) -> float:
        data = np.frombuffer(image.data, dtype=np.uint8)
        return float(data.mean())

    def _stamp_pair(self, header) -> float:
        return header.stamp.sec * 1e9 + header.stamp.nanosec

    def _check_tf(self, timeout_s: float = 15.0) -> bool:
        # 相机链全部位于 /tf_static（RSP 发布），沿父子链从
        # camera_optical_frame 走到 base_footprint；同时确认 Gazebo 动态
        # /tf 仍携带 odom -> base_link（差速闭环不回归）。
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            chain = ["camera_optical_frame"]
            for _ in range(8):
                parent = self.static_frames.get(chain[-1])
                if parent is None:
                    break
                if parent in chain:
                    break
                chain.append(parent)
            if chain[-1] == "base_footprint":
                self.tf_ok = True
                if self.dynamic_frames.get("base_link") == "odom":
                    return True
        print(
            "[camera-probe] 已见静态 TF 链：{}；动态 TF 链：{}".format(
                sorted(self.static_frames.items()),
                sorted(self.dynamic_frames.items()),
            )
        )
        return False

    def run_checks(self) -> int:
        if not self._spin_once(TIMEOUT_S):
            print("[camera-probe] FAIL 未收到足够相机图像帧")
            return 1
        if not self._check_tf():
            print("[camera-probe] FAIL base_footprint→camera_optical_frame TF 未连通")
            return 1
        self.tf_ok = True

        still_before = bytes(self.images[0].data)
        self._publish_turn(duration_s=4.0, angular=0.6)
        rclpy.spin_once(self, timeout_sec=0.5)
        still_after = bytes(self.images[-1].data)
        if still_after == still_before:
            print("[camera-probe] FAIL 原地旋转后画面未变化（相机疑似未渲染世界）")
            return 1
        print("[camera-probe] OK 原地旋转后画面发生变化（相机真实渲染世界）")

        failures = []
        first = self.images[0]
        mean_values = []
        for image in self.images:
            if image.width != EXPECTED_WIDTH or image.height != EXPECTED_HEIGHT:
                failures.append(
                    "图像尺寸 {}x{} != {}x{}".format(
                        image.width, image.height, EXPECTED_WIDTH, EXPECTED_HEIGHT
                    )
                )
                break
            if image.encoding != EXPECTED_ENCODING:
                failures.append("编码 {} != {}".format(image.encoding, EXPECTED_ENCODING))
                break
            mean_values.append(self._image_mean(image))
        mean_value = float(np.mean(mean_values)) if mean_values else 0.0
        if mean_value < MIN_MEAN:
            failures.append(
                "图像疑似全黑（平均像素 {:.2f}/255 < {:.0f}）".format(mean_value, MIN_MEAN)
            )

        stamps = [self._stamp_pair(image.header) for image in self.images]
        if not all(b > a for a, b in zip(stamps, stamps[1:])):
            failures.append("图像时间戳未持续推进")

        payloads = [bytes(image.data) for image in self.images]
        if len(set(payloads)) < 2:
            failures.append("连续帧内容完全相同")

        info = self.infos[0]
        if info.width != EXPECTED_WIDTH or info.height != EXPECTED_HEIGHT:
            failures.append(
                "CameraInfo 尺寸 {}x{} != {}x{}".format(
                    info.width, info.height, EXPECTED_WIDTH, EXPECTED_HEIGHT
                )
            )
        if len(info.d) < 5:
            failures.append("CameraInfo.d 长度 < 5")
        if len(info.k) < 9:
            failures.append("CameraInfo.K 不完整")
        else:
            fx, fy = info.k[0], info.k[4]
            if not (0.0 < fx < 2000.0 and 0.0 < fy < 2000.0):
                failures.append("CameraInfo 焦距非法 fx={} fy={}".format(fx, fy))
        if not info.p[0]:
            failures.append("CameraInfo.P[0] 为 0")

        if failures:
            for failure in failures:
                print("[camera-probe] FAIL {}".format(failure))
            return 1

        print(
            "[camera-probe] OK 图像 {}x{} {} 平均像素 {:.2f}/255".format(
                first.width, first.height, first.encoding, mean_value
            )
        )
        print(
            "[camera-probe] OK 收到 {} 帧，时间戳推进，连续帧有效".format(len(self.images))
        )
        print(
            "[camera-probe] OK CameraInfo {}x{} fx={:.1f}".format(
                info.width, info.height, info.k[0]
            )
        )
        print("[camera-probe] OK TF base_footprint→camera_optical_frame 连通")
        print("[camera-probe] PASS")
        return 0


def main() -> int:
    rclpy.init()
    try:
        return CameraProbe().run_checks()
    finally:
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
