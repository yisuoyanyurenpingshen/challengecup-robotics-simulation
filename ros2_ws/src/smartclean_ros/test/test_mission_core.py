from math import cos, inf, nan, sin

import pytest

from smartclean_ros.mission_core import CleaningToolApproach, DetectionObservation
from smartclean_ros.mission_core import MissionCoreError, MissionFailureReason
from smartclean_ros.mission_core import MissionState, MissionStatus
from smartclean_ros.mission_core import Point2D, SpatialTrackManager
from smartclean_ros.mission_core import TargetSelectionPolicy, TrackedTarget
from smartclean_ros.mission_core import compute_front_tool_approach
from smartclean_ros.mission_core import compute_lateral_approach_pose, select_target


def positioned(
    detection_id: str,
    class_name: str,
    confidence: float,
    x: float,
    y: float,
) -> DetectionObservation:
    return DetectionObservation(
        detection_id=detection_id,
        class_name=class_name,
        confidence=confidence,
        position=Point2D(x, y),
        position_valid=True,
        position_frame_id="map",
    )


def track(
    track_id: str,
    class_name: str,
    confidence: float,
    x: float,
    y: float,
    last_seen_s: float = 10.0,
    cleaned: bool = False,
) -> TrackedTarget:
    return TrackedTarget(
        track_id=track_id,
        class_name=class_name,
        position=Point2D(x, y),
        confidence=confidence,
        first_seen_s=min(0.0, last_seen_s),
        last_seen_s=last_seen_s,
        cleaned=cleaned,
    )


def test_normal_detection_builds_a_track_and_selects_it() -> None:
    manager = SpatialTrackManager()
    update = manager.update(
        [positioned("det-1", "plastic_bottle", 0.91, 2.0, 0.2)],
        observed_at_s=3.0,
    )

    assert update.received_count == update.accepted_count == 1
    assert update.created_track_ids == ("track-000001",)
    assert update.tracks[0].class_name == "plastic_bottle"

    selection = select_target(
        update,
        robot_position=Point2D(0.0, 0.0),
        now_s=3.1,
        policy=TargetSelectionPolicy(min_confidence=0.8),
    )
    assert selection.found is True
    assert selection.target == update.tracks[0]
    assert selection.distance_m == pytest.approx((2.0 ** 2 + 0.2 ** 2) ** 0.5)


def test_repeated_frames_keep_track_id_and_average_position() -> None:
    manager = SpatialTrackManager(association_distance_m=0.4)
    first = manager.update(
        [positioned("frame-1", "paper_cup", 0.8, 2.0, 1.0)], 1.0
    )
    second = manager.update(
        [positioned("frame-2", "paper_cup", 1.0, 2.2, 0.8)], 1.1
    )

    assert first.created_track_ids == ("track-000001",)
    assert second.created_track_ids == ()
    assert second.matched_track_ids == ("track-000001",)
    tracked = second.tracks[0]
    assert tracked.track_id == first.tracks[0].track_id
    assert tracked.position == Point2D(2.1, 0.9)
    assert tracked.confidence == pytest.approx(0.9)
    assert tracked.observation_count == 2
    assert tracked.last_detection_id == "frame-2"


def test_initial_track_ids_do_not_depend_on_detection_input_order() -> None:
    observations = [
        positioned("right", "plastic_bottle", 0.9, 4.0, 0.0),
        positioned("left", "plastic_bottle", 0.9, 2.0, 0.0),
        positioned("can", "aluminum_can", 0.9, 3.0, 0.0),
    ]
    forward = SpatialTrackManager().update(observations, 0.0)
    reverse = SpatialTrackManager().update(reversed(observations), 0.0)

    forward_identity = [
        (item.track_id, item.class_name, item.position) for item in forward.tracks
    ]
    reverse_identity = [
        (item.track_id, item.class_name, item.position) for item in reverse.tracks
    ]
    assert forward_identity == reverse_identity


