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
# 直接执行安装后的 console script，而不是经 `ros2 run` 包装器：包装器是
# 独立进程，SIGINT/SIGTERM 不会可靠地转发给真正的 bridge，会留下孤儿进程。
bridge_bin="${project_root}/ros2_ws/install/smartclean_ros/lib/smartclean_ros/smartclean_bridge"
"${bridge_bin}" --ros-args \
  -p config_path:="${project_root}/configs/demo.json" \
  -p replay_period_s:=0.02 \
  -p loop_replay:=true &
bridge_pid=$!

cleanup() {
  # rclpy 的 SIGTERM 处理器不会唤醒阻塞中的 DDS wait set，后台 bridge
  # 可能残留并保持管道打开；先用 SIGINT（rclpy 按 KeyboardInterrupt 退出），
  # 超时后再升级 SIGTERM/SIGKILL，确保不留下孤儿进程。
  kill -INT "${bridge_pid}" 2>/dev/null || true
  for _ in {1..30}; do
    kill -0 "${bridge_pid}" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "${bridge_pid}" 2>/dev/null; then
    kill -TERM "${bridge_pid}" 2>/dev/null || true
    for _ in {1..20}; do
      kill -0 "${bridge_pid}" 2>/dev/null || break
      sleep 0.1
    done
  fi
  if kill -0 "${bridge_pid}" 2>/dev/null; then
    kill -KILL "${bridge_pid}" 2>/dev/null || true
  fi
  wait "${bridge_pid}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

python3 scripts/ros2_topic_probe.py

if ! kill -0 "${bridge_pid}" 2>/dev/null; then
  echo "ROS 2 Topic 验证失败：本轮桥接节点已提前退出" >&2
  exit 1
fi
