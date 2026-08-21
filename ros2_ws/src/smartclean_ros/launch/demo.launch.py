"""Launch the deterministic SmartClean-Sim ROS bridge."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    arguments = [
        DeclareLaunchArgument(
            "config_path",
            default_value=PathJoinSubstitution(
                [FindPackageShare("smartclean_core"), "config", "demo.json"]
            ),
            description="SmartClean-Sim JSON 配置路径",
        ),
        DeclareLaunchArgument(
            "frame_id", default_value="map", description="ROS 轨迹坐标系"
        ),
        DeclareLaunchArgument(
            "cell_size_m",
            default_value="1.0",
            description="一个核心栅格对应的米数",
        ),
        DeclareLaunchArgument("origin_x_m", default_value="0.0"),
        DeclareLaunchArgument("origin_y_m", default_value="0.0"),
        DeclareLaunchArgument(
            "replay_period_s",
            default_value="0.2",
            description="逐帧 ROS 位姿发布周期",
        ),
        DeclareLaunchArgument(
            "loop_replay",
            default_value="false",
            description="到达末帧后是否循环回放",
        ),
    ]

    bridge = Node(
        package="smartclean_ros",
        executable="smartclean_bridge",
        name="smartclean_bridge",
        output="screen",
        parameters=[
            {
                "config_path": LaunchConfiguration("config_path"),
                "frame_id": LaunchConfiguration("frame_id"),
                "cell_size_m": ParameterValue(
                    LaunchConfiguration("cell_size_m"), value_type=float
                ),
                "origin_x_m": ParameterValue(
                    LaunchConfiguration("origin_x_m"), value_type=float
                ),
                "origin_y_m": ParameterValue(
                    LaunchConfiguration("origin_y_m"), value_type=float
                ),
                "replay_period_s": ParameterValue(
                    LaunchConfiguration("replay_period_s"), value_type=float
                ),
                "loop_replay": ParameterValue(
                    LaunchConfiguration("loop_replay"), value_type=bool
                ),
            }
        ],
    )
    return LaunchDescription(arguments + [bridge])
