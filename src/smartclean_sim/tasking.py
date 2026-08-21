"""把自然语言或结构化配置转换成安全、可校验的清扫任务。"""

from typing import Any, Dict, Iterable, List, Tuple

from smartclean_sim.models import CleaningTask


class TaskParseError(ValueError):
    """任务无法解析或字段不合法。"""


class RuleBasedTaskParser:
    """离线、确定性的中文任务解析器。

    该解析器是演示基线。后续 LLM 适配器也必须输出同一个
    ``CleaningTask``，并经过相同校验后才能交给执行器。
    """

    AREA_ALIASES = (
        ("教学楼门口", "teaching_building_gate"),
        ("教学楼", "teaching_building_gate"),
        ("校园道路", "campus_road"),
        ("停车场", "parking_lot"),
        ("全部区域", "all"),
        ("全区域", "all"),
    )
    CLASS_ALIASES = (
        ("落叶", "fallen_leaves"),
        ("塑料瓶", "plastic_bottle"),
        ("瓶子", "plastic_bottle"),
        ("纸屑", "paper_scrap"),
    )
    AVOID_ALIASES = (
        ("积水", "water"),
        ("水坑", "water"),
        ("行人", "pedestrian"),
        ("车辆", "vehicle"),
    )

    def parse(self, instruction: str) -> CleaningTask:
        if not isinstance(instruction, str) or not instruction.strip():
            raise TaskParseError("自然语言任务不能为空")

        target_area = "all"
        for alias, canonical in self.AREA_ALIASES:
            if alias in instruction:
                target_area = canonical
                break

        priority_classes = self._ordered_matches(instruction, self.CLASS_ALIASES)
        avoid_types = self._ordered_matches(instruction, self.AVOID_ALIASES)
        negative_return = any(
            phrase in instruction
            for phrase in ("不返航", "无需返航", "不用返航", "不要返航")
        )
        explicit_return = any(
            phrase in instruction
            for phrase in ("返航", "回充", "返回充电", "返回待命")
        )
        return_after_done = explicit_return and not negative_return

        return CleaningTask(
            target_area=target_area,
            priority_classes=priority_classes,
            avoid_types=avoid_types,
            return_to_dock=return_after_done,
        )

    @staticmethod
    def _ordered_matches(
        instruction: str, aliases: Iterable[Tuple[str, str]]
    ) -> Tuple[str, ...]:
        matches: List[Tuple[int, str]] = []
        for alias, canonical in aliases:
            index = instruction.find(alias)
            if index >= 0 and canonical not in [item[1] for item in matches]:
                matches.append((index, canonical))
        matches.sort(key=lambda item: item[0])
        return tuple(item[1] for item in matches)


def task_from_dict(payload: Dict[str, Any]) -> CleaningTask:
    if not isinstance(payload, dict):
        raise TaskParseError("task 必须是对象")

    if "instruction" in payload:
        task = RuleBasedTaskParser().parse(payload["instruction"])
    else:
        task = CleaningTask()

    target_area = payload.get("target_area", task.target_area)
    priority_classes = payload.get("priority_classes", task.priority_classes)
    avoid_types = payload.get("avoid_types", task.avoid_types)
    return_to_dock = payload.get(
        "return_to_dock",
        payload.get("return_after_done", task.return_to_dock),
    )

    if not isinstance(target_area, str) or not target_area.strip():
        raise TaskParseError("target_area 必须是非空字符串")
    if not _is_string_list(priority_classes):
        raise TaskParseError("priority_classes 必须是字符串列表")
    if not _is_string_list(avoid_types):
        raise TaskParseError("avoid_types 必须是字符串列表")
    if not isinstance(return_to_dock, bool):
        raise TaskParseError("return_to_dock 必须是布尔值")

    return CleaningTask(
        target_area=target_area.strip(),
        priority_classes=tuple(priority_classes),
        avoid_types=tuple(avoid_types),
        return_to_dock=return_to_dock,
    )


def _is_string_list(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and all(
        isinstance(item, str) and item for item in value
    )
