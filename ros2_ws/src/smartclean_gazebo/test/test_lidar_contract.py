"""Static contracts for the 2D LiDAR sensor, bridge and verification."""

import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
SDF_PATH = PACKAGE_ROOT / "models" / "smartclean_robot" / "model.sdf"
LAUNCH_PATH = PACKAGE_ROOT / "launch" / "drive.launch.py"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_lidar.sh"
PROBE_SCRIPT = REPO_ROOT / "scripts" / "lidar_probe.py"


def _sdf_root() -> ET.Element:
    return ET.parse(SDF_PATH).getroot()


def test_sdf_lidar_sensor_parameters() -> None:
    root = _sdf_root()
    lidar_link = root.find(".//link[@name='lidar_link']")
    assert lidar_link is not None
    sensor = lidar_link.find("sensor")
    assert sensor is not None
    assert sensor.attrib["type"] == "gpu_lidar"
    assert sensor.findtext("topic") == "/smartclean/lidar/scan"
    assert sensor.findtext("always_on") == "1"
    assert sensor.findtext("visualize") == "0"


def test_launch_bridges_lidar_with_default_off() -> None:
    text = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "sensor_msgs/msg/LaserScan" in text
    assert "ignition.msgs.LaserScan" in text
    assert "/smartclean/lidar/scan" in text
    assert '"/scan_raw"' in text
    assert "scan_frame_republisher" in text
    assert '"frame_id": "lidar_link"' in text
    assert 'default_value="false"' in text
    assert "IfCondition(LaunchConfiguration(\"lidar\")" in text


def test_sensors_config_used_when_lidar_enabled() -> None:
    text = LAUNCH_PATH.read_text(encoding="utf-8")
    assert 'LaunchConfiguration("lidar")' in text
    assert "sensors_enabled" in text


def test_verify_lidar_script_is_portable_and_safe() -> None:
    text = VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert "xvfb_start" in text
    assert "xvfb_stop" in text
    assert "lidar:=true" in text
    assert "kill -TERM" in text
    result = subprocess.run(
        ["bash", "-n", str(VERIFY_SCRIPT)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_lidar_probe_checks_required_evidence() -> None:
    result = subprocess.run(
        ["python3", "-m", "py_compile", str(PROBE_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    text = PROBE_SCRIPT.read_text(encoding="utf-8")
    for required in (
        "/scan",
        "lidar_link",
        "EXPECTED_SAMPLES = 360",
        "angle_increment",
        "range_min",
        "odom",
        "smartclean_cmd_vel_guard",
        "lookup_transform",
        "/cmd_vel",
    ):
        assert required in text, "lidar_probe.py is missing {}".format(required)
