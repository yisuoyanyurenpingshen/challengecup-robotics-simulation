# scripts：可执行入口与工具

本目录保存演示、实验、数据处理和维护脚本。

当前脚本：

- `run_demo.py`：自动加入 `src/` 到模块路径，运行二维默认演示，无需提前安装项目包。
- `bootstrap_ros2_env.sh`：校验并安装仓库内 Pixi 与锁定的 ROS 2 环境。
- `ros2.sh`：ROS 环境统一入口，提供 `install/build/test/demo/verify/gazebo/gazebo-verify/drive/drive-verify/trash-verify/camera-verify/perception-verify/position-verify/lidar-verify/nav2/nav2-verify/doctor/run/shell`。
- `ros2_build.sh`：只扫描 `ros2_ws/src` 的 colcon 构建脚本。
- `ros2_test.sh`：执行 ROS 包测试并汇总 JUnit 结果。
- `ros2_demo.sh`：启动 SmartClean ROS 2 回放桥。
- `verify_ros2.sh`、`ros2_topic_probe.py`：启动节点并自动断言状态、轨迹和位姿 Topic。
- `verify_nav2.sh`、`nav2_probe.py`：headless 端到端验证 Nav2（独立 ROS_DOMAIN_ID/
  IGN_PARTITION、双目标、/plan、Nav2 /cmd_vel、/odom 移动、到达误差、停车与进程清理）。
- `generate_nav2_map.py`：离线生成与 Gazebo World 一致的静态地图（PGM+YAML）。
- `gazebo_smoke.sh`：启动本地 Gazebo Fortress headless 最小场景与 `/clock` 桥。
- `verify_gazebo.sh`、`gazebo_clock_probe.py`：自动启动场景、断言 ROS 仿真时钟并清理子进程。
- `gazebo_drive.sh`：启动本地差速清扫车、速度安全看门狗和 ROS-Gazebo 双向桥。
- `verify_gazebo_drive.sh`、`gazebo_drive_probe.py`：自动断言前进、转向、`/odom`、TF、断流停车并清理子进程。

使用方法：

```bash
python3 scripts/run_demo.py --show-map
python3 scripts/run_demo.py --help
```

ROS 2：

```bash
bash scripts/ros2.sh install
bash scripts/ros2.sh build
bash scripts/ros2.sh verify
bash scripts/ros2.sh gazebo-verify
bash scripts/ros2.sh drive-verify
bash scripts/ros2.sh lidar-verify
bash scripts/ros2.sh nav2-verify
bash scripts/ros2.sh gazebo
bash scripts/ros2.sh drive
bash scripts/ros2.sh demo loop_replay:=true
bash scripts/ros2.sh run ros2 topic list -t
```

脚本约定：

- 从仓库根目录运行，路径不得硬编码为个人目录。
- 提供 `--help`，错误时返回非零退出码。
- 不在脚本中保存密钥、Token 或私有服务器配置。
- 新脚本应在本 README 中补充用途和最小命令。
