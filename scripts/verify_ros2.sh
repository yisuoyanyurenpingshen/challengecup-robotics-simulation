#!/usr/bin/env bash
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
verify_domain_id=$((100 + BASHPID % 100))
export ROS_DOMAIN_ID="${SMARTCLEAN_VERIFY_DOMAIN_ID:-${verify_domain_id}}"
ros2 run smartclean_ros smartclean_bridge --ros-args \
  -p config_path:="${project_root}/configs/demo.json" \
  -p replay_period_s:=0.02 \
  -p loop_replay:=true &
bridge_pid=$!

cleanup() {
  kill "${bridge_pid}" 2>/dev/null || true
  wait "${bridge_pid}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

python3 scripts/ros2_topic_probe.py

if ! kill -0 "${bridge_pid}" 2>/dev/null; then
  echo "ROS 2 Topic 验证失败：本轮桥接节点已提前退出" >&2
  exit 1
fi
