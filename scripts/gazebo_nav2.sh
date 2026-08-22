#!/usr/bin/env bash
# 启动 SmartClean 场地 + Nav2 导航栈。
# 默认 headless；有桌面时可用 gui:=true rviz:=true 弹出 Gazebo GUI 与 RViz2。
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"

for arg in "$@"; do
  case "${arg}" in
    gui:=true|gui:=1|rviz:=true|rviz:=1)
      if [[ -z "${DISPLAY:-}" ]]; then
        cat >&2 <<'HINT'
没有可用 DISPLAY，无法弹出 Gazebo GUI 或 RViz2 窗口。
本会话请改用 headless 命令：

  bash scripts/ros2.sh nav2             # headless Gazebo + Nav2
  bash scripts/ros2.sh nav2-verify      # headless 自动验证导航闭环

在带桌面的机器上执行时再使用：

  bash scripts/ros2.sh nav2 gui:=true rviz:=true
HINT
        exit 2
      fi
      ;;
  esac
done

if [[ ! -f ros2_ws/install/setup.bash ]]; then
  echo "首次运行，正在构建 ROS 2 工作空间..."
  bash scripts/ros2_build.sh
fi

set +u
source ros2_ws/install/setup.bash
set -u
export ROS2CLI_DISABLE_DAEMON=1
export SMARTCLEAN_GAZEBO_LOG_DIR="${SMARTCLEAN_GAZEBO_LOG_DIR:-${project_root}/.gazebo/log/nav2-${BASHPID}}"
mkdir -p "$(dirname "${SMARTCLEAN_GAZEBO_LOG_DIR}")"

exec ros2 launch smartclean_gazebo nav2.launch.py "$@"
