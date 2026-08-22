#!/usr/bin/env python3
"""Observe and verify the complete perception-to-cleaning mission.

This probe is intentionally passive: it subscribes to evidence produced by
the camera, detector, Nav2, mission controller, odometry, and safety guard. It
never publishes velocity commands or navigation goals and never calls the
entity-removal service. Gazebo ground truth is read only here, on the
evaluation side, to prove that the initially spawned entities really vanish.
"""

import argparse
import json
import math
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Set, Tuple

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry, Path as NavPath
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import Image

from smartclean_interfaces.msg import LitterCleaned, TrashDetectionArray
from smartclean_interfaces.msg import TrashMissionState


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = PROJECT_ROOT / "configs" / "gazebo_scene.json"

NAV2_CMD_VEL_PUBLISHERS = {"controller_server", "velocity_smoother"}
NAVIGATION_SUCCEEDED = GoalStatus.STATUS_SUCCEEDED
MIN_REAL_MOVEMENT_M = 0.20
MAX_POSITION_ERROR_M = 0.45
ROBOT_FRONT_EXTENT_M = 0.45
CLEANING_TOOL_OFFSET_M = 0.45
MAX_TOOL_HEADING_ERROR_RAD = 0.35
GEOMETRY_TOLERANCE_M = 0.03
MIN_STOP_DURATION_S = 0.75
MAX_STOP_LINEAR_MPS = 0.02
MAX_STOP_ANGULAR_RPS = 0.03
FINAL_STOP_WINDOW_S = 2.0
FINAL_STOP_GRACE_S = 0.20
MAX_FINAL_DRIFT_M = 0.03
MAX_DOCK_ERROR_M = 0.33
TARGET_CLEARANCE_BY_CLASS = {
    # Values already include collision radius plus the 0.05 m margin.
    "plastic_bottle": 0.09,
    "paper_cup": 0.095,
    "aluminum_can": 0.083,
    "fallen_leaves": 0.20,
    "paper_scrap": 0.11,
}

BEST_EFFORT = QoSProfile(depth=20)
BEST_EFFORT.reliability = ReliabilityPolicy.BEST_EFFORT
MISSION_STATE_QOS = QoSProfile(depth=1)
MISSION_STATE_QOS.reliability = ReliabilityPolicy.RELIABLE
MISSION_STATE_QOS.durability = DurabilityPolicy.TRANSIENT_LOCAL


def _finite(values: Iterable[float]) -> bool:
    return all(math.isfinite(float(value)) for value in values)


def _xy_distance(first: Sequence[float], second: Sequence[float]) -> float:
    return math.hypot(
        float(first[0]) - float(second[0]),
        float(first[1]) - float(second[1]),
    )


def _twist_magnitudes(message: Twist) -> Tuple[float, float]:
    linear = math.sqrt(
        message.linear.x ** 2
        + message.linear.y ** 2
        + message.linear.z ** 2
    )
    angular = math.sqrt(
        message.angular.x ** 2
        + message.angular.y ** 2
        + message.angular.z ** 2
    )
    return linear, angular


def _model_names(output: str) -> Set[str]:
    return {
        line.strip().lstrip("-").strip()
        for line in output.splitlines()
        if line.strip().lstrip("-").strip()
    }


