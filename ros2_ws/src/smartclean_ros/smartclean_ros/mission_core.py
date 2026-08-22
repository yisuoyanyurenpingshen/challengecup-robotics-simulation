"""Deterministic, ROS-independent helpers for a trash-cleaning mission.

The module deliberately consumes only detector observations supplied by its
caller.  It does not import ROS, read simulation configuration, or inspect
Gazebo ground truth.  ROS nodes can therefore adapt messages at the boundary
while the association, target choice, and approach geometry remain directly
unit-testable.
"""

from dataclasses import dataclass, replace
from enum import Enum
from math import atan2, cos, hypot, isfinite, pi, sin
from typing import Dict, Iterable, Optional, Sequence, Tuple, Union


class MissionCoreError(ValueError):
    """An observation, policy, timestamp, or geometry value is invalid."""


def _finite_number(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MissionCoreError("{} 必须是有限数值".format(name))
    normalized = float(value)
    if not isfinite(normalized):
        raise MissionCoreError("{} 必须是有限数值".format(name))
    return normalized


def _non_empty_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MissionCoreError("{} 不能为空".format(name))
    return value.strip()


def _normalized_angle(angle: float) -> float:
    return atan2(sin(angle), cos(angle))


@dataclass(frozen=True)
class Point2D:
    """A finite point in the mission tracking frame."""

    x: float
    y: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite_number("x", self.x))
        object.__setattr__(self, "y", _finite_number("y", self.y))

    def distance_to(self, other: "Point2D") -> float:
        if not isinstance(other, Point2D):
            raise TypeError("other 必须是 Point2D")
        return hypot(self.x - other.x, self.y - other.y)


@dataclass(frozen=True)
class Pose2D:
    """A finite planar pose, with yaw normalized to ``[-pi, pi]``."""

    x: float
    y: float
    yaw: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite_number("x", self.x))
        object.__setattr__(self, "y", _finite_number("y", self.y))
        yaw = _finite_number("yaw", self.yaw)
        object.__setattr__(self, "yaw", _normalized_angle(yaw))

    @property
    def position(self) -> Point2D:
        return Point2D(self.x, self.y)


