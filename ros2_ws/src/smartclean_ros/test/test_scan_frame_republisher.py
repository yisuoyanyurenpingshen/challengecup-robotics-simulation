"""Static and unit tests for the LaserScan frame-id relay."""

from pathlib import Path

import pytest

from smartclean_ros.scan_frame_republisher_node import ScanFrameRepublisher
from smartclean_ros.scan_frame_republisher_node import remap_frame_id

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_entry_point_exists() -> None:
    setup = (PACKAGE_ROOT / "setup.py").read_text(encoding="utf-8")
    assert '"scan_frame_republisher = "' in setup
    assert '"smartclean_ros.scan_frame_republisher_node:main"' in setup


def test_remap_frame_id_only_changes_header_frame() -> None:
    import numpy as np
    from sensor_msgs.msg import LaserScan

    message = LaserScan()
    message.header.frame_id = "smartclean_robot/lidar_link/lidar"
    message.header.stamp.sec = 7
    message.header.stamp.nanosec = 42
    message.angle_min = -3.14159
    message.angle_max = 3.14159
    message.ranges = [1.0, 2.0, float("inf")]
    message.intensities = []

    outgoing = remap_frame_id(message, "lidar_link")

    assert outgoing is message
    assert outgoing.header.frame_id == "lidar_link"
    assert outgoing.header.stamp.sec == 7
    assert outgoing.header.stamp.nanosec == 42
    assert outgoing.angle_min == pytest.approx(-3.14159)
    assert outgoing.angle_max == pytest.approx(3.14159)
    assert list(outgoing.ranges) == [1.0, 2.0, float("inf")]
    assert list(outgoing.intensities) == []


def test_node_roundtrip_rewrites_frame_id() -> None:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from rclpy.node import Node
    from sensor_msgs.msg import LaserScan

    received = []

    class Probe(Node):
        def __init__(self):
            super().__init__("scan_frame_republisher_test_probe")
            self.create_subscription(LaserScan, "/scan", self._on_scan, 10)
            qos = QoSProfile(depth=10)
            qos.reliability = ReliabilityPolicy.BEST_EFFORT
            self._raw_publisher = self.create_publisher(
                LaserScan, "/scan_raw", qos
            )

        def _on_scan(self, message):
            received.append(message)

    rclpy.init(args=[])
    relay = None
    probe = None
    try:
        relay = ScanFrameRepublisher()
        probe = Probe()
        executor = SingleThreadedExecutor()
        executor.add_node(relay)
        executor.add_node(probe)

        incoming = LaserScan()
        incoming.header.frame_id = "smartclean_robot/lidar_link/lidar"
        incoming.angle_min = -1.0
        incoming.angle_max = 1.0
        incoming.ranges = [0.5, 1.5, float("inf")]
        probe._raw_publisher.publish(incoming)

        deadline = probe.get_clock().now()
        import rclpy.time
        deadline = deadline + rclpy.time.Duration(seconds=5.0)
        while not received and probe.get_clock().now() < deadline:
            executor.spin_once(timeout_sec=0.1)

        assert len(received) == 1
        outgoing = received[0]
        assert outgoing.header.frame_id == "lidar_link"
        assert outgoing.angle_min == pytest.approx(-1.0)
        assert outgoing.angle_max == pytest.approx(1.0)
        assert list(outgoing.ranges) == [0.5, 1.5, float("inf")]
    finally:
        if relay is not None:
            relay.destroy_node()
        if probe is not None:
            probe.destroy_node()
        rclpy.shutdown()