def test_same_class_multiple_targets_use_one_to_one_nearest_association() -> None:
    manager = SpatialTrackManager(association_distance_m=1.0)
    first = manager.update(
        [
            positioned("left-1", "paper_scrap", 0.8, 1.0, 0.0),
            positioned("right-1", "paper_scrap", 0.8, 3.0, 0.0),
        ],
        0.0,
    )
    left_id, right_id = (item.track_id for item in first.tracks)

    second = manager.update(
        [
            positioned("right-2", "paper_scrap", 0.9, 2.9, 0.0),
            positioned("left-2", "paper_scrap", 0.7, 1.1, 0.0),
        ],
        0.1,
    )

    assert second.created_track_ids == ()
    assert set(second.matched_track_ids) == {left_id, right_id}
    assert manager.get_track(left_id).position.x == pytest.approx(1.05)
    assert manager.get_track(right_id).position.x == pytest.approx(2.95)
    assert manager.get_track(left_id).last_detection_id == "left-2"
    assert manager.get_track(right_id).last_detection_id == "right-2"


def test_association_never_crosses_class_boundary() -> None:
    manager = SpatialTrackManager(association_distance_m=0.5)
    first = manager.update(
        [positioned("bottle", "plastic_bottle", 0.8, 1.0, 1.0)], 0.0
    )
    second = manager.update(
        [positioned("can", "aluminum_can", 0.8, 1.0, 1.0)], 0.1
    )

    assert first.created_track_ids == ("track-000001",)
    assert second.created_track_ids == ("track-000002",)
    assert second.matched_track_ids == ()


def test_same_class_detection_outside_position_gate_creates_new_track() -> None:
    manager = SpatialTrackManager(association_distance_m=0.25)
    manager.update(
        [positioned("first", "paper_cup", 0.8, 1.0, 1.0)], 0.0
    )

    update = manager.update(
        [positioned("far", "paper_cup", 0.8, 1.26, 1.0)], 0.1
    )

    assert update.matched_track_ids == ()
    assert update.created_track_ids == ("track-000002",)
    assert len(update.tracks) == 2


def test_cleaned_track_is_excluded_and_absorbs_duplicate_frames() -> None:
    manager = SpatialTrackManager(association_distance_m=0.4)
    first = manager.update(
        [
            positioned("a", "plastic_bottle", 0.95, 2.0, 0.0),
            positioned("b", "plastic_bottle", 0.80, 4.0, 0.0),
        ],
        1.0,
    )
    cleaned_id = next(
        item.track_id for item in first.tracks if item.position.x == 2.0
    )
    remaining_id = next(
        item.track_id for item in first.tracks if item.position.x == 4.0
    )
    manager.mark_cleaned(cleaned_id)

    duplicate = manager.update(
        [positioned("a-again", "plastic_bottle", 0.99, 2.05, 0.0)], 1.1
    )
    assert duplicate.created_track_ids == ()
    assert duplicate.matched_track_ids == (cleaned_id,)
    assert manager.get_track(cleaned_id).cleaned is True

    selection = select_target(
        manager.tracks(), Point2D(0.0, 0.0), now_s=1.1
    )
    assert selection.target is not None
    assert selection.target.track_id == remaining_id


def test_all_cleaned_targets_report_explicit_reason() -> None:
    manager = SpatialTrackManager()
    update = manager.update(
        [positioned("a", "fallen_leaves", 0.9, 1.0, 0.0)], 2.0
    )
    manager.mark_cleaned(update.tracks[0].track_id)

    selection = select_target(manager.tracks(), Point2D(0.0, 0.0), 2.0)
    assert selection.found is False
    assert selection.failure_reason is MissionFailureReason.ALL_TARGETS_CLEANED


def test_no_valid_position_is_rejected_without_creating_a_track() -> None:
    manager = SpatialTrackManager(frame_id="map")
    update = manager.update(
        [
            DetectionObservation("no-depth", "paper_cup", 0.9),
            DetectionObservation(
                "wrong-frame",
                "paper_cup",
                0.9,
                position=Point2D(1.0, 1.0),
                position_valid=True,
                position_frame_id="camera_optical_frame",
            ),
        ],
        5.0,
    )

    assert update.accepted_count == 0
    assert update.rejected_position_count == 2
    assert update.tracks == ()
    selection = select_target(update, Point2D(0.0, 0.0), 5.0)
    assert selection.failure_reason is MissionFailureReason.NO_VALID_POSITION