@dataclass(frozen=True)
class DetectionObservation:
    """One detector result adapted into the platform-neutral mission input.

    A message with ``position_valid=False`` may still contain numeric position
    fields (ROS messages commonly use zero-filled fixed arrays); the tracker
    intentionally ignores those fields.  A true validity flag requires both a
    :class:`Point2D` and the configured tracking frame.
    """

    detection_id: str
    class_name: str
    confidence: float
    position: Optional[Point2D] = None
    position_valid: bool = False
    position_frame_id: str = "map"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "detection_id", _non_empty_text("detection_id", self.detection_id)
        )
        object.__setattr__(
            self, "class_name", _non_empty_text("class_name", self.class_name)
        )
        confidence = _finite_number("confidence", self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise MissionCoreError("confidence 必须位于 [0, 1]")
        object.__setattr__(self, "confidence", confidence)
        if not isinstance(self.position_valid, bool):
            raise MissionCoreError("position_valid 必须是布尔值")
        if self.position is not None and not isinstance(self.position, Point2D):
            raise MissionCoreError("position 必须是 Point2D 或 None")
        if self.position_valid and self.position is None:
            raise MissionCoreError("position_valid=true 时必须提供 position")
        if self.position_valid:
            object.__setattr__(
                self,
                "position_frame_id",
                _non_empty_text("position_frame_id", self.position_frame_id),
            )


@dataclass(frozen=True)
class TrackedTarget:
    """Stable spatial track built from one or more same-class observations."""

    track_id: str
    class_name: str
    position: Point2D
    confidence: float
    first_seen_s: float
    last_seen_s: float
    observation_count: int = 1
    last_detection_id: str = ""
    cleaned: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "track_id", _non_empty_text("track_id", self.track_id))
        object.__setattr__(
            self, "class_name", _non_empty_text("class_name", self.class_name)
        )
        if not isinstance(self.position, Point2D):
            raise MissionCoreError("position 必须是 Point2D")
        confidence = _finite_number("confidence", self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise MissionCoreError("confidence 必须位于 [0, 1]")
        object.__setattr__(self, "confidence", confidence)
        first_seen = _finite_number("first_seen_s", self.first_seen_s)
        last_seen = _finite_number("last_seen_s", self.last_seen_s)
        if last_seen < first_seen:
            raise MissionCoreError("last_seen_s 不得早于 first_seen_s")
        object.__setattr__(self, "first_seen_s", first_seen)
        object.__setattr__(self, "last_seen_s", last_seen)
        if (
            isinstance(self.observation_count, bool)
            or not isinstance(self.observation_count, int)
            or self.observation_count <= 0
        ):
            raise MissionCoreError("observation_count 必须是正整数")
        if not isinstance(self.last_detection_id, str):
            raise MissionCoreError("last_detection_id 必须是字符串")
        if not isinstance(self.cleaned, bool):
            raise MissionCoreError("cleaned 必须是布尔值")


@dataclass(frozen=True)
class TrackingUpdate:
    """Immutable result and rejection diagnostics for one detector frame."""

    observed_at_s: float
    tracks: Tuple[TrackedTarget, ...]
    received_count: int
    accepted_count: int
    rejected_position_count: int
    created_track_ids: Tuple[str, ...] = ()
    matched_track_ids: Tuple[str, ...] = ()
    pruned_track_ids: Tuple[str, ...] = ()

    @property
    def active_tracks(self) -> Tuple[TrackedTarget, ...]:
        return tuple(track for track in self.tracks if not track.cleaned)

    @property
    def cleaned_tracks(self) -> Tuple[TrackedTarget, ...]:
        return tuple(track for track in self.tracks if track.cleaned)


class SpatialTrackManager:
    """Associate detections to deterministic, persistent spatial tracks.

    Association is one-to-one within a frame.  Candidate edges are considered
    globally from shortest to longest, and deterministic IDs break exact ties.
    Only tracks of the same class and within ``association_distance_m`` can be
    matched.  Positions and confidence use a running mean because litter is
    static while depth estimates can jitter.

    Cleaned tracks are retained as tombstones: repeated detector frames near a
    just-cleaned location keep matching the same excluded track instead of
    creating a new target before the simulator removes the visual entity.
    """

    def __init__(
        self,
        association_distance_m: float = 0.35,
        max_track_age_s: float = 2.0,
        frame_id: str = "map",
        track_id_prefix: str = "track",
    ) -> None:
        association_distance = _finite_number(
            "association_distance_m", association_distance_m
        )
        max_track_age = _finite_number("max_track_age_s", max_track_age_s)
        if association_distance <= 0.0:
            raise MissionCoreError("association_distance_m 必须大于 0")
        if max_track_age <= 0.0:
            raise MissionCoreError("max_track_age_s 必须大于 0")
        self._association_distance_m = association_distance
        self._max_track_age_s = max_track_age
        self._frame_id = _non_empty_text("frame_id", frame_id)
        self._track_id_prefix = _non_empty_text(
            "track_id_prefix", track_id_prefix
        )
        self._tracks = {}  # type: Dict[str, TrackedTarget]
        self._next_track_number = 1
        self._last_update_s = None  # type: Optional[float]

    @property
    def association_distance_m(self) -> float:
        return self._association_distance_m

    @property
    def max_track_age_s(self) -> float:
        return self._max_track_age_s

    @property
    def frame_id(self) -> str:
        return self._frame_id

    def tracks(self, include_cleaned: bool = True) -> Tuple[TrackedTarget, ...]:
        """Return tracks sorted by deterministic ID."""

        if not isinstance(include_cleaned, bool):
            raise MissionCoreError("include_cleaned 必须是布尔值")
        return tuple(
            track
            for track_id, track in sorted(self._tracks.items())
            if include_cleaned or not track.cleaned
        )

    def get_track(self, track_id: str) -> TrackedTarget:
        normalized = _non_empty_text("track_id", track_id)
        try:
            return self._tracks[normalized]
        except KeyError as exc:
            raise MissionCoreError("未知 track_id: {}".format(normalized)) from exc

    def mark_cleaned(self, track_id: str) -> TrackedTarget:
        """Exclude a track permanently while retaining its spatial tombstone."""

        track = self.get_track(track_id)
        if not track.cleaned:
            track = replace(track, cleaned=True)
            self._tracks[track.track_id] = track
        return track

    def update(
        self,
        observations: Iterable[DetectionObservation],
        observed_at_s: float,
    ) -> TrackingUpdate:
        """Associate one detector frame and return its immutable snapshot."""

        observed_at = _finite_number("observed_at_s", observed_at_s)
        if self._last_update_s is not None and observed_at < self._last_update_s:
            raise MissionCoreError("observed_at_s 不得倒退")

        try:
            received = tuple(observations)
        except TypeError as exc:
            raise MissionCoreError("observations 必须可迭代") from exc
        for observation in received:
            if not isinstance(observation, DetectionObservation):
                raise MissionCoreError(
                    "observations 仅能包含 DetectionObservation"
                )
        detection_ids = [observation.detection_id for observation in received]
        if len(set(detection_ids)) != len(detection_ids):
            raise MissionCoreError("同一帧 detection_id 不得重复")

        pruned_track_ids = []
        for track_id, track in tuple(self._tracks.items()):
            if (
                not track.cleaned
                and observed_at - track.last_seen_s > self._max_track_age_s
            ):
                del self._tracks[track_id]
                pruned_track_ids.append(track_id)

        usable = [
            observation
            for observation in received
            if observation.position_valid
            and observation.position is not None
            and observation.position_frame_id == self._frame_id
        ]
        usable.sort(key=self._observation_sort_key)
        rejected_position_count = len(received) - len(usable)

        # Each tuple contains the squared distance, stable track ID, sorted
        # observation index, and the objects themselves.  Squared distance is
        # sufficient for ordering and avoids unnecessary square roots.
        candidate_edges = []
        gate_squared = self._association_distance_m ** 2
        for track_id, track in sorted(self._tracks.items()):
            for observation_index, observation in enumerate(usable):
                if observation.class_name != track.class_name:
                    continue
                assert observation.position is not None
                dx = observation.position.x - track.position.x
                dy = observation.position.y - track.position.y
                distance_squared = dx * dx + dy * dy
                if distance_squared <= gate_squared:
                    candidate_edges.append(
                        (
                            distance_squared,
                            track_id,
                            observation_index,
                            track,
                            observation,
                        )
                    )
        candidate_edges.sort(key=lambda edge: (edge[0], edge[1], edge[2]))

        assigned_tracks = set()
        assigned_observations = set()
        matched_track_ids = []
        for _, track_id, observation_index, track, observation in candidate_edges:
            if (
                track_id in assigned_tracks
                or observation_index in assigned_observations
            ):
                continue
            updated = self._merge(track, observation, observed_at)
            self._tracks[track_id] = updated
            assigned_tracks.add(track_id)
            assigned_observations.add(observation_index)
            matched_track_ids.append(track_id)

        created_track_ids = []
        for observation_index, observation in enumerate(usable):
            if observation_index in assigned_observations:
                continue
            track_id = "{}-{:06d}".format(
                self._track_id_prefix, self._next_track_number
            )
            self._next_track_number += 1
            assert observation.position is not None
            self._tracks[track_id] = TrackedTarget(
                track_id=track_id,
                class_name=observation.class_name,
                position=observation.position,
                confidence=observation.confidence,
                first_seen_s=observed_at,
                last_seen_s=observed_at,
                observation_count=1,
                last_detection_id=observation.detection_id,
            )
            created_track_ids.append(track_id)

        self._last_update_s = observed_at
        return TrackingUpdate(
            observed_at_s=observed_at,
            tracks=self.tracks(),
            received_count=len(received),
            accepted_count=len(usable),
            rejected_position_count=rejected_position_count,
            created_track_ids=tuple(created_track_ids),
            matched_track_ids=tuple(matched_track_ids),
            pruned_track_ids=tuple(sorted(pruned_track_ids)),
        )

    @staticmethod
    def _observation_sort_key(observation: DetectionObservation) -> tuple:
        assert observation.position is not None
        return (
            observation.class_name,
            observation.position.x,
            observation.position.y,
            observation.detection_id,
        )

    @staticmethod
    def _merge(
        track: TrackedTarget,
        observation: DetectionObservation,
        observed_at_s: float,
    ) -> TrackedTarget:
        assert observation.position is not None
        old_count = track.observation_count
        new_count = old_count + 1
        position = Point2D(
            (track.position.x * old_count + observation.position.x) / new_count,
            (track.position.y * old_count + observation.position.y) / new_count,
        )
        confidence = (
            track.confidence * old_count + observation.confidence
        ) / new_count
        return replace(
            track,
            position=position,
            confidence=confidence,
            last_seen_s=observed_at_s,
            observation_count=new_count,
            last_detection_id=observation.detection_id,
        )


class MissionState(str, Enum):
    """Externally reportable mission lifecycle states."""

    IDLE = "IDLE"
    WAITING_FOR_NAV2 = "WAITING_FOR_NAV2"
    WAITING_FOR_DETECTIONS = "WAITING_FOR_DETECTIONS"
    SELECTING_TARGET = "SELECTING_TARGET"
    NAVIGATING_TO_TARGET = "NAVIGATING_TO_TARGET"
    VERIFYING_CLEANING_GATE = "VERIFYING_CLEANING_GATE"
    CLEANING_TARGET = "CLEANING_TARGET"
    REMOVING_TARGET = "REMOVING_TARGET"
    RETURNING_TO_DOCK = "RETURNING_TO_DOCK"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MissionFailureReason(str, Enum):
    """Stable machine-readable reasons for selection or terminal failure."""

    NO_DETECTIONS = "NO_DETECTIONS"
    NO_VALID_POSITION = "NO_VALID_POSITION"
    STALE_DETECTIONS = "STALE_DETECTIONS"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    ALL_TARGETS_CLEANED = "ALL_TARGETS_CLEANED"
    TF_UNAVAILABLE = "TF_UNAVAILABLE"
    NAVIGATION_REJECTED = "NAVIGATION_REJECTED"
    NAVIGATION_FAILED = "NAVIGATION_FAILED"
    NAVIGATION_TIMEOUT = "NAVIGATION_TIMEOUT"
    ROBOT_NOT_STOPPED = "ROBOT_NOT_STOPPED"
    REMOVE_SERVICE_UNAVAILABLE = "REMOVE_SERVICE_UNAVAILABLE"
    ENTITY_REMOVE_FAILED = "ENTITY_REMOVE_FAILED"
    AMBIGUOUS_ENTITY_MAPPING = "AMBIGUOUS_ENTITY_MAPPING"
    CLEANING_FAILED = "CLEANING_FAILED"
    RETURN_TO_DOCK_FAILED = "RETURN_TO_DOCK_FAILED"
    MISSION_TIMEOUT = "MISSION_TIMEOUT"


@dataclass(frozen=True)
class MissionStatus:
    """Small validated status payload for a future ROS mission controller."""

    state: MissionState
    active_track_id: Optional[str] = None
    cleaned_track_ids: Tuple[str, ...] = ()
    remaining_track_ids: Tuple[str, ...] = ()
    failure_reason: Optional[MissionFailureReason] = None
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.state, MissionState):
            raise MissionCoreError("state 必须是 MissionState")
        if self.active_track_id is not None:
            object.__setattr__(
                self,
                "active_track_id",
                _non_empty_text("active_track_id", self.active_track_id),
            )
        cleaned = self._validated_ids("cleaned_track_ids", self.cleaned_track_ids)
        remaining = self._validated_ids(
            "remaining_track_ids", self.remaining_track_ids
        )
        object.__setattr__(self, "cleaned_track_ids", cleaned)
        object.__setattr__(self, "remaining_track_ids", remaining)
        if set(cleaned).intersection(remaining):
            raise MissionCoreError("已清扫与剩余 track_id 不得重叠")
        if self.state is MissionState.FAILED:
            if not isinstance(self.failure_reason, MissionFailureReason):
                raise MissionCoreError("FAILED 状态必须提供 failure_reason")
        elif self.failure_reason is not None:
            raise MissionCoreError("非 FAILED 状态不得提供 failure_reason")
        if self.state is MissionState.COMPLETED and (
            self.active_track_id is not None or remaining
        ):
            raise MissionCoreError("COMPLETED 状态不得保留活动或剩余目标")
        if not isinstance(self.detail, str):
            raise MissionCoreError("detail 必须是字符串")

    @staticmethod
    def _validated_ids(name: str, values: Sequence[str]) -> Tuple[str, ...]:
        if isinstance(values, str):
            raise MissionCoreError("{} 必须是 track_id 序列".format(name))
        normalized = tuple(_non_empty_text(name, value) for value in values)
        if len(normalized) != len(set(normalized)):
            raise MissionCoreError("{} 不得包含重复项".format(name))
        return normalized

    @classmethod
    def failed(
        cls,
        reason: MissionFailureReason,
        detail: str = "",
        active_track_id: Optional[str] = None,
        cleaned_track_ids: Sequence[str] = (),
        remaining_track_ids: Sequence[str] = (),
    ) -> "MissionStatus":
        """Construct a terminal failure without repeating the state value."""

        return cls(
            state=MissionState.FAILED,
            active_track_id=active_track_id,
            cleaned_track_ids=tuple(cleaned_track_ids),
            remaining_track_ids=tuple(remaining_track_ids),
            failure_reason=reason,
            detail=detail,
        )


