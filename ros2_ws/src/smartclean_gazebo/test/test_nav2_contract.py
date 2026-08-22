"""Static contracts for the SmartClean Nav2 map, params and launch files."""

from pathlib import Path

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
MAPS_DIR = PACKAGE_ROOT / "maps"
CONFIG_DIR = PACKAGE_ROOT / "config"
LAUNCH_DIR = PACKAGE_ROOT / "launch"

MAP_YAML = MAPS_DIR / "smartclean_arena.yaml"
MAP_PGM = MAPS_DIR / "smartclean_arena.pgm"
NAV2_PARAMS = CONFIG_DIR / "nav2_params.yaml"
NAV2_LAUNCH = LAUNCH_DIR / "nav2.launch.py"


def _params() -> dict:
    return yaml.safe_load(NAV2_PARAMS.read_text(encoding="utf-8"))


def test_map_yaml_is_consistent_with_world() -> None:
    text = MAP_YAML.read_text(encoding="utf-8")
    assert "image: smartclean_arena.pgm" in text
    assert "resolution: 0.05" in text
    assert "origin: [-10.0, -8.0, 0.0]" in text
    assert "negate: 0" in text
    assert MAP_PGM.is_file()
    assert MAP_PGM.stat().st_size > 1000


def test_pgm_header_matches_expected_size() -> None:
    data = MAP_PGM.read_bytes()
    assert data.startswith(b"P5\n400 320\n255\n")
    pixels = data[len(b"P5\n400 320\n255\n"):]
    assert len(pixels) == 400 * 320
    values = set(pixels)
    assert values <= {0, 254}


def test_nav2_params_use_sim_time_and_frames() -> None:
    params = _params()
    amcl = params["amcl"]["ros__parameters"]
    assert amcl["use_sim_time"] is True
    assert amcl["base_frame_id"] == "base_footprint"
    assert amcl["odom_frame_id"] == "odom"
    assert amcl["global_frame_id"] == "map"
    assert amcl["scan_topic"] == "scan"
    assert amcl["set_initial_pose"] is True
    assert amcl["initial_pose"]["x"] == 0.0
    assert amcl["initial_pose"]["y"] == 0.0
    assert amcl["initial_pose"]["yaw"] == 0.0

    local = params["local_costmap"]["local_costmap"]["ros__parameters"]
    assert local["global_frame"] == "odom"
    assert local["robot_base_frame"] == "base_link"
    assert "0.45" in local["footprint"]

    global_costmap = params["global_costmap"]["global_costmap"]["ros__parameters"]
    assert global_costmap["global_frame"] == "map"
    assert global_costmap["robot_base_frame"] == "base_link"
    assert "0.45" in global_costmap["footprint"]

    controller = params["controller_server"]["ros__parameters"]
    assert controller["FollowPath"]["max_vel_x"] <= 1.2
    assert controller["general_goal_checker"]["xy_goal_tolerance"] == 0.08
    assert controller["FollowPath"]["xy_goal_tolerance"] == 0.08


def test_nav2_launch_combines_drive_localization_navigation() -> None:
    text = NAV2_LAUNCH.read_text(encoding="utf-8")
    assert "drive.launch.py" in text
    assert "localization_launch.py" in text
    assert "navigation_launch.py" in text
    assert "smartclean_trash.sdf" in text
    assert "smartclean_arena.yaml" in text
    assert "nav2_params.yaml" in text
    assert 'use_sim_time": "true"' in text
    assert "use_composition\": \"False\"" in text


def test_nav2_params_reference_local_scan_only() -> None:
    params = _params()
    local = params["local_costmap"]["local_costmap"]["ros__parameters"]
    observation_sources = local["voxel_layer"]["observation_sources"]
    assert observation_sources == "scan"
    scan_topic = local["voxel_layer"]["scan"]["topic"]
    assert scan_topic == "/scan"


def test_nav2_probe_requires_succeeded_action_status() -> None:
    probe = (REPO_ROOT / "scripts" / "nav2_probe.py").read_text(
        encoding="utf-8"
    )
    assert "GoalStatus.STATUS_SUCCEEDED" in probe
    assert "result.status != GoalStatus.STATUS_SUCCEEDED" in probe
    assert "bool(result.result" not in probe
