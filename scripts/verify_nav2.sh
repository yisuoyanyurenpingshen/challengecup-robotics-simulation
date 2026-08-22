#!/usr/bin/env bash
# 端到端验证 Nav2 最小自主导航闭环：
#   - 独立 ROS_DOMAIN_ID 与 IGN_PARTITION，不与其它会话串扰；
#   - headless 启动 Gazebo 垃圾场景 + 完整 TF + /scan + Nav2 全家桶；
#   - 探针等待 /navigate_to_pose，发送两个自由区域目标；
#   - 确认 /plan、Nav2 发出的 /cmd_vel、/odom 实际移动、到达误差、最终停车；
#   - 验证完成后清理全部子进程（launch 进程组 + Xvfb）。
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"

if [[ ! -f ros2_ws/install/setup.bash ]]; then
  echo "首次运行，正在构建 ROS 2 工作空间..."
  bash scripts/ros2_build.sh
fi

set +u
source ros2_ws/install/setup.bash
set -u

# shellcheck source=scripts/xvfb_env.sh
source scripts/xvfb_env.sh
if ! xvfb_start; then
  echo "Nav2 验证失败：无可用 GLX 显示。请执行 bash scripts/fetch_xvfb.sh，" >&2
  echo "或在有桌面的环境运行；无传感器验证请改用 bash scripts/ros2.sh drive-verify" >&2
  exit 2
fi

export ROS2CLI_DISABLE_DAEMON=1
export SMARTCLEAN_GAZEBO_LOG_DIR="${SMARTCLEAN_GAZEBO_LOG_DIR:-${project_root}/.gazebo/log/nav2-verify-${BASHPID}}"
export ROS_DOMAIN_ID="${SMARTCLEAN_NAV2_VERIFY_DOMAIN_ID:-$((30 + BASHPID % 100))}"
export IGN_PARTITION="smartclean_nav2_verify_${BASHPID}"
export IGN_GAZEBO_RESOURCE_PATH="${project_root}/ros2_ws/install/smartclean_gazebo/share/smartclean_gazebo/models${IGN_GAZEBO_RESOURCE_PATH:+:${IGN_GAZEBO_RESOURCE_PATH}}"
mkdir -p "${SMARTCLEAN_GAZEBO_LOG_DIR}"

launch_pid=""

stop_launch() {
  if [[ -n "${launch_pid}" ]] && kill -0 "${launch_pid}" 2>/dev/null; then
    kill -INT "${launch_pid}" 2>/dev/null || true
    for _ in {1..80}; do
      kill -0 "${launch_pid}" 2>/dev/null || break
      sleep 0.1
    done
    kill -TERM -- "-${launch_pid}" 2>/dev/null || kill -TERM "${launch_pid}" 2>/dev/null || true
    wait "${launch_pid}" 2>/dev/null || true
  fi
  launch_pid=""
}

cleanup() {
  stop_launch
  xvfb_stop
}
trap cleanup EXIT INT TERM

setsid ros2 launch smartclean_gazebo nav2.launch.py lidar:=true record:=false   > "${SMARTCLEAN_GAZEBO_LOG_DIR}/launch.log" 2>&1 &
launch_pid=$!

if ! python3 scripts/nav2_probe.py --timeout 180; then
  echo "Nav2 验证失败" >&2
  exit 1
fi

if grep -F "Detected jump back in time" "${SMARTCLEAN_GAZEBO_LOG_DIR}/launch.log"; then
  echo "Nav2 验证失败：运行期间观察到 TF 时钟倒退（jump back in time）" >&2
  exit 1
fi

echo "Nav2 验证通过：/scan + 完整 TF + AMCL + NavigateToPose 双目标 + 到达误差 + 最终停车 + 时钟单调"
