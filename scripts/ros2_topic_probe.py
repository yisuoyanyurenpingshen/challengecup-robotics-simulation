#!/usr/bin/env python3
"""Assert that the SmartClean ROS bridge publishes a complete healthy snapshot."""

import json
import sys
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Path
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


class TopicProbe(Node):
    """Collect the bridge's latched summary and one replayed robot pose."""

    def __init__(self) -> None:
        super().__init__("smartclean_topic_probe")
        latched_qos = QoSProfile(depth=1)
        latched_qos.reliability = ReliabilityPolicy.RELIABLE
        latched_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.status = None
        self.path = None
        self.pose = None
        self.create_subscription(
            String, "/smartclean/status", self._on_status, latched_qos
        )
        self.create_subscription(
            Path, "/smartclean/trajectory", self._on_path, latched_qos
        )
        self.create_subscription(
            PoseStamped, "/smartclean/robot_pose", self._on_pose, latched_qos
        )

    def _on_status(self, message: String) -> None:
        self.status = json.loads(message.data)

    def _on_path(self, message: Path) -> None:
        self.path = message

    def _on_pose(self, message: PoseStamped) -> None:
        self.pose = message


def main() -> int:
    rclpy.init()
    node = TopicProbe()
    deadline = time.monotonic() + 20.0
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.2)
            if (
                isinstance(node.status, dict)
                and node.status.get("status") == "COMPLETED"
                and node.path is not None
                and node.pose is not None
            ):
                break

        if node.status is None:
            raise AssertionError("20 秒内未收到 /smartclean/status")
        if node.path is None:
            raise AssertionError("20 秒内未收到 /smartclean/trajectory")
        if node.pose is None:
            raise AssertionError("20 秒内未收到 /smartclean/robot_pose")

        metrics = node.status["final_metrics"]
        rates = node.status["final_rates"]
        assert node.status["status"] == "COMPLETED", node.status
        assert node.status["run_result_status"] == "COMPLETED", node.status
        assert metrics["cleaned_targets"] == metrics["total_targets"] == 4, metrics
        assert metrics["collisions"] == 0, metrics
        assert metrics["returned_to_dock"] is True, metrics
        assert rates["completion_rate"] == 1.0, rates
        assert rates["coverage_rate"] == 1.0, rates
        assert len(node.path.poses) > 1
        assert node.path.header.frame_id == "map"
        assert node.pose.header.frame_id == "map"
        print(
            "ROS 2 Topic 验证通过：status=COMPLETED, path_poses={}, "
            "coverage=1.0, collisions=0".format(len(node.path.poses))
        )
        return 0
    except (AssertionError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("ROS 2 Topic 验证失败：{}".format(exc), file=sys.stderr)
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
