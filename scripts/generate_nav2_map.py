#!/usr/bin/env python3
"""Generate the SmartClean arena static map (PGM + YAML) for Nav2.

The Gazebo trash world is a 20 x 16 m plane. The map uses the full plane with
its origin at world (-10, -8), so world (0, 0) equals map (10, 8) and pixel
(200, 160) at 0.05 m/pixel. Static obstacles mirror the world:

  - north_planter: cylinder, world (4, 3), radius 0.8 m (+0.08 margin);
  - waste_bin: box, world (-4, -3), 0.75 x 0.75 m (+0.08 margin).

Trash items are intentionally absent: they are small dynamic-looking objects
that the LiDAR observes at runtime. Output is deterministic and offline
(numpy only, no Gazebo/Fuel access).
"""

import argparse
from pathlib import Path

import numpy as np

WORLD_WIDTH_M = 20.0
WORLD_HEIGHT_M = 16.0
RESOLUTION_M = 0.05
ORIGIN_X = -10.0
ORIGIN_Y = -8.0

FREE = 254
OCCUPIED = 0
BORDER_CELLS = 2
OBSTACLE_MARGIN_M = 0.08

OBSTACLES = [
    {"kind": "circle", "x": 4.0, "y": 3.0, "r": 0.8},
    {"kind": "box", "x": -4.0, "y": -3.0, "half_x": 0.375, "half_y": 0.375},
]


def world_to_cell(x: float, y: float, width: int, height: int):
    column = int(round((x - ORIGIN_X) / RESOLUTION_M))
    row = int(round((ORIGIN_Y + WORLD_HEIGHT_M - y) / RESOLUTION_M))
    return column, row


def generate(width: int, height: int) -> np.ndarray:
    grid = np.full((height, width), FREE, dtype=np.uint8)
    grid[:BORDER_CELLS, :] = OCCUPIED
    grid[-BORDER_CELLS:, :] = OCCUPIED
    grid[:, :BORDER_CELLS] = OCCUPIED
    grid[:, -BORDER_CELLS:] = OCCUPIED

    xs = np.arange(width, dtype=np.float64)
    ys = np.arange(height, dtype=np.float64)
    world_x = ORIGIN_X + (xs + 0.5) * RESOLUTION_M
    world_y = ORIGIN_Y + WORLD_HEIGHT_M - (ys + 0.5) * RESOLUTION_M
    grid_x, grid_y = np.meshgrid(world_x, world_y)

    for obstacle in OBSTACLES:
        if obstacle["kind"] == "circle":
            radius = obstacle["r"] + OBSTACLE_MARGIN_M
            inside = (grid_x - obstacle["x"]) ** 2 + (
                grid_y - obstacle["y"]
            ) ** 2 <= radius**2
        elif obstacle["kind"] == "box":
            half_x = obstacle["half_x"] + OBSTACLE_MARGIN_M
            half_y = obstacle["half_y"] + OBSTACLE_MARGIN_M
            inside = (
                (np.abs(grid_x - obstacle["x"]) <= half_x)
                & (np.abs(grid_y - obstacle["y"]) <= half_y)
            )
        else:
            raise RuntimeError("未知障碍物类型：{}".format(obstacle["kind"]))
        grid[inside] = OCCUPIED
    return grid


def write_pgm(grid: np.ndarray, path: Path) -> None:
    header = "P5\n{} {}\n255\n".format(grid.shape[1], grid.shape[0])
    path.write_bytes(header.encode("ascii") + grid.tobytes())


def write_yaml(pgm_name: str, path: Path) -> None:
    text = (
        "image: {}\n"
        "mode: trinary\n"
        "resolution: {}\n"
        "origin: [{}, {}, 0.0]\n"
        "negate: 0\n"
        "occupied_thresh: 0.65\n"
        "free_thresh: 0.196\n"
    ).format(
        pgm_name,
        RESOLUTION_M,
        ORIGIN_X,
        ORIGIN_Y,
    )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="ros2_ws/src/smartclean_gazebo/maps",
        help="Directory that receives smartclean_arena.pgm/.yaml",
    )
    args = parser.parse_args()

    width = int(round(WORLD_WIDTH_M / RESOLUTION_M))
    height = int(round(WORLD_HEIGHT_M / RESOLUTION_M))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    grid = generate(width, height)
    write_pgm(grid, output_dir / "smartclean_arena.pgm")
    write_yaml("smartclean_arena.pgm", output_dir / "smartclean_arena.yaml")

    occupied_ratio = float((grid == OCCUPIED).mean())
    print(
        "已生成 {}x{} 地图：origin=({},{}), 分辨率={}m, 占用率={:.2%}".format(
            width,
            height,
            ORIGIN_X,
            ORIGIN_Y,
            RESOLUTION_M,
            occupied_ratio,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