def test_stale_and_low_confidence_tracks_have_distinct_reasons() -> None:
    stale = [track("track-1", "paper_cup", 0.99, 1.0, 0.0, last_seen_s=1.0)]
    stale_selection = select_target(
        stale,
        Point2D(0.0, 0.0),
        now_s=3.0,
        policy=TargetSelectionPolicy(max_track_age_s=1.0),
    )
    assert stale_selection.failure_reason is MissionFailureReason.STALE_DETECTIONS

    weak = [track("track-2", "paper_cup", 0.49, 1.0, 0.0)]
    weak_selection = select_target(
        weak,
        Point2D(0.0, 0.0),
        now_s=10.0,
        policy=TargetSelectionPolicy(min_confidence=0.5),
    )
    assert weak_selection.failure_reason is MissionFailureReason.LOW_CONFIDENCE


def test_selection_orders_by_priority_then_confidence_then_distance() -> None:
    tracks = [
        track("track-near", "paper_cup", 0.99, 0.5, 0.0),
        track("track-priority-low", "fallen_leaves", 0.80, 1.0, 0.0),
        track("track-priority-high", "fallen_leaves", 0.95, 4.0, 0.0),
        track("track-priority-high-near", "fallen_leaves", 0.95, 2.0, 0.0),
    ]
    selection = select_target(
        tracks,
        Point2D(0.0, 0.0),
        10.0,
        TargetSelectionPolicy(
            priority_classes=("fallen_leaves", "paper_cup"),
            min_confidence=0.5,
        ),
    )

    assert selection.target is not None
    assert selection.target.track_id == "track-priority-high-near"
    assert selection.ranked_track_ids == (
        "track-priority-high-near",
        "track-priority-high",
        "track-priority-low",
        "track-near",
    )


def test_exact_selection_tie_uses_stable_track_id() -> None:
    tracks = [
        track("track-000002", "paper_cup", 0.8, -1.0, 0.0),
        track("track-000001", "paper_cup", 0.8, 1.0, 0.0),
    ]
    selection = select_target(tracks, Point2D(0.0, 0.0), 10.0)
    assert selection.target is not None
    assert selection.target.track_id == "track-000001"


def test_track_pruning_reports_stale_ids_but_keeps_cleaned_tombstones() -> None:
    manager = SpatialTrackManager(max_track_age_s=1.0)
    initial = manager.update(
        [
            positioned("active", "paper_cup", 0.9, 1.0, 0.0),
            positioned("cleaned", "paper_scrap", 0.9, 2.0, 0.0),
        ],
        0.0,
    )
    cleaned_id = next(
        item.track_id for item in initial.tracks if item.class_name == "paper_scrap"
    )
    active_id = next(
        item.track_id for item in initial.tracks if item.class_name == "paper_cup"
    )
    manager.mark_cleaned(cleaned_id)

    update = manager.update([], 1.01)
    assert update.pruned_track_ids == (active_id,)
    assert tuple(item.track_id for item in update.tracks) == (cleaned_id,)
    assert update.tracks[0].cleaned is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"association_distance_m": 0.0},
        {"association_distance_m": nan},
        {"association_distance_m": True},
        {"max_track_age_s": -1.0},
        {"max_track_age_s": inf},
        {"frame_id": ""},
        {"track_id_prefix": "  "},
    ],
)
def test_invalid_tracker_configuration_is_rejected(kwargs) -> None:
    with pytest.raises(MissionCoreError):
        SpatialTrackManager(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_confidence": -0.1},
        {"min_confidence": 1.1},
        {"min_confidence": nan},
        {"max_track_age_s": 0.0},
        {"priority_classes": ("paper_cup", "paper_cup")},
        {"priority_classes": "paper_cup"},
    ],
)
def test_invalid_selection_policy_is_rejected(kwargs) -> None:
    with pytest.raises(MissionCoreError):
        TargetSelectionPolicy(**kwargs)


