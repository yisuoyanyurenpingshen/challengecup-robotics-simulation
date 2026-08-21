#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"

if [[ ! -f ros2_ws/install/setup.bash ]]; then
  echo "ROS 2 工作空间尚未构建，请先执行 scripts/ros2.sh build。" >&2
  exit 2
fi

set +u
source ros2_ws/install/setup.bash
set -u
colcon --log-base ros2_ws/log test \
  --base-paths ros2_ws/src \
  --build-base ros2_ws/build \
  --install-base ros2_ws/install \
  --packages-select smartclean_ros \
  --event-handlers console_direct+
colcon test-result --test-result-base ros2_ws/build --verbose
