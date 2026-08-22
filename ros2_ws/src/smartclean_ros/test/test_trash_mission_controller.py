"""Safety and interface contracts for the trash mission controller."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from action_msgs.msg import GoalStatus

from smartclean_ros.mission_core import Point2D, Pose2D
from smartclean_ros.trash_mission_controller_node import CleaningGateEvidence
from smartclean_ros.trash_mission_controller_node import RemovalTransaction
from smartclean_ros.trash_mission_controller_node import StopWindowEvidence
from smartclean_ros.trash_mission_controller_node import _OdomSample
from smartclean_ros.trash_mission_controller_node import commit_delete_response
from smartclean_ros.trash_mission_controller_node import (
    detection_observation_is_new,
)
from smartclean_ros.trash_mission_controller_node import evaluate_cleaning_gate
from smartclean_ros.trash_mission_controller_node import evaluate_dock_gate
from smartclean_ros.trash_mission_controller_node import evaluate_stop_window
from smartclean_ros.trash_mission_controller_node import navigation_result_succeeded


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = PACKAGE_ROOT / "smartclean_ros" / "trash_mission_controller_node.py"
INTERFACE_MSG_DIR = PACKAGE_ROOT.parent / "smartclean_interfaces" / "msg"


def stopped(passed: bool = True) -> StopWindowEvidence:
    return StopWindowEvidence(
        passed=passed,
        duration_s=0.75,
        max_linear_speed_mps=0.0,
        max_angular_speed_rps=0.0,
        displacement_m=0.0,
    )


def cleaning_gate(
    *,
    navigation_status: int = GoalStatus.STATUS_SUCCEEDED,
    base_pose: Pose2D = Pose2D(0.0, 0.0, 0.0),
    target_position: Point2D = Point2D(0.65, 0.0),
    stop: StopWindowEvidence = stopped(),
) -> CleaningGateEvidence:
    return evaluate_cleaning_gate(
        navigation_status=navigation_status,
        base_pose=base_pose,
        target_position=target_position,
        robot_front_extent_m=0.45,
        target_clearance_m=0.20,
        cleaning_tool_offset_m=0.45,
        cleaning_radius_m=0.45,
        stop=stop,
        heading_tolerance_rad=0.35,
    )


def test_aborted_navigation_with_empty_result_never_authorizes_delete() -> None:
    response = SimpleNamespace(
        status=GoalStatus.STATUS_ABORTED,
        result=SimpleNamespace(),
    )
    assert response.result
    assert navigation_result_succeeded(response) is False

    evidence = cleaning_gate(navigation_status=response.status)
    transaction = RemovalTransaction()
    commits = []
    assert evidence.passed is False
    assert transaction.start(evidence) is False
    assert commit_delete_response(
        transaction,
        SimpleNamespace(success=True),
        lambda: commits.append("deleted"),
    ) is False
    assert commits == []


def test_detection_observations_use_steady_receipt_time() -> None:
    assert detection_observation_is_new(None, 20.0) is True
    assert detection_observation_is_new(20.0, 20.01) is False
    assert detection_observation_is_new(20.0, 20.02) is True
    assert detection_observation_is_new(20.0, 20.10) is True


@pytest.mark.parametrize(
    "evidence",
    [
        cleaning_gate(navigation_status=GoalStatus.STATUS_ABORTED),
        # Chassis front edge is inside the leaves radius + 0.05 m margin.
        cleaning_gate(base_pose=Pose2D(0.25, 0.0, 0.0)),
        # Chassis is safe but the front tool point is outside 0.45 m reach.
        cleaning_gate(base_pose=Pose2D(-0.50, 0.0, 0.0)),
        # Tool can reach, but the robot is not facing the target closely enough.
        cleaning_gate(base_pose=Pose2D(0.0, 0.0, 0.40)),
        cleaning_gate(stop=stopped(False)),
    ],
    ids=("nav", "base-clearance", "tool-distance", "heading", "stop"),
)
def test_any_failed_cleaning_gate_prevents_delete(
    evidence: CleaningGateEvidence,
) -> None:
    transaction = RemovalTransaction()
    assert evidence.passed is False
    assert transaction.start(evidence) is False
    assert transaction.requested is False


def test_delete_false_does_not_commit_or_update_transaction() -> None:
    transaction = RemovalTransaction()
    commits = []
    assert transaction.start(cleaning_gate()) is True

    assert commit_delete_response(
        transaction,
        SimpleNamespace(success=False),
        lambda: commits.append("cleaned"),
    ) is False
    assert commits == []
    assert transaction.resolved is True
    assert transaction.committed is False


def test_positive_delete_commits_success_exactly_once() -> None:
    transaction = RemovalTransaction()
    commits = []
    assert transaction.start(cleaning_gate()) is True

    response = SimpleNamespace(success=True)
    assert commit_delete_response(
        transaction, response, lambda: commits.append("track-000001")
    ) is True
    assert commit_delete_response(
        transaction, response, lambda: commits.append("duplicate")
    ) is False
    assert transaction.committed is True
    assert commits == ["track-000001"]


def test_stop_window_accepts_normal_discrete_odom_coverage() -> None:
    samples = [
        _OdomSample(
            received_at_s=index * 0.05,
            x=0.0,
            y=0.0,
            linear_speed_mps=0.0,
            angular_speed_rps=0.0,
        )
        for index in range(1, 17)
    ]
    evidence = evaluate_stop_window(
        samples,
        now_s=0.80,
        since_s=0.0,
        hold_s=0.75,
        max_linear_speed_mps=0.02,
        max_angular_speed_rps=0.03,
        max_displacement_m=0.02,
    )
    assert evidence.passed is True
    assert evidence.duration_s == pytest.approx(0.75)


def test_stop_window_rejects_sparse_or_moving_evidence() -> None:
    sparse = [_OdomSample(0.80, 0.0, 0.0, 0.0, 0.0)]
    assert evaluate_stop_window(
        sparse,
        now_s=0.80,
        since_s=0.0,
        hold_s=0.75,
        max_linear_speed_mps=0.02,
        max_angular_speed_rps=0.03,
        max_displacement_m=0.02,
    ).passed is False

    moving = [
        _OdomSample(index * 0.05, index * 0.002, 0.0, 0.04, 0.0)
        for index in range(1, 17)
    ]
    assert evaluate_stop_window(
        moving,
        now_s=0.80,
        since_s=0.0,
        hold_s=0.75,
        max_linear_speed_mps=0.02,
        max_angular_speed_rps=0.03,
        max_displacement_m=0.02,
    ).passed is False


def test_return_requires_nav_success_tf_distance_and_stop() -> None:
    dock = Pose2D(0.0, 0.0, 0.0)
    assert evaluate_dock_gate(
        navigation_status=GoalStatus.STATUS_SUCCEEDED,
        base_pose=Pose2D(0.20, 0.0, 1.0),
        dock_pose=dock,
        distance_tolerance_m=0.30,
        stop=stopped(),
    ) is True
    assert evaluate_dock_gate(
        navigation_status=GoalStatus.STATUS_ABORTED,
        base_pose=Pose2D(0.0, 0.0, 0.0),
        dock_pose=dock,
        distance_tolerance_m=0.30,
        stop=stopped(),
    ) is False
    assert evaluate_dock_gate(
        navigation_status=GoalStatus.STATUS_SUCCEEDED,
        base_pose=Pose2D(0.31, 0.0, 0.0),
        dock_pose=dock,
        distance_tolerance_m=0.30,
        stop=stopped(),
    ) is False
    assert evaluate_dock_gate(
        navigation_status=GoalStatus.STATUS_SUCCEEDED,
        base_pose=Pose2D(0.0, 0.0, 0.0),
        dock_pose=dock,
        distance_tolerance_m=0.30,
        stop=stopped(False),
    ) is False


def test_state_and_event_interfaces_carry_auditable_fields() -> None:
    state = (INTERFACE_MSG_DIR / "TrashMissionState.msg").read_text(
        encoding="utf-8"
    )
    event = (INTERFACE_MSG_DIR / "LitterCleaned.msg").read_text(
        encoding="utf-8"
    )
    for field in (
        "string state",
        "string failure_code",
        "string active_target_id",
        "string active_class_name",
        "float32[3] active_target_position",
        "float32[3] active_goal_pose_xyyaw",
        "string[] failed_ids",
        "float32 progress",
        "bool returned_to_dock",
    ):
        assert field in state
    for field in (
        "string track_id",
        "string source_detection_id",
        "float32[3] target_position",
        "float32[3] robot_position",
        "float32[3] tool_position",
        "float32 base_target_distance_m",
        "float32 cleaning_distance_m",
        "float32 target_clearance_m",
        "int8 navigation_status",
        "float32 stop_duration_s",
        "string entity_name",
        "bool removal_confirmed",
    ):
        assert field in event


def test_node_source_preserves_the_frozen_mission_contract() -> None:
    source = CONTROLLER.read_text(encoding="utf-8")
    assert '"/smartclean/mission/state"' in source
    assert '"/smartclean/mission/litter_cleaned"' in source
    assert "DurabilityPolicy.TRANSIENT_LOCAL" in source
    assert "ReliabilityPolicy.RELIABLE" in source
    assert "compute_front_tool_approach(" in source
    assert "compute_lateral_approach_pose" not in source
    assert "configured_observations < 3" in source
    assert "latest common transform" in source
    assert 'ODOM_FRAME = "odom"' in source
    assert "_odom_pose_to_map(self._dock_pose)" in source
    assert "_lookup_base_pose_in_frame(ODOM_FRAME)" in source
    assert "max_return_attempts" in source
    assert "MissionFailureReason.AMBIGUOUS_ENTITY_MAPPING" in source
    assert "ENTITY_PREFIX + self._active_target.class_name" in source
    assert "response.result" not in source
    assert "spin_until_future_complete" not in source
    assert "gazebo_scene" not in source
    assert "subprocess" not in source
    assert "create_publisher(Twist" not in source


def test_console_entry_point_exists() -> None:
    setup = (PACKAGE_ROOT / "setup.py").read_text(encoding="utf-8")
    assert '"trash_mission_controller = "' in setup
    assert '"smartclean_ros.trash_mission_controller_node:main"' in setup
