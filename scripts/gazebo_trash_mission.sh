#!/usr/bin/env bash
# 启动 SmartClean RGB-D 感知 -> Nav2 -> 清扫 -> 删除实体 -> 返航闭环。
# 无桌面时自动使用仓库内 Xvfb 支撑相机/LiDAR 渲染；有桌面时可追加
# gui:=true rviz:=true 显示 Gazebo 和 RViz2。
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"

if [[ -z "${DISPLAY:-}" ]]; then
  for arg in "$@"; do
    case "${arg,,}" in
      gui:=true|gui:=1|gui:=yes|gui:=on|rviz:=true|rviz:=1|rviz:=yes|rviz:=on)
        cat >&2 <<'HINT'
当前没有桌面 DISPLAY，任务会通过 Xvfb 以 headless 模式运行，无法显示 GUI 窗口。

请使用：
  bash scripts/ros2.sh trash-mission

在带桌面的终端中可使用：
  bash scripts/ros2.sh trash-mission gui:=true rviz:=true
HINT
        exit 2
        ;;
    esac
  done
fi

if [[ ! -f ros2_ws/install/setup.bash ]]; then
  echo "首次运行，正在构建 ROS 2 工作空间..."
  bash scripts/ros2_build.sh
fi

set +u
source ros2_ws/install/setup.bash
set -u

# 相机与 LiDAR 的 Gazebo Sensors 系统需要 GLX。xvfb_start 在已有 DISPLAY
# 时只复用用户显示；无 DISPLAY 时启动隔离的软件显示。
# shellcheck source=scripts/xvfb_env.sh
source scripts/xvfb_env.sh
if ! xvfb_start; then
  echo "垃圾清扫任务启动失败：无可用 GLX 显示。" >&2
  echo "请先执行 bash scripts/fetch_xvfb.sh，或在有桌面的环境运行。" >&2
  exit 2
fi

export ROS2CLI_DISABLE_DAEMON=1
export SMARTCLEAN_GAZEBO_LOG_DIR="${SMARTCLEAN_GAZEBO_LOG_DIR:-${project_root}/.gazebo/log/trash-mission-${BASHPID}}"
export IGN_GAZEBO_RESOURCE_PATH="${project_root}/ros2_ws/install/smartclean_gazebo/share/smartclean_gazebo/models${IGN_GAZEBO_RESOURCE_PATH:+:${IGN_GAZEBO_RESOURCE_PATH}}"
mkdir -p "${SMARTCLEAN_GAZEBO_LOG_DIR}"

launch_pid=""

cleanup() {
  trap - EXIT INT TERM
  if [[ -n "${launch_pid}" ]]; then
    kill -INT -- "-${launch_pid}" 2>/dev/null || kill -INT "${launch_pid}" 2>/dev/null || true
    for _ in {1..80}; do
      kill -0 "${launch_pid}" 2>/dev/null || break
      sleep 0.1
    done
    if kill -0 "${launch_pid}" 2>/dev/null; then
      kill -TERM -- "-${launch_pid}" 2>/dev/null || kill -TERM "${launch_pid}" 2>/dev/null || true
    fi
    for _ in {1..50}; do
      kill -0 "${launch_pid}" 2>/dev/null || break
      sleep 0.1
    done
    if kill -0 "${launch_pid}" 2>/dev/null; then
      kill -KILL -- "-${launch_pid}" 2>/dev/null || kill -KILL "${launch_pid}" 2>/dev/null || true
    fi
    wait "${launch_pid}" 2>/dev/null || true
  fi
  # xvfb_start reuses an existing DISPLAY without owning it. Only stop the
  # private Xvfb process that this script actually started.
  if [[ -n "${SMARTCLEAN_XVFB_PID}" ]]; then
    xvfb_stop
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

setsid ros2 launch smartclean_gazebo trash_mission.launch.py "$@" &
launch_pid=$!

set +e
wait "${launch_pid}"
launch_status=$?
set -e
exit "${launch_status}"
