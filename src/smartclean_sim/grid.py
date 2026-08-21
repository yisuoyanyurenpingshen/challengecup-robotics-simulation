"""Grid-world representation for the deterministic 2D cleaning simulation."""

from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, Union

from .models import GridPosition, TrashItem


PositionValue = Union[GridPosition, Sequence[int], Mapping]


def _position_from_value(value: PositionValue, field_name: str) -> GridPosition:
    """Convert common JSON/YAML coordinate forms to :class:`GridPosition`."""

    try:
        return GridPosition.from_value(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid coordinate for {}: {}".format(field_name, exc)) from exc


class GridWorld:
    """A rectangular grid containing obstacles, hazards, and cleanable trash.

    Static obstacles are always blocked.  Hazards are semantic cells and are only
    blocked when their type is present in ``avoid_types``.  This lets two tasks use
    the same map with different safety policies.
    """

    _NEIGHBOR_OFFSETS = ((1, 0), (0, 1), (-1, 0), (0, -1))

    def __init__(
        self,
        width: int,
        height: int,
        start: GridPosition,
        dock: GridPosition,
        static_obstacles: Optional[Iterable[GridPosition]] = None,
        hazards: Optional[Mapping[str, Iterable[GridPosition]]] = None,
        trash: Optional[Iterable[TrashItem]] = None,
    ) -> None:
        if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
            raise ValueError("width must be a positive integer")
        if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
            raise ValueError("height must be a positive integer")

        self.width = width
        self.height = height
        self.start = start
        self.dock = dock
        self.static_obstacles: Set[GridPosition] = set(static_obstacles or ())
        self.hazards: Dict[str, Set[GridPosition]] = {
            kind: set(positions) for kind, positions in (hazards or {}).items()
        }
        self.trash: List[TrashItem] = list(trash or ())

        self._validate_contents()

    @classmethod
    def from_dict(cls, payload: Mapping) -> "GridWorld":
        """Build a world from a JSON/YAML-compatible mapping.

        Coordinates may be written as ``[x, y]`` or ``{"x": x, "y": y}``.
        Hazards accept either a mapping such as ``{"water": [[1, 2]]}`` or a
        list such as ``[{"kind": "water", "position": [1, 2]}]``.
        """

        if not isinstance(payload, Mapping):
            raise TypeError("world payload must be a mapping")

        try:
            width = payload["width"]
            height = payload["height"]
            start = _position_from_value(payload["start"], "start")
        except KeyError as exc:
            raise ValueError("missing required world field: {}".format(exc.args[0])) from exc

        dock = _position_from_value(payload.get("dock", start), "dock")
        obstacles = {
            _position_from_value(value, "static_obstacles")
            for value in payload.get("static_obstacles", ())
        }
        hazards = cls._parse_hazards(payload.get("hazards", {}))
        trash = cls._parse_trash(payload.get("trash", ()))

        return cls(
            width=width,
            height=height,
            start=start,
            dock=dock,
            static_obstacles=obstacles,
            hazards=hazards,
            trash=trash,
        )

    @staticmethod
    def _parse_hazards(raw_hazards: object) -> Dict[str, Set[GridPosition]]:
        parsed: Dict[str, Set[GridPosition]] = {}
        if raw_hazards is None:
            return parsed

        if isinstance(raw_hazards, Mapping):
            for kind, positions in raw_hazards.items():
                if not isinstance(kind, str) or not kind:
                    raise ValueError("hazard type must be a non-empty string")
                parsed[kind] = {
                    _position_from_value(value, "hazards.{}".format(kind))
                    for value in positions
                }
            return parsed

        if isinstance(raw_hazards, Sequence) and not isinstance(
            raw_hazards, (str, bytes)
        ):
            for index, entry in enumerate(raw_hazards):
                if not isinstance(entry, Mapping):
                    raise ValueError("hazards[{}] must be a mapping".format(index))
                kind = entry.get("kind", entry.get("type"))
                if not isinstance(kind, str) or not kind:
                    raise ValueError(
                        "hazards[{}] must contain a non-empty kind".format(index)
                    )
                if "positions" in entry:
                    values = entry["positions"]
                elif "position" in entry:
                    values = (entry["position"],)
                else:
                    raise ValueError(
                        "hazards[{}] must contain position or positions".format(index)
                    )
                parsed.setdefault(kind, set()).update(
                    _position_from_value(value, "hazards[{}]".format(index))
                    for value in values
                )
            return parsed

        raise ValueError("hazards must be a mapping or a list of mappings")

    @staticmethod
    def _parse_trash(raw_trash: object) -> List[TrashItem]:
        if raw_trash is None:
            return []
        if not isinstance(raw_trash, Sequence) or isinstance(raw_trash, (str, bytes)):
            raise ValueError("trash must be a list")

        parsed: List[TrashItem] = []
        for index, entry in enumerate(raw_trash):
            if isinstance(entry, TrashItem):
                parsed.append(entry)
                continue
            if not isinstance(entry, Mapping):
                raise ValueError("trash[{}] must be a mapping".format(index))
            item_id = entry.get("item_id", entry.get("id"))
            kind = entry.get("kind", entry.get("type"))
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(
                    "trash[{}] must contain a non-empty item_id".format(index)
                )
            if not isinstance(kind, str) or not kind:
                raise ValueError(
                    "trash[{}] must contain a non-empty kind".format(index)
                )
            if "position" not in entry:
                raise ValueError("trash[{}] must contain position".format(index))
            area = entry.get("area", "all")
            if not isinstance(area, str) or not area:
                raise ValueError("trash[{}].area must be a non-empty string".format(index))
            parsed.append(
                TrashItem(
                    item_id=item_id,
                    kind=kind,
                    position=_position_from_value(
                        entry["position"], "trash[{}].position".format(index)
                    ),
                    area=area,
                )
            )
        return parsed

    def _validate_contents(self) -> None:
        named_positions = (("start", self.start), ("dock", self.dock))
        for name, position in named_positions:
            if not self.in_bounds(position):
                raise ValueError("{} position is outside the world".format(name))
            if position in self.static_obstacles:
                raise ValueError("{} position cannot be a static obstacle".format(name))

        for position in self.static_obstacles:
            if not self.in_bounds(position):
                raise ValueError("static obstacle is outside the world: {}".format(position))

        for kind, positions in self.hazards.items():
            if not isinstance(kind, str) or not kind:
                raise ValueError("hazard type must be a non-empty string")
            for position in positions:
                if not self.in_bounds(position):
                    raise ValueError(
                        "{} hazard is outside the world: {}".format(kind, position)
                    )

        seen_ids: Set[str] = set()
        for item in self.trash:
            if item.item_id in seen_ids:
                raise ValueError("duplicate trash item_id: {}".format(item.item_id))
            seen_ids.add(item.item_id)
            if not self.in_bounds(item.position):
                raise ValueError(
                    "trash item {} is outside the world".format(item.item_id)
                )
            if item.position in self.static_obstacles:
                raise ValueError(
                    "trash item {} cannot occupy a static obstacle".format(item.item_id)
                )

    def in_bounds(self, position: GridPosition) -> bool:
        return 0 <= position.x < self.width and 0 <= position.y < self.height

    def is_blocked(
        self,
        position: GridPosition,
        avoid_types: Iterable[str] = (),
    ) -> bool:
        if not self.in_bounds(position) or position in self.static_obstacles:
            return True
        avoided = set(avoid_types)
        return any(position in self.hazards.get(kind, ()) for kind in avoided)

    def neighbors(
        self,
        position: GridPosition,
        avoid_types: Iterable[str] = (),
        extra_blocked: Optional[Iterable[GridPosition]] = None,
    ) -> Tuple[GridPosition, ...]:
        """Return traversable four-neighbors in a stable deterministic order."""

        blocked = set(extra_blocked or ())
        candidates = (
            GridPosition(position.x + dx, position.y + dy)
            for dx, dy in self._NEIGHBOR_OFFSETS
        )
        return tuple(
            candidate
            for candidate in candidates
            if candidate not in blocked and not self.is_blocked(candidate, avoid_types)
        )

    def remaining_trash(
        self,
        target_area: str = "all",
        kinds: Iterable[str] = (),
    ) -> Tuple[TrashItem, ...]:
        selected_kinds = set(kinds)
        return tuple(
            item
            for item in self.trash
            if (target_area == "all" or item.area == target_area)
            and (not selected_kinds or item.kind in selected_kinds)
        )

    def clean_at(
        self,
        position: GridPosition,
        target_area: str = "all",
        kinds: Iterable[str] = (),
    ) -> Optional[TrashItem]:
        """Remove and return the first task-matching item at ``position``.

        Returning one item keeps cleaning events and metrics unambiguous.  A caller
        may call the method again when a cell intentionally contains several items.
        """

        selected_kinds = set(kinds)
        for index, item in enumerate(self.trash):
            if (
                item.position == position
                and (target_area == "all" or item.area == target_area)
                and (not selected_kinds or item.kind in selected_kinds)
            ):
                return self.trash.pop(index)
        return None

    def hazard_types_at(self, position: GridPosition) -> Tuple[str, ...]:
        return tuple(
            sorted(kind for kind, positions in self.hazards.items() if position in positions)
        )

    def traversable_count(self, avoid_types: Iterable[str] = ()) -> int:
        return sum(
            1
            for y in range(self.height)
            for x in range(self.width)
            if not self.is_blocked(GridPosition(x, y), avoid_types)
        )
