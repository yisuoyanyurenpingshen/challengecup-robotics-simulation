#!/usr/bin/env python3
"""Wait for a positive Gazebo simulation clock bridged into ROS 2."""

import sys
import time

import rclpy
from rclpy.node import Node
from rosgraph_msgs.msg import Clock


class ClockProbe(Node):
    """Collect two samples proving that simulation time advances."""

    def __init__(self) -> None:
        super().__init__("smartclean_gazebo_clock_probe")
        self.first_clock_ns = None
        self.clock = None
        self.create_subscription(Clock, "/clock", self._on_clock, 10)

    def _on_clock(self, message: Clock) -> None:
        current_ns = message.clock.sec * 1_000_000_000 + message.clock.nanosec
        if current_ns <= 0:
            return
        if self.first_clock_ns is None:
            self.first_clock_ns = current_ns
        elif current_ns > self.first_clock_ns:
            self.clock = message.clock


def main() -> int:
    rclpy.init()
    node = ClockProbe()
    deadline = time.monotonic() + 30.0
    try:
        while time.monotonic() < deadline and node.clock is None:
            rclpy.spin_once(node, timeout_sec=0.2)
        if node.clock is None:
            print(
                "Gazebo 验证失败：30 秒内未收到两个递增的 /clock 样本",
                file=sys.stderr,
            )
            return 1
        print(
            "Gazebo Fortress 验证通过：/clock 从 {} ns 推进到 {} ns".format(
                node.first_clock_ns,
                node.clock.sec * 1_000_000_000 + node.clock.nanosec,
            )
        )
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
