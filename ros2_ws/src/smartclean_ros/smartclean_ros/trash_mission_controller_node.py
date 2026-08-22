"""Perception-driven Nav2 trash mission controller.

The controller selects targets exclusively from ``TrashDetectionArray``
messages.  It uses TF and odometry to prove arrival and a continuous stop,
then invokes the configured ``DeleteEntity`` service.  It never publishes a
velocity command and never reads a simulator scene description.

All service and action work is asynchronous.  The steady-clock timer polls
futures so a subscription or timer callback never performs a nested spin.
"""

import math
import time
from collections import Counter, deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict, Optional, Sequence, Tuple

import rclpy
import tf2_ros
from action_msgs.msg import GoalStatus
from lifecycle_msgs.srv import GetState
from nav_msgs.msg import Odometry
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.clock import Clock, ClockType
from rclpy.duration import Duration
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from rclpy.time import Time
from ros_gz_interfaces.msg import Entity
from ros_gz_interfaces.srv import DeleteEntity

from smartclean_interfaces.msg import LitterCleaned
from smartclean_interfaces.msg import TrashDetectionArray, TrashMissionState
from smartclean_sim.models import TRASH_CLASSES

from .mission_core import (
    DetectionObservation,
    MissionCoreError,
    MissionFailureReason,
    MissionState,
    Point2D,
    Pose2D,
    SpatialTrackManager,
    TargetSelectionPolicy,
    TrackedTarget,
    compute_front_tool_approach,
    select_target,
)


SCHEMA_VERSION = 1
NAV2_ACTIVE_STATE = 3
MAP_FRAME = "map"
ODOM_FRAME = "odom"
BASE_FRAME = "base_footprint"
ENTITY_PREFIX = "trash_"

# Collision radii declared by the local synthetic assets.  These values are
# robot geometry, not target positions, and are used only to keep the chassis
# clear of a target selected from perception.
TARGET_RADIUS_M = {
    "plastic_bottle": 0.04,
    "paper_cup": 0.045,
    "aluminum_can": 0.033,
    "fallen_leaves": 0.15,
    "paper_scrap": 0.06,
}

STATUS_QOS = QoSProfile(
    depth=1,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
)
EVENT_QOS = QoSProfile(
    depth=32,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
)


def _normalize_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def _quaternion_yaw(rotation) -> float:
    """Return planar yaw from a geometry quaternion."""

    siny = 2.0 * (rotation.w * rotation.z + rotation.x * rotation.y)
    cosy = 1.0 - 2.0 * (rotation.y * rotation.y + rotation.z * rotation.z)
    return math.atan2(siny, cosy)


def navigation_result_succeeded(response) -> bool:
    """Check the action status, never the truthiness of its Empty result."""

    return (
        response is not None
        and getattr(response, "status", GoalStatus.STATUS_UNKNOWN)
        == GoalStatus.STATUS_SUCCEEDED
    )


def delete_response_succeeded(response) -> bool:
    """Return true only for an explicit positive actuator response."""

    return response is not None and getattr(response, "success", False) is True


def detection_observation_is_new(
    previous_received_at_s: Optional[float],
    received_at_s: float,
    minimum_interval_s: float = 0.02,
) -> bool:
    """Rate-limit duplicate bursts using the host steady clock.

    Gazebo sensor stamps can rewind or remain constant during startup, so they
    are evidence fields rather than an ordering clock.  DDS callbacks spaced
    in steady time are independent observations even when their ROS stamps
    are equal.
    """

    return (
        previous_received_at_s is None
        or received_at_s - previous_received_at_s + 1e-9
        >= minimum_interval_s
    )


@dataclass(frozen=True)
class StopWindowEvidence:
    """Continuous odometry evidence used by cleaning and docking gates."""

    passed: bool
    duration_s: float
    max_linear_speed_mps: float
    max_angular_speed_rps: float
    displacement_m: float


@dataclass(frozen=True)
class CleaningGateEvidence:
    """Auditable evidence captured before an entity-removal request."""

    passed: bool
    navigation_status: int
    base_pose: Pose2D
    tool_position: Point2D
    base_target_distance_m: float
    cleaning_distance_m: float
    target_clearance_m: float
    heading_error_rad: float
    stop: StopWindowEvidence


def evaluate_cleaning_gate(
    *,
    navigation_status: int,
    base_pose: Pose2D,
    target_position: Point2D,
    robot_front_extent_m: float,
    target_clearance_m: float,
    cleaning_tool_offset_m: float,
    cleaning_radius_m: float,
    stop: StopWindowEvidence,
    heading_tolerance_rad: float = 0.35,
) -> CleaningGateEvidence:
    """Evaluate every condition that must hold before target removal."""

    tool_position = Point2D(
        base_pose.x + math.cos(base_pose.yaw) * cleaning_tool_offset_m,
        base_pose.y + math.sin(base_pose.yaw) * cleaning_tool_offset_m,
    )
    base_distance = base_pose.position.distance_to(target_position)
    cleaning_distance = tool_position.distance_to(target_position)
    target_heading = math.atan2(
        target_position.y - base_pose.y,
        target_position.x - base_pose.x,
    )
    heading_error = abs(_normalize_angle(target_heading - base_pose.yaw))
    minimum_base_distance = robot_front_extent_m + target_clearance_m
    passed = (
        navigation_status == GoalStatus.STATUS_SUCCEEDED
        and base_distance + 1e-3 >= minimum_base_distance
        and cleaning_distance <= cleaning_radius_m + 1e-3
        and heading_error <= heading_tolerance_rad
        and stop.passed
    )
    return CleaningGateEvidence(
        passed=passed,
        navigation_status=int(navigation_status),
        base_pose=base_pose,
        tool_position=tool_position,
        base_target_distance_m=base_distance,
        cleaning_distance_m=cleaning_distance,
        target_clearance_m=target_clearance_m,
        heading_error_rad=heading_error,
        stop=stop,
    )


