#!/usr/bin/env bash
# 端到端验证 2D LiDAR 与完整 TF：
#   - /scan 收到且参数合法（360 样本、范围 0.1-12 m）；
#   - frame_id=lidar_link，存在有限测距；
#   - odom -> lidar_link TF 连通（经 base_footprint/base_link）；
#   - 原地旋转时 /scan 测距发生变化（真实扫描而非静态数据）；
#   - /odom 与速度安全看门狗不回归。
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
  echo "LiDAR 验证失败：无可用 GLX 显示。请执行 bash scripts/fetch_xvfb.sh，" >&2
  echo "或在有桌面的环境运行；headless 底盘验证请改用 bash scripts/ros2.sh drive-verify" >&2
  exit 2
fi

export ROS2CLI_DISABLE_DAEMON=1
export SMARTCLEAN_GAZEBO_LOG_DIR="${SMARTCLEAN_GAZEBO_LOG_DIR:-${project_root}/.gazebo/log/lidar-verify-${BASHPID}}"
export ROS_DOMAIN_ID="${SMARTCLEAN_LIDAR_VERIFY_DOMAIN_ID:-$((200 + BASHPID % 30))}"
export IGN_PARTITION="smartclean_lidar_verify_${BASHPID}"
export IGN_GAZEBO_RESOURCE_PATH="${project_root}/ros2_ws/install/smartclean_gazebo/share/smartclean_gazebo/models${IGN_GAZEBO_RESOURCE_PATH:+:${IGN_GAZEBO_RESOURCE_PATH}}"
mkdir -p "$(dirname "${SMARTCLEAN_GAZEBO_LOG_DIR}")"

launch_pid=""

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

setsid ros2 launch smartclean_gazebo drive.launch.py \
  "world_path:=${trash_world}" camera:=true lidar:=true record:=false &
launch_pid=$!

if ! python3 scripts/lidar_probe.py --timeout 90; then
  echo "LiDAR 验证失败" >&2
  exit 1
fi

echo "LiDAR 验证通过：/scan 360 样本 + lidar_link TF 连通 + /odom/看门狗不回归"
