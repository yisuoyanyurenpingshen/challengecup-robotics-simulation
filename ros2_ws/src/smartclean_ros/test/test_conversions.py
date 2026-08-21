from math import inf, nan

import pytest

from smartclean_ros.conversions import CoordinateTransformError, GridMapTransform


def test_grid_corners_map_to_metric_cell_centers_with_y_flipped() -> None:
    transform = GridMapTransform(
        grid_width=12,
        grid_height=8,
        cell_size_m=0.5,
        origin_x_m=-1.0,
        origin_y_m=2.0,
    )

    assert transform.grid_to_map(0, 0) == pytest.approx((-0.75, 5.75))
    assert transform.grid_to_map(11, 7) == pytest.approx((4.75, 2.25))
    assert transform.grid_to_map(3, 2) == pytest.approx((0.75, 4.75))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"grid_width": 0, "grid_height": 1},
        {"grid_width": True, "grid_height": 1},
        {"grid_width": 1, "grid_height": -1},
        {"grid_width": 1, "grid_height": 1, "cell_size_m": 0.0},
        {"grid_width": 1, "grid_height": 1, "cell_size_m": nan},
        {"grid_width": 1, "grid_height": 1, "origin_x_m": inf},
    ],
)
def test_invalid_transform_geometry_is_rejected(kwargs) -> None:
    with pytest.raises(CoordinateTransformError):
        GridMapTransform(**kwargs)


@pytest.mark.parametrize(
    "coordinate",
    [(-1, 0), (2, 0), (0, -1), (0, 2), (0.5, 0), (0, True)],
)
def test_invalid_or_out_of_bounds_grid_coordinate_is_rejected(coordinate) -> None:
    transform = GridMapTransform(grid_width=2, grid_height=2)

    with pytest.raises(CoordinateTransformError):
        transform.grid_to_map(*coordinate)
