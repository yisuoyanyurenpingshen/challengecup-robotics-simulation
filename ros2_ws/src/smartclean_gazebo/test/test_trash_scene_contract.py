"""Static contracts for the local Gazebo trash scene.

The scene reuses the canonical trash classes of the 2D core
(smartclean_sim.models.TRASH_CLASSES) instead of inventing a second,
incompatible taxonomy. Ground truth lives in configs/gazebo_scene.json and is
used for evaluation and mission orchestration only, never as perception input.
"""

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

from smartclean_sim.models import TRASH_CLASSES


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
MODELS_DIRECTORY = PACKAGE_ROOT / "models"
WORLD_PATH = PACKAGE_ROOT / "worlds" / "smartclean_trash.sdf"
SCENE_PATH = REPO_ROOT / "configs" / "gazebo_scene.json"


def _scene() -> dict:
    return json.loads(SCENE_PATH.read_text(encoding="utf-8"))


def _xml_root(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def test_scene_config_has_at_least_four_canonical_classes() -> None:
    scene = _scene()

    assert scene["schema_version"] == 1
    assert scene["kind"] == "gazebo_trash_ground_truth"
    assert scene["world_name"] == "smartclean_trash"

    classes = {item["class_name"] for item in scene["trash"]}
    assert len(classes) >= 4
    assert classes <= set(TRASH_CLASSES)
    assert len(scene["trash"]) >= 4


def test_scene_objects_have_stable_unique_ids_and_finite_poses() -> None:
    scene = _scene()

    ids = [item["object_id"] for item in scene["trash"]]
    assert len(ids) == len(set(ids))
    for item in scene["trash"]:
        assert item["object_id"].startswith("trash_")
        position = item["position"]
        for component in (position["x"], position["y"], position["z"]):
            assert math.isfinite(component)
        assert 0.0 <= position["z"] < 0.5
        assert math.isfinite(item["yaw"])


def test_every_scene_model_is_a_local_self_contained_sdf() -> None:
    scene = _scene()

    for item in scene["trash"]:
        model_dir = MODELS_DIRECTORY / item["model_name"]
        assert model_dir.is_dir(), "missing model directory {}".format(model_dir)
        config_path = model_dir / "model.config"
        sdf_path = model_dir / "model.sdf"
        assert config_path.is_file()
        assert sdf_path.is_file()

        model = _xml_root(sdf_path).find("model")
        assert model is not None
        assert model.attrib["name"] == item["model_name"]

        text = sdf_path.read_text(encoding="utf-8").lower()
        assert "http://" not in text
        assert "https://" not in text
        assert "fuel.gazebosim.org" not in text
        assert "<mesh" not in text

        link = model.find("link")
        assert link is not None
        assert link.find("collision") is not None
        assert link.find("visual") is not None
        # Static so that cleaning via entity removal is deterministic.
        static = model.find("static")
        assert static is not None and static.text.strip() == "true"


def test_trash_sizes_are_suitable_for_camera_recognition() -> None:
    scene = _scene()

    for item in scene["trash"]:
        sdf_path = MODELS_DIRECTORY / item["model_name"] / "model.sdf"
        model = _xml_root(sdf_path).find("model")
        assert model is not None

        sizes = []
        for geometry in model.findall(".//collision/geometry"):
            for primitive in geometry:
                sizes.append(primitive)
        assert sizes, "model has no collision geometry"

        spans = []
        for primitive in sizes:
            tag = primitive.tag
            if tag in ("box", "cylinder"):
                if tag == "box":
                    values = [float(v) for v in primitive.find("size").text.split()]
                else:
                    radius = float(primitive.find("radius").text)
                    length = float(primitive.find("length").text)
                    values = [2.0 * radius, 2.0 * radius, length]
                spans.append(values)
        assert spans
        # The smallest span must still be image-visible, the largest must not
        # turn the trash into a navigation obstacle.
        for values in spans:
            assert 0.008 <= min(values) <= 0.5
            assert max(values) <= 0.6


def test_world_includes_robot_and_all_ground_truth_trash() -> None:
    scene = _scene()
    world = _xml_root(WORLD_PATH).find("world")
    assert world is not None
    assert world.attrib["name"] == "smartclean_trash"

    includes = world.findall("include")
    expected_names = {item["model_name"] for item in scene["trash"]}
    expected_names.add("smartclean_robot")
    actual_names = {include.find("name").text.strip() for include in includes}
    assert actual_names == expected_names

    for include in includes:
        uri = include.find("uri").text.strip()
        assert uri.startswith("model://")
        model_dir = MODELS_DIRECTORY / uri[len("model://") :]
        assert model_dir.is_dir()

    world_text = WORLD_PATH.read_text(encoding="utf-8").lower()
    assert "http://" not in world_text
    assert "fuel.gazebosim.org" not in world_text


def test_scene_config_classes_match_task_parser_aliases() -> None:
    """paper_cup and aluminum_can must be reachable from Chinese instructions."""

    tasking = (REPO_ROOT / "src" / "smartclean_sim" / "tasking.py").read_text(
        encoding="utf-8"
    )
    for class_name in TRASH_CLASSES:
        assert class_name in tasking
