#!/usr/bin/env python3
"""End-to-end acceptance probe for the 2D LiDAR and the full TF chain.

Checks:
  - /scan arrives with frame_id=lidar_link, 360 samples, legal angle and
    range parameters, advancing timestamps and at least one finite range;
  - odom -> lidar_link TF chain is connected through base_footprint and
    base_link;
  - rotating in place changes the measured ranges (real scan, not static);
  - /odom keeps arriving and the cmd_vel watchdog node stays alive.
"""

import argparse
import math
import sys
import time
from collections import deque

import rclpy
import tf2_ros
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import LaserScan

EXPECTED_SAMPLES = 360


class LidarProbe(Node):
    def __init__(self, timeout_s: float) -> None:
        super().__init__("smartclean_lidar_probe")
        self.timeout_s = timeout_s
        self.scans = deque(maxlen=12)
        self.odoms = []
        scan_qos = QoSProfile(depth=10)
        scan_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        self.create_subscription(
            LaserScan, "/scan", self._on_scan, scan_qos
        )
        self.create_subscription(
            Odometry, "/odom", self._on_odom, 10
        )
        self._cmd_publisher = self.create_publisher(Twist, "/cmd_vel", 10)
        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)

    def _on_scan(self, message: LaserScan) -> None:
        self.scans.append(message)

    def _on_odom(self, message: Odometry) -> None:
        if len(self.odoms) < 4:
            self.odoms.append(message)

    def _collect(self) -> bool:
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            if len(self.scans) >= 4 and len(self.odoms) >= 1:
                return True
        return False

    def _check_scan_message(self) -> None:
        scan = self.scans[-1]
        if scan.header.frame_id != "lidar_link":
            raise AssertionError(
                "frame_id 应为 lidar_link，实际 {}".format(scan.header.frame_id)
            )
        if len(scan.ranges) != EXPECTED_SAMPLES:
            raise AssertionError(
                "ranges 应为 {} 个，实际 {}".format(
                    EXPECTED_SAMPLES, len(scan.ranges)
                )
            )
        if abs(scan.angle_min - (-math.pi)) > 0.02:
            raise AssertionError("angle_min 应为 -pi")
        if abs(scan.angle_max - math.pi) > 0.02:
            raise AssertionError("angle_max 应为 pi")
        expected_increment = 2.0 * math.pi / EXPECTED_SAMPLES
        if abs(scan.angle_increment - expected_increment) > 1e-4:
            raise AssertionError("angle_increment 与样本数不一致")
        if not (0.05 < scan.range_min <= scan.range_max <= 20.0):
            raise AssertionError("range 参数非法")
        finite = [value for value in scan.ranges if math.isfinite(value)]
        if not finite:
            raise AssertionError("没有有限测距值")
        stamps = [
            float(m.header.stamp.sec) + float(m.header.stamp.nanosec) * 1e-9
            for m in self.scans
        ]
        if len(set(stamps)) < 3:
            raise AssertionError("/scan 时间戳没有推进")

    def _check_tf_chain(self) -> None:
        try:
            transform = self._tf_buffer.lookup_transform(
                "odom",
                "lidar_link",
                Time(seconds=0, nanoseconds=0),
                Duration(seconds=1.0),
            )
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                "odom -> lidar_link TF 不连通：{}".format(exc)
            )
        if transform.header.frame_id != "odom":
            raise AssertionError("TF 查询父帧不是 odom")

    def _check_watchdog_and_odom(self) -> None:
        names = [
            name
            for name, _ in self.get_node_names_and_namespaces()
        ]
        for required in ("smartclean_cmd_vel_guard", "robot_state_publisher"):
            if required not in names:
                raise AssertionError("缺少节点：{}".format(required))
        if not self.odoms:
            raise AssertionError("未收到 /odom")
        if self.odoms[-1].header.frame_id != "odom":
            raise AssertionError("/odom frame_id 非法")

    def _check_ranges_change_when_rotating(self) -> None:
        before_scan = self.scans[-1]
        before = list(before_scan.ranges)
        twist = Twist()
        twist.angular.z = 0.5
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            self._cmd_publisher.publish(twist)
            rclpy.spin_once(self, timeout_sec=0.1)
        twist.angular.z = 0.0
        self._cmd_publisher.publish(twist)
        rclpy.spin_once(self, timeout_sec=0.5)
        after = None
        for scan in reversed(self.scans):
            if (
                scan.header.stamp.sec,
                scan.header.stamp.nanosec,
            ) != (
                before_scan.header.stamp.sec,
                before_scan.header.stamp.nanosec,
            ):
                after = list(scan.ranges)
                break
        if after is None:
            raise AssertionError("旋转后没有新的 /scan")
        changed = sum(
            1 for a, b in zip(before, after) if abs(a - b) > 0.02
        )
        if changed < 5:
            raise AssertionError("旋转后 /scan 测距没有变化（疑似静态数据）")

    def run(self) -> bool:
        if not self._collect():
            self.get_logger().error(
                "超时：scan {}/4，odom {}/1".format(
                    len(self.scans), len(self.odoms)
                )
            )
            return False
        self._check_scan_message()
        self._check_tf_chain()
        self._check_watchdog_and_odom()
        self._check_ranges_change_when_rotating()
        print("[lidar-probe] PASS")
        return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    rclpy.init()
    node = LidarProbe(args.timeout)
    try:
        ok = node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
