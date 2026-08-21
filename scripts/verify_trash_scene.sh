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
export ROS2CLI_DISABLE_DAEMON=1
export SMARTCLEAN_GAZEBO_LOG_DIR="${SMARTCLEAN_GAZEBO_LOG_DIR:-${project_root}/.gazebo/log/trash-scene-${BASHPID}}"
verify_domain_id=$((300 + BASHPID % 20))
export ROS_DOMAIN_ID="${SMARTCLEAN_TRASH_VERIFY_DOMAIN_ID:-${verify_domain_id}}"
export IGN_PARTITION="smartclean_trash_verify_${BASHPID}"
export IGN_GAZEBO_RESOURCE_PATH="${project_root}/ros2_ws/install/smartclean_gazebo/share/smartclean_gazebo/models${IGN_GAZEBO_RESOURCE_PATH:+:${IGN_GAZEBO_RESOURCE_PATH}}"
mkdir -p "$(dirname "${SMARTCLEAN_GAZEBO_LOG_DIR}")"

setsid ign gazebo -r -s -v 2 \
  "${project_root}/ros2_ws/install/smartclean_gazebo/share/smartclean_gazebo/worlds/smartclean_trash.sdf" \
  --force-version 6 &
gazebo_pid=$!

cleanup() {
  kill -INT -- "-${gazebo_pid}" 2>/dev/null || kill -INT "${gazebo_pid}" 2>/dev/null || true
  for _ in {1..50}; do
    if ! kill -0 "${gazebo_pid}" 2>/dev/null; then
      wait "${gazebo_pid}" 2>/dev/null || true
      return
    fi
    sleep 0.1
  done
  kill -TERM -- "-${gazebo_pid}" 2>/dev/null || kill -TERM "${gazebo_pid}" 2>/dev/null || true
  wait "${gazebo_pid}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

python3 scripts/trash_scene_probe.py

if ! kill -0 "${gazebo_pid}" 2>/dev/null; then
  echo "垃圾场景验证失败：本轮 Gazebo 已提前退出" >&2
  exit 1
fi
if ! ign service -l | grep -Fxq "/world/smartclean_trash/control"; then
  echo "垃圾场景验证失败：未发现 smartclean_trash World 控制服务" >&2
  exit 1
fi
echo "垃圾场景验证通过：/world/smartclean_trash/control"