def test_duplicate_detection_ids_and_backward_frame_time_are_rejected() -> None:
    manager = SpatialTrackManager()
    observation = positioned("duplicate", "paper_cup", 0.9, 1.0, 0.0)
    with pytest.raises(MissionCoreError, match="detection_id"):
        manager.update([observation, observation], 1.0)

    manager.update([observation], 2.0)
    with pytest.raises(MissionCoreError, match="倒退"):
        manager.update([], 1.9)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, nan, inf, True])
def test_invalid_detection_confidence_is_rejected(confidence) -> None:
    with pytest.raises(MissionCoreError, match="confidence"):
        DetectionObservation("det", "paper_cup", confidence)


def test_lateral_approach_is_offset_inside_radius_and_tangent() -> None:
    target = Point2D(2.0, 0.0)
    robot = Point2D(0.0, 0.0)
    pose = compute_lateral_approach_pose(
        target,
        robot,
        cleaning_radius_m=0.45,
        approach_distance_m=0.36,
    )

    assert pose.position.distance_to(target) == pytest.approx(0.36)
    assert pose.position.distance_to(target) <= 0.45
    assert pose.x == pytest.approx(1.64)
    assert pose.y == pytest.approx(0.0)

    heading = (cos(pose.yaw), sin(pose.yaw))
    to_target = (target.x - pose.x, target.y - pose.y)
    assert heading[0] * to_target[0] + heading[1] * to_target[1] == pytest.approx(
        0.0, abs=1e-12
    )
    # Positive cross product means the target is on the vehicle's left.
    assert heading[0] * to_target[1] - heading[1] * to_target[0] > 0.0


def test_front_tool_approach_keeps_body_clear_while_tool_covers_target() -> None:
    target = Point2D(2.0, 0.0)
    approach = compute_front_tool_approach(
        target_position=target,
        robot_position=Point2D(0.0, 0.0),
        cleaning_radius_m=0.45,
        robot_front_extent_m=0.45,
        # 0.15 m target radius plus 0.05 m safety margin.
        target_clearance_m=0.20,
        cleaning_tool_offset_m=0.45,
    )

    assert isinstance(approach, CleaningToolApproach)
    assert approach.base_standoff_m == pytest.approx(0.65)
    assert approach.base_pose.position.distance_to(target) == pytest.approx(0.65)
    assert approach.base_standoff_m > approach.cleaning_radius_m
    assert approach.base_pose.x == pytest.approx(1.35)
    assert approach.base_pose.yaw == pytest.approx(0.0)

    # The front edge and cleaning tool are both 0.45 m ahead of base_link;
    # their 0.20 m target clearance is inside the 0.45 m cleaning radius.
    assert approach.tool_position == Point2D(1.8, 0.0)
    assert approach.tool_target_distance_m == pytest.approx(0.20)
    assert approach.within_cleaning_radius is True

    heading = (cos(approach.base_pose.yaw), sin(approach.base_pose.yaw))
    to_target = (
        target.x - approach.base_pose.x,
        target.y - approach.base_pose.y,
    )
    assert heading[0] * to_target[0] + heading[1] * to_target[1] > 0.0
    assert heading[0] * to_target[1] - heading[1] * to_target[0] == pytest.approx(
        0.0, abs=1e-12
    )


def test_front_tool_approach_rejects_geometry_that_cannot_reach_target() -> None:
    with pytest.raises(MissionCoreError, match="无法"):
        compute_front_tool_approach(
            target_position=Point2D(2.0, 0.0),
            robot_position=Point2D(0.0, 0.0),
            cleaning_radius_m=0.45,
            robot_front_extent_m=0.45,
            target_clearance_m=0.20,
            cleaning_tool_offset_m=0.10,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("cleaning_radius_m", 0.0),
        ("cleaning_radius_m", nan),
        ("robot_front_extent_m", -0.1),
        ("robot_front_extent_m", True),
        ("target_clearance_m", 0.0),
        ("target_clearance_m", inf),
        ("cleaning_tool_offset_m", 0.0),
    ],
)
def test_invalid_front_tool_geometry_is_rejected(field, value) -> None:
    kwargs = {
        "cleaning_radius_m": 0.45,
        "robot_front_extent_m": 0.45,
        "target_clearance_m": 0.20,
        "cleaning_tool_offset_m": 0.45,
    }
    kwargs[field] = value
    with pytest.raises(MissionCoreError):
        compute_front_tool_approach(
            target_position=Point2D(2.0, 0.0),
            robot_position=Point2D(0.0, 0.0),
            **kwargs,
        )


