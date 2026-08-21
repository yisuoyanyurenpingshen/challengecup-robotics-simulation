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
  drive)
    shift
    exec "${pixi_bin}" run gazebo-drive -- "$@"
    ;;
  drive-verify)
    exec "${pixi_bin}" run gazebo-drive-verify
    ;;
  doctor)
    exec "${pixi_bin}" run ros-doctor
    ;;
  run)
    shift
    if [[ "$#" -eq 0 ]]; then
      echo "用法：scripts/ros2.sh run <命令> [参数...]" >&2
      exit 2
    fi
    exec "${pixi_bin}" run -- "$@"
    ;;
  *)
    echo "用法：scripts/ros2.sh {install|shell|build|test|demo|verify|gazebo|gazebo-verify|drive|drive-verify|doctor|run}" >&2
    exit 2
    ;;
esac
