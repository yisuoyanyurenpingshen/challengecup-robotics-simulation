"""Launch the local SmartClean Gazebo smoke world and bridge simulation time."""

from pathlib import Path

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    OpaqueFunction,
    Shutdown,
)
from launch.substitutions import (
    EnvironmentVariable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def _as_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError("{} 必须是 true 或 false".format(name))


def _launch_gazebo(context):
    """Resolve and validate user paths, then execute without a shell."""

    world_path = Path(LaunchConfiguration("world_path").perform(context))
    if not world_path.is_absolute() or not world_path.is_file():
        raise RuntimeError(
            "world_path 必须是存在的绝对 SDF 文件：{}".format(world_path)
        )
    server_config_path = Path(
        LaunchConfiguration("server_config_path").perform(context)
    )
    if not server_config_path.is_absolute() or not server_config_path.is_file():
        raise RuntimeError(
            "server_config_path 必须是存在的绝对文件：{}".format(
                server_config_path
            )
        )

    command = ["ign", "gazebo", "-r", "-s", "-v", "2"]
    if _as_bool(LaunchConfiguration("record").perform(context), "record"):
        record_path = Path(LaunchConfiguration("record_path").perform(context))
        if not record_path.is_absolute():
            raise RuntimeError(
                "record_path 必须是绝对路径：{}".format(record_path)
            )
        command.extend(["--record-path", str(record_path)])
    command.extend([str(world_path), "--force-version", "6"])

    return [
        ExecuteProcess(
            cmd=command,
            output="screen",
            shell=False,
            additional_env={
                "IGN_GAZEBO_SERVER_CONFIG_PATH": str(server_config_path),
                "GZ_SIM_SERVER_CONFIG_PATH": str(server_config_path),
            },
            on_exit=Shutdown(reason="Gazebo server exited"),
        )
    ]


def generate_launch_description() -> LaunchDescription:
    """Build a headless Gazebo Fortress launch description."""
    default_world = PathJoinSubstitution(
        [FindPackageShare("smartclean_gazebo"), "worlds", "smartclean_smoke.sdf"]
    )
    default_server_config = PathJoinSubstitution(
        [FindPackageShare("smartclean_gazebo"), "config", "server.config"]
    )

    clock_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="smartclean_clock_bridge",
        arguments=["/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock"],
        output="screen",
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "world_path",
                default_value=default_world,
                description="Absolute path to the SDF world loaded by Gazebo.",
            ),
            DeclareLaunchArgument(
                "server_config_path",
                default_value=default_server_config,
                description="Absolute Gazebo server plugin configuration.",
            ),
            DeclareLaunchArgument(
                "record",
                default_value="false",
                description="Record Gazebo state and console output when true.",
            ),
            DeclareLaunchArgument(
                "record_path",
                default_value=EnvironmentVariable(
                    "SMARTCLEAN_GAZEBO_LOG_DIR",
                    default_value="/tmp/smartclean-gazebo-log",
                ),
                description="Gazebo recording and console-log directory.",
            ),
            OpaqueFunction(function=_launch_gazebo),
            clock_bridge,
        ]
    )
