"""ROS 2 fixed-rate fail-safe relay for velocity commands."""

import sys
from math import isfinite
from typing import Optional

import rclpy
from geometry_msgs.msg import Twist
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from smartclean_ros.cmd_vel_guard_core import CmdVelGuard
from smartclean_ros.cmd_vel_guard_core import VelocityCommand, VelocityGuardError


INPUT_TOPIC = "/smartclean/cmd_vel"
OUTPUT_TOPIC = "/smartclean/safe_cmd_vel"


class CmdVelGuardNode(Node):
    """Publish only finite and fresh velocity commands at a stable rate."""

    def __init__(self) -> None:
        super().__init__("cmd_vel_guard")
        self.declare_parameter("input_topic", INPUT_TOPIC)
        self.declare_parameter("output_topic", OUTPUT_TOPIC)
        self.declare_parameter("command_timeout_s", 0.5)
        self.declare_parameter("publish_rate_hz", 20.0)

        input_topic = str(self.get_parameter("input_topic").value).strip()
        output_topic = str(self.get_parameter("output_topic").value).strip()
        command_timeout_s = float(self.get_parameter("command_timeout_s").value)
        publish_rate_hz = float(self.get_parameter("publish_rate_hz").value)
        if not input_topic:
            raise VelocityGuardError("input_topic 不能为空")
        if not output_topic:
            raise VelocityGuardError("output_topic 不能为空")
        if not isfinite(publish_rate_hz) or publish_rate_hz <= 0.0:
            raise VelocityGuardError("publish_rate_hz 必须是大于 0 的有限数值")

        self._guard = CmdVelGuard(command_timeout_s=command_timeout_s)
        # Safety timing must not stop when simulated ROS time is paused or reset.
        self._steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self._publisher = self.create_publisher(Twist, output_topic, 10)
        self._subscription = self.create_subscription(
            Twist,
            input_topic,
            self._on_command,
            10,
        )
        self._timer = self.create_timer(
            1.0 / publish_rate_hz,
            self._on_timer,
            clock=self._steady_clock,
        )

        self.get_logger().info(
            "速度安全看门狗已启动：{} -> {}，timeout={:.3f}s，rate={:.3f}Hz".format(
                self.resolve_topic_name(input_topic),
                self.resolve_topic_name(output_topic),
                command_timeout_s,
                publish_rate_hz,
            )
        )

    def _now_s(self) -> float:
        return self._steady_clock.now().nanoseconds / 1_000_000_000.0

    def _on_command(self, message: Twist) -> None:
        command = VelocityCommand(
            linear_x=message.linear.x,
            linear_y=message.linear.y,
            linear_z=message.linear.z,
            angular_x=message.angular.x,
            angular_y=message.angular.y,
            angular_z=message.angular.z,
        )
        if not self._guard.accept(command, self._now_s()):
            self.get_logger().warning("收到包含 NaN/Inf 的速度命令，已切换为零速度")

    def _on_timer(self) -> None:
        command = self._guard.safe_command(self._now_s())
        message = Twist()
        message.linear.x = command.linear_x
        message.linear.y = command.linear_y
        message.linear.z = command.linear_z
        message.angular.x = command.angular_x
        message.angular.y = command.angular_y
        message.angular.z = command.angular_z
        self._publisher.publish(message)


def main(args: Optional[list] = None) -> int:
    """Run the velocity guard until ROS shutdown and return a process exit code."""

    rclpy.init(args=args)
    node = None  # type: Optional[CmdVelGuardNode]
    try:
        node = CmdVelGuardNode()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except (TypeError, ValueError, VelocityGuardError) as exc:
        print("cmd_vel_guard 启动失败：{}".format(exc), file=sys.stderr)
        return 2
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
