#!/usr/bin/env bash
# 仓库内 Xvfb 辅助：无 DISPLAY 时启动一个带 GLX 的软件 X 显示，
# 供 Gazebo 传感器渲染使用。不修改宿主机系统，不要求 root。
#
# 候选顺序：
#   1. 已设置的 DISPLAY 直接复用；
#   2. 仓库 .tools/xvfb-bin/Xvfb（scripts/fetch_xvfb.sh 获取，二进制不入 Git）；
#   3. 系统 Xvfb。
#
# Ubuntu 的 Xvfb 是一个双重 fork 的包装进程：真实服务器会被 init 收养，
# 因此停止时必须按进程组清理，否则会残留孤儿 X 服务器。
#
# 用法（需 source 本文件）：
#   source scripts/xvfb_env.sh
#   xvfb_start || exit 2
#   ... 使用 $DISPLAY ...
#   xvfb_stop

SMARTCLEAN_XVFB_PID=""
SMARTCLEAN_XVFB_DISPLAY=""
SMARTCLEAN_XVFB_KILL_GROUP=""

_smartclean_project_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

_smartclean_xvfb_bin() {
  local project_root
  project_root="$(_smartclean_project_root)"
  if [[ -x "${project_root}/.tools/xvfb-bin/Xvfb" ]]; then
    echo "${project_root}/.tools/xvfb-bin/Xvfb"
    return 0
  fi
  if command -v Xvfb >/dev/null 2>&1; then
    command -v Xvfb
    return 0
  fi
  return 1
}

_smartclean_glx_ready() {
  # xdpyinfo 不可用时只确认 socket 存在（不保证 GLX）。
  # 注意：不能写成 xdpyinfo | grep -q——set -o pipefail 下 grep -q 提前退出
  # 会让 xdpyinfo 收到 SIGPIPE，整个管道被误判为失败。
  if command -v xdpyinfo >/dev/null 2>&1; then
    local extension_report
    extension_report="$(xdpyinfo 2>/dev/null || true)"
    if grep -q "^    GLX" <<<"${extension_report}"; then
      return 0
    fi
    return 1
  fi
  [[ -S "/tmp/.X11-unix/X${SMARTCLEAN_XVFB_DISPLAY#:}" ]]
}

xvfb_start() {
  if [[ -n "${DISPLAY:-}" ]]; then
    SMARTCLEAN_XVFB_DISPLAY="${DISPLAY}"
    return 0
  fi
  local xvfb_bin
  if ! xvfb_bin="$(_smartclean_xvfb_bin)"; then
    echo "未找到 Xvfb：请在有桌面显示的环境运行，或执行 scripts/fetch_xvfb.sh 获取仓库内 Xvfb" >&2
    return 1
  fi

  # 避开已有 socket 或锁文件的陈旧显示（例如旧版 conda Xvfb 残留）。
  local display_number attempt
  for attempt in 1 2 3 4 5 6 7 8 9; do
    display_number=$((90 + ((BASHPID + attempt) % 9)))
    if [[ ! -S "/tmp/.X11-unix/X${display_number}" ]] &&
       [[ ! -e "/tmp/.X${display_number}-lock" ]]; then
      break
    fi
  done
  SMARTCLEAN_XVFB_DISPLAY=":${display_number}"
  export DISPLAY="${SMARTCLEAN_XVFB_DISPLAY}"

  setsid "${xvfb_bin}" "${SMARTCLEAN_XVFB_DISPLAY}" \
    -screen 0 1280x1024x24 -ac -nolisten tcp >/dev/null 2>&1 &
  SMARTCLEAN_XVFB_PID=$!
  SMARTCLEAN_XVFB_KILL_GROUP=1

  local attempt_index
  for attempt_index in 1 2; do
    local deadline=$((SECONDS + 12))
    while (( SECONDS < deadline )); do
      if ! kill -0 "${SMARTCLEAN_XVFB_PID}" 2>/dev/null; then
        break
      fi
      if _smartclean_glx_ready; then
        return 0
      fi
      sleep 0.3
    done
    # 第一次显示未及时就绪：清理后换一个显示重试一次。
    xvfb_stop
    if (( attempt_index == 1 )); then
      local retry_number=$((91 + (BASHPID + 4) % 8))
      while [[ -S "/tmp/.X11-unix/X${retry_number}" ]] ||
            [[ -e "/tmp/.X${retry_number}-lock" ]]; do
        retry_number=$((90 + (retry_number - 89) % 9))
      done
      SMARTCLEAN_XVFB_DISPLAY=":${retry_number}"
      export DISPLAY="${SMARTCLEAN_XVFB_DISPLAY}"
      setsid "${xvfb_bin}" "${SMARTCLEAN_XVFB_DISPLAY}" \
        -screen 0 1280x1024x24 -ac -nolisten tcp >/dev/null 2>&1 &
      SMARTCLEAN_XVFB_PID=$!
      SMARTCLEAN_XVFB_KILL_GROUP=1
    fi
  done
  echo "Xvfb 已启动但缺少 GLX 扩展（显示 ${SMARTCLEAN_XVFB_DISPLAY}）：传感器渲染不可用，" >&2
  echo "请执行 scripts/fetch_xvfb.sh 获取带 GLX 的 Xvfb，或清理陈旧 X 服务器后重试" >&2
  return 1
}

xvfb_stop() {
  if [[ -n "${SMARTCLEAN_XVFB_KILL_GROUP}" && -n "${SMARTCLEAN_XVFB_PID}" ]]; then
    kill -TERM -- "-${SMARTCLEAN_XVFB_PID}" 2>/dev/null || true
    for _ in {1..20}; do
      kill -0 "${SMARTCLEAN_XVFB_PID}" 2>/dev/null || break
      sleep 0.1
    done
    kill -KILL -- "-${SMARTCLEAN_XVFB_PID}" 2>/dev/null || true
  elif [[ -n "${SMARTCLEAN_XVFB_PID}" ]]; then
    kill "${SMARTCLEAN_XVFB_PID}" 2>/dev/null || true
  fi
  # Ubuntu Xvfb 是双重 fork 包装：真实服务器可能已被 init 收养，
  # 进程组清理覆盖不到，这里再按“二进制路径 + 显示号”精确补杀。
  if [[ -n "${SMARTCLEAN_XVFB_DISPLAY}" ]]; then
    pkill -f "Xvfb ${SMARTCLEAN_XVFB_DISPLAY} -screen" 2>/dev/null || true
  fi
  wait "${SMARTCLEAN_XVFB_PID}" 2>/dev/null || true
  SMARTCLEAN_XVFB_PID=""
  SMARTCLEAN_XVFB_DISPLAY=""
  SMARTCLEAN_XVFB_KILL_GROUP=""
}
