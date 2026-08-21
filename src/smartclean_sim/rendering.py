"""无额外依赖的终端地图渲染。"""

from typing import Dict, Optional, Sequence, Set

from smartclean_sim.grid import GridWorld
from smartclean_sim.models import GridPosition, TRASH_CLASSES


TRASH_SYMBOLS: Dict[str, str] = {
    "fallen_leaves": "L",
    "plastic_bottle": "B",
    "paper_scrap": "P",
    "paper_cup": "C",
    "aluminum_can": "A",
}


def render_ascii(
    world: GridWorld,
    trajectory: Sequence[GridPosition] = (),
    current: Optional[GridPosition] = None,
) -> str:
    route: Set[GridPosition] = set(trajectory)
    trash_by_position = {
        item.position: item for item in world.remaining_trash("all")
    }
    rows = []
    for y in range(world.height):
        symbols = []
        for x in range(world.width):
            point = GridPosition(x, y)
            symbol = "."
            if point in world.static_obstacles:
                symbol = "#"
            elif any(point in cells for cells in world.hazards.values()):
                symbol = "W"
            elif point in route:
                symbol = "*"
            if point in trash_by_position:
                symbol = TRASH_SYMBOLS.get(trash_by_position[point].kind, "T")
            if point == world.dock:
                symbol = "D"
            if current is not None and point == current:
                symbol = "R"
            symbols.append(symbol)
        rows.append("".join(symbols))
    return "\n".join(rows)
