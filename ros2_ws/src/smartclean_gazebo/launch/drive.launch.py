"""Launch the SmartClean differential-drive robot, bridges, GUI and RViz.

Headless default keeps the verified P4-M1 behavior. ``gui:=true`` adds the
Gazebo GUI client, ``rviz:=true`` adds RViz2 with the local robot model.
"""

import os
from pathlib import Path

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    OpaqueFunction,
    Shutdown,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.substitutions import (
    EnvironmentVariable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def _as_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError("{} 必须是 true 或 false".format(name))


def _prepend_resource_path(path: Path, current: str) -> str:
    """Prepend one validated local model path without dropping user paths."""

    if not current:
        return str(path)
    entries = current.split(os.pathsep)
    if str(path) in entries:
        return current
    return str(path) + os.pathsep + current


def _launch_gazebo(context):
    """Resolve local paths, then execute the Gazebo server without a shell."""

    world_path = Path(LaunchConfiguration("world_path").perform(context))
    if not world_path.is_absolute() or not world_path.is_file():
        raise RuntimeError(
            "world_path 必须是存在的绝对 SDF 文件：{}".format(world_path)
        )

    server_config_path = Path(
        LaunchConfiguration("server_config_path").perform(context)
    )
    # 相机/LiDAR 等传感器需要 Sensors 系统，而 Sensors 系统会初始化渲染引擎；
    # headless 差速验证（无 GLX 显示）必须继续使用不含 Sensors 的基础配置。
    sensors_enabled = _as_bool(
        LaunchConfiguration("camera").perform(context), "camera"
    ) or _as_bool(
        LaunchConfiguration("lidar").perform(context), "lidar"
    )
    if sensors_enabled:
        server_config_path = Path(
            LaunchConfiguration("sensors_config_path").perform(context)
        )
    if not server_config_path.is_absolute() or not server_config_path.is_file():
        raise RuntimeError(
            "server_config_path 必须是存在的绝对文件：{}".format(
                server_config_path
            )
        )

    models_path = Path(LaunchConfiguration("models_path").perform(context))
    if not models_path.is_absolute() or not models_path.is_dir():
        raise RuntimeError(
            "models_path 必须是存在的绝对目录：{}".format(models_path)
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

    ignition_resources = _prepend_resource_path(
        models_path, os.environ.get("IGN_GAZEBO_RESOURCE_PATH", "")
    )
    gazebo_resources = _prepend_resource_path(
        models_path, os.environ.get("GZ_SIM_RESOURCE_PATH", "")
    )

    return [
        ExecuteProcess(
            cmd=command,
            output="screen",
            shell=False,
            additional_env={
                "IGN_GAZEBO_SERVER_CONFIG_PATH": str(server_config_path),
                "GZ_SIM_SERVER_CONFIG_PATH": str(server_config_path),
                "IGN_GAZEBO_RESOURCE_PATH": ignition_resources,
                "GZ_SIM_RESOURCE_PATH": gazebo_resources,
            },
            on_exit=Shutdown(reason="Gazebo drive server exited"),
        )
    ]


def _launch_gazebo_gui(context):
    """Launch the Gazebo GUI client that attaches to the running server."""

    return [
        ExecuteProcess(
            cmd=["ign", "gazebo", "-g", "-v", "2", "--force-version", "6"],
            output="screen",
            shell=False,
            on_exit=Shutdown(reason="Gazebo GUI client exited"),
        )
    ]


def generate_launch_description() -> LaunchDescription:
    """Build the differential-drive launch description.

    Headless (default): Gazebo server + bridges + safety guard.
    gui:=true: additionally starts the Gazebo GUI client.
    rviz:=true: additionally starts RViz2 with the local RViz configuration.
    """

    package_share = FindPackageShare("smartclean_gazebo")
    default_world = PathJoinSubstitution(
        [package_share, "worlds", "smartclean_drive.sdf"]
    )
    default_server_config = PathJoinSubstitution(
        [package_share, "config", "server.config"]
    )
    default_sensors_config = PathJoinSubstitution(
        [package_share, "config", "server_sensors.config"]
    )
    default_models = PathJoinSubstitution([package_share, "models"])
    default_urdf = PathJoinSubstitution(
        [package_share, "urdf", "smartclean_drive.urdf"]
    )
    default_rviz = PathJoinSubstitution(
        [package_share, "rviz", "smartclean_drive.rviz"]
    )

    bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="smartclean_drive_bridge",
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock",
            (
                "/smartclean/safe_cmd_vel@geometry_msgs/msg/Twist]"
                "ignition.msgs.Twist"
            ),
            (
                "/smartclean/odom@nav_msgs/msg/Odometry["
                "ignition.msgs.Odometry"
            ),
            (
                "/smartclean/tf@tf2_msgs/msg/TFMessage["
                "ignition.msgs.Pose_V"
            ),
        ],
        remappings=[
            ("/smartclean/odom", "/odom"),
            ("/smartclean/tf", "/tf"),
            # The bridge forwards /clock onto /clock_raw; the monotonic relay
            # below republishes it on /clock so downstream sim-time consumers
            # never observe a backwards clock jump.
            ("/clock", "/clock_raw"),
        ],
        output="screen",
        on_exit=Shutdown(reason="ROS-Gazebo drive bridge exited"),
    )

    clock_monotonic_relay = Node(
        package="smartclean_ros",
        executable="smartclean_clock_relay",
        name="smartclean_clock_relay",
        parameters=[
            {"input_topic": "/clock_raw", "output_topic": "/clock"}
        ],
        output="screen",
        on_exit=Shutdown(reason="simulation clock relay exited"),
    )

    command_guard = Node(
        package="smartclean_ros",
        executable="smartclean_cmd_vel_guard",
        name="smartclean_cmd_vel_guard",
        parameters=[
            {
                "input_topic": "/cmd_vel",
                "output_topic": "/smartclean/safe_cmd_vel",
                "command_timeout_s": ParameterValue(
                    LaunchConfiguration("command_timeout_s"), value_type=float
                ),
                "publish_rate_hz": ParameterValue(
                    LaunchConfiguration("command_publish_rate_hz"),
                    value_type=float,
                ),
            }
        ],
        output="screen",
        on_exit=Shutdown(reason="cmd_vel safety guard exited"),
    )

    camera_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="smartclean_camera_bridge",
        arguments=[
            (
                "/smartclean/camera/image@sensor_msgs/msg/Image["
                "ignition.msgs.Image"
            ),
            (
                "/smartclean/camera/camera_info@"
                "sensor_msgs/msg/CameraInfo[ignition.msgs.CameraInfo"
            ),
            (
                "/smartclean/camera/depth_image@"
                "sensor_msgs/msg/Image[ignition.msgs.Image"
            ),
        ],
        remappings=[
            ("/smartclean/camera/image", "/camera/image_raw"),
            ("/smartclean/camera/camera_info", "/camera/camera_info"),
            (
                "/smartclean/camera/depth_image",
                "/camera/depth/image_rect_raw",
            ),
        ],
        condition=IfCondition(LaunchConfiguration("camera")),
        output="screen",
        on_exit=Shutdown(reason="ROS-Gazebo camera bridge exited"),
    )

    lidar_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="smartclean_lidar_bridge",
        arguments=[
            (
                "/smartclean/lidar/scan@"
                "sensor_msgs/msg/LaserScan[ignition.msgs.LaserScan"
            ),
        ],
        remappings=[
            ("/smartclean/lidar/scan", "/scan_raw"),
        ],
        condition=IfCondition(LaunchConfiguration("lidar")),
        output="screen",
        on_exit=Shutdown(reason="ROS-Gazebo lidar bridge exited"),
    )

    scan_frame_republisher = Node(
        package="smartclean_ros",
        executable="scan_frame_republisher",
        name="smartclean_scan_frame_republisher",
        parameters=[
            {
                "input_topic": "/scan_raw",
                "output_topic": "/scan",
                "frame_id": "lidar_link",
            }
        ],
        condition=IfCondition(LaunchConfiguration("lidar")),
        output="screen",
        on_exit=Shutdown(reason="scan frame republisher exited"),
    )

    # Publishes base_footprint -> base_link and every attached child frame.
    # Gazebo DiffDrive owns odom -> base_footprint, and this publisher owns
    # base_footprint -> base_link plus the attached sensor frames, so it
    # intentionally never declares an odom link or an odom parent frame.
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        arguments=[LaunchConfiguration("urdf")],
        parameters=[{"use_sim_time": True}],
        output="screen",
        on_exit=Shutdown(reason="robot_state_publisher exited"),
    )

    gazebo_gui_client = TimerAction(
        period=1.5,
        actions=[
            OpaqueFunction(
                function=_launch_gazebo_gui,
                condition=IfCondition(LaunchConfiguration("gui")),
            ),
        ],
    )

    rviz_node = TimerAction(
        period=2.5,
        actions=[
            Node(
                package="rviz2",
                executable="rviz2",
                name="rviz2",
                arguments=[
                    "-d",
                    LaunchConfiguration("rviz_config"),
                    "-f",
                    "odom",
                ],
                parameters=[{"use_sim_time": True}],
                output="screen",
                condition=IfCondition(LaunchConfiguration("rviz")),
                on_exit=Shutdown(reason="RViz2 exited"),
            )
        ],
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "world_path",
                default_value=default_world,
                description="Absolute SmartClean drive-world SDF path.",
            ),
            DeclareLaunchArgument(
                "server_config_path",
                default_value=default_server_config,
                description="Absolute Gazebo server configuration path.",
            ),
            DeclareLaunchArgument(
                "sensors_config_path",
                default_value=default_sensors_config,
                description="Sensors-enabled server config used when camera:=true.",
            ),
            DeclareLaunchArgument(
                "models_path",
                default_value=default_models,
                description="Absolute local model search directory.",
            ),
            DeclareLaunchArgument(
                "urdf",
                default_value=default_urdf,
                description="Absolute local URDF description of the robot.",
            ),
            DeclareLaunchArgument(
                "rviz_config",
                default_value=default_rviz,
                description="Absolute RViz2 configuration file.",
            ),
            DeclareLaunchArgument(
                "gui",
                default_value="false",
                description="Start the Gazebo GUI client when true.",
            ),
            DeclareLaunchArgument(
                "rviz",
                default_value="false",
                description="Start RViz2 when true.",
            ),
            DeclareLaunchArgument(
                "camera",
                default_value="false",
                description="Bridge the RGB camera to /camera when true.",
            ),
            DeclareLaunchArgument(
                "lidar",
                default_value="false",
                description="Bridge the 2D LiDAR to /scan when true.",
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
                    default_value="/tmp/smartclean-gazebo-drive-log",
                ),
                description="Absolute Gazebo recording directory.",
            ),
            DeclareLaunchArgument(
                "command_timeout_s",
                default_value="0.5",
                description="Stop the robot after this command silence period.",
            ),
            DeclareLaunchArgument(
                "command_publish_rate_hz",
                default_value="20.0",
                description="Safe velocity output frequency.",
            ),
            OpaqueFunction(function=_launch_gazebo),
            bridge,
            clock_monotonic_relay,
            command_guard,
            camera_bridge,
            lidar_bridge,
            scan_frame_republisher,
            robot_state_publisher,
            gazebo_gui_client,
            rviz_node,
        ]
    )
