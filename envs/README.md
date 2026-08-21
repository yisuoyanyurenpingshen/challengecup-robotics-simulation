# envs：环境说明

本目录记录项目环境的安装方式和版本，不保存真实虚拟环境或大型二进制库。

## 当前 P1 基础环境

- 已验证 Python：3.8.10
- 二维仿真、A*、全覆盖规划和 HTML 动画：仅使用 Python 标准库
- 自动测试：pytest（当前服务器已安装）
- ROS2、Gazebo、YOLO 和 RDK SDK：尚未纳入基础环境

## 本地虚拟环境

如果后续需要安装 Python 依赖，优先在仓库内部创建已被 `.gitignore` 排除的 `.venv/`：

```bash
cd /home/bktx/projects/challengecup-robotics-simulation
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

新增依赖时必须同步记录：包名、精确版本、用途、安装命令和验证结果。模型权重、数据集、ROS2 构建产物和完整虚拟环境不得提交到 Git。
