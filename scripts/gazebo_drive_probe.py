#!/usr/bin/env python3
"""Verify command, odometry, TF, turning and watchdog stop in Gazebo."""

import math
import sys
import time
from typing import Callable, Optional, Tuple

import rclpy
from geometry_msgs.msg import Quaternion, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock
from tf2_msgs.msg import TFMessage


def _yaw(quaternion: Quaternion) -> float:
    """Return planar yaw from a normalized ROS quaternion."""

    sin_yaw = 2.0 * (
        quaternion.w * quaternion.z + quaternion.x * quaternion.y
    )
    cos_yaw = 1.0 - 2.0 * (
        quaternion.y * quaternion.y + quaternion.z * quaternion.z
    )
    return math.atan2(sin_yaw, cos_yaw)


def _angle_delta(start: float, end: float) -> float:
    """Return the signed shortest angular displacement."""

    return math.atan2(math.sin(end - start), math.cos(end - start))


class DriveProbe(Node):
    """Publish user velocity commands and collect closed-loop evidence."""

    def __init__(self) -> None:
        super().__init__("smartclean_gazebo_drive_probe")
        self.latest_odom: Optional[Odometry] = None
        self.clock_samples = []
        self.has_odom_tf = False

        self.command_publisher = self.create_publisher(Twist, "/cmd_vel", 10)
        self.create_subscription(
            Odometry, "/odom", self._on_odom, 20
        )

        sensor_qos = QoSProfile(depth=50)
        sensor_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        sensor_qos.durability = DurabilityPolicy.VOLATILE
        self.create_subscription(Clock, "/clock", self._on_clock, sensor_qos)
        self.create_subscription(TFMessage, "/tf", self._on_tf, sensor_qos)

    def _on_odom(self, message: Odometry) -> None:
        self.latest_odom = message

    def _on_clock(self, message: Clock) -> None:
        nanoseconds = (
            message.clock.sec * 1_000_000_000 + message.clock.nanosec
        )
        if not self.clock_samples or nanoseconds != self.clock_samples[-1]:
            self.clock_samples.append(nanoseconds)

    def _on_tf(self, message: TFMessage) -> None:
        for transform in message.transforms:
            if (
                transform.header.frame_id == "odom"
                and transform.child_frame_id == "base_footprint"
            ):
                self.has_odom_tf = True

    def wait_for(self, predicate: Callable[[], bool], timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if predicate():
                return True
        return False

    def publish_for(self, command: Twist, duration_s: float) -> None:
        deadline = time.monotonic() + duration_s
        next_publish = 0.0
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_publish:
                self.command_publisher.publish(command)
                next_publish = now + 0.05
            rclpy.spin_once(self, timeout_sec=0.02)

    def settle_without_commands(self, duration_s: float) -> None:
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)

    def publish_emergency_zero(self) -> None:
        zero = Twist()
        for _ in range(8):
            self.command_publisher.publish(zero)
            rclpy.spin_once(self, timeout_sec=0.03)


def _pose(message: Odometry) -> Tuple[float, float, float]:
    position = message.pose.pose.position
    return position.x, position.y, _yaw(message.pose.pose.orientation)


def main() -> int:
    rclpy.init()
    node = DriveProbe()
    try:
        assert node.wait_for(
            lambda: node.command_publisher.get_subscription_count() > 0,
            15.0,
        ), "15 秒内 /cmd_vel 未连接安全看门狗"
        assert node.wait_for(
            lambda: node.latest_odom is not None, 20.0
        ), "20 秒内未收到 /odom"
        assert node.wait_for(
            lambda: len(node.clock_samples) >= 2, 10.0
        ), "未收到两个递增的 /clock 样本"
        assert node.wait_for(
            lambda: node.has_odom_tf, 10.0
        ), "未收到 odom -> base_footprint TF"

        initial = node.latest_odom
        assert initial is not None
        assert initial.header.frame_id == "odom", initial.header.frame_id
        assert (
            initial.child_frame_id == "base_footprint"
        ), initial.child_frame_id
        start_x, start_y, _ = _pose(initial)

        forward_command = Twist()
        forward_command.linear.x = 0.4
        node.publish_for(forward_command, 1.8)
        assert node.latest_odom is not None
        forward_x, forward_y, forward_yaw = _pose(node.latest_odom)
        forward_distance = math.hypot(
            forward_x - start_x, forward_y - start_y
        )
        assert forward_distance >= 0.30, (
            "前进位移不足：{:.3f} m".format(forward_distance)
        )

        turn_command = Twist()
        turn_command.angular.z = 0.8
        node.publish_for(turn_command, 1.5)
        assert node.latest_odom is not None
        _, _, turn_yaw = _pose(node.latest_odom)
        yaw_change = abs(_angle_delta(forward_yaw, turn_yaw))
        assert yaw_change >= 0.55, (
            "转向角不足：{:.3f} rad".format(yaw_change)
        )

        # Deliberately stop publishing. The guard, rather than this probe,
        # must generate zero velocity after command_timeout_s.
        assert node.wait_for(
            lambda: node.latest_odom is not None
            and abs(node.latest_odom.twist.twist.linear.x) <= 0.05
            and abs(node.latest_odom.twist.twist.angular.z) <= 0.05,
            3.0,
        ), "停止发送命令后 3 秒内速度看门狗未让车辆停止"

        stopped = node.latest_odom
        assert stopped is not None
        stop_x, stop_y, stop_yaw = _pose(stopped)
        node.settle_without_commands(0.6)
        assert node.latest_odom is not None
        final_x, final_y, final_yaw = _pose(node.latest_odom)
        stop_drift = math.hypot(final_x - stop_x, final_y - stop_y)
        stop_yaw_drift = abs(_angle_delta(stop_yaw, final_yaw))
        assert stop_drift <= 0.06, (
            "停车后平移漂移过大：{:.3f} m".format(stop_drift)
        )
        assert stop_yaw_drift <= 0.08, (
            "停车后角度漂移过大：{:.3f} rad".format(stop_yaw_drift)
        )

        assert node.clock_samples[-1] > node.clock_samples[0]
        print(
            "Gazebo 差速闭环验证通过：forward={:.3f} m, "
            "turn={:.3f} rad, stop_drift={:.3f} m, TF=odom->base_link, "
            "watchdog=passed".format(
                forward_distance, yaw_change, stop_drift
            )
        )
        return 0
    except (AssertionError, AttributeError, TypeError, ValueError) as exc:
        print("Gazebo 差速闭环验证失败：{}".format(exc), file=sys.stderr)
        return 1
    finally:
        node.publish_emergency_zero()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
