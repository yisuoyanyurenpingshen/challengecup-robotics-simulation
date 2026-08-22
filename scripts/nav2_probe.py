#!/usr/bin/env python3
"""End-to-end acceptance probe for the SmartClean Nav2 navigation loop.

Checks, in order:
  - /scan arrives with frame_id=lidar_link and finite ranges;
  - /odom arrives and the odom -> base_footprint -> base_link -> lidar_link
    TF chain is connected;
  - map -> odom TF appears (AMCL); if AMCL has not initialized after a
    grace period, one /initialpose message is published (the same action a
    human would take from RViz, not a fake result);
  - /map is published by map_server;
  - the /navigate_to_pose action server becomes ready;
  - for every goal: Nav2 publishes /plan, the /cmd_vel publisher is a Nav2
    node (velocity_smoother or controller_server), and /odom really moves;
  - after each goal: result.success and arrival error within tolerance;
  - after the last goal: the robot stops (odom displacement decays to ~0).
The probe never publishes /cmd_vel itself.
"""

import argparse
import math
import sys
import threading
import time
from collections import deque

import rclpy
import tf2_ros
from lifecycle_msgs.srv import GetState
from rclpy._rclpy_pybind11 import RCLError
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from geometry_msgs.msg import PoseWithCovarianceStamped, Twist
from nav_msgs.msg import Odometry, OccupancyGrid, Path
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from rclpy.time import Time
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import LaserScan

# Map frame == world frame: the arena map image origin is at world (-10,-8),
# so world/map coordinates are identical and the robot starts at map (0, 0).
MAP_ORIGIN_X = 0.0
MAP_ORIGIN_Y = 0.0

GOALS_MAP = [
    (1.5, 2.5, 0.0),
    (-2.5, 1.0, 0.0),
]

ARRIVAL_TOLERANCE_M = 0.40
MIN_GOAL_DISPLACEMENT_M = 0.20
MIN_GOAL_SPEED = 0.05
STOP_WINDOW_S = 1.5
STOP_DISPLACEMENT_M = 0.03
STOP_SPEED = 0.02
NAV2_CMD_VEL_PUBLISHERS = {"velocity_smoother", "controller_server"}

TRANSIENT_LOCAL = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE,
)
BEST_EFFORT = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)


