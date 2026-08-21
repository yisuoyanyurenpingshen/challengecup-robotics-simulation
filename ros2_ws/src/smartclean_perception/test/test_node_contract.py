"""Static contracts for the perception ROS node and launch file."""

import subprocess
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]


def test_console_script_entry_point_exists() -> None:
    setup = (PACKAGE_ROOT / "setup.py").read_text(encoding="utf-8")
    assert (
        '"trash_detector = smartclean_perception.trash_detector_node:main"'
        in setup
    )


def test_node_uses_required_topics_and_messages() -> None:
    node = (
        PACKAGE_ROOT / "smartclean_perception" / "trash_detector_node.py"
    ).read_text(encoding="utf-8")
    for required in (
        "/camera/image_raw",
        "/smartclean/detections",
        "/smartclean/debug/detection_image",
        "TrashDetectionArray",
        "TrashDetectionMsg",
        "schema_version",
        "position_valid",
        "image_stamp",
        "SCHEMA_VERSION = 1",
        "smartclean_perception.color_baseline",
    ):
        assert required in node, required


def test_launch_file_declares_defaults() -> None:
    launch = (PACKAGE_ROOT / "launch" / "perception.launch.py").read_text(
        encoding="utf-8"
    )
    assert "world_path" in launch
    assert "camera" in launch
    assert "trash_detector" in launch
    assert "horizon_row" in launch
    assert "flip_vertical" in launch


def test_node_declares_depth_position_pipeline() -> None:
    node = (
        PACKAGE_ROOT / "smartclean_perception" / "trash_detector_node.py"
    ).read_text(encoding="utf-8")
    for required in (
        "use_depth",
        "/camera/depth/image_rect_raw",
        "camera_hfov_deg",
        "position_frame_ids",
        "tf2_ros",
        "from_hfov",
        "position_valid = True",
        "position_frame_id = position.frame_id",
    ):
        assert required in node, required


def test_launch_file_enables_depth_by_default() -> None:
    launch = (PACKAGE_ROOT / "launch" / "perception.launch.py").read_text(
        encoding="utf-8"
    )
    assert '"use_depth": True' in launch
    assert '"position_frame_ids": ["map", "odom"]' in launch


def test_python_syntax_and_compile() -> None:
    for name in (
        "detector_core.py",
        "trash_detector_node.py",
        "synthetic_dataset.py",
    ):
        path = PACKAGE_ROOT / "smartclean_perception" / name
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_interfaces_exist_in_workspace() -> None:
    interfaces = REPO_ROOT / "ros2_ws" / "src" / "smartclean_interfaces" / "msg"
    assert (interfaces / "TrashDetection.msg").is_file()
    assert (interfaces / "TrashDetectionArray.msg").is_file()
    detection = (interfaces / "TrashDetection.msg").read_text(encoding="utf-8")
    for field in (
        "schema_version",
        "detection_id",
        "class_name",
        "confidence",
        "bbox_xyxy",
        "image_stamp",
        "source",
        "position_valid",
        "position",
    ):
        assert field in detection, field
