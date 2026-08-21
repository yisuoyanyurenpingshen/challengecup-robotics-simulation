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
export SMARTCLEAN_GAZEBO_LOG_DIR="${SMARTCLEAN_GAZEBO_LOG_DIR:-${project_root}/.gazebo/log/drive-verify-${BASHPID}}"
verify_domain_id=$((200 + BASHPID % 20))
export ROS_DOMAIN_ID="${SMARTCLEAN_DRIVE_VERIFY_DOMAIN_ID:-${verify_domain_id}}"
export IGN_PARTITION="smartclean_drive_verify_${BASHPID}"
mkdir -p "$(dirname "${SMARTCLEAN_GAZEBO_LOG_DIR}")"

setsid ros2 launch smartclean_gazebo drive.launch.py record:=false &
launch_pid=$!

cleanup() {
  # Signal launch once and let it cascade SIGINT to managed children. Sending
  # SIGINT to the whole process group here would race launch's own shutdown.
  kill -INT "${launch_pid}" 2>/dev/null || true
  for _ in {1..50}; do
    if ! kill -0 "${launch_pid}" 2>/dev/null; then
      wait "${launch_pid}" 2>/dev/null || true
      return
    fi
    sleep 0.1
  done
  kill -TERM -- "-${launch_pid}" 2>/dev/null || kill -TERM "${launch_pid}" 2>/dev/null || true
  wait "${launch_pid}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

python3 scripts/gazebo_drive_probe.py

if ! kill -0 "${launch_pid}" 2>/dev/null; then
  echo "Gazebo 差速验证失败：本轮 launch 已提前退出" >&2
  exit 1
fi
if ! ign service -l | rg -Fxq "/world/smartclean_drive/control"; then
  echo "Gazebo 差速验证失败：未发现 smartclean_drive World 控制服务" >&2
  exit 1
fi
if ! ign topic -l | rg -Fxq "/smartclean/odom"; then
  echo "Gazebo 差速验证失败：未发现 /smartclean/odom" >&2
  exit 1
fi
if ! ign topic -l | rg -Fxq "/smartclean/tf"; then
  echo "Gazebo 差速验证失败：未发现 /smartclean/tf" >&2
  exit 1
fi
echo "Gazebo 差速 World 验证通过：/world/smartclean_drive/control"
