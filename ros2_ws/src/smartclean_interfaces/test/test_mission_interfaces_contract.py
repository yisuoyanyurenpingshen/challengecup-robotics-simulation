"""Static contract checks for the trash-mission ROS messages."""

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MSG_DIR = PACKAGE_ROOT / "msg"


def _fields(name: str) -> str:
    return (MSG_DIR / name).read_text(encoding="utf-8")


def test_litter_cleaned_carries_detection_navigation_and_actuator_evidence() -> None:
    message = _fields("LitterCleaned.msg")
    for field in (
        "std_msgs/Header header",
        "uint32 schema_version",
        "string mission_id",
        "string track_id",
        "string source_detection_id",
        "string class_name",
        "float32[3] target_position",
        "float32[3] robot_position",
        "float32[3] tool_position",
        "float32 base_target_distance_m",
        "float32 cleaning_distance_m",
        "float32 target_clearance_m",
        "int8 navigation_status",
        "float32 stop_duration_s",
        "float32 linear_speed_mps",
        "float32 angular_speed_rps",
        "string actuator",
        "string entity_name",
        "bool removal_confirmed",
    ):
        assert field in message, field


def test_mission_state_exposes_stable_progress_and_structured_failure() -> None:
    message = _fields("TrashMissionState.msg")
    for field in (
        "string state",
        "string failure_code",
        "string active_target_id",
        "string active_class_name",
        "float32[3] active_target_position",
        "float32[3] active_goal_pose_xyyaw",
        "string[] discovered_trash_ids",
        "string[] cleaned_ids",
        "string[] remaining_trash_ids",
        "string[] failed_ids",
        "uint32 initial_trash_count",
        "uint32 navigation_goals_sent",
        "uint32 cleaning_events",
        "float32 progress",
        "bool return_after_done",
        "bool returned_to_dock",
    ):
        assert field in message, field
