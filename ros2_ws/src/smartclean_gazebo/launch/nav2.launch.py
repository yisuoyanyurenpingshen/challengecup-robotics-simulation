"""Launch the SmartClean arena with the Nav2 navigation stack.

Combines the verified drive stack (Gazebo server, bridges, cmd_vel watchdog,
scan frame republisher, robot_state_publisher) with Nav2 localization
(map_server + AMCL) and navigation (planner/controller/behavior/BT/
lifecycle). Defaults are headless; ``gui:=true`` adds the Gazebo client and
``rviz:=true`` adds RViz2 with the Nav2 view.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

DRIVE_LAUNCH = PathJoinSubstitution(
    [FindPackageShare("smartclean_gazebo"), "launch", "drive.launch.py"]
)
LOCALIZATION_LAUNCH = PathJoinSubstitution(
    [FindPackageShare("nav2_bringup"), "launch", "localization_launch.py"]
)
NAVIGATION_LAUNCH = PathJoinSubstitution(
    [FindPackageShare("nav2_bringup"), "launch", "navigation_launch.py"]
)
TRASH_WORLD = PathJoinSubstitution(
    [FindPackageShare("smartclean_gazebo"), "worlds", "smartclean_trash.sdf"]
)
ARENA_MAP = PathJoinSubstitution(
    [FindPackageShare("smartclean_gazebo"), "maps", "smartclean_arena.yaml"]
)
NAV2_PARAMS = PathJoinSubstitution(
    [FindPackageShare("smartclean_gazebo"), "config", "nav2_params.yaml"]
)
NAV2_RVIZ = PathJoinSubstitution(
    [FindPackageShare("nav2_bringup"), "rviz", "nav2_default_view.rviz"]
)


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "gui",
                default_value="false",
                description="Start the Gazebo GUI client when true.",
            ),
            DeclareLaunchArgument(
                "rviz",
                default_value="false",
                description="Start RViz2 with the Nav2 view when true.",
            ),
            DeclareLaunchArgument(
                "camera",
                default_value="false",
                description="Bridge the RGB camera when true.",
            ),
            DeclareLaunchArgument(
                "record",
                default_value="false",
                description="Record Gazebo state when true.",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([DRIVE_LAUNCH]),
                launch_arguments={
                    "world_path": TRASH_WORLD,
                    "lidar": "true",
                    "camera": LaunchConfiguration("camera"),
                    "gui": LaunchConfiguration("gui"),
                    "rviz": "false",
                    "record": LaunchConfiguration("record"),
                    # Nav2 can pause briefly during replanning; keep the
                    # safety watchdog slightly more patient than the default.
                    "command_timeout_s": "1.0",
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([LOCALIZATION_LAUNCH]),
                launch_arguments={
                    "map": ARENA_MAP,
                    "params_file": NAV2_PARAMS,
                    "use_sim_time": "true",
                    "autostart": "true",
                    "use_composition": "False",
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([NAVIGATION_LAUNCH]),
                launch_arguments={
                    "params_file": NAV2_PARAMS,
                    "use_sim_time": "true",
                    "autostart": "true",
                    "use_composition": "False",
                }.items(),
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                name="rviz2",
                arguments=["-d", NAV2_RVIZ, "-f", "map"],
                parameters=[{"use_sim_time": True}],
                condition=IfCondition(LaunchConfiguration("rviz")),
                output="screen",
            ),
        ]
    )
