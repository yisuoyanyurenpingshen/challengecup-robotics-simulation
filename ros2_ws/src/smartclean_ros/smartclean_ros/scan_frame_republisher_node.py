"""Republish LaserScan with a corrected frame id.

Gazebo Fortress scopes sensor frames as ``world/model/link/sensor``, e.g.
``smartclean_robot/lidar_link/lidar``, while the TF tree uses the plain
``lidar_link`` frame. This node subscribes to the raw bridged scan and
republishes it on /scan with the configured frame id so Nav2/AMCL/RViz
always look up the same frame.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan


def remap_frame_id(message: LaserScan, frame_id: str) -> LaserScan:
    """Rewrite the header frame of a LaserScan in place and return it."""
    message.header.frame_id = frame_id
    return message


class ScanFrameRepublisher(Node):
    """LaserScan frame-id relay."""

    def __init__(self) -> None:
        super().__init__("smartclean_scan_frame_republisher")
        self.declare_parameter("input_topic", "/scan_raw")
        self.declare_parameter("output_topic", "/scan")
        self.declare_parameter("frame_id", "lidar_link")
        input_topic = self.get_parameter("input_topic").value
        output_topic = self.get_parameter("output_topic").value
        self._frame_id = self.get_parameter("frame_id").value

        qos = QoSProfile(depth=10)
        qos.reliability = ReliabilityPolicy.BEST_EFFORT
        self.create_subscription(
            LaserScan, input_topic, self._on_scan, qos
        )
        self._publisher = self.create_publisher(LaserScan, output_topic, 10)
        self.get_logger().info(
            "LaserScan frame 中继：{} -> {} (frame={})".format(
                input_topic, output_topic, self._frame_id
            )
        )

    def _on_scan(self, message: LaserScan) -> None:
        remap_frame_id(message, self._frame_id)
        self._publisher.publish(message)


def main() -> None:
    rclpy.init()
    node = ScanFrameRepublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