def evaluate_dock_gate(
    *,
    navigation_status: int,
    base_pose: Pose2D,
    dock_pose: Pose2D,
    distance_tolerance_m: float,
    stop: StopWindowEvidence,
) -> bool:
    """Require Nav2 success, map-frame dock distance, and a continuous stop."""

    return (
        navigation_status == GoalStatus.STATUS_SUCCEEDED
        and base_pose.position.distance_to(dock_pose.position)
        <= distance_tolerance_m
        and stop.passed
    )


@dataclass
class RemovalTransaction:
    """One-shot latch preventing early or duplicate removal commits."""

    requested: bool = False
    resolved: bool = False
    committed: bool = False

    def start(self, evidence: CleaningGateEvidence) -> bool:
        if not evidence.passed or self.requested or self.resolved:
            return False
        self.requested = True
        return True

    def resolve(self, success: bool) -> bool:
        if not self.requested or self.resolved:
            return False
        self.resolved = True
        self.committed = bool(success)
        return self.committed


def commit_delete_response(
    transaction: RemovalTransaction,
    response,
    commit: Callable[[], None],
) -> bool:
    """Run ``commit`` exactly once after a positive delete response."""

    if not transaction.resolve(delete_response_succeeded(response)):
        return False
    commit()
    return True


@dataclass(frozen=True)
class _OdomSample:
    received_at_s: float
    x: float
    y: float
    linear_speed_mps: float
    angular_speed_rps: float


def evaluate_stop_window(
    samples: Sequence[_OdomSample],
    *,
    now_s: float,
    since_s: float,
    hold_s: float,
    max_linear_speed_mps: float,
    max_angular_speed_rps: float,
    max_displacement_m: float,
    max_sample_gap_s: float = 0.25,
) -> StopWindowEvidence:
    """Evaluate a rolling, continuously sampled odometry stop window."""

    eligible = tuple(
        sample for sample in samples if sample.received_at_s >= since_s
    )
    if not eligible:
        return StopWindowEvidence(False, 0.0, math.inf, math.inf, math.inf)

    latest = eligible[-1]
    evidence_start = max(since_s, latest.received_at_s - hold_s)
    window = tuple(
        sample
        for sample in eligible
        if sample.received_at_s >= evidence_start
    )
    duration = max(0.0, latest.received_at_s - evidence_start)
    max_linear = max(sample.linear_speed_mps for sample in window)
    max_angular = max(sample.angular_speed_rps for sample in window)
    first = window[0]
    displacement = max(
        math.hypot(sample.x - first.x, sample.y - first.y)
        for sample in window
    )
    gaps = [window[0].received_at_s - evidence_start]
    gaps.extend(
        later.received_at_s - earlier.received_at_s
        for earlier, later in zip(window, window[1:])
    )
    gaps.append(now_s - latest.received_at_s)
    continuously_sampled = all(
        -1e-6 <= gap <= max_sample_gap_s for gap in gaps
    )
    passed = (
        continuously_sampled
        and duration + 1e-3 >= hold_s
        and max_linear <= max_linear_speed_mps
        and max_angular <= max_angular_speed_rps
        and displacement <= max_displacement_m
    )
    return StopWindowEvidence(
        passed,
        duration,
        max_linear,
        max_angular,
        displacement,
    )


