"""Launch Gazebo camera bridge plus the trash detector node.

Usage:
  ros2 launch smartclean_perception perception.launch.py \
    world_path:=<absolute smartclean_trash.sdf> camera:=true
"""

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory

import os


def _expand(context, *args):
    package_share = get_package_share_directory("smartclean_gazebo")
    drive_launch = os.path.join(package_share, "launch", "drive.launch.py")
    drive = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(drive_launch),
        launch_arguments={
            "world_path": context.launch_configurations["world_path"],
            "camera": context.launch_configurations["camera"],
            "record": context.launch_configurations["record"],
            "gui": "false",
            "rviz": "false",
        }.items(),
    )
    detector = Node(
        package="smartclean_perception",
        executable="trash_detector",
        name="smartclean_trash_detector",
        output="screen",
        parameters=[
            {
                "horizon_row": 360,
                "min_area": 50,
                "flip_vertical": False,
                "white_min_value": 185,
                "white_max_saturation": 60,
                "use_depth": True,
                "position_frame_ids": ["map", "odom"],
                "depth_topic": "/camera/depth/image_rect_raw",
                "camera_hfov_deg": 60.0,
                "depth_max_stamp_delta_s": 0.5,
                "depth_patch_radius": 4,
            }
        ],
    )
    return [drive, detector]


def generate_launch_description():
    from launch.actions import DeclareLaunchArgument
    from launch.substitutions import LaunchConfiguration

    world_path = DeclareLaunchArgument(
        "world_path",
        description="Absolute path to the Gazebo world SDF.",
    )
    camera = DeclareLaunchArgument(
        "camera", default_value="true", description="Enable RGB camera bridge."
    )
    record = DeclareLaunchArgument(
        "record", default_value="false", description="Enable rosbag record."
    )
    return LaunchDescription(
        [
            world_path,
            camera,
            record,
            OpaqueFunction(function=_expand),
        ]
    )