@dataclass(frozen=True)
class TargetSelectionPolicy:
    """Eligibility and deterministic ordering knobs for target selection."""

    priority_classes: Tuple[str, ...] = ()
    min_confidence: float = 0.5
    max_track_age_s: float = 1.0

    def __post_init__(self) -> None:
        if isinstance(self.priority_classes, str):
            raise MissionCoreError("priority_classes 必须是类别序列")
        priorities = tuple(
            _non_empty_text("priority_classes", class_name)
            for class_name in self.priority_classes
        )
        if len(priorities) != len(set(priorities)):
            raise MissionCoreError("priority_classes 不得重复")
        object.__setattr__(self, "priority_classes", priorities)
        confidence = _finite_number("min_confidence", self.min_confidence)
        if not 0.0 <= confidence <= 1.0:
            raise MissionCoreError("min_confidence 必须位于 [0, 1]")
        object.__setattr__(self, "min_confidence", confidence)
        max_age = _finite_number("max_track_age_s", self.max_track_age_s)
        if max_age <= 0.0:
            raise MissionCoreError("max_track_age_s 必须大于 0")
        object.__setattr__(self, "max_track_age_s", max_age)


@dataclass(frozen=True)
class TargetSelection:
    """Selected target, or one explicit reason why no target is eligible."""

    target: Optional[TrackedTarget]
    failure_reason: Optional[MissionFailureReason]
    distance_m: Optional[float] = None
    ranked_track_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.target is None:
            if not isinstance(self.failure_reason, MissionFailureReason):
                raise MissionCoreError("未选中目标时必须提供 failure_reason")
            if self.distance_m is not None:
                raise MissionCoreError("未选中目标时 distance_m 必须为 None")
        else:
            if not isinstance(self.target, TrackedTarget):
                raise MissionCoreError("target 必须是 TrackedTarget 或 None")
            if self.failure_reason is not None:
                raise MissionCoreError("选中目标时 failure_reason 必须为 None")
            distance = _finite_number("distance_m", self.distance_m)
            if distance < 0.0:
                raise MissionCoreError("distance_m 不得小于 0")
            object.__setattr__(self, "distance_m", distance)

    @property
    def found(self) -> bool:
        return self.target is not None


