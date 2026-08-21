# envs：环境说明

本文件夹用于记录环境配置说明，不上传完整虚拟环境。

可以放：

- Python 版本说明
- PyTorch 版本说明
- CUDA 版本说明
- requirements.txt
- environment.yml
- 安装步骤记录

cat > envs/README.md <<'EOF'
# envs：环境说明

本目录用于记录项目所需环境的安装方式、版本信息和使用方法。

注意：

- 本目录只保存环境说明文件，不保存真实 conda 环境。
- 真实 conda 环境建议放在 `/home/bktx/conda_envs/`。
- ROS2 通常使用系统安装路径或已有工作空间，不建议直接塞进本目录。
- 大型环境、虚拟环境、二进制库不上传 GitHub。

推荐实际环境路径：

- YOLO / PyTorch：`/home/bktx/conda_envs/yolo`
- 通用 PyTorch：`/home/bktx/conda_envs/pytorch`
- 机器人仿真：`/home/bktx/conda_envs/robot-sim`
- ROS2：记录 source 路径和工作空间，不复制完整环境
EOF
