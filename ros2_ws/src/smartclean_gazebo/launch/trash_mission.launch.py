"""Launch the perception-to-navigation SmartClean trash mission.

This composes the verified Nav2 stack with the real RGB-D detector, the
Gazebo ``DeleteEntity`` service bridge, and the mission controller.  The
controller receives detections only; Gazebo scene ground truth is never
passed into the mission process.
"""

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    Shutdown,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


NAV2_LAUNCH = PathJoinSubstitution(
    [FindPackageShare("smartclean_gazebo"), "launch", "nav2.launch.py"]
)
DELETE_ENTITY_SERVICE = "/world/smartclean_trash/remove"
DELETE_ENTITY_BRIDGE = (
    "/world/smartclean_trash/remove@ros_gz_interfaces/srv/DeleteEntity"
)

# The order is intentional: large, easily scattered litter is serviced first;
# unlisted detected classes remain eligible through the controller policy.
PRIORITY_CLASSES = ["fallen_leaves", "plastic_bottle"]

DETECTOR_PARAMETERS = {
    "use_sim_time": True,
    # AMCL intentionally publishes map->odom with a future transform
    # tolerance. Exact image-time map lookup can therefore be unavailable,
    # while odom remains time-aligned with the camera. The controller
    # converts this fallback to map before tracking or navigation.
    "position_frame_ids": ["map", "odom"],
    "use_depth": True,
    "depth_topic": "/camera/depth/image_rect_raw",
}

CONTROLLER_PARAMETERS = {
    "use_sim_time": True,
    "priority_classes": PRIORITY_CLASSES,
    "cleaning_radius_m": 0.45,
    "robot_front_extent_m": 0.45,
    "cleaning_tool_offset_m": 0.45,
    "navigation_standoff_margin_m": 0.10,
    "min_observations": 3,
    "mission_timeout_s": 360.0,
    "return_after_done": True,
    "dock_x": 0.0,
    "dock_y": 0.0,
    "dock_yaw": 0.0,
    "max_return_attempts": 3,
    "delete_service": DELETE_ENTITY_SERVICE,
}


def generate_launch_description() -> LaunchDescription:
    """Compose navigation, perception, deletion, and mission orchestration."""

    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([NAV2_LAUNCH]),
        launch_arguments={
            "gui": LaunchConfiguration("gui"),
            "rviz": LaunchConfiguration("rviz"),
            "record": LaunchConfiguration("record"),
            "camera": "true",
        }.items(),
    )

    detector = Node(
        package="smartclean_perception",
        executable="trash_detector",
        name="smartclean_trash_detector",
        parameters=[DETECTOR_PARAMETERS],
        output="screen",
        on_exit=Shutdown(reason="trash detector exited"),
    )

    delete_entity_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="smartclean_delete_entity_bridge",
        arguments=[DELETE_ENTITY_BRIDGE],
        output="screen",
        on_exit=Shutdown(reason="DeleteEntity bridge exited"),
    )

    mission_controller = Node(
        package="smartclean_ros",
        executable="trash_mission_controller",
        name="smartclean_trash_mission_controller",
        parameters=[CONTROLLER_PARAMETERS],
        output="screen",
        on_exit=Shutdown(reason="trash mission controller exited"),
    )

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
                "record",
                default_value="false",
                description="Record Gazebo state when true.",
            ),
            nav2,
            detector,
            delete_entity_bridge,
            mission_controller,
        ]
    )
