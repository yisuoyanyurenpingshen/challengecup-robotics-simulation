"""ament_python packaging for the SmartClean ROS 2 adapter."""

import os
from glob import glob

from setuptools import find_packages, setup


PACKAGE_NAME = "smartclean_ros"


setup(
    name=PACKAGE_NAME,
    version="0.1.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/{}".format(PACKAGE_NAME)],
        ),
        ("share/{}".format(PACKAGE_NAME), ["package.xml"]),
        (
            os.path.join("share", PACKAGE_NAME, "launch"),
            glob("launch/*.launch.py"),
        ),
    ],
    install_requires=["setuptools"],
    extras_require={"test": ["pytest"]},
    zip_safe=True,
    maintainer="SmartClean Team",
    maintainer_email="smartclean@example.com",
    description=(
        "ROS 2 bridge, deterministic trajectory replay, and velocity safety guard "
        "for SmartClean-Sim"
    ),
    license="Proprietary",
    url="https://github.com/yisuoyanyurenpingshen/challengecup-robotics-simulation",
    entry_points={
        "console_scripts": [
            "cmd_vel_guard = smartclean_ros.cmd_vel_guard_node:main",
            (
                "scan_frame_republisher = "
                "smartclean_ros.scan_frame_republisher_node:main"
            ),
            "smartclean_cmd_vel_guard = smartclean_ros.cmd_vel_guard_node:main",
            "smartclean_bridge = smartclean_ros.bridge_node:main",
            (
                "smartclean_clock_relay = "
                "smartclean_ros.clock_monotonic_relay_node:main"
            ),
        ],
    },
)
