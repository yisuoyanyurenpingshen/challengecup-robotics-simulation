"""Static contracts for the end-to-end Gazebo trash mission launch."""

import ast
from pathlib import Path
import subprocess


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
MISSION_LAUNCH = PACKAGE_ROOT / "launch" / "trash_mission.launch.py"
NAV2_LAUNCH = PACKAGE_ROOT / "launch" / "nav2.launch.py"
MISSION_SCRIPT = REPO_ROOT / "scripts" / "gazebo_trash_mission.sh"
ROS2_SCRIPT = REPO_ROOT / "scripts" / "ros2.sh"
PIXI_MANIFEST = REPO_ROOT / "pixi.toml"


def _launch_text() -> str:
    return MISSION_LAUNCH.read_text(encoding="utf-8")


def _assigned_dict(name: str) -> dict:
    tree = ast.parse(_launch_text())
    constants = {
        "DELETE_ENTITY_SERVICE": "/world/smartclean_trash/remove",
        "PRIORITY_CLASSES": ["fallen_leaves", "plastic_bottle"],
    }
    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == name
            for target in statement.targets
        ):
            continue
        expression = ast.fix_missing_locations(statement.value)
        compiled = compile(
            ast.Expression(expression), str(MISSION_LAUNCH), "eval"
        )
        value = eval(compiled, {"__builtins__": {}}, constants)
        assert isinstance(value, dict)
        return value
    raise AssertionError("missing launch dictionary {}".format(name))


def test_launch_composes_nav2_detector_bridge_and_controller() -> None:
    text = _launch_text()
    for required in (
        "nav2.launch.py",
        'package="smartclean_perception"',
        'executable="trash_detector"',
        'package="ros_gz_bridge"',
        'executable="parameter_bridge"',
        'package="smartclean_ros"',
        'executable="trash_mission_controller"',
    ):
        assert required in text

    assert (
        "/world/smartclean_trash/remove@ros_gz_interfaces/srv/DeleteEntity"
        in text.replace("\n", "").replace(" ", "")
    )


def test_launch_enables_camera_and_forwards_user_view_arguments() -> None:
    text = _launch_text()
    assert '"camera": "true"' in text
    for argument in ("gui", "rviz", "record"):
        assert '"{}": LaunchConfiguration("{}")'.format(argument, argument) in text
        assert '"{}",\n'.format(argument) in text

    nav2_text = NAV2_LAUNCH.read_text(encoding="utf-8")
    assert '"record",\n' in nav2_text
    assert '"record": LaunchConfiguration("record")' in nav2_text


def test_detector_requires_depth_positions_with_odom_tf_fallback() -> None:
    parameters = _assigned_dict("DETECTOR_PARAMETERS")
    assert parameters["use_sim_time"] is True
    assert parameters["use_depth"] is True
    assert parameters["position_frame_ids"] == ["map", "odom"]
    assert parameters["depth_topic"] == "/camera/depth/image_rect_raw"


def test_controller_parameters_keep_safe_cleaning_geometry() -> None:
    parameters = _assigned_dict("CONTROLLER_PARAMETERS")
    assert parameters["priority_classes"] == [
        "fallen_leaves",
        "plastic_bottle",
    ]
    assert parameters["cleaning_radius_m"] == 0.45
    assert parameters["robot_front_extent_m"] == 0.45
    assert parameters["cleaning_tool_offset_m"] == 0.45
    assert parameters["navigation_standoff_margin_m"] == 0.10
    assert parameters["min_observations"] == 3
    assert parameters["mission_timeout_s"] == 360.0
    assert parameters["return_after_done"] is True
    assert parameters["dock_x"] == 0.0
    assert parameters["dock_y"] == 0.0
    assert parameters["dock_yaw"] == 0.0
    assert parameters["max_return_attempts"] == 3
    assert parameters["delete_service"] == "/world/smartclean_trash/remove"


def test_controller_receives_no_gazebo_ground_truth_path() -> None:
    parameters = _assigned_dict("CONTROLLER_PARAMETERS")
    serialized = repr(parameters).lower()
    for forbidden in (
        "gazebo_scene.json",
        "ground_truth",
        "scene_path",
        "truth_path",
        "configs/",
        "model://",
    ):
        assert forbidden not in serialized


def test_shell_and_unified_entries_are_wired_and_parse() -> None:
    shell_text = MISSION_SCRIPT.read_text(encoding="utf-8")
    assert "xvfb_start" in shell_text
    assert "xvfb_stop" in shell_text
    assert "trash_mission.launch.py" in shell_text
    assert "setsid ros2 launch" in shell_text
    assert "kill -INT" in shell_text
    assert "kill -TERM" in shell_text

    ros2_text = ROS2_SCRIPT.read_text(encoding="utf-8")
    assert "trash-mission" in ros2_text
    assert "gazebo-trash-mission" in ros2_text
    assert "trash-mission-verify" in ros2_text

    pixi_text = PIXI_MANIFEST.read_text(encoding="utf-8")
    assert "gazebo-trash-mission" in pixi_text
    assert "gazebo-trash-mission-verify" in pixi_text
    assert 'depends-on = ["ros-build"]' in pixi_text

    for script in (MISSION_SCRIPT, ROS2_SCRIPT):
        result = subprocess.run(
            ["bash", "-n", str(script)], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr


def test_cmake_registers_mission_contract() -> None:
    cmake = (PACKAGE_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "test_trash_mission_contract" in cmake
