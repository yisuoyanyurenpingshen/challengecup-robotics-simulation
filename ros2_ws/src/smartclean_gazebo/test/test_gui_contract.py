"""Static contracts for the Gazebo GUI and RViz drive view."""

from pathlib import Path
import xml.etree.ElementTree as ET

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
LAUNCH_PATH = PACKAGE_ROOT / "launch" / "drive.launch.py"
URDF_PATH = PACKAGE_ROOT / "urdf" / "smartclean_drive.urdf"
RVIZ_PATH = PACKAGE_ROOT / "rviz" / "smartclean_drive.rviz"
REPO_ROOT = PACKAGE_ROOT.parents[2]
GUI_SCRIPT = REPO_ROOT / "scripts" / "gazebo_drive_gui.sh"
ROS2_SCRIPT = REPO_ROOT / "scripts" / "ros2.sh"


def _launch_text() -> str:
    return LAUNCH_PATH.read_text(encoding="utf-8")


def _urdf_root() -> ET.Element:
    return ET.parse(URDF_PATH).getroot()


def test_launch_exposes_gui_and_rviz_arguments() -> None:
    text = _launch_text()

    assert 'DeclareLaunchArgument(\n                "gui"' in text.replace(" ", "") or (
        '"gui"' in text and "default_value" in text
    )
    assert '"rviz"' in text
    assert "default_value=" in text
    assert "robot_state_publisher" in text
    assert "rviz2" in text
    assert "ign" in text and '"gazebo"' in text
    assert "-g" in text
    # Both GUI and RViz remain switchable from the command line.
    assert "gui:=false" not in text


def test_urdf_mirrors_sdf_links_and_adds_sensor_frames() -> None:
    robot = _urdf_root()
    assert robot.tag == "robot"
    assert robot.attrib["name"] == "smartclean_robot"

    links = {link.attrib["name"]: link for link in robot.findall("link")}
    joints = {joint.attrib["name"]: joint for joint in robot.findall("joint")}

    for name in (
        "base_footprint",
        "base_link",
        "left_wheel_link",
        "right_wheel_link",
        "caster_link",
        "camera_link",
        "camera_optical_frame",
        "lidar_link",
    ):
        assert name in links, "URDF is missing link {}".format(name)

    for name in (
        "base_footprint_joint",
        "left_wheel_joint",
        "right_wheel_joint",
        "caster_joint",
        "camera_joint",
        "camera_optical_joint",
        "lidar_joint",
    ):
        assert name in joints, "URDF is missing joint {}".format(name)

    assert joints["base_footprint_joint"].attrib["type"] == "fixed"
    assert joints["left_wheel_joint"].attrib["type"] == "continuous"
    assert joints["right_wheel_joint"].attrib["type"] == "continuous"


def test_urdf_never_publishes_odom_to_base() -> None:
    """Gazebo DiffDrive already publishes odom -> base_footprint.

    The URDF must not declare an odom link or an odom parent frame, otherwise
    two publishers would race on the same transform. The URDF owns
    base_footprint -> base_link and all attached sensor frames.
    """

    robot = _urdf_root()
    link_names = [link.attrib["name"] for link in robot.findall("link")]
    assert "odom" not in link_names
    assert "map" not in link_names

    for joint in robot.findall("joint"):
        parent = joint.find("parent")
        assert parent is not None
        assert parent.attrib["link"] not in ("odom", "map")


def test_camera_optical_frame_uses_standard_rotation() -> None:
    robot = _urdf_root()
    joint = robot.find("./joint[@name='camera_optical_joint']")
    assert joint is not None
    origin = joint.find("origin")
    assert origin is not None
    assert origin.attrib["rpy"] == "-1.57079632679 0 -1.57079632679"


def test_urdf_uses_only_local_primitives() -> None:
    text = URDF_PATH.read_text(encoding="utf-8").lower()

    assert "http://" not in text
    assert "https://" not in text
    assert "<mesh" not in text
    assert "package://" not in text


def test_rviz_config_lists_required_displays_and_topics() -> None:
    config = yaml.safe_load(RVIZ_PATH.read_text(encoding="utf-8"))
    manager = config["Visualization Manager"]
    assert manager["Global Options"]["Fixed Frame"] == "odom"

    displays = {d["Name"]: d for d in manager["Displays"]}
    for name in (
        "Grid",
        "TF",
        "RobotModel",
        "Odometry",
        "LaserScan",
        "Camera",
        "DetectionDebug",
    ):
        assert name in displays, "RViz config is missing display {}".format(name)

    assert displays["Camera"]["Topic"]["Value"] == "/camera/image_raw"
    assert (
        displays["DetectionDebug"]["Topic"]["Value"]
        == "/smartclean/debug/detection_image"
    )
    assert displays["Odometry"]["Topic"]["Value"] == "/odom"
    assert displays["LaserScan"]["Topic"]["Value"] == "/scan"
    assert (
        displays["RobotModel"]["Description Topic"]["Value"]
        == "/robot_description"
    )


def test_gui_script_reports_missing_display_in_chinese() -> None:
    text = GUI_SCRIPT.read_text(encoding="utf-8")

    assert "DISPLAY" in text
    assert "无法弹出 Gazebo GUI" in text
    assert "bash scripts/ros2.sh drive" in text
    assert "drive-gui" in text


def test_unified_entry_exposes_drive_gui() -> None:
    text = ROS2_SCRIPT.read_text(encoding="utf-8")

    assert "drive-gui" in text
    assert "gazebo-drive-gui" in text
    assert "drivebash" in text


def test_build_installs_urdf_and_rviz_assets() -> None:
    cmake = (PACKAGE_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")

    assert "urdf" in cmake
    assert "rviz" in cmake
    assert "test_gui_contract" in cmake
