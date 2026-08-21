#!/usr/bin/env bash
# 端到端验证垃圾位置估计：
#   - 深度相机 /camera/depth/image_rect_raw + camera_info 真实到达且合法；
#   - /smartclean/detections 至少一个 position_valid=true 的目标；
#   - 位置在 odom/map 帧且与真值（仅用于误差评估）误差小于阈值；
#   - camera_optical_frame -> odom TF 连通。
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
  echo "位置估计验证失败：无可用 GLX 显示。请执行 bash scripts/fetch_xvfb.sh，" >&2
  echo "或在有桌面的环境运行；headless 底盘验证请改用 bash scripts/ros2.sh drive-verify" >&2
  exit 2
fi

export ROS2CLI_DISABLE_DAEMON=1
export SMARTCLEAN_GAZEBO_LOG_DIR="${SMARTCLEAN_GAZEBO_LOG_DIR:-${project_root}/.gazebo/log/position-verify-${BASHPID}}"
export ROS_DOMAIN_ID="${SMARTCLEAN_POSITION_VERIFY_DOMAIN_ID:-$((190 + BASHPID % 40))}"
export IGN_PARTITION="smartclean_position_verify_${BASHPID}"
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

setsid ros2 launch smartclean_perception perception.launch.py \
  "world_path:=${trash_world}" camera:=true record:=false &
launch_pid=$!

if ! python3 scripts/position_probe.py --timeout 90; then
  echo "垃圾位置估计验证失败" >&2
  exit 1
fi

echo "垃圾位置估计验证通过：深度相机 + 反投影 + TF 变换，误差 < 0.45 m"
