#!/usr/bin/env bash
# 把带 GLX 的 Xvfb 提取到仓库 .tools/xvfb-bin/（Git 忽略目录）。
# 需要系统已安装 xserver-xorg-core（Ubuntu/Debian）；不修改系统文件。
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work_dir="${project_root}/.tools/downloads/xvfb-deb"
dest_dir="${project_root}/.tools/xvfb-bin"
mkdir -p "${work_dir}" "${dest_dir}"

if [[ ! -f "${dest_dir}/Xvfb" ]]; then
  if command -v apt-get >/dev/null 2>&1; then
    (cd "${work_dir}" && apt-get download xvfb 2>/dev/null) || true
  fi
  deb_file="$(ls "${work_dir}"/xvfb_*.deb 2>/dev/null | head -n 1 || true)"
  if [[ -z "${deb_file}" ]]; then
    echo "无法自动获取 Xvfb 软件包：请在 Ubuntu/Debian 上手动执行" >&2
    echo "  apt-get download xvfb && dpkg-deb -x xvfb_*.deb .tools/downloads/xvfb-deb" >&2
    exit 1
  fi
  dpkg-deb -x "${deb_file}" "${work_dir}/extracted"
  cp "${work_dir}/extracted/usr/bin/Xvfb" "${dest_dir}/Xvfb"
fi

if ! "${dest_dir}/Xvfb" -help 2>&1 | grep -q "use: X"; then
  echo "提取的 Xvfb 二进制无法运行" >&2
  exit 1
fi
echo "Xvfb 已就绪：${dest_dir}/Xvfb"
