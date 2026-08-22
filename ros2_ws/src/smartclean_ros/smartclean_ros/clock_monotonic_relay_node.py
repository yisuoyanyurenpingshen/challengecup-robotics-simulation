"""Republish /clock_raw as a strictly monotonic /clock.

Gazebo Fortress delivers ignition.msgs.Clock to the parameter_bridge on a
pool of transport worker threads, so a busy bridge can forward the high-rate
clock stream out of order. Every use_sim_time consumer (tf2, AMCL, Nav2,
RViz) assumes node time never runs backwards, and tf2_ros reports
"Detected jump back in time. Clearing TF buffer" as soon as it does, which
breaks map <-> base_link lookups and localization.

This node is a deterministic, bridge-version-independent fix: it filters the
incoming stream so the published clock stamps only ever increase. The
parameter_bridge then publishes /clock_raw and this relay owns /clock as the
single clock source of the launch.
"""

from typing import Optional, Tuple

import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import QoSProfile
from rosgraph_msgs.msg import Clock


def stamp_newer(
    candidate: Tuple[int, int], current: Tuple[int, int]
) -> bool:
    """Return True when candidate (sec, nanosec) is strictly newer."""
    return candidate[0] > current[0] or (
        candidate[0] == current[0] and candidate[1] > current[1]
    )


class ClockMonotonicFilter:
    """Drop non-monotonic clock stamps and count the stream statistics."""

    def __init__(self) -> None:
        self.received = 0
        self.published = 0
        self.dropped = 0
        self.last: Optional[Tuple[int, int]] = None

    def update(self, stamp: Tuple[int, int]) -> bool:
        """Record one stamp; return True when it should be published."""
        self.received += 1
        if self.last is None or stamp_newer(stamp, self.last):
            self.last = stamp
            self.published += 1
            return True
        self.dropped += 1
        return False


class ClockMonotonicRelay(Node):
    """Strictly monotonic /clock relay backed by ClockMonotonicFilter."""

    def __init__(self) -> None:
        super().__init__("smartclean_clock_relay")
        self.declare_parameter("input_topic", "/clock_raw")
        self.declare_parameter("output_topic", "/clock")
        input_topic = self.get_parameter("input_topic").value
        output_topic = self.get_parameter("output_topic").value

        self._filter = ClockMonotonicFilter()
        self.create_subscription(
            Clock, input_topic, self._on_clock, QoSProfile(depth=10)
        )
        self._publisher = self.create_publisher(Clock, output_topic, 1)
        self._last_stats_log = self.get_clock().now()
        self.get_logger().info(
            "仿真时钟单调中继：{} -> {}（丢弃倒退时间戳，保证单调递增）".format(
                input_topic, output_topic
            )
        )

    def _on_clock(self, message: Clock) -> None:
        stamp = (message.clock.sec, message.clock.nanosec)
        if self._filter.update(stamp):
            self._publisher.publish(message)
        now = self.get_clock().now()
        if now - self._last_stats_log > Duration(seconds=30.0):
            self.get_logger().info(
                "时钟中继统计：收到={} 发布={} 丢弃={} 当前={}.{:09d}".format(
                    self._filter.received,
                    self._filter.published,
                    self._filter.dropped,
                    stamp[0],
                    stamp[1],
                )
            )
            self._last_stats_log = now


def main() -> None:
    rclpy.init()
    node = ClockMonotonicRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
