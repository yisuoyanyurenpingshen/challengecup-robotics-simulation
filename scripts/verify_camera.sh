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

# 相机传感器渲染需要 GLX：无 DISPLAY 时用仓库内 Xvfb（xvfb_stop 在 cleanup 中调用）。
# shellcheck source=scripts/xvfb_env.sh
source scripts/xvfb_env.sh
if ! xvfb_start; then
  echo "RGB 相机验证失败：无可用 GLX 显示。请执行 bash scripts/fetch_xvfb.sh，" >&2
  echo "或在有桌面的环境运行；headless 底盘验证请改用 bash scripts/ros2.sh drive-verify" >&2
  exit 2
fi

export ROS2CLI_DISABLE_DAEMON=1
export SMARTCLEAN_GAZEBO_LOG_DIR="${SMARTCLEAN_GAZEBO_LOG_DIR:-${project_root}/.gazebo/log/camera-verify-${BASHPID}}"
verify_domain_id=$((180 + BASHPID % 50))
export ROS_DOMAIN_ID="${SMARTCLEAN_CAMERA_VERIFY_DOMAIN_ID:-${verify_domain_id}}"
export IGN_PARTITION="smartclean_camera_verify_${BASHPID}"
export IGN_GAZEBO_RESOURCE_PATH="${project_root}/ros2_ws/install/smartclean_gazebo/share/smartclean_gazebo/models${IGN_GAZEBO_RESOURCE_PATH:+:${IGN_GAZEBO_RESOURCE_PATH}}"
mkdir -p "$(dirname "${SMARTCLEAN_GAZEBO_LOG_DIR}")"

setsid ros2 launch smartclean_gazebo drive.launch.py \
  world_path:="${project_root}/ros2_ws/install/smartclean_gazebo/share/smartclean_gazebo/worlds/smartclean_trash.sdf" \
  camera:=true record:=false &
launch_pid=$!

cleanup() {
  kill -INT "${launch_pid}" 2>/dev/null || true
  for _ in {1..50}; do
    if ! kill -0 "${launch_pid}" 2>/dev/null; then
      wait "${launch_pid}" 2>/dev/null || true
      break
    fi
    sleep 0.1
  done
  kill -TERM -- "-${launch_pid}" 2>/dev/null || kill -TERM "${launch_pid}" 2>/dev/null || true
  wait "${launch_pid}" 2>/dev/null || true
  xvfb_stop
}
trap cleanup EXIT INT TERM

python3 scripts/camera_probe.py

if ! kill -0 "${launch_pid}" 2>/dev/null; then
  echo "RGB 相机验证失败：本轮 launch 已提前退出" >&2
  exit 1
fi
if ! ign topic -l | grep -Fxq "/smartclean/camera/image"; then
  echo "RGB 相机验证失败：未发现 Gazebo /smartclean/camera/image" >&2
  exit 1
fi
if ! ign topic -l | grep -Fxq "/smartclean/camera/camera_info"; then
  echo "RGB 相机验证失败：未发现 Gazebo /smartclean/camera/camera_info" >&2
  exit 1
fi
echo "Gazebo RGB 相机验证通过：/smartclean/camera/image + camera_info"
