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
    assert first.metrics.replans >= 1
    assert first.metrics.collisions == 0
    assert first.metrics.returned_to_dock is True
