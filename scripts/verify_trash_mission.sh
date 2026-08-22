#!/usr/bin/env bash
# 端到端验证 detection -> 稳定目标 -> Nav2 -> 安全停车 -> 实体删除 -> 返航。
# 探针只旁路订阅；不会发布 /cmd_vel、导航目标或调用 Gazebo 删除服务。
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
  echo "垃圾任务验证失败：无可用 GLX 显示。请执行 bash scripts/fetch_xvfb.sh。" >&2
  exit 2
fi
owns_xvfb=""
if [[ -n "${SMARTCLEAN_XVFB_PID}" ]]; then
  owns_xvfb=1
fi

export ROS2CLI_DISABLE_DAEMON=1
export SMARTCLEAN_GAZEBO_LOG_DIR="${SMARTCLEAN_GAZEBO_LOG_DIR:-${project_root}/.gazebo/log/trash-mission-verify-${BASHPID}}"
export ROS_DOMAIN_ID="${SMARTCLEAN_TRASH_MISSION_VERIFY_DOMAIN_ID:-$((80 + BASHPID % 100))}"
export IGN_PARTITION="smartclean_trash_mission_verify_${BASHPID}"
export IGN_GAZEBO_RESOURCE_PATH="${project_root}/ros2_ws/install/smartclean_gazebo/share/smartclean_gazebo/models${IGN_GAZEBO_RESOURCE_PATH:+:${IGN_GAZEBO_RESOURCE_PATH}}"
mkdir -p "${SMARTCLEAN_GAZEBO_LOG_DIR}"

launch_pid=""

stop_launch() {
  if [[ -z "${launch_pid}" ]] || ! kill -0 "${launch_pid}" 2>/dev/null; then
    launch_pid=""
    return
  fi

  # Let ros2 launch cascade SIGINT first, then escalate to the exact process
  # group so bridge/rclpy children cannot retain DDS pipes or Gazebo transport.
  kill -INT "${launch_pid}" 2>/dev/null || true
  for _ in {1..80}; do
    kill -0 "${launch_pid}" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "${launch_pid}" 2>/dev/null; then
    kill -TERM -- "-${launch_pid}" 2>/dev/null || \
      kill -TERM "${launch_pid}" 2>/dev/null || true
    for _ in {1..50}; do
      kill -0 "${launch_pid}" 2>/dev/null || break
      sleep 0.1
    done
  fi
  if kill -0 "${launch_pid}" 2>/dev/null; then
    kill -KILL -- "-${launch_pid}" 2>/dev/null || \
      kill -KILL "${launch_pid}" 2>/dev/null || true
  fi
  wait "${launch_pid}" 2>/dev/null || true
  launch_pid=""
}

cleanup() {
  stop_launch
  if [[ -n "${owns_xvfb}" ]]; then
    xvfb_stop
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

launch_log="${SMARTCLEAN_GAZEBO_LOG_DIR}/launch.log"
setsid ros2 launch smartclean_gazebo trash_mission.launch.py \
  gui:=false rviz:=false record:=false >"${launch_log}" 2>&1 &
launch_pid=$!

probe_status=0
python3 scripts/trash_mission_probe.py --timeout 420 || probe_status=$?
if (( probe_status != 0 )); then
  echo "垃圾任务验证失败：probe exit=${probe_status}" >&2
  echo "launch 日志末尾：${launch_log}" >&2
  tail -n 120 "${launch_log}" >&2 || true
  exit "${probe_status}"
fi

if ! kill -0 "${launch_pid}" 2>/dev/null; then
  echo "垃圾任务验证失败：任务完成前 launch 已退出" >&2
  tail -n 120 "${launch_log}" >&2 || true
  exit 1
fi

if grep -F "Detected jump back in time" "${launch_log}"; then
  echo "垃圾任务验证失败：launch 日志出现 TF/clock 时间倒退" >&2
  exit 1
fi
if grep -F "Traceback (most recent call last):" "${launch_log}"; then
  echo "垃圾任务验证失败：launch 日志出现 Python traceback" >&2
  exit 1
fi

echo "垃圾任务验证通过：真实 RGB/检测 + 稳定轨迹 + Nav2 + 安全工具门控 + 实体删除 + 全量返航停车"