def _ign_model_list() -> Set[str]:
    """Return the current Gazebo models in this process's IGN_PARTITION."""

    try:
        result = subprocess.run(
            ["ign", "model", "--list"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if result.returncode != 0:
        return set()
    return _model_names(result.stdout)


class TrashMissionProbe(Node):
    """Collect independent evidence and enforce the Phase 12 contract."""

    def __init__(self, timeout_s: float) -> None:
        super().__init__("smartclean_trash_mission_probe")
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            raise ValueError("timeout 必须是大于 0 的有限数值")
        self.timeout_s = float(timeout_s)

        scene = json.loads(SCENE_PATH.read_text(encoding="utf-8"))
        self.world_name = str(scene["world_name"])
        self.cleaning_radius_m = float(
            scene["robot"]["cleaning_radius_m"]
        )
        self.dock_xy = (
            float(scene["robot"]["dock_pose"]["x"]),
            float(scene["robot"]["dock_pose"]["y"]),
        )
        self.truth_by_entity = {
            str(item["model_name"]): item for item in scene["trash"]
        }  # type: Dict[str, dict]
        self.truth_by_class = {}  # type: Dict[str, list]
        for item in scene["trash"]:
            self.truth_by_class.setdefault(str(item["class_name"]), []).append(
                item
            )
        self.expected_entities = set(self.truth_by_entity)

        self.image_summaries = []
        self.position_detections = []
        self.state_samples = []
        self.events = []
        self.odom_samples = deque(maxlen=20000)
        self.cmd_vel_samples = deque(maxlen=12000)
        self.safe_cmd_vel_samples = deque(maxlen=12000)
        self.plan_count = 0
        self.plan_frames = set()
        self.clock_count = 0
        self.clock_jumps = 0
        self.first_clock_ns = None  # type: Optional[int]
        self.last_clock_ns = None  # type: Optional[int]
        self.failed_state = None
        self.completed_state = None
        self.completed_at = None  # type: Optional[float]
        self.last_logged_state = None  # type: Optional[str]
        self.cmd_vel_publishers = set()
        self.safe_cmd_vel_publishers = set()
        self.cmd_vel_subscribers = set()

        self.create_subscription(
            Image, "/camera/image_raw", self._on_image, BEST_EFFORT
        )
        self.create_subscription(
            TrashDetectionArray,
            "/smartclean/detections",
            self._on_detections,
            20,
        )
        self.create_subscription(
            TrashMissionState,
            "/smartclean/mission/state",
            self._on_state,
            MISSION_STATE_QOS,
        )
        self.create_subscription(
            LitterCleaned,
            "/smartclean/mission/litter_cleaned",
            self._on_cleaned,
            20,
        )
        self.create_subscription(Odometry, "/odom", self._on_odom, BEST_EFFORT)
        self.create_subscription(NavPath, "/plan", self._on_plan, 20)
        self.create_subscription(Twist, "/cmd_vel", self._on_cmd_vel, 50)
        self.create_subscription(
            Twist,
            "/smartclean/safe_cmd_vel",
            self._on_safe_cmd_vel,
            50,
        )
        self.create_subscription(Clock, "/clock", self._on_clock, BEST_EFFORT)

    def _on_image(self, message: Image) -> None:
        if len(self.image_summaries) >= 24:
            return
        data = bytes(message.data)
        stride = max(1, len(data) // 4096)
        sampled_values = len(set(data[::stride])) if data else 0
        stamp_ns = (
            int(message.header.stamp.sec) * 1_000_000_000
            + int(message.header.stamp.nanosec)
        )
        self.image_summaries.append(
            (
                int(message.width),
                int(message.height),
                str(message.encoding),
                int(message.step),
                len(data),
                sampled_values,
                stamp_ns,
            )
        )

    def _on_detections(self, message: TrashDetectionArray) -> None:
        for detection in message.detections:
            if not detection.position_valid:
                continue
            if detection.position_frame_id not in ("map", "odom"):
                continue
            position = tuple(float(value) for value in detection.position)
            if not _finite(position):
                continue
            if len(self.position_detections) < 512:
                self.position_detections.append(
                    (
                        str(detection.detection_id),
                        str(detection.class_name),
                        float(detection.confidence),
                        position,
                    )
                )

    def _on_state(self, message: TrashMissionState) -> None:
        received_at = time.monotonic()
        self.state_samples.append((received_at, message))
        if message.state != self.last_logged_state:
            self.get_logger().info(
                "[mission-probe] state={} active={} cleaned={} remaining={} "
                "failure={}".format(
                    message.state,
                    message.active_target_id or "-",
                    len(message.cleaned_ids),
                    len(message.remaining_trash_ids),
                    message.failure_code or "-",
                )
            )
            self.last_logged_state = message.state
        if message.state == "FAILED":
            self.failed_state = message
        if message.state == "COMPLETED":
            self.completed_state = message
            if self.completed_at is None:
                self.completed_at = received_at

    def _on_cleaned(self, message: LitterCleaned) -> None:
        self.events.append((time.monotonic(), message))
        self.get_logger().info(
            "[mission-probe] cleaned event={} track={} entity={} "
            "distance={:.3f}".format(
                message.event_id,
                message.track_id,
                message.entity_name,
                message.cleaning_distance_m,
            )
        )

    def _on_odom(self, message: Odometry) -> None:
        pose = message.pose.pose.position
        twist = message.twist.twist
        self.odom_samples.append(
            (
                time.monotonic(),
                float(pose.x),
                float(pose.y),
                abs(float(twist.linear.x)),
                abs(float(twist.angular.z)),
            )
        )

    def _on_plan(self, message: NavPath) -> None:
        if len(message.poses) >= 2:
            self.plan_count += 1
            self.plan_frames.add(str(message.header.frame_id))

    def _on_cmd_vel(self, message: Twist) -> None:
        linear, angular = _twist_magnitudes(message)
        self.cmd_vel_samples.append((time.monotonic(), linear, angular))

    def _on_safe_cmd_vel(self, message: Twist) -> None:
        linear, angular = _twist_magnitudes(message)
        self.safe_cmd_vel_samples.append((time.monotonic(), linear, angular))

    def _on_clock(self, message: Clock) -> None:
        stamp_ns = (
            int(message.clock.sec) * 1_000_000_000
            + int(message.clock.nanosec)
        )
        if self.last_clock_ns is not None and stamp_ns < self.last_clock_ns:
            self.clock_jumps += 1
        if self.first_clock_ns is None:
            self.first_clock_ns = stamp_ns
        self.last_clock_ns = stamp_ns
        self.clock_count += 1

    def _refresh_graph_evidence(self) -> None:
        self.cmd_vel_publishers.update(
            info.node_name.lstrip("/")
            for info in self.get_publishers_info_by_topic("/cmd_vel")
        )
        self.safe_cmd_vel_publishers.update(
            info.node_name.lstrip("/")
            for info in self.get_publishers_info_by_topic(
                "/smartclean/safe_cmd_vel"
            )
        )
        try:
            self.cmd_vel_subscribers.update(
                info.node_name.lstrip("/")
                for info in self.get_subscriptions_info_by_topic("/cmd_vel")
            )
        except AttributeError:
            # Older rclpy releases lack this graph helper. Publisher and node
            # evidence below still verifies the guard without weakening motion.
            pass

    def _spin_for(self, duration_s: float) -> None:
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            self._raise_if_controller_failed()

    def _raise_if_controller_failed(self) -> None:
        if self.failed_state is None:
            return
        message = self.failed_state
        raise AssertionError(
            "controller FAILED: failure_code={} detail={!r} active={} "
            "cleaned={} remaining={} failed={}".format(
                message.failure_code or "<empty>",
                message.detail,
                message.active_target_id or "-",
                list(message.cleaned_ids),
                list(message.remaining_trash_ids),
                list(message.failed_ids),
            )
        )

    def _wait_for_initial_entities(self, deadline: float) -> Set[str]:
        required = set(self.expected_entities)
        required.add("smartclean_robot")
        latest = set()
        while time.monotonic() < deadline:
            latest = _ign_model_list()
            if required <= latest:
                self.get_logger().info(
                    "[mission-probe] Gazebo 初始快照：机器人 + "
                    "{} 个垃圾实体".format(
                        len(self.expected_entities)
                    )
                )
                return latest
            rclpy.spin_once(self, timeout_sec=0.10)
            self._raise_if_controller_failed()
            time.sleep(0.20)
        raise AssertionError(
            "Gazebo 初始实体快照不完整，missing={}".format(
                sorted(required - latest)
            )
        )

    def _wait_for_removed_entities(self, deadline: float) -> Set[str]:
        latest = set()
        while time.monotonic() < deadline:
            latest = _ign_model_list()
            if (
                "smartclean_robot" in latest
                and not (self.expected_entities & latest)
            ):
                return latest
            rclpy.spin_once(self, timeout_sec=0.10)
            time.sleep(0.20)
        present = sorted(self.expected_entities & latest)
        raise AssertionError(
            "Gazebo 垃圾实体未全部真实消失，仍在场={}".format(present)
        )

    def _check_rgb_images(self) -> None:
        if len(self.image_summaries) < 3:
            raise AssertionError(
                "有效 RGB 帧不足：{} < 3".format(len(self.image_summaries))
            )
        stamps = set()
        for summary in self.image_summaries:
            width, height, encoding, step, size, colors, stamp_ns = summary
            if width != 640 or height != 480:
                raise AssertionError(
                    "RGB 尺寸非法：{}x{}，期望 640x480".format(width, height)
                )
            if encoding.lower() not in ("rgb8", "bgr8"):
                raise AssertionError("RGB encoding 非法：{}".format(encoding))
            if step < width * 3 or size < step * height:
                raise AssertionError("RGB data/step 长度不足")
            if colors < 4:
                raise AssertionError("RGB 图像近似单色，未证明真实渲染")
            stamps.add(stamp_ns)
        if len(stamps) < 3 or max(stamps) <= min(stamps):
            raise AssertionError("RGB 图像时间戳未推进")

    def _check_position_detections(self) -> None:
        if not self.position_detections:
            raise AssertionError(
                "没有 position_valid=true 且 frame=map/odom 的检测"
            )
        best_error = None
        best_class = None
        for (
            detection_id,
            class_name,
            confidence,
            position,
        ) in self.position_detections:
            if not detection_id or not class_name:
                raise AssertionError("有效位置检测缺少 detection_id/class_name")
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                raise AssertionError("检测 confidence 非法：{}".format(confidence))
            truths = self.truth_by_class.get(class_name, [])
            for truth in truths:
                truth_xy = (
                    float(truth["position"]["x"]),
                    float(truth["position"]["y"]),
                )
                error = _xy_distance(position, truth_xy)
                if best_error is None or error < best_error:
                    best_error = error
                    best_class = class_name
        if best_error is None:
            raise AssertionError("map/odom 检测类别与评估场景无交集")
        if best_error > MAX_POSITION_ERROR_M:
            raise AssertionError(
                "最佳 map/odom 检测位置误差 {:.3f}m > {:.2f}m".format(
                    best_error, MAX_POSITION_ERROR_M
                )
            )
        self.get_logger().info(
            "[mission-probe] map/odom 检测 PASS：{} 最佳误差 {:.3f}m".format(
                best_class, best_error
            )
        )

    @staticmethod
    def _unique_ids(name: str, values: Sequence[str]) -> Tuple[str, ...]:
        normalized = tuple(str(value) for value in values)
        if any(not value for value in normalized):
            raise AssertionError("{} 含空 ID".format(name))
        if len(normalized) != len(set(normalized)):
            raise AssertionError("{} 含重复 ID".format(name))
        return normalized

    def _check_state_history(self) -> Tuple[str, Set[str]]:
        if not self.state_samples:
            raise AssertionError("未收到 /smartclean/mission/state")
        mission_ids = {
            message.mission_id
            for _, message in self.state_samples
            if message.mission_id
        }
        if len(mission_ids) != 1:
            raise AssertionError(
                "mission_id 不稳定或为空：{}".format(sorted(mission_ids))
            )
        mission_id = next(iter(mission_ids))
        for _, message in self.state_samples:
            if message.schema_version != 1:
                raise AssertionError(
                    "TrashMissionState schema_version={} 非 1".format(
                        message.schema_version
                    )
                )
            if message.state != "FAILED" and message.failure_code:
                raise AssertionError(
                    "非 FAILED 状态携带 failure_code={}".format(
                        message.failure_code
                    )
                )

        frozen_index = None
        frozen_state = None
        for index, (_, message) in enumerate(self.state_samples):
            if message.initial_trash_count > 0 and message.discovered_trash_ids:
                frozen_index = index
                frozen_state = message
                break
        if frozen_state is None or frozen_index is None:
            raise AssertionError(
                "任务未形成 initial_trash_count>0 的稳定目标集"
            )

        discovered = set(
            self._unique_ids(
                "discovered_trash_ids", frozen_state.discovered_trash_ids
            )
        )
        initial_count = int(frozen_state.initial_trash_count)
        if initial_count <= 0 or len(discovered) != initial_count:
            raise AssertionError(
                "初始稳定目标计数不一致：initial={} discovered={}".format(
                    initial_count, len(discovered)
                )
            )

        remaining_counts = []
        for _, message in self.state_samples[frozen_index:]:
            if int(message.initial_trash_count) != initial_count:
                raise AssertionError("冻结后 initial_trash_count 发生变化")
            current_discovered = set(
                self._unique_ids(
                    "discovered_trash_ids", message.discovered_trash_ids
                )
            )
            if current_discovered != discovered:
                raise AssertionError("冻结后 discovered_trash_ids 发生变化")
            cleaned = set(self._unique_ids("cleaned_ids", message.cleaned_ids))
            remaining = set(
                self._unique_ids(
                    "remaining_trash_ids", message.remaining_trash_ids
                )
            )
            failed = set(self._unique_ids("failed_ids", message.failed_ids))
            if cleaned & remaining or cleaned & failed or remaining & failed:
                raise AssertionError("cleaned/remaining/failed 集合发生重叠")
            if not (cleaned | remaining | failed) <= discovered:
                raise AssertionError("状态进度含未发现的 track_id")
            count = len(remaining)
            if not remaining_counts or count != remaining_counts[-1]:
                remaining_counts.append(count)

        expected_counts = list(range(initial_count, -1, -1))
        if remaining_counts != expected_counts:
            raise AssertionError(
                "remaining 未逐目标严格递减：observed={} expected={}".format(
                    remaining_counts, expected_counts
                )
            )

        final = self.completed_state
        if final is None or final.state != "COMPLETED":
            raise AssertionError("任务未进入 COMPLETED")
        final_cleaned = set(self._unique_ids("cleaned_ids", final.cleaned_ids))
        final_remaining = set(
            self._unique_ids("remaining_trash_ids", final.remaining_trash_ids)
        )
        final_failed = set(self._unique_ids("failed_ids", final.failed_ids))
        if final_cleaned != discovered or final_remaining or final_failed:
            raise AssertionError(
                "COMPLETED 并非全 clean：cleaned={} remaining={} failed={}".format(
                    sorted(final_cleaned),
                    sorted(final_remaining),
                    sorted(final_failed),
                )
            )
        if final.failure_code:
            raise AssertionError("COMPLETED 携带 failure_code")
        if not final.return_after_done or not final.returned_to_dock:
            raise AssertionError("COMPLETED 未证明按任务返航")
        if float(final.progress) < 0.999:
            raise AssertionError("最终 progress < 1.0")
        if int(final.cleaning_events) != initial_count:
            raise AssertionError("最终 cleaning_events 与初始目标数不一致")
        if int(final.navigation_goals_sent) < initial_count + 1:
            raise AssertionError("导航目标数未覆盖全部垃圾与返航")
        return mission_id, discovered

    def _check_events(self, mission_id: str, discovered: Set[str]) -> None:
        messages = [message for _, message in self.events]
        if len(messages) != len(discovered):
            raise AssertionError(
                "LitterCleaned 数量 {} != 稳定目标数 {}".format(
                    len(messages), len(discovered)
                )
            )
        event_ids = self._unique_ids(
            "event_id", [message.event_id for message in messages]
        )
        track_ids = self._unique_ids(
            "event.track_id", [message.track_id for message in messages]
        )
        entity_names = self._unique_ids(
            "event.entity_name", [message.entity_name for message in messages]
        )
        if len(event_ids) != len(messages):
            raise AssertionError("事件 ID 不唯一")
        if set(track_ids) != discovered:
            raise AssertionError("事件 track_id 与稳定目标集不一致")
        if set(entity_names) != self.expected_entities:
            raise AssertionError(
                "事件实体与 Gazebo 初始垃圾不一致："
                "events={} expected={}".format(
                    sorted(entity_names), sorted(self.expected_entities)
                )
            )

        for message in messages:
            if message.schema_version != 1:
                raise AssertionError("LitterCleaned schema_version 非 1")
            if message.mission_id != mission_id:
                raise AssertionError("LitterCleaned mission_id 不一致")
            if message.header.frame_id != "map":
                raise AssertionError("LitterCleaned frame_id 必须是 map")
            if not message.source_detection_id or not message.class_name:
                raise AssertionError("清扫事件缺少检测来源或类别")
            truth = self.truth_by_entity.get(message.entity_name)
            if truth is None:
                raise AssertionError(
                    "清扫事件引用未知实体 {}".format(message.entity_name)
                )
            if message.class_name != truth["class_name"]:
                raise AssertionError("清扫事件实体类别映射错误")
            if not message.actuator:
                raise AssertionError("清扫事件缺少 actuator")
            if not message.removal_confirmed:
                raise AssertionError("清扫事件未确认实体删除")
            if int(message.navigation_status) != NAVIGATION_SUCCEEDED:
                raise AssertionError(
                    "清扫事件 navigation_status={}，期望 SUCCEEDED({})".format(
                        message.navigation_status, NAVIGATION_SUCCEEDED
                    )
                )

            target = tuple(float(value) for value in message.target_position)
            robot = tuple(float(value) for value in message.robot_position)
            tool = tuple(float(value) for value in message.tool_position)
            if not _finite(target + robot + tool):
                raise AssertionError("清扫事件位置包含 NaN/Inf")
            truth_position = (
                float(truth["position"]["x"]),
                float(truth["position"]["y"]),
            )
            target_error = _xy_distance(target, truth_position)
            if target_error > MAX_POSITION_ERROR_M:
                raise AssertionError(
                    "事件目标位置误差 {:.3f}m > {:.2f}m".format(
                        target_error, MAX_POSITION_ERROR_M
                    )
                )

            measured_tool_distance = _xy_distance(tool, target)
            reported_tool_distance = float(message.cleaning_distance_m)
            if (
                abs(measured_tool_distance - reported_tool_distance)
                > GEOMETRY_TOLERANCE_M
            ):
                raise AssertionError("工具距离字段与事件坐标不一致")
            if reported_tool_distance > self.cleaning_radius_m + 1e-3:
                raise AssertionError(
                    "工具距离 {:.3f}m 超出 cleaning_radius {:.3f}m".format(
                        reported_tool_distance, self.cleaning_radius_m
                    )
                )

            tool_offset = _xy_distance(robot, tool)
            if abs(tool_offset - CLEANING_TOOL_OFFSET_M) > GEOMETRY_TOLERANCE_M:
                raise AssertionError(
                    "base->tool 偏移 {:.3f}m 与车体契约 {:.2f}m 不一致".format(
                        tool_offset, CLEANING_TOOL_OFFSET_M
                    )
                )
            base_to_tool = (tool[0] - robot[0], tool[1] - robot[1])
            base_to_target = (target[0] - robot[0], target[1] - robot[1])
            target_length = math.hypot(*base_to_target)
            if tool_offset <= 0.0 or target_length <= 0.0:
                raise AssertionError("工具朝向几何退化")
            cosine = (
                base_to_tool[0] * base_to_target[0]
                + base_to_tool[1] * base_to_target[1]
            ) / (tool_offset * target_length)
            heading_error = math.acos(max(-1.0, min(1.0, cosine)))
            if heading_error > MAX_TOOL_HEADING_ERROR_RAD + 1e-3:
                raise AssertionError(
                    "车头/工具未朝向目标：error={:.3f}rad".format(
                        heading_error
                    )
                )

            measured_base_distance = _xy_distance(robot, target)
            reported_base_distance = float(message.base_target_distance_m)
            if (
                abs(measured_base_distance - reported_base_distance)
                > GEOMETRY_TOLERANCE_M
            ):
                raise AssertionError("base 距离字段与事件坐标不一致")
            minimum_base_distance = (
                float(message.target_clearance_m) + ROBOT_FRONT_EXTENT_M
            )
            expected_clearance = TARGET_CLEARANCE_BY_CLASS[message.class_name]
            if (
                float(message.target_clearance_m) + GEOMETRY_TOLERANCE_M
                < expected_clearance
            ):
                raise AssertionError(
                    "{} target_clearance {:.3f}m 小于安全契约 {:.3f}m".format(
                        message.class_name,
                        message.target_clearance_m,
                        expected_clearance,
                    )
                )
            if reported_base_distance + GEOMETRY_TOLERANCE_M < minimum_base_distance:
                raise AssertionError(
                    "base 目标距离 {:.3f}m 小于车体安全距离 {:.3f}m".format(
                        reported_base_distance, minimum_base_distance
                    )
                )

            if float(message.stop_duration_s) + 1e-3 < MIN_STOP_DURATION_S:
                raise AssertionError(
                    "停车证据时长 {:.3f}s < {:.1f}s".format(
                        message.stop_duration_s, MIN_STOP_DURATION_S
                    )
                )
            if abs(float(message.linear_speed_mps)) > MAX_STOP_LINEAR_MPS:
                raise AssertionError("清扫事件线速度不满足停车门控")
            if abs(float(message.angular_speed_rps)) > MAX_STOP_ANGULAR_RPS:
                raise AssertionError("清扫事件角速度不满足停车门控")

    def _check_navigation_and_motion(self) -> None:
        if self.plan_count <= 0 or "map" not in self.plan_frames:
            raise AssertionError("未观察到 Nav2 的 map 帧 /plan")
        nav_publishers = self.cmd_vel_publishers & NAV2_CMD_VEL_PUBLISHERS
        if not nav_publishers:
            raise AssertionError(
                "/cmd_vel 发布者不是 Nav2：{}".format(
                    sorted(self.cmd_vel_publishers)
                )
            )
        if len(self.odom_samples) < 2:
            raise AssertionError("/odom 样本不足")
        start = self.odom_samples[0]
        max_displacement = max(
            math.hypot(sample[1] - start[1], sample[2] - start[2])
            for sample in self.odom_samples
        )
        if max_displacement < MIN_REAL_MOVEMENT_M:
            raise AssertionError(
                "/odom 最大实际位移 {:.3f}m < {:.2f}m".format(
                    max_displacement, MIN_REAL_MOVEMENT_M
                )
            )
        requested_motion = any(
            linear > 0.05 or angular > 0.05
            for _, linear, angular in self.cmd_vel_samples
        )
        if not requested_motion:
            raise AssertionError("/cmd_vel 从未出现非零 Nav2 运动命令")
        self.get_logger().info(
            "[mission-probe] Nav2 PASS：plan={} publishers={} max_move={:.3f}m".format(
                self.plan_count, sorted(nav_publishers), max_displacement
            )
        )

    def _check_final_stop_dock_and_watchdog(self) -> None:
        if self.completed_at is None:
            raise AssertionError("缺少 COMPLETED 到达时间")
        cutoff = self.completed_at + FINAL_STOP_GRACE_S
        final_odoms = [sample for sample in self.odom_samples if sample[0] >= cutoff]
        if len(final_odoms) < 2:
            raise AssertionError("COMPLETED 后 /odom 样本不足")
        drift = math.hypot(
            final_odoms[-1][1] - final_odoms[0][1],
            final_odoms[-1][2] - final_odoms[0][2],
        )
        if drift > MAX_FINAL_DRIFT_M:
            raise AssertionError(
                "COMPLETED 后位移漂移 {:.4f}m > {:.2f}m".format(
                    drift, MAX_FINAL_DRIFT_M
                )
            )
        if max(sample[3] for sample in final_odoms) > MAX_STOP_LINEAR_MPS:
            raise AssertionError("COMPLETED 后 odom 线速度未归零")
        if max(sample[4] for sample in final_odoms) > MAX_STOP_ANGULAR_RPS:
            raise AssertionError("COMPLETED 后 odom 角速度未归零")

        final_commands = [
            sample for sample in self.cmd_vel_samples if sample[0] >= cutoff
        ]
        if any(
            linear > MAX_STOP_LINEAR_MPS or angular > MAX_STOP_ANGULAR_RPS
            for _, linear, angular in final_commands
        ):
            raise AssertionError("COMPLETED 后 /cmd_vel 仍有非零命令")
        final_safe_commands = [
            sample for sample in self.safe_cmd_vel_samples if sample[0] >= cutoff
        ]
        if len(final_safe_commands) < 10:
            raise AssertionError("COMPLETED 后安全看门狗输出样本不足")
        if any(
            linear > MAX_STOP_LINEAR_MPS or angular > MAX_STOP_ANGULAR_RPS
            for _, linear, angular in final_safe_commands
        ):
            raise AssertionError(
                "安全看门狗在 COMPLETED 后未持续输出零速度"
            )

        if "smartclean_cmd_vel_guard" not in self.safe_cmd_vel_publishers:
            raise AssertionError(
                "安全速度发布者缺少 smartclean_cmd_vel_guard：{}".format(
                    sorted(self.safe_cmd_vel_publishers)
                )
            )
        node_names = {name.lstrip("/") for name in self.get_node_names()}
        if "smartclean_cmd_vel_guard" not in node_names:
            raise AssertionError("最终安全看门狗节点不存活")
        if self.cmd_vel_subscribers and (
            "smartclean_cmd_vel_guard" not in self.cmd_vel_subscribers
        ):
            raise AssertionError("/cmd_vel 未连接安全看门狗")

        final_xy = (final_odoms[-1][1], final_odoms[-1][2])
        dock_error = _xy_distance(final_xy, self.dock_xy)
        if dock_error > MAX_DOCK_ERROR_M:
            raise AssertionError(
                "最终实际位置距 dock {:.3f}m > {:.2f}m".format(
                    dock_error, MAX_DOCK_ERROR_M
                )
            )
        self.get_logger().info(
            "[mission-probe] 返航/停车/看门狗 PASS：dock_error={:.3f}m "
            "drift={:.4f}m safe_zero_samples={}".format(
                dock_error, drift, len(final_safe_commands)
            )
        )

    def _check_clock(self) -> None:
        if self.clock_count < 10:
            raise AssertionError("/clock 样本不足")
        if self.clock_jumps:
            raise AssertionError(
                "/clock 出现 {} 次倒退".format(self.clock_jumps)
            )
        if (
            self.first_clock_ns is None
            or self.last_clock_ns is None
            or self.last_clock_ns <= self.first_clock_ns
        ):
            raise AssertionError("/clock 未推进")

    def run(self) -> int:
        deadline = time.monotonic() + self.timeout_s
        initial_deadline = min(deadline, time.monotonic() + 60.0)
        initial_models = self._wait_for_initial_entities(initial_deadline)
        if not self.expected_entities <= initial_models:
            raise AssertionError("初始 Gazebo 垃圾实体数不完整")

        next_graph_refresh = 0.0
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.10)
            self._raise_if_controller_failed()
            now = time.monotonic()
            if now >= next_graph_refresh:
                self._refresh_graph_evidence()
                next_graph_refresh = now + 1.0
            if self.completed_state is not None:
                break
        if self.completed_state is None:
            latest = self.state_samples[-1][1] if self.state_samples else None
            raise AssertionError(
                "{}s 内任务未完成，latest_state={} detail={!r}".format(
                    self.timeout_s,
                    latest.state if latest is not None else "<none>",
                    latest.detail if latest is not None else "",
                )
            )

        self._spin_for(FINAL_STOP_WINDOW_S)
        self._refresh_graph_evidence()
        self._wait_for_removed_entities(time.monotonic() + 20.0)

        self._check_rgb_images()
        self._check_position_detections()
        mission_id, discovered = self._check_state_history()
        self._check_events(mission_id, discovered)
        self._check_navigation_and_motion()
        self._check_final_stop_dock_and_watchdog()
        self._check_clock()

        print(
            "[trash-mission-probe] PASS targets={} events={} plans={} "
            "images={} position_detections={} clock_samples={}".format(
                len(discovered),
                len(self.events),
                self.plan_count,
                len(self.image_summaries),
                len(self.position_detections),
                self.clock_count,
            )
        )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=420.0)
    args = parser.parse_args()

    rclpy.init(args=sys.argv[1:])
    node = TrashMissionProbe(args.timeout)
    try:
        return node.run()
    except (AssertionError, AttributeError, KeyError, TypeError, ValueError) as exc:
        print("[trash-mission-probe] FAIL {}".format(exc), file=sys.stderr)
        return 1
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
