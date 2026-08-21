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
