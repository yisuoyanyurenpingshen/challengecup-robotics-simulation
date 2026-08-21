import json
from pathlib import Path

import pytest

from smartclean_ros.bridge_core import BridgeError, build_status_payload, load_and_run


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def test_bridge_runs_existing_demo_without_ros_dependencies() -> None:
    run = load_and_run(PROJECT_ROOT / "configs" / "demo.json")

    assert run.grid_width == 12
    assert run.grid_height == 8
    assert run.result.status == "COMPLETED"
    assert run.result.metrics.cleaned_targets == run.result.metrics.total_targets == 4
    assert run.result.metrics.coverage_rate == 1.0
    assert run.result.metrics.collisions == 0
    assert run.result.metrics.returned_to_dock is True

    payload = build_status_payload(run)
    assert payload["status"] == "COMPLETED"
    assert payload["task_state"] == "COMPLETED"
    assert payload["run_result_status"] == "COMPLETED"
    assert payload["frame_index"] == payload["frame_count"] - 1
    assert payload["final_rates"]["coverage_rate"] == 1.0
    assert payload["robot_grid_position"] == [1, 1]
    json.dumps(payload, ensure_ascii=False)


def test_status_can_describe_the_initial_replay_frame() -> None:
    run = load_and_run(PROJECT_ROOT / "configs" / "demo.json")

    payload = build_status_payload(run, 0)

    assert payload["frame_index"] == 0
    assert payload["status"] == "PLANNING"
    assert payload["task_state"] == "PLANNING"
    assert payload["run_result_status"] == "COMPLETED"
    assert payload["progress"]["cleaned_targets"] == 0
    assert payload["final_metrics"]["cleaned_targets"] == 4
    assert payload["robot_grid_position"] == [1, 1]


def test_missing_config_reports_the_resolved_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"

    with pytest.raises(BridgeError, match="ROS 桥接无法加载配置") as error:
        load_and_run(missing)

    assert str(missing.resolve()) in str(error.value)


@pytest.mark.parametrize("frame_index", [-1, 9999, True])
def test_invalid_status_frame_index_is_rejected(frame_index) -> None:
    run = load_and_run(PROJECT_ROOT / "configs" / "demo.json")

    with pytest.raises(BridgeError, match="frame_index"):
        build_status_payload(run, frame_index)