class TrashMissionController(Node):
    """Coordinate detection tracking, Nav2, safe removal, and return."""

    def __init__(self) -> None:
        super().__init__("trash_mission_controller")
        self._read_parameters()

        # These ages deliberately cover the entire mission.  Confirmed targets
        # are also copied into _targets when discovery closes, so turning the
        # camera away during a long Nav2 goal cannot erase mission intent.
        retained_age = self._mission_timeout_s + 60.0
        self._track_manager = SpatialTrackManager(
            association_distance_m=self._association_distance_m,
            max_track_age_s=retained_age,
            frame_id=MAP_FRAME,
        )
        self._selection_policy = TargetSelectionPolicy(
            priority_classes=self._priority_classes,
            min_confidence=self._min_confidence,
            max_track_age_s=retained_age,
        )

        self._status_publisher = self.create_publisher(
            TrashMissionState, "/smartclean/mission/state", STATUS_QOS
        )
        self._cleaned_publisher = self.create_publisher(
            LitterCleaned, "/smartclean/mission/litter_cleaned", EVENT_QOS
        )
        self.create_subscription(
            TrashDetectionArray,
            self._detection_topic,
            self._on_detections,
            10,
        )
        self.create_subscription(
            Odometry,
            self._odom_topic,
            self._on_odom,
            20,
        )

        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)
        self._navigate_client = ActionClient(
            self, NavigateToPose, "/navigate_to_pose"
        )
        self._delete_client = self.create_client(
            DeleteEntity, self._delete_service
        )
        self._nav2_servers = (
            "planner_server",
            "controller_server",
            "bt_navigator",
        )
        self._lifecycle_clients = {
            name: self.create_client(GetState, "/{}/get_state".format(name))
            for name in self._nav2_servers
        }
        self._lifecycle_futures = {}  # type: Dict[str, object]
        self._active_nav2_servers = set()
        self._next_lifecycle_check_at = 0.0

        self._state = MissionState.WAITING_FOR_NAV2
        self._failure_reason = None  # type: Optional[MissionFailureReason]
        self._detail = "等待 Nav2 lifecycle ACTIVE、TF、odom 与删除服务"
        self._started_at = time.monotonic()
        self._discovery_started_at = None  # type: Optional[float]
        self._last_status_at = 0.0
        self._detection_message_count = 0
        self._valid_position_count = 0
        self._last_detection_stamp = None  # type: Optional[Tuple[int, int]]
        self._last_detection_received_at = None  # type: Optional[float]

        self._targets = {}  # type: Dict[str, TrackedTarget]
        self._initial_target_ids = ()  # type: Tuple[str, ...]
        self._cleaned_ids = []  # type: list
        self._failed_ids = []  # type: list
        self._active_target = None  # type: Optional[TrackedTarget]
        self._active_goal = None  # type: Optional[Pose2D]
        self._active_approach = None
        self._active_target_clearance_m = None  # type: Optional[float]
        self._gate_evidence = None  # type: Optional[CleaningGateEvidence]
        self._removal_transaction = None  # type: Optional[RemovalTransaction]
        self._event_sequence = 0
        self._navigation_goals_sent = 0
        self._cleaning_events = 0
        self._returned_to_dock = False

        self._odom_samples = deque(maxlen=400)  # type: Deque[_OdomSample]
        self._goal_context = None  # type: Optional[str]
        self._goal_send_future = None
        self._goal_result_future = None
        self._goal_handle = None
        self._goal_started_at = None  # type: Optional[float]
        self._last_navigation_status = GoalStatus.STATUS_UNKNOWN
        self._gate_started_at = None  # type: Optional[float]
        self._return_navigation_succeeded = False
        self._return_attempts = 0
        self._delete_future = None
        self._delete_started_at = None  # type: Optional[float]
        self._active_entity_name = ""

        self._steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self._timer = self.create_timer(
            0.05, self._on_tick, clock=self._steady_clock
        )
        self._publish_status()
        self.get_logger().info(
            "垃圾任务控制器启动：detections + TF/odom -> Nav2 -> DeleteEntity"
        )

    def _read_parameters(self) -> None:
        def parameter(name, default):
            self.declare_parameter(name, default)
            return self.get_parameter(name).value

        self._mission_id = str(parameter("mission_id", "trash-mission-001"))
        priorities = parameter("priority_classes", list(TRASH_CLASSES))
        self._priority_classes = tuple(str(item) for item in priorities)
        self._detection_topic = str(
            parameter("detection_topic", "/smartclean/detections")
        )
        self._odom_topic = str(parameter("odom_topic", "/odom"))
        self._delete_service = str(
            parameter(
                "delete_service", "/world/smartclean_trash/remove"
            )
        )
        self._return_after_done = bool(parameter("return_after_done", True))
        self._dock_pose = Pose2D(
            float(parameter("dock_x", 0.0)),
            float(parameter("dock_y", 0.0)),
            float(parameter("dock_yaw", 0.0)),
        )
        self._cleaning_radius_m = float(parameter("cleaning_radius_m", 0.45))
        self._robot_front_extent_m = float(
            parameter("robot_front_extent_m", 0.45)
        )
        self._cleaning_tool_offset_m = float(
            parameter("cleaning_tool_offset_m", 0.45)
        )
        self._target_safety_margin_m = float(
            parameter("target_safety_margin_m", 0.05)
        )
        self._navigation_standoff_margin_m = float(
            parameter("navigation_standoff_margin_m", 0.10)
        )
        if self._navigation_standoff_margin_m < 0.0:
            raise ValueError("navigation_standoff_margin_m 不得小于 0")
        self._association_distance_m = float(
            parameter("association_distance_m", 0.35)
        )
        self._min_confidence = float(parameter("min_confidence", 0.5))
        configured_observations = int(parameter("min_observations", 3))
        self._min_observations = max(3, configured_observations)
        if configured_observations < 3:
            self.get_logger().warn("min_observations 小于 3，已安全提升为 3")
        self._discovery_window_s = float(
            parameter("discovery_window_s", 2.0)
        )
        self._detection_timeout_s = float(
            parameter("detection_timeout_s", 30.0)
        )
        self._mission_timeout_s = float(parameter("mission_timeout_s", 360.0))
        self._navigation_timeout_s = float(
            parameter("navigation_timeout_s", 100.0)
        )
        self._cleaning_gate_timeout_s = float(
            parameter("cleaning_gate_timeout_s", 8.0)
        )
        self._delete_timeout_s = float(parameter("delete_timeout_s", 8.0))
        self._stop_hold_s = float(parameter("stop_hold_s", 0.75))
        self._stop_linear_speed_mps = float(
            parameter("stop_linear_speed_mps", 0.02)
        )
        self._stop_angular_speed_rps = float(
            parameter("stop_angular_speed_rps", 0.03)
        )
        self._stop_displacement_m = float(
            parameter("stop_displacement_m", 0.02)
        )
        self._heading_tolerance_rad = float(
            parameter("heading_tolerance_rad", 0.35)
        )
        self._dock_tolerance_m = float(parameter("dock_tolerance_m", 0.30))
        self._max_return_attempts = max(
            1, int(parameter("max_return_attempts", 3))
        )

    def _on_detections(self, message: TrashDetectionArray) -> None:
        if self._state in (MissionState.COMPLETED, MissionState.FAILED):
            return
        received_at = time.monotonic()
        if not detection_observation_is_new(
            self._last_detection_received_at, received_at
        ):
            return
        self._last_detection_received_at = received_at
        stamp_key = (message.header.stamp.sec, message.header.stamp.nanosec)
        if (
            self._last_detection_stamp is not None
            and stamp_key < self._last_detection_stamp
        ):
            self.get_logger().warn(
                "检测时间戳回拨，按新的仿真纪元继续积累稳定观测",
                throttle_duration_sec=5.0,
            )
        self._last_detection_stamp = stamp_key
        self._detection_message_count += 1
        observations = []
        for item in message.detections:
            if item.class_name not in TARGET_RADIUS_M:
                continue
            position = self._detection_position_in_map(item)
            if position is not None:
                self._valid_position_count += 1
            try:
                observations.append(
                    DetectionObservation(
                        detection_id=item.detection_id,
                        class_name=item.class_name,
                        confidence=float(item.confidence),
                        position=position,
                        position_valid=position is not None,
                        position_frame_id=MAP_FRAME,
                    )
                )
            except MissionCoreError as exc:
                self.get_logger().warn(
                    "忽略非法检测：{}".format(exc),
                    throttle_duration_sec=5.0,
                )
        try:
            self._track_manager.update(observations, received_at)
        except MissionCoreError as exc:
            self.get_logger().warn(
                "忽略无法关联的检测帧：{}".format(exc),
                throttle_duration_sec=5.0,
            )

    def _detection_position_in_map(self, item) -> Optional[Point2D]:
        if not item.position_valid or len(item.position) < 2:
            return None
        x = float(item.position[0])
        y = float(item.position[1])
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        source_frame = item.position_frame_id
        if source_frame == MAP_FRAME:
            return Point2D(x, y)
        if not source_frame:
            return None
        try:
            transform = self._tf_buffer.lookup_transform(
                MAP_FRAME,
                source_frame,
                Time.from_msg(item.image_stamp),
                Duration(seconds=0.0),
            )
        except Exception:
            # AMCL normally timestamps map->odom slightly into the future.
            # The odom-frame point itself is fixed after projection, so the
            # latest common transform is a safe fallback when an exact
            # image-time map transform is not yet representable.
            try:
                transform = self._tf_buffer.lookup_transform(
                    MAP_FRAME,
                    source_frame,
                    Time(),
                    Duration(seconds=0.0),
                )
            except Exception:
                return None
        yaw = _quaternion_yaw(transform.transform.rotation)
        translated_x = (
            math.cos(yaw) * x
            - math.sin(yaw) * y
            + transform.transform.translation.x
        )
        translated_y = (
            math.sin(yaw) * x
            + math.cos(yaw) * y
            + transform.transform.translation.y
        )
        return Point2D(translated_x, translated_y)

    def _on_odom(self, message: Odometry) -> None:
        linear = message.twist.twist.linear
        angular = message.twist.twist.angular
        self._odom_samples.append(
            _OdomSample(
                received_at_s=time.monotonic(),
                x=float(message.pose.pose.position.x),
                y=float(message.pose.pose.position.y),
                linear_speed_mps=math.sqrt(
                    linear.x * linear.x
                    + linear.y * linear.y
                    + linear.z * linear.z
                ),
                angular_speed_rps=math.sqrt(
                    angular.x * angular.x
                    + angular.y * angular.y
                    + angular.z * angular.z
                ),
            )
        )

    def _on_tick(self) -> None:
        now = time.monotonic()
        try:
            if self._state not in (MissionState.COMPLETED, MissionState.FAILED):
                if now - self._started_at > self._mission_timeout_s:
                    self._fail(
                        MissionFailureReason.MISSION_TIMEOUT,
                        "任务超过 {:.1f}s".format(self._mission_timeout_s),
                    )
                elif self._state is MissionState.WAITING_FOR_NAV2:
                    self._tick_waiting_for_nav2(now)
                elif self._state is MissionState.WAITING_FOR_DETECTIONS:
                    self._tick_discovery(now)
                elif self._state is MissionState.SELECTING_TARGET:
                    self._tick_select_target(now)
                elif self._state in (
                    MissionState.NAVIGATING_TO_TARGET,
                    MissionState.RETURNING_TO_DOCK,
                ):
                    self._tick_navigation(now)
                elif self._state is MissionState.VERIFYING_CLEANING_GATE:
                    self._tick_cleaning_gate(now)
                elif self._state is MissionState.CLEANING_TARGET:
                    self._begin_delete(now)
                elif self._state is MissionState.REMOVING_TARGET:
                    self._tick_delete(now)
        except Exception as exc:  # keep the terminal state observable to probes
            self._fail(
                MissionFailureReason.CLEANING_FAILED,
                "控制器内部错误：{}".format(exc),
            )
        if now - self._last_status_at >= 1.0:
            self._publish_status()

    def _tick_waiting_for_nav2(self, now: float) -> None:
        self._poll_lifecycle(now)
        ready = (
            set(self._nav2_servers) == self._active_nav2_servers
            and self._navigate_client.server_is_ready()
            and self._delete_client.service_is_ready()
            and bool(self._odom_samples)
            and self._lookup_base_pose() is not None
        )
        if ready:
            self._discovery_started_at = now
            self._set_state(
                MissionState.WAITING_FOR_DETECTIONS,
                "Nav2 ACTIVE，收集至少 {} 帧一致检测".format(
                    self._min_observations
                ),
            )

    def _poll_lifecycle(self, now: float) -> None:
        for name, future in tuple(self._lifecycle_futures.items()):
            if not future.done():
                continue
            self._lifecycle_futures.pop(name, None)
            try:
                response = future.result()
            except Exception:
                self._active_nav2_servers.discard(name)
                continue
            if response is not None and response.current_state.id == NAV2_ACTIVE_STATE:
                self._active_nav2_servers.add(name)
            else:
                self._active_nav2_servers.discard(name)
        if now < self._next_lifecycle_check_at:
            return
        self._next_lifecycle_check_at = now + 0.5
        for name, client in self._lifecycle_clients.items():
            if name in self._active_nav2_servers or name in self._lifecycle_futures:
                continue
            if client.service_is_ready():
                self._lifecycle_futures[name] = client.call_async(
                    GetState.Request()
                )

    def _tick_discovery(self, now: float) -> None:
        confirmed = tuple(
            track
            for track in self._track_manager.tracks(include_cleaned=False)
            if track.observation_count >= self._min_observations
            and track.confidence >= self._min_confidence
        )
        elapsed = now - (self._discovery_started_at or now)
        if confirmed and elapsed >= self._discovery_window_s:
            class_counts = Counter(track.class_name for track in confirmed)
            ambiguous = sorted(
                name for name, count in class_counts.items() if count > 1
            )
            if ambiguous:
                self._fail(
                    MissionFailureReason.AMBIGUOUS_ENTITY_MAPPING,
                    "同类多目标无法安全映射实体：{}".format(
                        ",".join(ambiguous)
                    ),
                )
                return
            self._targets = {
                track.track_id: track for track in sorted(
                    confirmed, key=lambda candidate: candidate.track_id
                )
            }
            self._initial_target_ids = tuple(self._targets)
            self._set_state(
                MissionState.SELECTING_TARGET,
                "冻结 {} 个多帧确认目标".format(len(self._targets)),
            )
            return
        if elapsed < self._detection_timeout_s:
            return
        if self._detection_message_count == 0:
            reason = MissionFailureReason.NO_DETECTIONS
            detail = "未收到垃圾检测消息"
        elif self._valid_position_count == 0:
            reason = MissionFailureReason.NO_VALID_POSITION
            detail = "检测到垃圾但没有可靠 map 位置"
        else:
            reason = MissionFailureReason.LOW_CONFIDENCE
            tracks = self._track_manager.tracks(include_cleaned=False)
            diagnostics = ", ".join(
                "{}:{} obs={} conf={:.3f} xy=({:.2f},{:.2f})".format(
                    track.track_id,
                    track.class_name,
                    track.observation_count,
                    track.confidence,
                    track.position.x,
                    track.position.y,
                )
                for track in sorted(
                    tracks,
                    key=lambda item: (
                        -item.observation_count,
                        -item.confidence,
                        item.track_id,
                    ),
                )[:12]
            )
            detail = (
                "没有目标通过多帧确认与置信度门限；tracks={} [{}]".format(
                    len(tracks), diagnostics
                )
            )
        self._fail(reason, detail)

    def _tick_select_target(self, now: float) -> None:
        remaining = tuple(
            target
            for track_id, target in sorted(self._targets.items())
            if track_id not in self._cleaned_ids and track_id not in self._failed_ids
        )
        if not remaining:
            if self._return_after_done:
                self._start_return(now)
            else:
                self._set_state(MissionState.COMPLETED, "全部目标已清扫")
            return
        base_pose = self._lookup_base_pose()
        if base_pose is None:
            self._fail(MissionFailureReason.TF_UNAVAILABLE, "map->base_footprint 不可用")
            return
        selection = select_target(
            remaining,
            base_pose.position,
            now,
            self._selection_policy,
        )
        if not selection.found or selection.target is None:
            self._fail(
                selection.failure_reason or MissionFailureReason.NO_DETECTIONS,
                "无法选择剩余目标",
            )
            return
        target = selection.target
        clearance = TARGET_RADIUS_M[target.class_name] + self._target_safety_margin_m
        try:
            approach = compute_front_tool_approach(
                target_position=target.position,
                robot_position=base_pose.position,
                cleaning_radius_m=self._cleaning_radius_m,
                robot_front_extent_m=self._robot_front_extent_m,
                target_clearance_m=(
                    clearance + self._navigation_standoff_margin_m
                ),
                cleaning_tool_offset_m=self._cleaning_tool_offset_m,
            )
        except MissionCoreError as exc:
            self._fail(MissionFailureReason.CLEANING_FAILED, str(exc))
            return
        self._active_target = target
        self._active_approach = approach
        self._active_target_clearance_m = clearance
        self._active_goal = approach.base_pose
        self._start_navigation(approach.base_pose, "target", now)

    def _start_return(self, now: float) -> None:
        self._active_target = None
        self._active_approach = None
        self._active_target_clearance_m = None
        self._return_navigation_succeeded = False
        self._return_attempts = 0
        self._send_return_goal(now)

    def _send_return_goal(self, now: float) -> None:
        dock_goal_map = self._odom_pose_to_map(self._dock_pose)
        if dock_goal_map is None:
            self._fail(
                MissionFailureReason.RETURN_TO_DOCK_FAILED,
                "无法把 odom 物理回桩点变换到 map",
            )
            return
        self._return_attempts += 1
        self._return_navigation_succeeded = False
        self._active_goal = dock_goal_map
        self._start_navigation(dock_goal_map, "dock", now)

    def _start_navigation(self, pose: Pose2D, context: str, now: float) -> None:
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = MAP_FRAME
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = pose.x
        goal.pose.pose.position.y = pose.y
        goal.pose.pose.orientation.z = math.sin(pose.yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(pose.yaw / 2.0)
        self._goal_context = context
        self._goal_started_at = now
        self._goal_send_future = self._navigate_client.send_goal_async(goal)
        self._goal_result_future = None
        self._goal_handle = None
        self._navigation_goals_sent += 1
        if context == "dock":
            self._set_state(MissionState.RETURNING_TO_DOCK, "Nav2 返航")
        else:
            self._set_state(
                MissionState.NAVIGATING_TO_TARGET,
                "Nav2 前往 {}".format(self._active_target.track_id),
            )

    def _tick_navigation(self, now: float) -> None:
        if self._goal_started_at is None:
            self._fail(MissionFailureReason.NAVIGATION_FAILED, "导航上下文缺失")
            return
        if now - self._goal_started_at > self._navigation_timeout_s:
            self._cancel_active_goal()
            reason = (
                MissionFailureReason.RETURN_TO_DOCK_FAILED
                if self._goal_context == "dock"
                else MissionFailureReason.NAVIGATION_TIMEOUT
            )
            self._fail(reason, "NavigateToPose 超时")
            return
        if self._goal_send_future is not None:
            if not self._goal_send_future.done():
                return
            try:
                goal_handle = self._goal_send_future.result()
            except Exception as exc:
                self._fail_navigation("发送目标异常：{}".format(exc))
                return
            self._goal_send_future = None
            if goal_handle is None or not goal_handle.accepted:
                self._fail_navigation("NavigateToPose 拒绝目标", rejected=True)
                return
            self._goal_handle = goal_handle
            self._goal_result_future = goal_handle.get_result_async()
            return
        if self._goal_result_future is None or not self._goal_result_future.done():
            if self._goal_context == "dock" and self._return_navigation_succeeded:
                self._tick_dock_gate(now)
            return
        try:
            response = self._goal_result_future.result()
        except Exception as exc:
            self._fail_navigation("导航结果异常：{}".format(exc))
            return
        self._goal_result_future = None
        self._goal_handle = None
        self._last_navigation_status = int(
            getattr(response, "status", GoalStatus.STATUS_UNKNOWN)
        )
        if not navigation_result_succeeded(response):
            self._fail_navigation(
                "NavigateToPose status={}".format(self._last_navigation_status)
            )
            return
        self._gate_started_at = now
        if self._goal_context == "dock":
            self._return_navigation_succeeded = True
            self._tick_dock_gate(now)
        else:
            self._set_state(
                MissionState.VERIFYING_CLEANING_GATE,
                "Nav2 成功，验证工具距离与连续停车",
            )

    def _fail_navigation(self, detail: str, rejected: bool = False) -> None:
        if self._goal_context == "dock":
            reason = MissionFailureReason.RETURN_TO_DOCK_FAILED
        elif rejected:
            reason = MissionFailureReason.NAVIGATION_REJECTED
        else:
            reason = MissionFailureReason.NAVIGATION_FAILED
        self._fail(reason, detail)

    def _tick_cleaning_gate(self, now: float) -> None:
        if (
            self._active_target is None
            or self._active_approach is None
            or self._active_target_clearance_m is None
        ):
            self._fail(MissionFailureReason.CLEANING_FAILED, "活动目标或接近几何缺失")
            return
        base_pose = self._lookup_base_pose()
        if base_pose is None:
            if now - (self._gate_started_at or now) > self._cleaning_gate_timeout_s:
                self._fail(MissionFailureReason.TF_UNAVAILABLE, "清扫门控期间 TF 不可用")
            return
        stop = self._stop_window(now, self._gate_started_at or now)
        evidence = evaluate_cleaning_gate(
            navigation_status=self._last_navigation_status,
            base_pose=base_pose,
            target_position=self._active_target.position,
            robot_front_extent_m=self._robot_front_extent_m,
            target_clearance_m=self._active_target_clearance_m,
            cleaning_tool_offset_m=self._cleaning_tool_offset_m,
            cleaning_radius_m=self._cleaning_radius_m,
            stop=stop,
            heading_tolerance_rad=self._heading_tolerance_rad,
        )
        if evidence.passed:
            self._gate_evidence = evidence
            self._removal_transaction = RemovalTransaction()
            self._set_state(
                MissionState.CLEANING_TARGET,
                "到达与停车门控通过，准备删除实体",
            )
            return
        if now - (self._gate_started_at or now) > self._cleaning_gate_timeout_s:
            reason = (
                MissionFailureReason.ROBOT_NOT_STOPPED
                if not evidence.stop.passed
                else MissionFailureReason.CLEANING_FAILED
            )
            self._fail(
                reason,
                "清扫门控超时：base={:.3f}m tool={:.3f}m heading={:.3f}rad "
                "stop={}".format(
                    evidence.base_target_distance_m,
                    evidence.cleaning_distance_m,
                    evidence.heading_error_rad,
                    evidence.stop.passed,
                ),
            )

    def _begin_delete(self, now: float) -> None:
        if (
            self._active_target is None
            or self._gate_evidence is None
            or self._removal_transaction is None
        ):
            self._fail(MissionFailureReason.CLEANING_FAILED, "删除上下文缺失")
            return
        if not self._delete_client.service_is_ready():
            self._fail(
                MissionFailureReason.REMOVE_SERVICE_UNAVAILABLE,
                "DeleteEntity 服务不可用",
            )
            return
        if not self._removal_transaction.start(self._gate_evidence):
            self._fail(MissionFailureReason.CLEANING_FAILED, "删除门控未授权或重复")
            return
        entity_name = ENTITY_PREFIX + self._active_target.class_name
        request = DeleteEntity.Request()
        request.entity.id = 0
        request.entity.name = entity_name
        request.entity.type = Entity.MODEL
        self._active_entity_name = entity_name
        self._delete_started_at = now
        self._delete_future = self._delete_client.call_async(request)
        self._set_state(
            MissionState.REMOVING_TARGET,
            "DeleteEntity {} 等待响应".format(entity_name),
        )

    def _tick_delete(self, now: float) -> None:
        if self._delete_future is None or self._delete_started_at is None:
            self._fail(MissionFailureReason.ENTITY_REMOVE_FAILED, "删除 future 缺失")
            return
        if now - self._delete_started_at > self._delete_timeout_s:
            self._fail(MissionFailureReason.ENTITY_REMOVE_FAILED, "DeleteEntity 超时")
            return
        if not self._delete_future.done():
            return
        try:
            response = self._delete_future.result()
        except Exception as exc:
            self._fail(
                MissionFailureReason.ENTITY_REMOVE_FAILED,
                "DeleteEntity 异常：{}".format(exc),
            )
            return
        self._delete_future = None
        committed = commit_delete_response(
            self._removal_transaction,
            response,
            self._commit_active_target,
        )
        if not committed:
            self._fail(
                MissionFailureReason.ENTITY_REMOVE_FAILED,
                "DeleteEntity 返回 success=false",
            )
            return
        self._active_target = None
        self._active_goal = None
        self._active_approach = None
        self._active_target_clearance_m = None
        self._gate_evidence = None
        self._removal_transaction = None
        self._set_state(MissionState.SELECTING_TARGET, "选择下一个目标")

    def _commit_active_target(self) -> None:
        target = self._active_target
        evidence = self._gate_evidence
        if target is None or evidence is None:
            raise RuntimeError("无法提交缺失的活动目标")
        self._track_manager.mark_cleaned(target.track_id)
        if target.track_id not in self._cleaned_ids:
            self._cleaned_ids.append(target.track_id)
        self._cleaning_events += 1
        self._publish_cleaned_event(target, evidence)

    def _publish_cleaned_event(
        self, target: TrackedTarget, evidence: CleaningGateEvidence
    ) -> None:
        self._event_sequence += 1
        message = LitterCleaned()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = MAP_FRAME
        message.schema_version = SCHEMA_VERSION
        message.mission_id = self._mission_id
        message.event_id = "{}-cleaned-{:04d}".format(
            self._mission_id, self._event_sequence
        )
        message.track_id = target.track_id
        message.source_detection_id = target.last_detection_id
        message.class_name = target.class_name
        message.confidence = float(target.confidence)
        message.target_position = [target.position.x, target.position.y, 0.0]
        message.robot_position = [
            evidence.base_pose.x,
            evidence.base_pose.y,
            0.0,
        ]
        message.tool_position = [
            evidence.tool_position.x,
            evidence.tool_position.y,
            0.0,
        ]
        message.base_target_distance_m = float(evidence.base_target_distance_m)
        message.cleaning_distance_m = float(evidence.cleaning_distance_m)
        message.target_clearance_m = float(evidence.target_clearance_m)
        message.navigation_status = int(evidence.navigation_status)
        message.stop_duration_s = float(evidence.stop.duration_s)
        message.linear_speed_mps = float(evidence.stop.max_linear_speed_mps)
        message.angular_speed_rps = float(evidence.stop.max_angular_speed_rps)
        message.actuator = "DeleteEntity"
        message.entity_name = self._active_entity_name
        message.removal_confirmed = True
        self._cleaned_publisher.publish(message)

    def _tick_dock_gate(self, now: float) -> None:
        if not self._return_navigation_succeeded:
            return
        base_pose = self._lookup_base_pose_in_frame(ODOM_FRAME)
        if base_pose is None:
            if now - (self._gate_started_at or now) > self._cleaning_gate_timeout_s:
                self._fail(
                    MissionFailureReason.RETURN_TO_DOCK_FAILED,
                    "返航停车门控期间 TF 不可用",
                )
            return
        stop = self._stop_window(now, self._gate_started_at or now)
        if evaluate_dock_gate(
            navigation_status=self._last_navigation_status,
            base_pose=base_pose,
            dock_pose=self._dock_pose,
            distance_tolerance_m=self._dock_tolerance_m,
            stop=stop,
        ):
            self._returned_to_dock = True
            self._active_goal = None
            self._set_state(
                MissionState.COMPLETED,
                "全部目标已清扫、返航并停车",
            )
            return
        if now - (self._gate_started_at or now) > self._cleaning_gate_timeout_s:
            if self._return_attempts < self._max_return_attempts:
                self.get_logger().warn(
                    "map 导航完成但 odom 物理回桩门控未通过，发送第 {} 次纠偏".format(
                        self._return_attempts + 1
                    )
                )
                self._send_return_goal(now)
            else:
                self._fail(
                    MissionFailureReason.RETURN_TO_DOCK_FAILED,
                    "返航到点但 odom 距离或连续停车门控失败",
                )

    def _stop_window(self, now: float, since: float) -> StopWindowEvidence:
        return evaluate_stop_window(
            tuple(self._odom_samples),
            now_s=now,
            since_s=since,
            hold_s=self._stop_hold_s,
            max_linear_speed_mps=self._stop_linear_speed_mps,
            max_angular_speed_rps=self._stop_angular_speed_rps,
            max_displacement_m=self._stop_displacement_m,
        )

    def _lookup_base_pose(self) -> Optional[Pose2D]:
        return self._lookup_base_pose_in_frame(MAP_FRAME)

    def _lookup_base_pose_in_frame(
        self, target_frame: str
    ) -> Optional[Pose2D]:
        try:
            transform = self._tf_buffer.lookup_transform(
                target_frame,
                BASE_FRAME,
                Time(),
                Duration(seconds=0.0),
            )
        except Exception:
            return None
        return Pose2D(
            transform.transform.translation.x,
            transform.transform.translation.y,
            _quaternion_yaw(transform.transform.rotation),
        )

    def _odom_pose_to_map(self, pose: Pose2D) -> Optional[Pose2D]:
        try:
            transform = self._tf_buffer.lookup_transform(
                MAP_FRAME,
                ODOM_FRAME,
                Time(),
                Duration(seconds=0.0),
            )
        except Exception:
            return None
        transform_yaw = _quaternion_yaw(transform.transform.rotation)
        return Pose2D(
            transform.transform.translation.x
            + math.cos(transform_yaw) * pose.x
            - math.sin(transform_yaw) * pose.y,
            transform.transform.translation.y
            + math.sin(transform_yaw) * pose.x
            + math.cos(transform_yaw) * pose.y,
            _normalize_angle(transform_yaw + pose.yaw),
        )

    def _cancel_active_goal(self) -> None:
        if self._goal_handle is None:
            return
        try:
            self._goal_handle.cancel_goal_async()
        except Exception:
            pass

    def _fail(self, reason: MissionFailureReason, detail: str) -> None:
        if self._state in (MissionState.COMPLETED, MissionState.FAILED):
            return
        self._cancel_active_goal()
        self._failure_reason = reason
        if self._active_target is not None:
            track_id = self._active_target.track_id
            if track_id not in self._failed_ids:
                self._failed_ids.append(track_id)
        self._set_state(MissionState.FAILED, detail)
        self.get_logger().error("任务失败 [{}] {}".format(reason.value, detail))

    def _set_state(self, state: MissionState, detail: str) -> None:
        self._state = state
        self._detail = detail
        self._publish_status()

    def _remaining_ids(self) -> Tuple[str, ...]:
        return tuple(
            track_id
            for track_id in self._initial_target_ids
            if track_id not in self._cleaned_ids
        )

    def _publish_status(self) -> None:
        message = TrashMissionState()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = MAP_FRAME
        message.schema_version = SCHEMA_VERSION
        message.mission_id = self._mission_id
        message.state = self._state.value
        message.failure_code = (
            self._failure_reason.value if self._failure_reason is not None else ""
        )
        message.detail = self._detail
        message.active_target_id = (
            self._active_target.track_id if self._active_target is not None else ""
        )
        message.active_class_name = (
            self._active_target.class_name if self._active_target is not None else ""
        )
        if self._active_target is None:
            message.active_target_position = [0.0, 0.0, 0.0]
        else:
            message.active_target_position = [
                self._active_target.position.x,
                self._active_target.position.y,
                0.0,
            ]
        if self._active_goal is None:
            message.active_goal_pose_xyyaw = [0.0, 0.0, 0.0]
        else:
            message.active_goal_pose_xyyaw = [
                self._active_goal.x,
                self._active_goal.y,
                self._active_goal.yaw,
            ]
        if self._initial_target_ids:
            discovered = self._initial_target_ids
        else:
            discovered = tuple(
                track.track_id
                for track in self._track_manager.tracks()
                if track.observation_count >= self._min_observations
            )
        remaining = self._remaining_ids()
        message.discovered_trash_ids = list(discovered)
        message.cleaned_ids = list(self._cleaned_ids)
        message.remaining_trash_ids = list(remaining)
        message.failed_ids = list(self._failed_ids)
        message.initial_trash_count = len(self._initial_target_ids)
        message.navigation_goals_sent = self._navigation_goals_sent
        message.cleaning_events = self._cleaning_events
        message.progress = (
            float(len(self._cleaned_ids)) / float(len(self._initial_target_ids))
            if self._initial_target_ids
            else 0.0
        )
        message.return_after_done = self._return_after_done
        message.returned_to_dock = self._returned_to_dock
        self._status_publisher.publish(message)
        self._last_status_at = time.monotonic()


def main() -> None:
    rclpy.init()
    node = TrashMissionController()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
