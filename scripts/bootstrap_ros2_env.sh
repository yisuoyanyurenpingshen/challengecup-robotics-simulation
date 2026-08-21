#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pixi_version="v0.77.0"
pixi_archive="pixi-x86_64-unknown-linux-musl.tar.gz"
expected_sha256="bff2f77ef23178f0c73c7ddbc90ca57c68f8b75a5bd85ce8e7404f33b32852d5"
download_url="https://github.com/prefix-dev/pixi/releases/download/${pixi_version}/${pixi_archive}"
download_dir="${project_root}/.tools/downloads/pixi-${pixi_version}"
pixi_bin="${project_root}/.tools/bin/pixi"

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "当前脚本只支持 Linux x86_64；检测到 $(uname -s) $(uname -m)。" >&2
  exit 2
fi

mkdir -p "${download_dir}" "$(dirname "${pixi_bin}")" \
  "${project_root}/.cache/pixi" "${project_root}/.tools/pixi-home"

if [[ ! -x "${pixi_bin}" ]]; then
  echo "下载 Pixi ${pixi_version} 到仓库内 .tools/ ..."
  curl --fail --location --retry 3 --show-error \
    --output "${download_dir}/${pixi_archive}" "${download_url}"
  actual_sha256="$(sha256sum "${download_dir}/${pixi_archive}" | awk '{print $1}')"
  if [[ "${actual_sha256}" != "${expected_sha256}" ]]; then
    echo "Pixi 下载校验失败：期望 ${expected_sha256}，实际 ${actual_sha256}" >&2
    exit 4
  fi
  tar -xzf "${download_dir}/${pixi_archive}" -C "${download_dir}"
  install -m 0755 "${download_dir}/pixi" "${pixi_bin}"
fi

export PIXI_HOME="${project_root}/.tools/pixi-home"
export PIXI_CACHE_DIR="${project_root}/.cache/pixi"
export PIXI_NO_CONFIG=1

actual_version="$(${pixi_bin} --version)"
if [[ "${actual_version}" != "pixi 0.77.0" ]]; then
  echo "Pixi 版本不匹配：期望 pixi 0.77.0，实际 ${actual_version}" >&2
  exit 3
fi

echo "安装锁定的 ROS 2 Humble 环境（首次执行需要下载依赖）..."
cd "${project_root}"
"${pixi_bin}" install --locked
echo "ROS 2 环境已安装在 ${project_root}/.pixi/envs/default"