@dataclass(frozen=True)
class CleaningToolApproach:
    """Safe front-tool approach pose plus auditable cleaning geometry.

    ``target_clearance_m`` is the complete clearance required between the
    vehicle's front edge and the target center.  It should therefore include
    the target radius and any additional safety margin chosen by the caller.
    """

    base_pose: Pose2D
    tool_position: Point2D
    base_standoff_m: float
    tool_target_distance_m: float
    robot_front_extent_m: float
    target_clearance_m: float
    cleaning_tool_offset_m: float
    cleaning_radius_m: float

    def __post_init__(self) -> None:
        if not isinstance(self.base_pose, Pose2D):
            raise MissionCoreError("base_pose 必须是 Pose2D")
        if not isinstance(self.tool_position, Point2D):
            raise MissionCoreError("tool_position 必须是 Point2D")
        for name in (
            "base_standoff_m",
            "tool_target_distance_m",
            "robot_front_extent_m",
            "target_clearance_m",
            "cleaning_tool_offset_m",
            "cleaning_radius_m",
        ):
            value = _finite_number(name, getattr(self, name))
            object.__setattr__(self, name, value)
        if self.base_standoff_m <= 0.0:
            raise MissionCoreError("base_standoff_m 必须大于 0")
        if self.tool_target_distance_m < 0.0:
            raise MissionCoreError("tool_target_distance_m 不得小于 0")
        if self.robot_front_extent_m <= 0.0:
            raise MissionCoreError("robot_front_extent_m 必须大于 0")
        if self.target_clearance_m <= 0.0:
            raise MissionCoreError("target_clearance_m 必须大于 0")
        if self.cleaning_tool_offset_m <= 0.0:
            raise MissionCoreError("cleaning_tool_offset_m 必须大于 0")
        if self.cleaning_radius_m <= 0.0:
            raise MissionCoreError("cleaning_radius_m 必须大于 0")
        expected_standoff = self.robot_front_extent_m + self.target_clearance_m
        if abs(self.base_standoff_m - expected_standoff) > 1e-9:
            raise MissionCoreError(
                "base_standoff_m 必须等于车头前悬与目标净空之和"
            )
        if self.tool_target_distance_m > self.cleaning_radius_m + 1e-9:
            raise MissionCoreError("清扫工具点不在 cleaning_radius_m 内")

    @property
    def within_cleaning_radius(self) -> bool:
        return self.tool_target_distance_m <= self.cleaning_radius_m


