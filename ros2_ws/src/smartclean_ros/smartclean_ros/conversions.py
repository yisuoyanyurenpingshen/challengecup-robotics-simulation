"""Pure coordinate conversions between the grid core and a ROS ``map`` frame."""

from dataclasses import dataclass
from math import isfinite
from typing import Tuple


class CoordinateTransformError(ValueError):
    """The grid geometry or coordinate cannot be converted safely."""


def _positive_integer(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CoordinateTransformError("{} 必须是正整数".format(name))
    return value


def _finite_number(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CoordinateTransformError("{} 必须是有限数值".format(name))
    normalized = float(value)
    if not isfinite(normalized):
        raise CoordinateTransformError("{} 必须是有限数值".format(name))
    return normalized


@dataclass(frozen=True)
class GridMapTransform:
    """Convert top-left-origin grid-cell coordinates to ROS map-cell centers.

    The deterministic core uses ``x`` right, ``y`` down and integer cells.  ROS
    uses a right-handed metric map where ``y`` points up.  ``origin_*`` denotes
    the lower-left corner of the complete grid, not the center of cell (0, 0).
    """

    grid_width: int
    grid_height: int
    cell_size_m: float = 1.0
    origin_x_m: float = 0.0
    origin_y_m: float = 0.0

    def __post_init__(self) -> None:
        _positive_integer("grid_width", self.grid_width)
        _positive_integer("grid_height", self.grid_height)
        cell_size = _finite_number("cell_size_m", self.cell_size_m)
        if cell_size <= 0.0:
            raise CoordinateTransformError("cell_size_m 必须大于 0")
        origin_x = _finite_number("origin_x_m", self.origin_x_m)
        origin_y = _finite_number("origin_y_m", self.origin_y_m)
        object.__setattr__(self, "cell_size_m", cell_size)
        object.__setattr__(self, "origin_x_m", origin_x)
        object.__setattr__(self, "origin_y_m", origin_y)

    def grid_to_map(self, grid_x: int, grid_y: int) -> Tuple[float, float]:
        """Return the metric center of an in-bounds grid cell."""

        if isinstance(grid_x, bool) or not isinstance(grid_x, int):
            raise CoordinateTransformError("grid_x 必须是整数")
        if isinstance(grid_y, bool) or not isinstance(grid_y, int):
            raise CoordinateTransformError("grid_y 必须是整数")
        if not 0 <= grid_x < self.grid_width:
            raise CoordinateTransformError(
                "grid_x={} 超出 [0, {})".format(grid_x, self.grid_width)
            )
        if not 0 <= grid_y < self.grid_height:
            raise CoordinateTransformError(
                "grid_y={} 超出 [0, {})".format(grid_y, self.grid_height)
            )

        map_x = self.origin_x_m + (grid_x + 0.5) * self.cell_size_m
        map_y = (
            self.origin_y_m
            + (self.grid_height - grid_y - 0.5) * self.cell_size_m
        )
        return map_x, map_y
