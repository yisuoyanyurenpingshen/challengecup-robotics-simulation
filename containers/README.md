# containers：标准 ROS 2 容器蓝图

`ros2-humble/Dockerfile` 基于 Ubuntu 22.04 的官方 `ros:humble-ros-base-jammy` 镜像，并固定 2026-08-21 查询到的多架构内容 digest；其上安装 Desktop、构建工具、Nav2、SLAM Toolbox 和 `ros_gz`。`compose.ros2.yaml` 将仓库挂载到 `/workspace`，使用 host network 方便未来与 RDK 的 DDS 发现。

本轮已通过 `docker compose config --quiet` 语法校验。当前 Codex 执行会话不能访问 Docker daemon，因此没有声称镜像构建或容器内 Gazebo 已验证。基础镜像 digest 已固定，但 `apt` 软件源仍可能更新；首次成功构建后还应保存镜像 digest 和 Debian/ROS 包清单。

在具备 Docker daemon 权限的终端中：

```bash
export SMARTCLEAN_UID="$(id -u)"
export SMARTCLEAN_GID="$(id -g)"
docker compose -f compose.ros2.yaml build
docker compose -f compose.ros2.yaml run --rm ros2 bash
```

不要使用 `--privileged`；后续相机、串口和 GPU 应按设备逐项映射。当前 Compose 为 DDS 开发使用 host network、host IPC 和整仓库读写挂载，只应运行本项目构建的可信镜像与场景，不能当成不可信代码沙箱。镜像层由 Docker daemon 管理，不位于 Git 工作区。