TrackSource = Union[Sequence[TrackedTarget], TrackingUpdate]


def select_target(
    source: TrackSource,
    robot_position: Point2D,
    now_s: float,
    policy: Optional[TargetSelectionPolicy] = None,
) -> TargetSelection:
    """Select by class priority, confidence, distance, then stable track ID.

    Classes omitted from ``priority_classes`` remain eligible and share the
    lowest priority.  Passing :class:`TrackingUpdate` preserves enough frame
    diagnostics to distinguish no detections from detections without a usable
    map position.
    """

    if not isinstance(robot_position, Point2D):
        raise MissionCoreError("robot_position 必须是 Point2D")
    now = _finite_number("now_s", now_s)
    selection_policy = policy or TargetSelectionPolicy()
    if not isinstance(selection_policy, TargetSelectionPolicy):
        raise MissionCoreError("policy 必须是 TargetSelectionPolicy")

    update = source if isinstance(source, TrackingUpdate) else None
    tracks = update.tracks if update is not None else tuple(source)
    for track in tracks:
        if not isinstance(track, TrackedTarget):
            raise MissionCoreError("source 仅能包含 TrackedTarget")

    active = tuple(track for track in tracks if not track.cleaned)
    if not active:
        if tracks and all(track.cleaned for track in tracks):
            reason = MissionFailureReason.ALL_TARGETS_CLEANED
        elif update is not None and update.received_count > 0:
            reason = MissionFailureReason.NO_VALID_POSITION
        elif update is not None and update.pruned_track_ids:
            reason = MissionFailureReason.STALE_DETECTIONS
        else:
            reason = MissionFailureReason.NO_DETECTIONS
        return TargetSelection(target=None, failure_reason=reason)

    fresh = []
    for track in active:
        age_s = now - track.last_seen_s
        if age_s < 0.0:
            raise MissionCoreError("now_s 不得早于 track.last_seen_s")
        if age_s <= selection_policy.max_track_age_s:
            fresh.append(track)
    if not fresh:
        return TargetSelection(
            target=None,
            failure_reason=MissionFailureReason.STALE_DETECTIONS,
        )

    confident = [
        track
        for track in fresh
        if track.confidence >= selection_policy.min_confidence
    ]
    if not confident:
        return TargetSelection(
            target=None,
            failure_reason=MissionFailureReason.LOW_CONFIDENCE,
        )

    priority_rank = {
        class_name: index
        for index, class_name in enumerate(selection_policy.priority_classes)
    }
    fallback_rank = len(priority_rank)
    ranked = sorted(
        confident,
        key=lambda track: (
            priority_rank.get(track.class_name, fallback_rank),
            -track.confidence,
            track.position.distance_to(robot_position),
            track.track_id,
        ),
    )
    selected = ranked[0]
    return TargetSelection(
        target=selected,
        failure_reason=None,
        distance_m=selected.position.distance_to(robot_position),
        ranked_track_ids=tuple(track.track_id for track in ranked),
    )


