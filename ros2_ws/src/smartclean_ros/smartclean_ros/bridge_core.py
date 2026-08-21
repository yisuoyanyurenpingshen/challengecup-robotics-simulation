"""ROS-independent orchestration used by the ROS bridge and host-side tests."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

from smartclean_sim.config import ConfigError, load_config
from smartclean_sim.simulation import SimulationFrame, SimulationResult, Simulator
from smartclean_sim.tasking import TaskParseError, task_from_dict


class BridgeError(RuntimeError):
    """A configuration could not be converted into a bridge-ready run."""


@dataclass(frozen=True)
class BridgeRun:
    """Validated scenario metadata and its deterministic simulation result."""

    config_path: Path
    scenario_name: str
    grid_width: int
    grid_height: int
    result: SimulationResult


def load_and_run(config_path: Union[str, Path]) -> BridgeRun:
    """Load one configuration and execute the existing platform-neutral core."""

    if isinstance(config_path, str) and not config_path.strip():
        raise BridgeError("config_path 不能为空")
    resolved_path = Path(config_path).expanduser().resolve()
    try:
        config = load_config(resolved_path)
        task = task_from_dict(config["task"])
        simulator = Simulator.from_config(config, task)
        result = simulator.run()
    except (ConfigError, TaskParseError, OSError, TypeError, ValueError) as exc:
        raise BridgeError(
            "ROS 桥接无法加载配置 {}：{}".format(resolved_path, exc)
        ) from exc

    scenario_name = config["scenario"].get("name", resolved_path.stem)
    if not isinstance(scenario_name, str) or not scenario_name.strip():
        scenario_name = resolved_path.stem
    return BridgeRun(
        config_path=resolved_path,
        scenario_name=scenario_name,
        grid_width=simulator.world.width,
        grid_height=simulator.world.height,
        result=result,
    )


def _frame_at(result: SimulationResult, frame_index: Optional[int]) -> SimulationFrame:
    if not result.frames:
        raise BridgeError("仿真结果没有可回放帧")
    if frame_index is None:
        return result.frames[-1]
    if isinstance(frame_index, bool) or not isinstance(frame_index, int):
        raise BridgeError("frame_index 必须是整数")
    if not 0 <= frame_index < len(result.frames):
        raise BridgeError(
            "frame_index={} 超出 [0, {})".format(frame_index, len(result.frames))
        )
    return result.frames[frame_index]


def build_status_payload(
    run: BridgeRun, frame_index: Optional[int] = None
) -> Dict[str, Any]:
    """Build the stable JSON-compatible status published by the ROS node."""

    frame = _frame_at(run.result, frame_index)
    metrics = run.result.metrics
    return {
        "schema_version": 1,
        "scenario_name": run.scenario_name,
        "status": frame.state,
        "task_state": frame.state,
        "run_result_status": run.result.status,
        "frame_index": frame.frame_index,
        "frame_count": len(run.result.frames),
        "sim_step": frame.sim_step,
        "action": frame.action,
        "robot_grid_position": [
            frame.robot_position.x,
            frame.robot_position.y,
        ],
        "cleaned_ids": list(frame.cleaned_ids),
        "remaining_trash_ids": list(frame.remaining_trash_ids),
        "events": list(frame.events),
        "progress": {
            "cleaned_targets": len(frame.cleaned_ids),
            "total_targets": metrics.total_targets,
        },
        "final_metrics": {
            "total_targets": metrics.total_targets,
            "cleaned_targets": metrics.cleaned_targets,
            "path_length_cells": metrics.path_length_cells,
            "replans": metrics.replans,
            "collisions": metrics.collisions,
            "returned_to_dock": metrics.returned_to_dock,
            "completed": metrics.completed,
        },
        "final_rates": {
            "completion_rate": metrics.completion_rate,
            "coverage_rate": metrics.coverage_rate,
        },
    }
