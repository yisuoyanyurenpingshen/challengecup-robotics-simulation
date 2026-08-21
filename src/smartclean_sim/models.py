"""Core domain models shared by the 2D cleaning simulation.

The module intentionally contains no renderer, configuration, or ROS dependencies so
the same values can later be reused by a command-line runner or an integration layer.
"""

from dataclasses import dataclass
from typing import Mapping, Sequence, Tuple


@dataclass(frozen=True, order=True)
class GridPosition:
    """An immutable integer coordinate in the simulation grid."""

    x: int
    y: int

    def __post_init__(self) -> None:
        if isinstance(self.x, bool) or not isinstance(self.x, int):
            raise TypeError("GridPosition.x must be an integer")
        if isinstance(self.y, bool) or not isinstance(self.y, int):
            raise TypeError("GridPosition.y must be an integer")

    @classmethod
    def from_value(cls, value: object) -> "GridPosition":
        """Normalize a coordinate from an object, mapping, or two-item sequence."""

        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            try:
                return cls(x=value["x"], y=value["y"])
            except KeyError as exc:
                raise ValueError("position mapping must contain x and y") from exc
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            if len(value) == 2:
                return cls(x=value[0], y=value[1])
        raise ValueError(
            "position must be a GridPosition, [x, y], or {'x': x, 'y': y}"
        )

    def manhattan_distance(self, other: "GridPosition") -> int:
        """Return four-neighbor grid distance without considering obstacles."""

        if not isinstance(other, GridPosition):
            raise TypeError("other must be a GridPosition")
        return abs(self.x - other.x) + abs(self.y - other.y)


@dataclass(frozen=True)
class TrashItem:
    """A cleanable item placed in a named area of the world."""

    item_id: str
    kind: str
    position: GridPosition
    area: str = "all"


@dataclass(frozen=True)
class CleaningTask:
    """A normalized cleaning instruction understood by the simulator."""

    target_area: str = "all"
    priority_classes: Tuple[str, ...] = ()
    avoid_types: Tuple[str, ...] = ()
    return_to_dock: bool = True
    mode: str = "clean_spots"

    def __post_init__(self) -> None:
        # Accept lists from configuration loaders while preserving immutable values.
        object.__setattr__(self, "priority_classes", tuple(self.priority_classes))
        object.__setattr__(self, "avoid_types", tuple(self.avoid_types))
        if self.mode not in ("clean_spots", "clean_area"):
            raise ValueError(
                "CleaningTask.mode must be 'clean_spots' or 'clean_area'"
            )


@dataclass
class SimulationMetrics:
    """Counters and derived rates produced by one simulation run.

    Rates are returned as fractions in the inclusive range 0.0 to 1.0.  A run with
    no targets is considered fully complete; a world with no navigable cells has
    zero coverage because no meaningful coverage denominator exists.
    """

    total_targets: int = 0
    cleaned_targets: int = 0
    path_length_cells: int = 0
    unique_visited_cells: int = 0
    navigable_cells: int = 0
    replans: int = 0
    collisions: int = 0
    returned_to_dock: bool = False
    completed: bool = False

    @property
    def completion_rate(self) -> float:
        if self.total_targets <= 0:
            return 1.0
        return min(1.0, max(0.0, self.cleaned_targets / self.total_targets))

    @property
    def coverage_rate(self) -> float:
        if self.navigable_cells <= 0:
            return 0.0
        return min(
            1.0,
            max(0.0, self.unique_visited_cells / self.navigable_cells),
        )