def compute_front_tool_approach(
    target_position: Point2D,
    robot_position: Point2D,
    cleaning_radius_m: float,
    robot_front_extent_m: float,
    target_clearance_m: float,
    cleaning_tool_offset_m: float,
) -> CleaningToolApproach:
    """Compute a collision-aware approach for a front-mounted cleaning tool.

    The base stops ``robot_front_extent_m + target_clearance_m`` from the
    target and faces it.  This keeps the body behind the requested clearance,
    while cleaning eligibility is evaluated at the front tool point rather
    than incorrectly at ``base_link``.  An impossible combination whose tool
    cannot reach ``cleaning_radius_m`` is rejected instead of producing a pose
    that could later be reported as cleaned.
    """

    if not isinstance(target_position, Point2D):
        raise MissionCoreError("target_position 必须是 Point2D")
    if not isinstance(robot_position, Point2D):
        raise MissionCoreError("robot_position 必须是 Point2D")
    cleaning_radius = _finite_number("cleaning_radius_m", cleaning_radius_m)
    front_extent = _finite_number(
        "robot_front_extent_m", robot_front_extent_m
    )
    target_clearance = _finite_number(
        "target_clearance_m", target_clearance_m
    )
    tool_offset = _finite_number(
        "cleaning_tool_offset_m", cleaning_tool_offset_m
    )
    if cleaning_radius <= 0.0:
        raise MissionCoreError("cleaning_radius_m 必须大于 0")
    if front_extent <= 0.0:
        raise MissionCoreError("robot_front_extent_m 必须大于 0")
    if target_clearance <= 0.0:
        raise MissionCoreError("target_clearance_m 必须大于 0")
    if tool_offset <= 0.0:
        raise MissionCoreError("cleaning_tool_offset_m 必须大于 0")

    # Pick the point on the target-to-robot ray so the nominal approach path
    # reaches the near side and never continues through the target center.
    away_x = robot_position.x - target_position.x
    away_y = robot_position.y - target_position.y
    away_length = hypot(away_x, away_y)
    if away_length == 0.0:
        away_x, away_y = 1.0, 0.0
    else:
        away_x /= away_length
        away_y /= away_length

    base_standoff = front_extent + target_clearance
    base_x = target_position.x + away_x * base_standoff
    base_y = target_position.y + away_y * base_standoff
    yaw = atan2(target_position.y - base_y, target_position.x - base_x)
    base_pose = Pose2D(base_x, base_y, yaw)
    tool_position = Point2D(
        base_x + cos(base_pose.yaw) * tool_offset,
        base_y + sin(base_pose.yaw) * tool_offset,
    )
    tool_target_distance = tool_position.distance_to(target_position)
    if tool_target_distance > cleaning_radius + 1e-9:
        raise MissionCoreError(
            "当前车体/工具几何无法在保持净空时覆盖目标"
        )
    return CleaningToolApproach(
        base_pose=base_pose,
        tool_position=tool_position,
        base_standoff_m=base_standoff,
        tool_target_distance_m=tool_target_distance,
        robot_front_extent_m=front_extent,
        target_clearance_m=target_clearance,
        cleaning_tool_offset_m=tool_offset,
        cleaning_radius_m=cleaning_radius,
    )


