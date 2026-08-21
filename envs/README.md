# envs：环境说明

本目录记录项目环境的安装方式和版本，不保存真实虚拟环境或大型二进制库。

## 当前已验证环境

- 宿主系统：Ubuntu 20.04.6 LTS，x86_64
- 宿主基础 Python：3.8.10
- 二维仿真、A*、全覆盖规划和 HTML 动画：仅使用 Python 标准库
- 仓库内环境管理器：Pixi 0.77.0
- ROS 2：Humble（RoboStack 社区构建，Python 3.12.13）
- ROS 包：Desktop、Nav2 1.1.20、SLAM Toolbox 2.6.10、`ros_gz` 0.244.24
- Gazebo：Fortress 6.16.0；本地最小 World `/clock` 与差速清扫车运动闭环均通过探针
- ROS 中间件：默认 Fast DDS；项目固定 `ROS_DOMAIN_ID=42`
- 自动测试：宿主与 Pixi 环境均已验证

完整精确依赖由仓库根目录的 `pixi.lock` 固定。`.pixi/`、`.tools/`、`.cache/`、`.ros/` 和 `.gazebo/` 都在仓库内但被 Git 忽略；当前实际占用会随包缓存变化。

## 安装 ROS 2 环境

```bash
# 在仓库根目录执行
bash scripts/ros2.sh install
```

安装脚本固定下载 Pixi 0.77.0，并检查发布资产 SHA-256；随后严格使用已提交的锁文件安装。不要同时 `source /opt/ros/*/setup.bash` 或激活其他 Conda 环境，否则可能混入不兼容的 Python/C++ ABI。

常用命令：

```bash
bash scripts/ros2.sh build
bash scripts/ros2.sh test
bash scripts/ros2.sh verify
bash scripts/ros2.sh gazebo-verify
bash scripts/ros2.sh drive-verify
bash scripts/ros2.sh gazebo
bash scripts/ros2.sh drive
bash scripts/ros2.sh shell
```

这条 Pixi 路径是当前 Ubuntu 20.04 机器在无 Docker daemon 权限时的已验证方案，属于社区支持的 ROS Tier 3 环境。正式可移植主线仍是 `compose.ros2.yaml` 描述的 Ubuntu 22.04 + 官方 ROS 2 Humble 包；本轮仅完成 Compose 语法检查，未在当前代理会话中构建镜像。

## 本地虚拟环境

如果后续需要安装 Python 依赖，优先在仓库内部创建已被 `.gitignore` 排除的 `.venv/`：

```bash
# 在仓库根目录执行
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

新增依赖时必须同步更新 `pixi.toml`、重新生成并审查 `pixi.lock`，同时记录包名、精确版本、用途、安装命令和验证结果。模型权重、数据集、ROS2 构建产物和完整虚拟环境不得提交到 Git。
