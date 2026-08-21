# ros2_ws：ROS 2 工作空间

本目录承载 SmartClean-Sim 的 ROS 2 适配层，核心算法仍位于仓库根目录的 `src/smartclean_sim`，不反向依赖 ROS。

```text
ros2_ws/src/smartclean_core/     将根目录二维核心与 demo 配置安装到 ROS 前缀
ros2_ws/src/smartclean_ros/      状态、轨迹与逐帧位姿回放桥
ros2_ws/src/smartclean_gazebo/   Fortress 最小 World、headless launch 与时钟桥
ros2_ws/build/                   colcon 构建产物，Git 忽略
ros2_ws/install/                 colcon 安装空间，Git 忽略
ros2_ws/log/                     colcon 日志，Git 忽略
```

统一从仓库根目录执行：

```bash
bash scripts/ros2.sh install
bash scripts/ros2.sh build
bash scripts/ros2.sh test
bash scripts/ros2.sh verify
bash scripts/ros2.sh gazebo-verify
bash scripts/ros2.sh gazebo
```

不要在这里复制二维规划状态机；ROS 包只做协议转换、系统编排和外部平台适配。