def test_lateral_approach_has_deterministic_degenerate_direction_and_side() -> None:
    point = Point2D(1.0, 2.0)
    left = compute_lateral_approach_pose(point, point, 0.5)
    right = compute_lateral_approach_pose(point, point, 0.5, target_on_left=False)

    assert left.position == Point2D(1.4, 2.0)
    assert left.yaw == pytest.approx(1.5707963267948966)
    assert right.position == left.position
    assert right.yaw == pytest.approx(-1.5707963267948966)


@pytest.mark.parametrize(
    "radius,distance,target_on_left",
    [
        (0.0, None, True),
        (-0.1, None, True),
        (nan, None, True),
        (0.5, 0.0, True),
        (0.5, -0.1, True),
        (0.5, 0.51, True),
        (0.5, inf, True),
        (0.5, 0.4, "yes"),
    ],
)
def test_invalid_approach_geometry_is_rejected(
    radius, distance, target_on_left
) -> None:
    with pytest.raises(MissionCoreError):
        compute_lateral_approach_pose(
            Point2D(1.0, 0.0),
            Point2D(0.0, 0.0),
            cleaning_radius_m=radius,
            approach_distance_m=distance,
            target_on_left=target_on_left,
        )


def test_mission_status_exposes_validated_state_and_failure_reason() -> None:
    navigating = MissionStatus(
        state=MissionState.NAVIGATING_TO_TARGET,
        active_track_id="track-1",
        cleaned_track_ids=("track-0",),
        remaining_track_ids=("track-1", "track-2"),
    )
    assert navigating.failure_reason is None

    failed = MissionStatus.failed(
        MissionFailureReason.NAVIGATION_FAILED,
        detail="planner returned ABORTED",
        active_track_id="track-1",
        cleaned_track_ids=("track-0",),
        remaining_track_ids=("track-1", "track-2"),
    )
    assert failed.state is MissionState.FAILED
    assert failed.failure_reason is MissionFailureReason.NAVIGATION_FAILED


def test_states_and_failure_reasons_cover_controller_safety_boundaries() -> None:
    assert MissionState.WAITING_FOR_NAV2.value == "WAITING_FOR_NAV2"
    assert MissionState.VERIFYING_CLEANING_GATE.value == "VERIFYING_CLEANING_GATE"
    assert MissionState.REMOVING_TARGET.value == "REMOVING_TARGET"

    expected_reasons = {
        "TF_UNAVAILABLE",
        "NAVIGATION_TIMEOUT",
        "ROBOT_NOT_STOPPED",
        "REMOVE_SERVICE_UNAVAILABLE",
        "ENTITY_REMOVE_FAILED",
        "AMBIGUOUS_ENTITY_MAPPING",
    }
    assert expected_reasons.issubset(MissionFailureReason.__members__)


def test_mission_status_rejects_ambiguous_or_impossible_payloads() -> None:
    with pytest.raises(MissionCoreError, match="failure_reason"):
        MissionStatus(state=MissionState.FAILED)
    with pytest.raises(MissionCoreError, match="非 FAILED"):
        MissionStatus(
            state=MissionState.IDLE,
            failure_reason=MissionFailureReason.NO_DETECTIONS,
        )
    with pytest.raises(MissionCoreError, match="重叠"):
        MissionStatus(
            state=MissionState.NAVIGATING_TO_TARGET,
            cleaned_track_ids=("track-1",),
            remaining_track_ids=("track-1",),
        )
    with pytest.raises(MissionCoreError, match="COMPLETED"):
        MissionStatus(
            state=MissionState.COMPLETED,
            remaining_track_ids=("track-1",),
        )
