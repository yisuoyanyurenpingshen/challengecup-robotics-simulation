"""Static contracts for the Gazebo RGB camera sensor and ROS bridge."""

import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
SDF_PATH = PACKAGE_ROOT / "models" / "smartclean_robot" / "model.sdf"
LAUNCH_PATH = PACKAGE_ROOT / "launch" / "drive.launch.py"
SERVER_CONFIG = PACKAGE_ROOT / "config" / "server.config"
SENSORS_CONFIG = PACKAGE_ROOT / "config" / "server_sensors.config"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_camera.sh"
PROBE_SCRIPT = REPO_ROOT / "scripts" / "camera_probe.py"
XVFB_SCRIPT = REPO_ROOT / "scripts" / "xvfb_env.sh"


def _sdf_root() -> ET.Element:
    return ET.parse(SDF_PATH).getroot()


def test_sdf_declares_rgb_camera_sensor() -> None:
    root = _sdf_root()
    sensors = root.findall(".//sensor[@type='camera']")
    assert sensors, "model.sdf is missing a camera sensor"
    sensor = sensors[0]
    assert sensor.attrib["name"] == "rgb_camera"
    topic = sensor.find("topic")
    assert topic is not None
    assert topic.text == "/smartclean/camera/image"
    info_topic = sensor.find("camera_info_topic")
    assert info_topic is not None
    assert info_topic.text == "/smartclean/camera/camera_info"
    assert sensor.findtext("update_rate") == "10"
    camera = sensor.find("camera")
    assert camera is not None
    image = camera.find("image")
    assert image is not None
    assert image.findtext("width") == "640"
    assert image.findtext("height") == "480"
    assert image.findtext("format") == "R8G8B8"

    camera_link = root.find(".//link[@name='camera_link']")
    assert camera_link is not None
    assert camera_link.find("inertial") is not None
    assert camera_link.find("collision") is not None
    assert camera_link.find("visual") is not None
    joint = root.find(".//joint[@name='camera_joint']")
    assert joint is not None
    assert joint.findtext("parent") == "base_link"
    assert joint.findtext("child") == "camera_link"


def test_server_configs_split_sensors_from_headless_baseline() -> None:
    """Sensors system only loads in the sensors config.

    The headless drive verification must keep working without any GLX
    display, so the base server.config must never initialize rendering.
    """

    base = ET.parse(SERVER_CONFIG).getroot()
    base_sensors = [
        p for p in base.findall(".//plugin")
        if "Sensors" in (p.attrib.get("name") or "")
    ]
    assert not base_sensors, "server.config must stay free of the Sensors system"

    sensors = ET.parse(SENSORS_CONFIG).getroot()
    sensors_plugins = [
        p for p in sensors.findall(".//plugin")
        if "Sensors" in (p.attrib.get("name") or "")
    ]
    assert sensors_plugins, "server_sensors.config is missing the Sensors system"
    assert sensors_plugins[0].attrib["filename"] == "ignition-gazebo-sensors-system"


def test_launch_bridges_camera_with_default_off() -> None:
    text = LAUNCH_PATH.read_text(encoding="utf-8")
    assert '"camera"' in text
    assert 'default_value="false"' in text
    assert "sensor_msgs/msg/Image" in text
    assert "sensor_msgs/msg/CameraInfo" in text
    assert "/camera/image_raw" in text
    assert "/camera/camera_info" in text
    assert "IfCondition(LaunchConfiguration(\"camera\")" in text
    assert "sensors_config_path" in text


def test_verify_camera_script_is_portable_and_safe() -> None:
    text = VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert "grep -Fxq" in text
    assert "setsid ros2 launch smartclean_gazebo drive.launch.py" in text
    assert "camera:=true" in text
    assert "xvfb_start" in text
    assert "xvfb_stop" in text
    assert "kill -TERM" in text
    result = subprocess.run(
        ["bash", "-n", str(VERIFY_SCRIPT)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr

    xvfb_text = XVFB_SCRIPT.read_text(encoding="utf-8")
    assert "xvfb_start" in xvfb_text and "xvfb_stop" in xvfb_text
    assert "GLX" in xvfb_text
    assert "DISPLAY" in xvfb_text


def test_camera_probe_checks_required_evidence() -> None:
    result = subprocess.run(
        ["python3", "-m", "py_compile", str(PROBE_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    text = PROBE_SCRIPT.read_text(encoding="utf-8")
    for required in (
        "/camera/image_raw",
        "/camera/camera_info",
        "camera_optical_frame",
        "EXPECTED_WIDTH = 640",
        "EXPECTED_HEIGHT = 480",
        "rgb8",
        "MIN_MEAN",
        "stamp",
        "/tf_static",
        "base_footprint",
    ):
        assert required in text, "camera_probe.py is missing {}".format(required)
