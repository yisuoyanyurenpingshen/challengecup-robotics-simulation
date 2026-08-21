#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"
mkdir -p .ros/log ros2_ws/build ros2_ws/install ros2_ws/log

# rosidl code generation must use the environment's Python (pixi env), never a
# host interpreter such as /usr/bin/python3.6 discovered via PythonInterp.
build_python="$(command -v python3 || true)"
if [[ -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python3" ]]; then
  build_python="${CONDA_PREFIX}/bin/python3"
fi

colcon --log-base ros2_ws/log build \
  --base-paths ros2_ws/src \
  --build-base ros2_ws/build \
  --install-base ros2_ws/install \
  --symlink-install \
  --cmake-args "-DPYTHON_EXECUTABLE=${build_python}"
