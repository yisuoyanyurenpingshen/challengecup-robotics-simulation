"""二维清扫任务执行闭环与动态障碍安全重规划。"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from smartclean_sim.grid import GridWorld
from smartclean_sim.models import CleaningTask, GridPosition, SimulationMetrics, TrashItem
from smartclean_sim.planning import AStarPlanner, CoveragePlanner, NoPathError


@dataclass(frozen=True)
class DynamicObstacle:
    obstacle_id: str
    kind: str
    path: Tuple[GridPosition, ...]
    start_step: int = 0
    loop: bool = True

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "DynamicObstacle":
        path = tuple(GridPosition.from_value(item) for item in payload.get("path", []))
        if not path:
            raise ValueError("动态障碍 {} 缺少 path".format(payload.get("id", "<unknown>")))
        obstacle_id = payload.get("id", "dynamic-obstacle")
        kind = payload.get("kind", "pedestrian")
        start_step = payload.get("start_step", 0)
        loop = payload.get("loop", True)
        if not isinstance(obstacle_id, str) or not obstacle_id:
            raise ValueError("动态障碍 id 必须是非空字符串")
        if not isinstance(kind, str) or not kind:
            raise ValueError("动态障碍 kind 必须是非空字符串")
        if (
            isinstance(start_step, bool)
            or not isinstance(start_step, int)
            or start_step < 0
        ):
            raise ValueError("动态障碍 start_step 必须是非负整数")
        if not isinstance(loop, bool):
            raise ValueError("动态障碍 loop 必须是布尔值")
        return cls(
            obstacle_id=obstacle_id,
            kind=kind,
            path=path,
            start_step=start_step,
            loop=loop,
        )

    def position_at(self, step: int) -> Optional[GridPosition]:
        if step < self.start_step:
            return None
        offset = step - self.start_step
        if self.loop:
            return self.path[offset % len(self.path)]
        if offset >= len(self.path):
            return self.path[-1]
        return self.path[offset]


@dataclass(frozen=True)
class DynamicObstacleSnapshot:
    obstacle_id: str
    kind: str
    position: Optional[GridPosition]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.obstacle_id,
            "kind": self.kind,
            "position": (
                [self.position.x, self.position.y]
                if self.position is not None
                else None
            ),
        }


@dataclass(frozen=True)
class SimulationFrame:
    frame_index: int
    sim_step: int
    state: str
    action: str
    robot_position: GridPosition
    dynamic_obstacles: Tuple[DynamicObstacleSnapshot, ...]
    remaining_trash_ids: Tuple[str, ...]
    cleaned_ids: Tuple[str, ...]
    cleaned_this_frame: Tuple[str, ...] = ()
    events: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "sim_step": self.sim_step,
            "state": self.state,
            "action": self.action,
            "robot_position": [self.robot_position.x, self.robot_position.y],
            "dynamic_obstacles": [
                obstacle.to_dict() for obstacle in self.dynamic_obstacles
            ],
            "remaining_trash_ids": list(self.remaining_trash_ids),
            "cleaned_ids": list(self.cleaned_ids),
            "cleaned_this_frame": list(self.cleaned_this_frame),
            "events": list(self.events),
        }


@dataclass(frozen=True)
class SimulationResult:
    status: str
    final_position: GridPosition
    trajectory: Tuple[GridPosition, ...]
    cleaned_ids: Tuple[str, ...]
    events: Tuple[str, ...]
    metrics: SimulationMetrics
    frames: Tuple[SimulationFrame, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "final_position": [self.final_position.x, self.final_position.y],
            "trajectory": [[point.x, point.y] for point in self.trajectory],
            "cleaned_ids": list(self.cleaned_ids),
            "events": list(self.events),
            "metrics": asdict(self.metrics),
            "rates": {
                "completion_rate": self.metrics.completion_rate,
                "coverage_rate": self.metrics.coverage_rate,
            },
            "trace": {
                "schema_version": 1,
                "frames": [frame.to_dict() for frame in self.frames],
            },
        }


class Simulator:
    """按任务优先级逐点清扫，并在每一步预测动态障碍。"""

    def __init__(
        self,
        world: GridWorld,
        task: CleaningTask,
        dynamic_obstacles: Sequence[DynamicObstacle] = (),
        planner: Optional[AStarPlanner] = None,
        max_steps: int = 1000,
        coverage_planner: Optional[CoveragePlanner] = None,
    ) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps 必须大于 0")
        self.world = world
        self.task = task
        self.dynamic_obstacles = tuple(dynamic_obstacles)
        self.planner = planner or AStarPlanner()
        self.coverage_planner = coverage_planner or CoveragePlanner(self.planner)
        self.max_steps = max_steps
        for obstacle in self.dynamic_obstacles:
            for position in obstacle.path:
                if not self.world.in_bounds(position):
                    raise ValueError(
                        "动态障碍 {} 的路径越界：{}".format(
                            obstacle.obstacle_id, position
                        )
                    )
                if position in self.world.static_obstacles:
                    raise ValueError(
                        "动态障碍 {} 的路径穿过静态障碍：{}".format(
                            obstacle.obstacle_id, position
                        )
                    )

    @classmethod
    def from_config(cls, payload: Dict[str, Any], task: CleaningTask) -> "Simulator":
        scenario = payload["scenario"]
        world = GridWorld.from_dict(scenario)
        obstacles = tuple(
            DynamicObstacle.from_dict(item)
            for item in scenario.get("dynamic_obstacles", [])
        )
        max_steps = int(payload.get("simulation", {}).get("max_steps", 1000))
        return cls(world, task, obstacles, max_steps=max_steps)

    def run(self) -> SimulationResult:
        position = self.world.start
        trajectory: List[GridPosition] = [position]
        visited: Set[GridPosition] = {position}
        cleaned_ids: List[str] = []
        events: List[str] = ["IDLE -> PLANNING"]
        replans = 0
        collisions = 0
        steps = 0
        status = "COMPLETED"
        frames: List[SimulationFrame] = []

        self._record_frame(
            frames,
            step=steps,
            state="PLANNING",
            action="initial",
            position=position,
            cleaned_ids=cleaned_ids,
            frame_events=("IDLE -> PLANNING",),
        )

        targets = self._ordered_targets(position)
        events.append("PLANNING -> NAVIGATING ({} targets)".format(len(targets)))
        self._record_frame(
            frames,
            step=steps,
            state="NAVIGATING",
            action="transition",
            position=position,
            cleaned_ids=cleaned_ids,
            frame_events=(events[-1],),
        )

        for target in targets:
            reached, position, steps, target_replans = self._navigate(
                position,
                target.position,
                steps,
                trajectory,
                visited,
                events,
                frames,
                cleaned_ids,
                phase="NAVIGATING",
            )
            replans += target_replans
            if not reached:
                status = "FAILED"
                events.append("NAVIGATING -> FAILED ({})".format(target.item_id))
                break
            cleaned = self.world.clean_at(
                position,
                target_area=self.task.target_area,
                kinds=(target.kind,),
            )
            if cleaned is not None:
                cleaned_ids.append(cleaned.item_id)
                events.append("NAVIGATING -> CLEANING ({})".format(cleaned.item_id))
                self._record_frame(
                    frames,
                    step=steps,
                    state="CLEANING",
                    action="clean",
                    position=position,
                    cleaned_ids=cleaned_ids,
                    cleaned_this_frame=(cleaned.item_id,),
                    frame_events=(events[-1],),
                )
                events.append("CLEANING -> NAVIGATING")

        if status == "COMPLETED" and len(cleaned_ids) != len(targets):
            status = "FAILED"
            events.append("CLEANING -> FAILED (target state mismatch)")

        coverage_cells: Set[GridPosition] = set()
        if status == "COMPLETED" and self.task.mode == "clean_area":
            coverage_cells = set(
                self.world.traversable_area_cells(
                    self.task.target_area, self.task.avoid_types
                )
            )
            events.append("NAVIGATING -> COVERAGE_PLANNING")
            self._record_frame(
                frames,
                step=steps,
                state="PLANNING",
                action="transition",
                position=position,
                cleaned_ids=cleaned_ids,
                frame_events=(events[-1],),
            )
            try:
                coverage_route = self.coverage_planner.plan(
                    self.world,
                    position,
                    target_area=self.task.target_area,
                    avoid_types=self.task.avoid_types,
                )
            except NoPathError as exc:
                status = "FAILED"
                events.append("COVERAGE_PLANNING -> FAILED ({})".format(exc))
            else:
                events.append(
                    "COVERAGE_PLANNING -> NAVIGATING ({} cells)".format(
                        len(coverage_cells)
                    )
                )
                self._record_frame(
                    frames,
                    step=steps,
                    state="NAVIGATING",
                    action="transition",
                    position=position,
                    cleaned_ids=cleaned_ids,
                    frame_events=(events[-1],),
                )
                for waypoint in coverage_route[1:]:
                    reached, position, steps, coverage_replans = self._navigate(
                        position,
                        waypoint,
                        steps,
                        trajectory,
                        visited,
                        events,
                        frames,
                        cleaned_ids,
                        phase="NAVIGATING",
                    )
                    replans += coverage_replans
                    if not reached:
                        status = "FAILED"
                        events.append("COVERAGE -> FAILED")
                        break

                if status == "COMPLETED" and not coverage_cells.issubset(visited):
                    status = "FAILED"
                    events.append("COVERAGE -> FAILED (coverage incomplete)")

        if status == "COMPLETED" and self.task.return_to_dock:
            events.append("NAVIGATING -> RETURNING")
            self._record_frame(
                frames,
                step=steps,
                state="RETURNING",
                action="transition",
                position=position,
                cleaned_ids=cleaned_ids,
                frame_events=(events[-1],),
            )
            reached, position, steps, return_replans = self._navigate(
                position,
                self.world.dock,
                steps,
                trajectory,
                visited,
                events,
                frames,
                cleaned_ids,
                phase="RETURNING",
            )
            replans += return_replans
            if not reached:
                status = "FAILED"
                events.append("RETURNING -> FAILED")

        returned = position == self.world.dock
        if status == "COMPLETED":
            events.append(
                "RETURNING -> COMPLETED"
                if self.task.return_to_dock
                else "NAVIGATING -> COMPLETED"
            )

        self._record_frame(
            frames,
            step=steps,
            state=status,
            action="terminal",
            position=position,
            cleaned_ids=cleaned_ids,
            frame_events=(events[-1],),
        )

        if self.task.mode == "clean_area":
            navigable_cells = len(coverage_cells)
            unique_visited_cells = len(visited & coverage_cells)
            coverage_complete = bool(coverage_cells) and coverage_cells.issubset(
                visited
            )
        else:
            navigable_cells = self.world.traversable_count(self.task.avoid_types)
            unique_visited_cells = len(visited)
            coverage_complete = True

        metrics = SimulationMetrics(
            total_targets=len(targets),
            cleaned_targets=len(cleaned_ids),
            path_length_cells=max(0, len(trajectory) - 1),
            unique_visited_cells=unique_visited_cells,
            navigable_cells=navigable_cells,
            replans=replans,
            collisions=collisions,
            returned_to_dock=returned,
            completed=(
                status == "COMPLETED"
                and len(cleaned_ids) == len(targets)
                and coverage_complete
            ),
        )
        return SimulationResult(
            status=status,
            final_position=position,
            trajectory=tuple(trajectory),
            cleaned_ids=tuple(cleaned_ids),
            events=tuple(events),
            metrics=metrics,
            frames=tuple(frames),
        )

    def _ordered_targets(self, start: GridPosition) -> List[TrashItem]:
        targets = list(self.world.remaining_trash(self.task.target_area))
        priority = {
            kind: index for index, kind in enumerate(self.task.priority_classes)
        }
        default_rank = len(priority)
        targets.sort(
            key=lambda item: (
                priority.get(item.kind, default_rank),
                start.manhattan_distance(item.position),
                item.item_id,
            )
        )
        return targets

    def _navigate(
        self,
        start: GridPosition,
        goal: GridPosition,
        step: int,
        trajectory: List[GridPosition],
        visited: Set[GridPosition],
        events: List[str],
        frames: List[SimulationFrame],
        cleaned_ids: List[str],
        phase: str,
    ) -> Tuple[bool, GridPosition, int, int]:
        position = start
        replans = 0
        path: List[GridPosition] = []
        while position != goal and step < self.max_steps:
            if len(path) < 2:
                blocked_now = self._dynamic_positions(step)
                blocked_next = self._dynamic_positions(step + 1)
                predicted_blocked = blocked_now | blocked_next
                predicted_blocked.discard(position)
                predicted_blocked.discard(goal)
                try:
                    path = self.planner.plan(
                        self.world,
                        position,
                        goal,
                        avoid_types=self.task.avoid_types,
                        extra_blocked=predicted_blocked,
                    )
                except NoPathError:
                    try:
                        self.planner.plan(
                            self.world,
                            position,
                            goal,
                            avoid_types=self.task.avoid_types,
                        )
                    except NoPathError:
                        events.append("FAILED: no static feasible path")
                        self._record_frame(
                            frames,
                            step=step,
                            state="FAILED",
                            action="transition",
                            position=position,
                            cleaned_ids=cleaned_ids,
                            frame_events=(events[-1],),
                        )
                        return False, position, step, replans
                    replans += 1
                    step += 1
                    events.append("REPLANNING: path temporarily unavailable")
                    self._record_frame(
                        frames,
                        step=step,
                        state="REPLANNING",
                        action="wait",
                        position=position,
                        cleaned_ids=cleaned_ids,
                        frame_events=(events[-1],),
                    )
                    continue

            next_position = path[1]
            actual_next_blocked = self._dynamic_positions(step + 1)
            if next_position in actual_next_blocked:
                replans += 1
                step += 1
                events.append("AVOIDING -> REPLANNING")
                self._record_frame(
                    frames,
                    step=step,
                    state="REPLANNING",
                    action="wait",
                    position=position,
                    cleaned_ids=cleaned_ids,
                    frame_events=(events[-1],),
                )
                path = []
                continue

            position = next_position
            path = path[1:]
            trajectory.append(position)
            visited.add(position)
            step += 1
            self._record_frame(
                frames,
                step=step,
                state=phase,
                action="move",
                position=position,
                cleaned_ids=cleaned_ids,
            )

        return position == goal, position, step, replans

    def _record_frame(
        self,
        frames: List[SimulationFrame],
        step: int,
        state: str,
        action: str,
        position: GridPosition,
        cleaned_ids: Sequence[str],
        cleaned_this_frame: Sequence[str] = (),
        frame_events: Sequence[str] = (),
    ) -> None:
        frames.append(
            SimulationFrame(
                frame_index=len(frames),
                sim_step=step,
                state=state,
                action=action,
                robot_position=position,
                dynamic_obstacles=self._dynamic_snapshots(step),
                remaining_trash_ids=tuple(
                    sorted(item.item_id for item in self.world.remaining_trash("all"))
                ),
                cleaned_ids=tuple(cleaned_ids),
                cleaned_this_frame=tuple(cleaned_this_frame),
                events=tuple(frame_events),
            )
        )

    def _dynamic_snapshots(
        self, step: int
    ) -> Tuple[DynamicObstacleSnapshot, ...]:
        return tuple(
            DynamicObstacleSnapshot(
                obstacle_id=obstacle.obstacle_id,
                kind=obstacle.kind,
                position=obstacle.position_at(step),
            )
            for obstacle in sorted(
                self.dynamic_obstacles, key=lambda item: item.obstacle_id
            )
        )

    def _dynamic_positions(self, step: int) -> Set[GridPosition]:
        positions: Set[GridPosition] = set()
        for obstacle in self.dynamic_obstacles:
            position = obstacle.position_at(step)
            if position is not None:
                positions.add(position)
        return positions