class Nav2Probe(Node):
    def __init__(self, timeout_s: float) -> None:
        super().__init__("smartclean_nav2_probe")
        self.timeout_s = timeout_s
        self.scans = deque(maxlen=8)
        self.odoms = deque(maxlen=200)
        self.maps = deque(maxlen=4)
        self.plans = deque(maxlen=8)
        self.cmd_vels = deque(maxlen=500)
        self.cmd_vel_publishers = set()
        self.cmd_vel_times = []
        self.create_subscription(
            LaserScan, "/scan", self._on_scan, BEST_EFFORT
        )
        self.create_subscription(Odometry, "/odom", self._on_odom, 10)
        self.create_subscription(
            OccupancyGrid, "/map", self._on_map, TRANSIENT_LOCAL
        )
        self.create_subscription(Path, "/plan", self._on_plan, 10)
        self._cmd_vel_subscription = self.create_subscription(
            Twist,
            "/cmd_vel",
            self._on_cmd_vel,
            10,
        )
        self._initial_pose_publisher = self.create_publisher(
            PoseWithCovarianceStamped, "/initialpose", 10
        )
        # Dedicated node for the TF listener: its executor then never holds
        # the probe action client in a wait set, which avoids the rclpy
        # teardown race ("wait set index ... out of bounds") when the probe
        # exits while the transform thread is spinning.
        self._tf_listener_node = Node("smartclean_nav2_probe_tf_listener")
        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(
            self._tf_buffer, self._tf_listener_node, spin_thread=False
        )
        self._tf_executor = SingleThreadedExecutor()
        self._tf_executor.add_node(self._tf_listener_node)
        self._tf_thread = threading.Thread(
            target=self._spin_tf_executor, daemon=True
        )
        self._tf_thread.start()
        self._action_client = ActionClient(self, NavigateToPose, "navigate_to_pose")

        # Nav2 exposes its action servers during CONFIGURING; goals sent
        # before the lifecycle manager finishes activation are rejected.
        # Poll each server GetState service until PRIMARY_STATE_ACTIVE (3).
        self._nav2_servers = ("planner_server", "controller_server", "bt_navigator")
        self._nav2_state_clients = {
            server: self.create_client(
                GetState, "/{}/get_state".format(server)
            )
            for server in self._nav2_servers
        }

        # /clock must stay strictly monotonic for the whole run; tf2_ros
        # clears its buffer and localization breaks when sim time runs
        # backwards. The smartclean_clock_relay guarantees this, and this
        # counter guards against the relay being bypassed.
        self.clock_jumps = 0
        self._last_clock = None
        self.create_subscription(Clock, "/clock", self._on_clock, 10)

    def _on_clock(self, message: Clock) -> None:
        stamp = (message.clock.sec, message.clock.nanosec)
        if self._last_clock is not None and stamp < self._last_clock:
            self.clock_jumps += 1
        self._last_clock = stamp

    def _spin_tf_executor(self) -> None:
        try:
            self._tf_executor.spin()
        except (ExternalShutdownException, RCLError):
            # Expected during node/context teardown.
            pass

    def _on_scan(self, message: LaserScan) -> None:
        self.scans.append(message)

    def _on_odom(self, message: Odometry) -> None:
        self.odoms.append(message)

    def _on_map(self, message: OccupancyGrid) -> None:
        self.maps.append(message)

    def _on_plan(self, message: Path) -> None:
        self.plans.append(message)

    def _on_cmd_vel(self, message) -> None:
        self.cmd_vels.append(message)
        self.cmd_vel_times.append(time.monotonic())
        for info in self.get_publishers_info_by_topic("/cmd_vel"):
            self.cmd_vel_publishers.add(info.node_name)

    def _spin_until(self, predicate, deadline: float, label: str) -> bool:
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if predicate():
                return True
        self.get_logger().error("等待超时：{}".format(label))
        return False

    def _spin_for(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)

    def _nav2_servers_active(self) -> bool:
        for server, client in self._nav2_state_clients.items():
            if not client.service_is_ready():
                return False
            future = client.call_async(GetState.Request())
            rclpy.spin_until_future_complete(self, future, timeout_sec=0.5)
            if not future.done():
                return False
            response = future.result()
            if response is None or response.current_state.id != 3:
                return False
        return True

    def _publish_initial_pose(self) -> None:
        message = PoseWithCovarianceStamped()
        message.header.frame_id = "map"
        message.header.stamp = self.get_clock().now().to_msg()
        message.pose.pose.position.x = MAP_ORIGIN_X
        message.pose.pose.position.y = MAP_ORIGIN_Y
        message.pose.pose.orientation.w = 1.0
        self._initial_pose_publisher.publish(message)
        self.get_logger().info(
            "发布 /initialpose：map({:.2f}, {:.2f})".format(
                MAP_ORIGIN_X, MAP_ORIGIN_Y
            )
        )

    def _tf_connected(self, parent: str, child: str) -> bool:
        try:
            return self._tf_buffer.can_transform(
                parent, child, Time(), Duration(seconds=1.0)
            )
        except Exception:
            return False

    def _odom_pose(self):
        if not self.odoms:
            return None
        latest = self.odoms[-1]
        return (latest.pose.pose.position.x, latest.pose.pose.position.y)

    def _base_pose_in_map(self):
        if not self._tf_connected("map", "base_footprint"):
            return None
        transform = self._tf_buffer.lookup_transform(
            "map", "base_footprint", Time()
        )
        return (
            transform.transform.translation.x,
            transform.transform.translation.y,
        )

    def _check_scene(self, deadline: float) -> bool:
        if not self._spin_until(
            lambda: bool(self.scans), deadline, "/scan 到达"
        ):
            return False
        scan = self.scans[-1]
        if scan.header.frame_id != "lidar_link":
            self.get_logger().error(
                "/scan frame_id={}，期望 lidar_link".format(
                    scan.header.frame_id
                )
            )
            return False
        if len(scan.ranges) != 360:
            self.get_logger().error(
                "/scan samples={}，期望 360".format(len(scan.ranges))
            )
            return False
        finite = [r for r in scan.ranges if math.isfinite(r) and r > 0.0]
        if not finite:
            self.get_logger().error("/scan 没有有限测距")
            return False
        self.get_logger().info(
            "[nav2-probe] /scan 到达：frame=lidar_link，samples={}，有限测距 {} 个".format(
                len(scan.ranges), len(finite)
            )
        )

        if not self._spin_until(
            lambda: bool(self.odoms), deadline, "/odom 到达"
        ):
            return False
        for parent, child in (
            ("odom", "base_footprint"),
            ("base_footprint", "base_link"),
            ("base_link", "lidar_link"),
        ):
            if not self._spin_until(
                lambda p=parent, c=child: self._tf_connected(p, c),
                deadline,
                "TF {} -> {}".format(parent, child),
            ):
                return False
            self.get_logger().info(
                "[nav2-probe] TF 连通：{} -> {}".format(parent, child)
            )

        if not self._spin_until(
            lambda: bool(self.maps), deadline, "/map 到达"
        ):
            return False
        self.get_logger().info("[nav2-probe] /map 已发布（map_server 激活）")

        if not self._spin_until(
            lambda: self._tf_connected("map", "odom"),
            time.monotonic() + 20.0,
            "AMCL map -> odom",
        ):
            self.get_logger().warn(
                "AMCL 20s 未发布 map -> odom，发布一次 /initialpose（等效 RViz 2D Pose Estimate）"
            )
            self._publish_initial_pose()
            if not self._spin_until(
                lambda: self._tf_connected("map", "odom"),
                deadline,
                "AMCL map -> odom（initialpose 后）",
            ):
                return False
        self.get_logger().info("[nav2-probe] AMCL map -> odom TF 已发布")

        if not self._spin_until(
            lambda: self._action_client.server_is_ready(),
            deadline,
            "navigate_to_pose action server",
        ):
            return False
        self.get_logger().info("[nav2-probe] /navigate_to_pose action 就绪")

        # The action server is visible during CONFIGURING; wait until the
        # whole Nav2 stack reached PRIMARY_STATE_ACTIVE so goals are not
        # rejected by servers that are still activating.
        if not self._spin_until(
            self._nav2_servers_active,
            deadline,
            "Nav2 lifecycle 激活（planner/controller/bt_navigator ACTIVE）",
        ):
            return False
        self.get_logger().info("[nav2-probe] Nav2 lifecycle 全部 ACTIVE")
        return True

    def _send_goal(self, x: float, y: float, yaw: float):
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
        return self._action_client.send_goal_async(goal)

    def _run_goal(self, index: int, goal: tuple, deadline: float) -> bool:
        goal_x, goal_y, goal_yaw = goal
        self.plans.clear()
        self.cmd_vels.clear()
        self.cmd_vel_times.clear()
        start = self._odom_pose()
        if start is None:
            self.get_logger().error("目标 {}：无 /odom 起点".format(index))
            return False

        future = self._send_goal(goal_x, goal_y, goal_yaw)
        rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)
        if not future.done() or future.result() is None:
            self.get_logger().error("目标 {}：goal 未送达".format(index))
            return False
        accepted = future.result().accepted
        if not accepted:
            self.get_logger().error("目标 {}：被 Nav2 拒绝".format(index))
            return False
        goal_handle = future.result()
        self.get_logger().info(
            "[nav2-probe] 目标 {}：map({:.2f}, {:.2f}) 已接受".format(
                index, goal_x, goal_y
            )
        )

        result_future = goal_handle.get_result_async()
        observed_plan = False
        observed_motion = False
        max_speed = 0.0
        while not result_future.done() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if self.plans and len(self.plans[-1].poses) >= 2:
                observed_plan = True
            current = self._odom_pose()
            if current is not None:
                displacement = math.hypot(
                    current[0] - start[0], current[1] - start[1]
                )
                if displacement >= MIN_GOAL_DISPLACEMENT_M:
                    observed_motion = True
            for message in self.cmd_vels:
                max_speed = max(
                    max_speed,
                    math.hypot(
                        message.linear.x,
                        math.hypot(message.linear.y, message.linear.z),
                    ),
                )
        if not result_future.done():
            self.get_logger().error("目标 {}：超时未完成".format(index))
            return False

        result = result_future.result()
        success = bool(result.result.data if hasattr(result.result, "data") else result.result)
        if not success:
            self.get_logger().error("目标 {}：Nav2 报告失败".format(index))
            return False

        if not observed_plan:
            self.get_logger().error("目标 {}：未观察到 /plan".format(index))
            return False
        if not observed_motion:
            self.get_logger().error("目标 {}：/odom 未实际移动".format(index))
            return False
        if not (self.cmd_vel_publishers & NAV2_CMD_VEL_PUBLISHERS):
            self.get_logger().error(
                "目标 {}：/cmd_vel 发布者 {} 不是 Nav2 节点".format(
                    index, sorted(self.cmd_vel_publishers)
                )
            )
            return False

        arrival = self._base_pose_in_map()
        if arrival is None:
            self.get_logger().error("目标 {}：map 下机器人位姿不可用".format(index))
            return False
        error = math.hypot(arrival[0] - goal_x, arrival[1] - goal_y)
        if error > ARRIVAL_TOLERANCE_M:
            self.get_logger().error(
                "目标 {}：到达误差 {:.3f} m > {:.2f} m".format(
                    index, error, ARRIVAL_TOLERANCE_M
                )
            )
            return False
        self.get_logger().info(
            "[nav2-probe] 目标 {} PASS：/plan={}，移动={}，max_speed={:.3f} m/s，"
            "cmd_vel 来源={}，到达误差={:.3f} m".format(
                index,
                observed_plan,
                observed_motion,
                max_speed,
                sorted(self.cmd_vel_publishers & NAV2_CMD_VEL_PUBLISHERS),
                error,
            )
        )
        return True

    def _check_stop(self) -> bool:
        self.get_logger().info(
            "[nav2-probe] 最终停车检查：观察 {:.1f} s".format(STOP_WINDOW_S)
        )
        start = self._odom_pose()
        if start is None:
            return False
        self._spin_for(STOP_WINDOW_S)
        end = self._odom_pose()
        displacement = math.hypot(end[0] - start[0], end[1] - start[1])
        recent = [
            message
            for message, stamp in zip(self.cmd_vels, self.cmd_vel_times)
            if time.monotonic() - stamp < STOP_WINDOW_S
        ]
        max_recent_speed = 0.0
        for message in recent:
            max_recent_speed = max(
                max_recent_speed,
                math.hypot(
                    message.linear.x,
                    math.hypot(message.linear.y, message.linear.z),
                ),
            )
        if displacement > STOP_DISPLACEMENT_M:
            self.get_logger().error(
                "停车检查失败：{:.1f}s 内位移 {:.4f} m".format(
                    STOP_WINDOW_S, displacement
                )
            )
            return False
        if max_recent_speed > STOP_SPEED:
            self.get_logger().error(
                "停车检查失败：末尾 /cmd_vel 速度 {:.3f} m/s".format(
                    max_recent_speed
                )
            )
            return False
        self.get_logger().info(
            "[nav2-probe] 停车 PASS：位移 {:.4f} m，速度 {:.3f} m/s".format(
                displacement, max_recent_speed
            )
        )
        return True

    def run(self) -> int:
        deadline = time.monotonic() + self.timeout_s
        if not self._check_scene(deadline):
            return 1
        for index, goal in enumerate(GOALS_MAP, start=1):
            goal_deadline = time.monotonic() + 90.0
            if not self._run_goal(index, goal, goal_deadline):
                return 1
        if not self._check_stop():
            return 1
        if self.clock_jumps:
            self.get_logger().error(
                "/clock 出现 {} 次倒退（jump back），TF/定位不可信".format(
                    self.clock_jumps
                )
            )
            return 1
        self.get_logger().info(
            "[nav2-probe] /clock 单调 PASS（无倒退，末值={}）".format(
                self._last_clock
            )
        )
        self.get_logger().info("[nav2-probe] PASS")
        print("[nav2-probe] PASS")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    rclpy.init(args=sys.argv[1:])
    node = Nav2Probe(timeout_s=args.timeout)
    try:
        return node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()
        # The TF listener node is destroyed by the context shutdown; wait for
        # its executor thread to observe the shutdown and exit cleanly.
        node._tf_thread.join(timeout=2.0)


if __name__ == "__main__":
    raise SystemExit(main())
