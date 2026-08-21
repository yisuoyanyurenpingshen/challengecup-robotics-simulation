#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"

if [[ -z "${DISPLAY:-}" ]]; then
  cat >&2 <<'HINT'
没有可用 DISPLAY，无法弹出 Gazebo GUI 和 RViz2 窗口。
本会话请改用无界面命令：

  bash scripts/ros2.sh drive          # headless Gazebo 差速车
  bash scripts/ros2.sh drive-verify   # headless 自动验证

在带桌面的机器上执行时再使用：

  bash scripts/ros2.sh drive-gui      # Gazebo GUI + RViz2
HINT
  exit 2
fi

if [[ ! -f ros2_ws/install/setup.bash ]]; then
  echo "首次运行，正在构建 ROS 2 工作空间..."
  bash scripts/ros2_build.sh
fi

set +u
source ros2_ws/install/setup.bash
set -u
export ROS2CLI_DISABLE_DAEMON=1
export SMARTCLEAN_GAZEBO_LOG_DIR="${SMARTCLEAN_GAZEBO_LOG_DIR:-${project_root}/.gazebo/log/drive-gui-${BASHPID}}"
mkdir -p "$(dirname "${SMARTCLEAN_GAZEBO_LOG_DIR}")"

exec ros2 launch smartclean_gazebo drive.launch.py gui:=true rviz:=true "$@"