def compute_lateral_approach_pose(
    target_position: Point2D,
    robot_position: Point2D,
    cleaning_radius_m: float,
    approach_distance_m: Optional[float] = None,
    target_on_left: bool = True,
) -> Pose2D:
    """Place the base beside litter and orient the vehicle tangentially.

    The approach point lies on the target-to-robot ray, so a straight initial
    approach does not cross the litter.  Its non-zero standoff is at most the
    cleaning radius.  Final yaw is tangent to the standoff circle; by default
    the litter is on the vehicle's left side.  If robot and target coincide, a
    deterministic positive-x radial direction is used to move the base away.

    This geometric helper implements a lateral-tool contract in which
    ``base_link`` itself must be within the cleaning radius.  Callers with a
    wide physical chassis should use :func:`compute_front_tool_approach`,
    which checks body clearance and the actual cleaning-tool point separately.
    """

    if not isinstance(target_position, Point2D):
        raise MissionCoreError("target_position 必须是 Point2D")
    if not isinstance(robot_position, Point2D):
        raise MissionCoreError("robot_position 必须是 Point2D")
    cleaning_radius = _finite_number("cleaning_radius_m", cleaning_radius_m)
    if cleaning_radius <= 0.0:
        raise MissionCoreError("cleaning_radius_m 必须大于 0")
    if approach_distance_m is None:
        approach_distance = cleaning_radius * 0.8
    else:
        approach_distance = _finite_number(
            "approach_distance_m", approach_distance_m
        )
    if not 0.0 < approach_distance <= cleaning_radius:
        raise MissionCoreError(
            "approach_distance_m 必须位于 (0, cleaning_radius_m]"
        )
    if not isinstance(target_on_left, bool):
        raise MissionCoreError("target_on_left 必须是布尔值")

    radial_x = robot_position.x - target_position.x
    radial_y = robot_position.y - target_position.y
    radial_length = hypot(radial_x, radial_y)
    if radial_length == 0.0:
        radial_x, radial_y = 1.0, 0.0
    else:
        radial_x /= radial_length
        radial_y /= radial_length

    approach_x = target_position.x + radial_x * approach_distance
    approach_y = target_position.y + radial_y * approach_distance
    radial_yaw = atan2(radial_y, radial_x)
    yaw = radial_yaw + (pi / 2.0 if target_on_left else -pi / 2.0)
    return Pose2D(approach_x, approach_y, yaw)
