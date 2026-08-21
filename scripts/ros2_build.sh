#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"
mkdir -p .ros/log ros2_ws/build ros2_ws/install ros2_ws/log

colcon --log-base ros2_ws/log build \
  --base-paths ros2_ws/src \
  --build-base ros2_ws/build \
  --install-base ros2_ws/install \
  --symlink-install
