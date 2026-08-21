"""Deterministic path planning algorithms for the grid world."""

import heapq
import itertools
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .grid import GridWorld
from .models import GridPosition


class NoPathError(RuntimeError):
    """Raised when no traversable route exists between two positions."""


class AStarPlanner:
    """Unit-cost, four-neighbor A* planner with Manhattan-distance heuristic."""

    def plan(
        self,
        world: GridWorld,
        start: GridPosition,
        goal: GridPosition,
        avoid_types: Iterable[str] = (),
        extra_blocked: Optional[Iterable[GridPosition]] = None,
    ) -> List[GridPosition]:
        avoided = tuple(avoid_types)
        dynamic_obstacles: Set[GridPosition] = set(extra_blocked or ())
        # The robot may legitimately occupy a cell that has just become blocked.
        dynamic_obstacles.discard(start)

        if world.is_blocked(start, avoided):
            raise NoPathError("start position is blocked: {}".format(start))
        if world.is_blocked(goal, avoided) or goal in dynamic_obstacles:
            raise NoPathError("goal position is blocked: {}".format(goal))
        if start == goal:
            return [start]

        sequence = itertools.count()
        start_h = self._manhattan(start, goal)
        frontier: List[Tuple[int, int, int, int, GridPosition]] = [
            (start_h, start_h, next(sequence), 0, start)
        ]
        came_from: Dict[GridPosition, GridPosition] = {}
        best_cost: Dict[GridPosition, int] = {start: 0}

        while frontier:
            _, _, _, cost_so_far, current = heapq.heappop(frontier)
            if cost_so_far != best_cost.get(current):
                continue
            if current == goal:
                return self._reconstruct_path(came_from, start, goal)

            for neighbor in world.neighbors(
                current,
                avoid_types=avoided,
                extra_blocked=dynamic_obstacles,
            ):
                candidate_cost = cost_so_far + 1
                if candidate_cost >= best_cost.get(neighbor, candidate_cost + 1):
                    continue
                best_cost[neighbor] = candidate_cost
                came_from[neighbor] = current
                heuristic = self._manhattan(neighbor, goal)
                heapq.heappush(
                    frontier,
                    (
                        candidate_cost + heuristic,
                        heuristic,
                        next(sequence),
                        candidate_cost,
                        neighbor,
                    ),
                )

        raise NoPathError("no path from {} to {}".format(start, goal))

    @staticmethod
    def _manhattan(first: GridPosition, second: GridPosition) -> int:
        return abs(first.x - second.x) + abs(first.y - second.y)

    @staticmethod
    def _reconstruct_path(
        came_from: Dict[GridPosition, GridPosition],
        start: GridPosition,
        goal: GridPosition,
    ) -> List[GridPosition]:
        path = [goal]
        current = goal
        while current != start:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path


class CoveragePlanner:
    """Build a deterministic full-coverage route over a named grid area.

    Horizontal and vertical serpentine orders are connected with A*.  The shorter
    feasible route is selected, with horizontal order winning deterministic ties.
    """

    def __init__(self, connector: Optional[AStarPlanner] = None) -> None:
        self.connector = connector or AStarPlanner()

    def plan(
        self,
        world: GridWorld,
        start: GridPosition,
        target_area: str = "all",
        avoid_types: Iterable[str] = (),
    ) -> List[GridPosition]:
        avoided = tuple(avoid_types)
        targets = world.traversable_area_cells(target_area, avoided)
        if not targets:
            raise NoPathError(
                "target area has no traversable cells: {}".format(target_area)
            )
        if world.is_blocked(start, avoided):
            raise NoPathError("start position is blocked: {}".format(start))

        orders = (
            self._horizontal_serpentine(targets),
            self._vertical_serpentine(targets),
        )
        candidates: List[Tuple[int, List[GridPosition]]] = []
        failures: List[NoPathError] = []
        for preference, order in enumerate(orders):
            try:
                route = self._connect_order(world, start, order, avoided)
            except NoPathError as exc:
                failures.append(exc)
                continue
            candidates.append((preference, route))

        if not candidates:
            message = "no coverage path from {} through area {}".format(
                start, target_area
            )
            if failures:
                raise NoPathError(message) from failures[0]
            raise NoPathError(message)

        _, route = min(candidates, key=lambda item: (len(item[1]), item[0]))
        return route

    def _connect_order(
        self,
        world: GridWorld,
        start: GridPosition,
        order: Tuple[GridPosition, ...],
        avoid_types: Tuple[str, ...],
    ) -> List[GridPosition]:
        targets = set(order)
        covered: Set[GridPosition] = {start} & targets
        route = [start]
        current = start

        for goal in order:
            if goal in covered:
                continue
            connector = self.connector.plan(
                world,
                current,
                goal,
                avoid_types=avoid_types,
            )
            route.extend(connector[1:])
            covered.update(position for position in connector if position in targets)
            current = goal

        return route

    @staticmethod
    def _horizontal_serpentine(
        targets: Tuple[GridPosition, ...],
    ) -> Tuple[GridPosition, ...]:
        rows: Dict[int, List[GridPosition]] = {}
        for position in targets:
            rows.setdefault(position.y, []).append(position)

        ordered: List[GridPosition] = []
        for row_index, y in enumerate(sorted(rows)):
            row = sorted(rows[y], key=lambda position: position.x)
            if row_index % 2:
                row.reverse()
            ordered.extend(row)
        return tuple(ordered)

    @staticmethod
    def _vertical_serpentine(
        targets: Tuple[GridPosition, ...],
    ) -> Tuple[GridPosition, ...]:
        columns: Dict[int, List[GridPosition]] = {}
        for position in targets:
            columns.setdefault(position.x, []).append(position)

        ordered: List[GridPosition] = []
        for column_index, x in enumerate(sorted(columns)):
            column = sorted(columns[x], key=lambda position: position.y)
            if column_index % 2:
                column.reverse()
            ordered.extend(column)
        return tuple(ordered)
