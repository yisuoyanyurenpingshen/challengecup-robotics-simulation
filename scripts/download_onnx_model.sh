#!/usr/bin/env bash
# 下载并校验一个 ONNX 垃圾检测模型（幂等）。
#
# 用法：
#   bash scripts/download_onnx_model.sh weights/model-card-template.json
#
# 流程：读取模型卡 -> 若文件已存在则只做 SHA-256 校验 -> 否则下载到
# weights/downloads/<file_name> -> 校验哈希 -> 校验通过才把文件移到
# weights/downloads/ 正式位置。权重目录被 Git 忽略，绝不会被提交。
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
card_path="${1:-}"
if [[ -z "${card_path}" ]]; then
  echo "用法：bash scripts/download_onnx_model.sh <模型卡 JSON 路径>" >&2
  exit 2
fi
if [[ ! -f "${card_path}" ]]; then
  echo "模型卡不存在：${card_path}" >&2
  exit 2
fi

download_dir="${project_root}/weights/downloads"
mkdir -p "${download_dir}"

source_url="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["source_url"])' "${card_path}")"
file_name="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["file_name"])' "${card_path}")"
sha_256="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["sha_256"])' "${card_path}")"

if [[ ! "${source_url}" =~ ^https?:// ]]; then
  echo "模型卡 source_url 不是合法的 http(s) 地址" >&2
  exit 2
fi
if [[ ! "${sha_256}" =~ ^[0-9a-f]{64}$ ]]; then
  echo "模型卡 sha_256 不是 64 位十六进制哈希" >&2
  exit 2
fi

target="${download_dir}/${file_name}"
if [[ -f "${target}" ]]; then
  actual="$(sha256sum "${target}" | awk '{print $1}')"
  if [[ "${actual}" == "${sha_256}" ]]; then
    echo "已存在且哈希一致：${target}"
    exit 0
  fi
  echo "已存在文件哈希不一致，重新下载：${target}" >&2
  rm -f "${target}"
fi

tmp_file="${target}.part"
rm -f "${tmp_file}"
echo "下载 ${source_url} -> ${tmp_file}"
if command -v curl >/dev/null 2>&1; then
  curl -fL --retry 3 --connect-timeout 30 -o "${tmp_file}" "${source_url}"
elif command -v wget >/dev/null 2>&1; then
  wget -O "${tmp_file}" "${source_url}"
else
  echo "需要 curl 或 wget" >&2
  exit 1
fi

actual="$(sha256sum "${tmp_file}" | awk '{print $1}')"
if [[ "${actual}" != "${sha_256}" ]]; then
  echo "SHA-256 校验失败：期望 ${sha_256}，实际 ${actual}" >&2
  rm -f "${tmp_file}"
  exit 1
fi
mv "${tmp_file}" "${target}"
echo "已下载并通过 SHA-256 校验：${target}"
