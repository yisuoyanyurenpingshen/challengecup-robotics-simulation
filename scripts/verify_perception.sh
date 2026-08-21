#!/usr/bin/env bash
# 端到端验证像素级垃圾识别基线：
#   Phase A：smartclean_trash 世界，要求识别到场景中真实存在的垃圾；
#   Phase B：smartclean_empty 世界，要求零虚假检测。
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
  echo "垃圾识别验证失败：无可用 GLX 显示。请执行 bash scripts/fetch_xvfb.sh，" >&2
  echo "或在有桌面的环境运行；headless 底盘验证请改用 bash scripts/ros2.sh drive-verify" >&2
  exit 2
fi

export ROS2CLI_DISABLE_DAEMON=1
export SMARTCLEAN_GAZEBO_LOG_DIR="${SMARTCLEAN_GAZEBO_LOG_DIR:-${project_root}/.gazebo/log/perception-verify-${BASHPID}}"
export ROS_DOMAIN_ID="${SMARTCLEAN_PERCEPTION_VERIFY_DOMAIN_ID:-$((180 + BASHPID % 50))}"
export IGN_PARTITION="smartclean_perception_verify_${BASHPID}"
export IGN_GAZEBO_RESOURCE_PATH="${project_root}/ros2_ws/install/smartclean_gazebo/share/smartclean_gazebo/models${IGN_GAZEBO_RESOURCE_PATH:+:${IGN_GAZEBO_RESOURCE_PATH}}"
mkdir -p "$(dirname "${SMARTCLEAN_GAZEBO_LOG_DIR}")"

launch_pid=""

start_launch() {
  local world_path="$1"
  setsid ros2 launch smartclean_perception perception.launch.py \
    "world_path:=${world_path}" camera:=true record:=false &
  launch_pid=$!
}

stop_launch() {
  if [[ -n "${launch_pid}" ]] && kill -0 "${launch_pid}" 2>/dev/null; then
    kill -INT "${launch_pid}" 2>/dev/null || true
    for _ in {1..50}; do
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

share_dir="${project_root}/ros2_ws/install/smartclean_gazebo/share/smartclean_gazebo"
trash_world="${share_dir}/worlds/smartclean_trash.sdf"
empty_world="${share_dir}/worlds/smartclean_empty.sdf"

echo "== Phase A：垃圾场景识别验证 =="
start_launch "${trash_world}"
if ! python3 scripts/perception_probe.py --expect detections --timeout 60; then
  echo "垃圾识别验证失败：Phase A 未通过" >&2
  exit 1
fi
stop_launch
sleep 2

echo "== Phase B：空场景无虚假检测验证 =="
start_launch "${empty_world}"
if ! python3 scripts/perception_probe.py --expect empty --timeout 45; then
  echo "垃圾识别验证失败：Phase B 未通过" >&2
  exit 1
fi

echo "垃圾识别验证通过：真实图像检测 + 空场景零虚假检测"
