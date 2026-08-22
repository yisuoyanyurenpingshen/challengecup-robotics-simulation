"""ROS 2 node exposing a deterministic SmartClean-Sim run and replay."""

import json
import sys
from math import isfinite
from typing import Optional

import rclpy
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Path
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from std_msgs.msg import String

from smartclean_ros.bridge_core import BridgeError, BridgeRun, build_status_payload
from smartclean_ros.bridge_core import load_and_run
from smartclean_ros.conversions import CoordinateTransformError, GridMapTransform


class SmartCleanBridgeNode(Node):
    """Run the platform-neutral core once and replay its trace over ROS topics."""

    def __init__(self) -> None:
        super().__init__("smartclean_bridge")
        default_config = "{}/config/demo.json".format(
            get_package_share_directory("smartclean_core")
        )
        self.declare_parameter("config_path", default_config)
        self.declare_parameter("frame_id", "map")
        self.declare_parameter("cell_size_m", 1.0)
        self.declare_parameter("origin_x_m", 0.0)
        self.declare_parameter("origin_y_m", 0.0)
        self.declare_parameter("replay_period_s", 0.2)
        self.declare_parameter("loop_replay", False)

        config_path = str(self.get_parameter("config_path").value)
        self._frame_id = str(self.get_parameter("frame_id").value).strip()
        cell_size_m = float(self.get_parameter("cell_size_m").value)
        origin_x_m = float(self.get_parameter("origin_x_m").value)
        origin_y_m = float(self.get_parameter("origin_y_m").value)
        replay_period_s = float(self.get_parameter("replay_period_s").value)
        self._loop_replay = bool(self.get_parameter("loop_replay").value)

        if not self._frame_id:
            raise BridgeError("frame_id 不能为空")
        if not isfinite(replay_period_s) or replay_period_s <= 0.0:
            raise BridgeError("replay_period_s 必须是大于 0 的有限数值")

        self._run = load_and_run(config_path)
        self._transform = GridMapTransform(
            grid_width=self._run.grid_width,
            grid_height=self._run.grid_height,
            cell_size_m=cell_size_m,
            origin_x_m=origin_x_m,
            origin_y_m=origin_y_m,
        )

        latched_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        pose_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._status_publisher = self.create_publisher(
            String, "smartclean/status", latched_qos
        )
        self._trajectory_publisher = self.create_publisher(
            Path, "smartclean/trajectory", latched_qos
        )
        self._pose_publisher = self.create_publisher(
            PoseStamped, "smartclean/robot_pose", pose_qos
        )

        self._timer = None  # type: Optional[object]
        self._next_frame_index = 0
        self._publish_trajectory(self._run)
        self._publish_frame(0)
        self._next_frame_index = 1

        if len(self._run.result.frames) > 1 or self._loop_replay:
            self._timer = self.create_timer(replay_period_s, self._on_timer)

        self.get_logger().info(
            "已加载场景 '{}': status={}, frames={}, trajectory={}".format(
                self._run.scenario_name,
                self._run.result.status,
                len(self._run.result.frames),
                len(self._run.result.trajectory),
            )
        )

    def _new_pose(self, grid_x: int, grid_y: int) -> PoseStamped:
        map_x, map_y = self._transform.grid_to_map(grid_x, grid_y)
        pose = PoseStamped()
        pose.header.frame_id = self._frame_id
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = map_x
        pose.pose.position.y = map_y
        pose.pose.position.z = 0.0
        pose.pose.orientation.w = 1.0
        return pose

    def _publish_trajectory(self, run: BridgeRun) -> None:
        message = Path()
        message.header.frame_id = self._frame_id
        message.header.stamp = self.get_clock().now().to_msg()
        for point in run.result.trajectory:
            pose = self._new_pose(point.x, point.y)
            pose.header.stamp = message.header.stamp
            message.poses.append(pose)
        self._trajectory_publisher.publish(message)

    def _publish_frame(self, frame_index: int) -> None:
        frame = self._run.result.frames[frame_index]
        pose = self._new_pose(frame.robot_position.x, frame.robot_position.y)
        self._pose_publisher.publish(pose)

        status = String()
        status.data = json.dumps(
            build_status_payload(self._run, frame_index),
            ensure_ascii=False,
            sort_keys=True,
        )
        self._status_publisher.publish(status)

    def _on_timer(self) -> None:
        frame_count = len(self._run.result.frames)
        if self._next_frame_index >= frame_count:
            if self._loop_replay:
                self._next_frame_index = 0
            else:
                if self._timer is not None:
                    self._timer.cancel()
                return

        self._publish_frame(self._next_frame_index)
        self._next_frame_index += 1


def main(args: Optional[list] = None) -> int:
    """Run the bridge until ROS shutdown and return a process exit code."""

    rclpy.init(args=args)
    node = None  # type: Optional[SmartCleanBridgeNode]
    try:
        node = SmartCleanBridgeNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except ExternalShutdownException:
        # SIGINT/SIGTERM 触发 context shutdown 时 executor 的正常退出路径。
        pass
    except (BridgeError, CoordinateTransformError, ValueError) as exc:
        print("smartclean_bridge 启动失败：{}".format(exc), file=sys.stderr)
        return 2
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
