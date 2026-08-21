import json
from pathlib import Path

import pytest

from smartclean_sim.html_visualization import (
    render_animation_html,
    write_animation_html,
)


class FakeResult:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return self.payload


def scenario_payload(name="compact-demo"):
    return {
        "name": name,
        "width": 3,
        "height": 2,
        "start": [0, 0],
        "dock": [0, 0],
        "static_obstacles": [[1, 1]],
        "hazards": {"water": [[2, 1]]},
        "trash": [
            {
                "id": "trash-01",
                "kind": "fallen_leaves",
                "position": [1, 0],
                "area": "gate",
            }
        ],
    }


def result_payload():
    return {
        "status": "COMPLETED",
        "final_position": [0, 0],
        "trajectory": [[0, 0], [1, 0], [0, 0]],
        "cleaned_ids": ["trash-01"],
        "events": ["IDLE -> PLANNING", "RETURNING -> COMPLETED"],
        "metrics": {
            "total_targets": 1,
            "cleaned_targets": 1,
            "path_length_cells": 2,
            "unique_visited_cells": 2,
            "navigable_cells": 5,
            "replans": 0,
            "collisions": 0,
            "returned_to_dock": True,
            "completed": True,
        },
        "rates": {"completion_rate": 1.0, "coverage_rate": 0.4},
        "trace": {
            "schema_version": 1,
            "frames": [
                {
                    "frame_index": 0,
                    "sim_step": 0,
                    "state": "PLANNING",
                    "action": "initial",
                    "robot_position": [0, 0],
                    "dynamic_obstacles": [
                        {
                            "obstacle_id": "pedestrian-01",
                            "kind": "pedestrian",
                            "position": [2, 0],
                        }
                    ],
                    "remaining_trash_ids": ["trash-01"],
                    "cleaned_ids": [],
                    "cleaned_this_frame": [],
                    "events": ["IDLE -> PLANNING"],
                },
                {
                    "frame_index": 1,
                    "sim_step": 1,
                    "state": "CLEANING",
                    "action": "clean",
                    "robot_position": [1, 0],
                    "dynamic_obstacles": [
                        {
                            "obstacle_id": "pedestrian-01",
                            "kind": "pedestrian",
                            "position": None,
                        }
                    ],
                    "remaining_trash_ids": [],
                    "cleaned_ids": ["trash-01"],
                    "cleaned_this_frame": ["trash-01"],
                    "events": ["NAVIGATING -> CLEANING (trash-01)"],
                },
                {
                    "frame_index": 2,
                    "sim_step": 2,
                    "state": "COMPLETED",
                    "action": "terminal",
                    "robot_position": [0, 0],
                    "dynamic_obstacles": [],
                    "remaining_trash_ids": [],
                    "cleaned_ids": ["trash-01"],
                    "cleaned_this_frame": [],
                    "events": ["RETURNING -> COMPLETED"],
                },
            ],
        },
    }


def embedded_payload(document):
    opening = '<script id="simulation-data" type="application/json">'
    start = document.index(opening) + len(opening)
    end = document.index("</script>", start)
    return json.loads(document[start:end])


def test_render_is_deterministic_inline_and_contains_replay_payload() -> None:
    scenario = scenario_payload()
    result = FakeResult(result_payload())

    first = render_animation_html(scenario, result, title="离线清扫演示")
    second = render_animation_html(scenario, result, title="离线清扫演示")

    assert first == second
    assert first.startswith("<!doctype html>")
    assert '<canvas id="worldCanvas"' in first
    assert 'id="playButton"' in first
    assert 'id="timeline"' in first
    assert 'id="speedSelect"' in first
    assert "pedestrian-01" in first
    assert "trash-01" in first
    assert "http://" not in first
    assert "https://" not in first
    assert "fetch(" not in first
    assert "<link" not in first
    assert " src=" not in first

    payload = embedded_payload(first)
    assert payload["schema_version"] == 1
    assert payload["scenario"] == scenario
    assert payload["result"] == result_payload()


def test_embedded_values_cannot_close_script_or_inject_title_markup() -> None:
    malicious_scenario_name = "demo</script><script>window.injected=true</script>"
    malicious_title = "Demo</title><script>window.titleInjected=true</script>"
    scenario = scenario_payload(name=malicious_scenario_name)

    document = render_animation_html(
        scenario,
        FakeResult(result_payload()),
        title=malicious_title,
    )

    assert malicious_scenario_name not in document
    assert malicious_title not in document
    assert "</script><script>window.injected=true" not in document
    assert "</title><script>window.titleInjected=true" not in document
    assert "\\u003c/script\\u003e\\u003cscript\\u003e" in document
    assert "&lt;/title&gt;&lt;script&gt;" in document
    assert embedded_payload(document)["scenario"]["name"] == malicious_scenario_name


def test_write_animation_html_creates_parent_and_writes_utf8(tmp_path: Path) -> None:
    scenario = scenario_payload(name="教学楼门口")
    result = FakeResult(result_payload())
    destination = tmp_path / "nested" / "animation.html"

    written = write_animation_html(
        scenario,
        result,
        destination,
        title="智慧环卫动画",
    )

    assert written == destination
    assert written.is_file()
    assert written.read_text(encoding="utf-8") == render_animation_html(
        scenario,
        result,
        title="智慧环卫动画",
    )
    assert "教学楼门口" in written.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("scenario", "result", "title", "message"),
    [
        ([], FakeResult(result_payload()), "demo", "scenario must be a mapping"),
        (scenario_payload(), object(), "demo", "result must provide to_dict()"),
        (scenario_payload(), FakeResult([]), "demo", "must return a mapping"),
        (scenario_payload(), FakeResult(result_payload()), 3, "title must be a string"),
    ],
)
def test_render_rejects_invalid_inputs(scenario, result, title, message) -> None:
    with pytest.raises(TypeError, match=message):
        render_animation_html(scenario, result, title=title)
