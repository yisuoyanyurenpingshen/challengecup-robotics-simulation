from pathlib import Path

from smartclean_sim.config import load_config
from smartclean_sim.simulation import Simulator
from smartclean_sim.tasking import task_from_dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_demo():
    config = load_config(PROJECT_ROOT / "configs" / "demo.json")
    task = task_from_dict(config["task"])
    return Simulator.from_config(config, task).run()


def test_demo_is_complete_safe_and_reproducible() -> None:
    first = run_demo()
    second = run_demo()

    assert first.to_dict() == second.to_dict()
    assert first.status == "COMPLETED"
    assert first.metrics.cleaned_targets == first.metrics.total_targets == 4
    assert first.metrics.coverage_rate == 1.0
    assert first.metrics.replans >= 1
    assert first.metrics.collisions == 0
    assert first.metrics.returned_to_dock is True
    assert [frame.frame_index for frame in first.frames] == list(
        range(len(first.frames))
    )
    assert [frame.sim_step for frame in first.frames] == sorted(
        frame.sim_step for frame in first.frames
    )
    assert first.frames[0].action == "initial"
    assert first.frames[-1].action == "terminal"
    assert first.frames[-1].state == "COMPLETED"


def test_demo_trace_synchronizes_motion_waiting_and_cleaning() -> None:
    result = run_demo()
    move_frames = [frame for frame in result.frames if frame.action == "move"]
    wait_frames = [frame for frame in result.frames if frame.action == "wait"]
    clean_frames = [frame for frame in result.frames if frame.action == "clean"]

    assert len(move_frames) == result.metrics.path_length_cells
    assert len(wait_frames) == result.metrics.replans
    assert len(clean_frames) == result.metrics.cleaned_targets

    for previous, current in zip(result.frames, result.frames[1:]):
        assert current.sim_step >= previous.sim_step
        if current.action == "move":
            distance = previous.robot_position.manhattan_distance(
                current.robot_position
            )
            assert distance == 1
        if current.action == "wait":
            assert current.robot_position == previous.robot_position
            assert current.sim_step == previous.sim_step + 1

    initially_remaining = set(result.frames[0].remaining_trash_ids)
    for frame in clean_frames:
        assert len(frame.cleaned_this_frame) == 1
        cleaned_id = frame.cleaned_this_frame[0]
        assert cleaned_id in initially_remaining
        assert cleaned_id not in frame.remaining_trash_ids
    assert result.frames[-1].remaining_trash_ids == ()
