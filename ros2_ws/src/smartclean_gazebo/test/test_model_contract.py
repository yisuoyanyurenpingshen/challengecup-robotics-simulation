"""Static contracts for the local SmartClean Gazebo model and drive world."""

from pathlib import Path
import re
import xml.etree.ElementTree as ET


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIRECTORY = PACKAGE_ROOT / "models" / "smartclean_robot"
MODEL_PATH = MODEL_DIRECTORY / "model.sdf"
MODEL_CONFIG_PATH = MODEL_DIRECTORY / "model.config"
WORLD_PATH = PACKAGE_ROOT / "worlds" / "smartclean_drive.sdf"


def _xml_root(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def _model() -> ET.Element:
    model = _xml_root(MODEL_PATH).find("model")
    assert model is not None
    return model


def _required_text(parent: ET.Element, tag: str) -> str:
    element = parent.find(tag)
    assert element is not None
    assert element.text is not None
    return element.text.strip()


def test_model_config_points_to_the_local_sdf() -> None:
    config = _xml_root(MODEL_CONFIG_PATH)

    assert config.tag == "model"
    assert _required_text(config, "name") == "SmartClean Differential Drive Robot"
    sdf = config.find("sdf")
    assert sdf is not None
    assert sdf.attrib["version"] == "1.8"
    assert _required_text(config, "sdf") == "model.sdf"
    assert (MODEL_DIRECTORY / _required_text(config, "sdf")).is_file()


def test_robot_has_two_drive_wheels_and_a_free_caster() -> None:
    model = _model()
    links = {link.attrib["name"]: link for link in model.findall("link")}
    joints = {joint.attrib["name"]: joint for joint in model.findall("joint")}

    assert model.attrib["name"] == "smartclean_robot"
    assert {"base_link", "left_wheel_link", "right_wheel_link", "caster_link"} <= links.keys()
    assert joints["left_wheel_joint"].attrib["type"] == "revolute"
    assert joints["right_wheel_joint"].attrib["type"] == "revolute"
    assert joints["caster_joint"].attrib["type"] == "ball"

    expected_children = {
        "left_wheel_joint": "left_wheel_link",
        "right_wheel_joint": "right_wheel_link",
        "caster_joint": "caster_link",
    }
    for joint_name, child_name in expected_children.items():
        joint = joints[joint_name]
        assert _required_text(joint, "parent") == "base_link"
        assert _required_text(joint, "child") == child_name

    for joint_name in ("left_wheel_joint", "right_wheel_joint"):
        axis = joints[joint_name].find("./axis/xyz")
        assert axis is not None
        assert axis.attrib["expressed_in"] == "__model__"
        assert axis.text is not None
        assert tuple(float(value) for value in axis.text.split()) == (0.0, 1.0, 0.0)


def test_dynamic_links_have_positive_inertia_and_collision_geometry() -> None:
    model = _model()

    for link in model.findall("link"):
        mass = float(_required_text(link, "./inertial/mass"))
        ixx = float(_required_text(link, "./inertial/inertia/ixx"))
        iyy = float(_required_text(link, "./inertial/inertia/iyy"))
        izz = float(_required_text(link, "./inertial/inertia/izz"))
        collisions = link.findall("collision")

        assert mass > 0.0
        assert min(ixx, iyy, izz) > 0.0
        assert ixx <= iyy + izz
        assert iyy <= ixx + izz
        assert izz <= ixx + iyy
        assert collisions
        assert all(collision.find("geometry") is not None for collision in collisions)


def test_fortress_diff_drive_contract_is_stable() -> None:
    model = _model()
    plugins = [
        plugin
        for plugin in model.findall("plugin")
        if plugin.attrib.get("name") == "gz::sim::systems::DiffDrive"
    ]

    assert len(plugins) == 1
    plugin = plugins[0]
    assert plugin.attrib["filename"] == "ignition-gazebo-diff-drive-system"
    assert _required_text(plugin, "left_joint") == "left_wheel_joint"
    assert _required_text(plugin, "right_joint") == "right_wheel_joint"
    assert float(_required_text(plugin, "wheel_separation")) == 0.74
    assert float(_required_text(plugin, "wheel_radius")) == 0.14
    assert _required_text(plugin, "topic") == "/smartclean/safe_cmd_vel"
    assert _required_text(plugin, "odom_topic") == "/smartclean/odom"
    assert _required_text(plugin, "tf_topic") == "/smartclean/tf"
    assert _required_text(plugin, "frame_id") == "odom"
    assert _required_text(plugin, "child_frame_id") == "base_footprint"


def test_model_declares_footprint_and_lidar_for_complete_tf() -> None:
    model = _model()
    footprint = model.find("./link[@name='base_footprint']")
    assert footprint is not None, "缺少 base_footprint link"
    footprint_joint = model.find("./joint[@name='base_footprint_joint']")
    assert footprint_joint is not None
    assert footprint_joint.findtext("parent") == "base_footprint"
    assert footprint_joint.findtext("child") == "base_link"

    lidar_link = model.find("./link[@name='lidar_link']")
    assert lidar_link is not None, "缺少 lidar_link"
    assert lidar_link.find("inertial") is not None
    assert lidar_link.find("collision") is not None
    assert lidar_link.find("visual") is not None
    lidar_joint = model.find("./joint[@name='lidar_joint']")
    assert lidar_joint is not None
    assert lidar_joint.findtext("parent") == "base_link"
    assert lidar_joint.findtext("child") == "lidar_link"

    sensors = lidar_link.findall("sensor")
    assert len(sensors) == 1
    sensor = sensors[0]
    # conda 构建的 ignition-sensors 6.6.3 不含 CPU lidar，必须用 gpu_lidar。
    assert sensor.attrib["type"] == "gpu_lidar"
    assert sensor.findtext("topic") == "/smartclean/lidar/scan"
    assert sensor.findtext("update_rate") == "10"
    ray = sensor.find("ray")
    assert ray is not None
    horizontal = ray.find("scan/horizontal")
    assert horizontal is not None
    assert int(horizontal.findtext("samples")) >= 180
    assert float(horizontal.findtext("min_angle")) < 0
    assert float(horizontal.findtext("max_angle")) > 0
    range_element = ray.find("range")
    assert range_element is not None
    assert float(range_element.findtext("min")) > 0
    assert float(range_element.findtext("max")) > float(
        range_element.findtext("min")
    )


def test_model_is_self_contained_without_remote_assets() -> None:
    model = _model()
    uri_values = [
        element.text.strip()
        for element in model.findall(".//uri")
        if element.text is not None
    ]

    assert uri_values == []
    model_text = MODEL_PATH.read_text(encoding="utf-8").lower()
    assert "http://" not in model_text
    assert "https://" not in model_text
    assert "fuel.gazebosim.org" not in model_text


def test_drive_world_includes_only_the_local_robot_model() -> None:
    world = _xml_root(WORLD_PATH).find("world")
    assert world is not None

    assert world.attrib["name"] == "smartclean_drive"
    includes = world.findall("include")
    assert len(includes) == 1
    robot_uri = _required_text(includes[0], "uri")
    assert robot_uri == "model://smartclean_robot"
    assert _required_text(includes[0], "name") == "smartclean_robot"
    assert world.find("./model[@name='drive_surface']") is not None

    resource_name = robot_uri[len("model://") :]
    resolved_model = PACKAGE_ROOT / "models" / resource_name
    assert resolved_model == MODEL_DIRECTORY
    assert (resolved_model / "model.config").is_file()
    assert (resolved_model / "model.sdf").is_file()

    uri_values = [
        element.text.strip()
        for element in world.findall(".//uri")
        if element.text is not None
    ]
    assert uri_values == ["model://smartclean_robot"]


def test_build_installs_models_and_exports_the_resource_path() -> None:
    cmake = (PACKAGE_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    directory_installs = re.findall(
        r"install\s*\(\s*DIRECTORY\s+(.*?)\s+DESTINATION",
        cmake,
        flags=re.DOTALL,
    )
    assert any("models" in install.split() for install in directory_installs)

    package = _xml_root(PACKAGE_ROOT / "package.xml")
    gazebo_export = package.find("./export/gazebo_ros")
    assert gazebo_export is not None
    assert gazebo_export.attrib["gazebo_model_path"] == "${prefix}/models"
