#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pixi_bin="${project_root}/.tools/bin/pixi"

export PIXI_HOME="${project_root}/.tools/pixi-home"
export PIXI_CACHE_DIR="${project_root}/.cache/pixi"
export PIXI_NO_CONFIG=1

if [[ ! -x "${pixi_bin}" ]]; then
  "${project_root}/scripts/bootstrap_ros2_env.sh"
fi

cd "${project_root}"

case "${1:-shell}" in
  install)
    exec "${project_root}/scripts/bootstrap_ros2_env.sh"
    ;;
  shell)
    exec "${pixi_bin}" shell
    ;;
  build)
    exec "${pixi_bin}" run ros-build
    ;;
  test)
    exec "${pixi_bin}" run ros-test
    ;;
  demo)
    shift
    exec "${pixi_bin}" run ros-demo -- "$@"
    ;;
  verify)
    exec "${pixi_bin}" run ros-verify
    ;;
  gazebo)
    shift
    exec "${pixi_bin}" run gazebo-smoke -- "$@"
    ;;
  gazebo-verify)
    exec "${pixi_bin}" run gazebo-verify
    ;;
  trash-verify)
    exec "${pixi_bin}" run gazebo-trash-verify
    ;;
  camera-verify)
    exec "${pixi_bin}" run gazebo-camera-verify
    ;;
  perception-verify)
    exec "${pixi_bin}" run gazebo-perception-verify
    ;;
  position-verify)
    exec "${pixi_bin}" run gazebo-position-verify
    ;;
  lidar-verify)
    exec "${pixi_bin}" run gazebo-lidar-verify
    ;;
  nav2)
    shift
    exec "${pixi_bin}" run gazebo-nav2 -- "$@"
    ;;
  nav2-verify)
    exec "${pixi_bin}" run gazebo-nav2-verify
    ;;
  drive)
    shift
    exec "${pixi_bin}" run gazebo-drive -- "$@"
    ;;
  drive-verify)
    exec "${pixi_bin}" run gazebo-drive-verify
    ;;
  drive-gui)
    exec "${pixi_bin}" run gazebo-drive-gui
    ;;
  doctor)
    exec "${pixi_bin}" run ros-doctor
    ;;
  run)
    shift
    if [[ "$#" -eq 0 ]]; then
      echo "用法：bash scripts/ros2.sh run <命令> [参数...]" >&2
      exit 2
    fi
    exec "${pixi_bin}" run -- "$@"
    ;;
  *)
    cat >&2 <<'USAGE'
用法：bash scripts/ros2.sh {install|shell|build|test|demo|verify|gazebo|gazebo-verify|trash-verify|camera-verify|perception-verify|position-verify|lidar-verify|nav2|nav2-verify|drive|drive-verify|drive-gui|doctor|run}

示例：
  bash scripts/ros2.sh drive          # 启动 Gazebo 差速清扫车（Ctrl+C 停止）
  bash scripts/ros2.sh drive-verify   # 自动验证差速闭环
  bash scripts/ros2.sh drive-gui      # Gazebo GUI + RViz2（需要桌面 DISPLAY）
  bash scripts/ros2.sh camera-verify  # 自动验证 RGB 相机桥接与像素输出
  bash scripts/ros2.sh perception-verify  # 自动验证像素级垃圾识别（真实图像+空场景）
  bash scripts/ros2.sh position-verify    # 自动验证深度反投影垃圾位置估计
  bash scripts/ros2.sh lidar-verify       # 自动验证 2D LiDAR /scan 与完整 TF
  bash scripts/ros2.sh nav2              # Gazebo + Nav2 导航（可加 gui:=true rviz:=true）
  bash scripts/ros2.sh nav2-verify       # 自动验证 Nav2 双目标导航闭环

注意：一次只输入一个命令。不要把两条命令粘贴成一行，
例如 "bash scripts/ros2.sh drivebash scripts/ros2.sh drive"
是误粘贴，正确命令只有 "bash scripts/ros2.sh drive"。
USAGE
    exit 2
    ;;
esac
