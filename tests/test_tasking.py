from smartclean_sim.tasking import RuleBasedTaskParser, task_from_dict


def test_parse_chinese_instruction() -> None:
    task = RuleBasedTaskParser().parse(
        "清扫教学楼门口，优先处理落叶和塑料瓶，绕开积水和行人，完成后返航。"
    )

    assert task.target_area == "teaching_building_gate"
    assert task.priority_classes == ("fallen_leaves", "plastic_bottle")
    assert task.avoid_types == ("water", "pedestrian")
    assert task.return_to_dock is True
    assert task.mode == "clean_spots"


def test_structured_fields_override_instruction() -> None:
    task = task_from_dict(
        {
            "instruction": "清扫教学楼，不用返航",
            "priority_classes": ["paper_scrap"],
            "avoid_types": ["water"],
        }
    )

    assert task.priority_classes == ("paper_scrap",)
    assert task.avoid_types == ("water",)
    assert task.return_to_dock is False


def test_external_return_after_done_alias_is_supported() -> None:
    task = task_from_dict(
        {
            "target_area": "gate",
            "priority_classes": [],
            "avoid_types": [],
            "return_after_done": False,
        }
    )

    assert task.return_to_dock is False


def test_explicit_coverage_instruction_uses_clean_area_mode() -> None:
    task = RuleBasedTaskParser().parse(
        "全覆盖清扫教学楼门口，绕开积水和行人，完成后返航。"
    )

    assert task.mode == "clean_area"
    assert task.target_area == "teaching_building_gate"


def test_structured_mode_overrides_instruction() -> None:
    task = task_from_dict(
        {
            "instruction": "全覆盖清扫教学楼门口",
            "mode": "clean_spots",
        }
    )

    assert task.mode == "clean_spots"
