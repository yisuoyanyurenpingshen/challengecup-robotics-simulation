# 2026-08-21 Gazebo 差速清扫车最小闭环

## 目标

在已经通过的 ROS2 回放桥与 Gazebo `/clock` 冒烟基础上，完成下一条可测量的机器人主线：

```text
/cmd_vel → 安全看门狗 → ROS-Gazebo bridge → Gazebo DiffDrive
                                             ├→ /odom
                                             └→ /tf（odom -> base_link）
```

本轮只声明“差速底盘运动闭环”，不把它表述为 LiDAR、定位或 Nav2 自主导航闭环。

## 技术设计

- 使用当前锁定环境中的 Gazebo Fortress 6.16.0 与 `ros_gz` 0.244.24，不新增宿主机级依赖。
- SDF 模型、World、脚本、ROS 日志和 Gazebo 运行数据全部保留在仓库或仓库内 Git 忽略目录。
- 机器人使用左右轮差速驱动，外部速度入口固定为标准 ROS2 `/cmd_vel`。
- `/cmd_vel` 不直接进入 Gazebo，而是先经过 `smartclean_cmd_vel_guard`。
- 看门狗使用单调时钟，默认 20 Hz 输出；输入断流 0.5 秒、NaN/Inf 或时钟异常时输出全零命令。
- Gazebo 内部 Topic 使用 `/smartclean/*` 命名，ROS 公开里程计和 TF 保持标准 `/odom`、`/tf`。
- 自动验收使用临时 `ROS_DOMAIN_ID` 与唯一 `IGN_PARTITION`，防止其他节点造成假阳性。

Gazebo DiffDrive 的 Topic、里程计和 TF 参数取值以本机实际版本源码为准：

- [Fortress 6.16.0 DiffDrive 实现](https://github.com/gazebosim/gz-sim/blob/ignition-gazebo6_6.16.0/src/systems/diff_drive/DiffDrive.cc)
- [Gazebo 官方 DiffDrive 示例](https://github.com/gazebosim/gz-sim/blob/main/examples/worlds/diff_drive.sdf)

## 改动路径

| 路径 | 本轮作用 |
| --- | --- |
| `ros2_ws/src/smartclean_gazebo/models/smartclean_robot/` | 清扫车 SDF 模型、模型元数据、碰撞、惯性、轮子和 DiffDrive plugin |
| `ros2_ws/src/smartclean_gazebo/worlds/smartclean_drive.sdf` | 使用本地模型的差速验证 World |
| `ros2_ws/src/smartclean_gazebo/launch/drive.launch.py` | 启动 Gazebo、四条 bridge 和速度看门狗 |
| `ros2_ws/src/smartclean_gazebo/test/test_model_contract.py` | 锁定模型、关节、Topic、frame 与资源契约 |
| `ros2_ws/src/smartclean_ros/smartclean_ros/cmd_vel_guard_core.py` | 零 ROS 依赖的速度新鲜度与有限数值安全核心 |
| `ros2_ws/src/smartclean_ros/smartclean_ros/cmd_vel_guard_node.py` | ROS2 固定频率安全中继节点 |
| `ros2_ws/src/smartclean_ros/test/test_cmd_vel_guard_core.py` | 超时、边界、非法数值、时钟回退与重置测试 |
| `scripts/gazebo_drive.sh` | 持续运行入口 |
| `scripts/gazebo_drive_probe.py` | 前进、转向、里程计、TF、时钟和停车断言 |
| `scripts/verify_gazebo_drive.sh` | 隔离启动、World/Topic 断言与进程清理 |
| `scripts/ros2.sh`、`pixi.toml` | 增加 `drive` 和 `drive-verify` 统一命令 |
| `scripts/ros2_test.sh` | 将 `smartclean_gazebo` 契约测试纳入包测试 |

技术状态已同步到根 README、`docs/00_project_charter.md`、`docs/02_system_architecture.md`、`docs/03_module_interfaces.md`、`docs/04_quickstart.md`、`docs/07_implementation_roadmap.md` 与 `docs/08_ros2_environment_and_bridge.md`。

## 验证与故障修正

依次执行：

```bash
bash scripts/ros2.sh install
bash scripts/ros2.sh build
bash scripts/ros2.sh test
bash scripts/ros2.sh verify
bash scripts/ros2.sh gazebo-verify
bash scripts/ros2.sh drive-verify
bash scripts/ros2.sh run python -m pytest -q tests
```

已取得的结果：

- 锁定环境安装成功，manifest 与 `pixi.lock` 一致。
- 三个 ROS 包构建成功。
- `colcon` 汇总为 48 项测试，0 error、0 failure、0 skipped。
- 二维核心 34 项测试通过。
- 原 ROS2 回放回归通过：`status=COMPLETED`、`path_poses=103`、覆盖率 `1.0`、碰撞 `0`。
- 原 Gazebo 时钟冒烟回归通过：`/clock` 从 `2000000 ns` 推进到 `3000000 ns`，World 控制服务存在。
- 差速专项最终结果：前进 `0.593 m`、转向 `0.982 rad`、停车后平移漂移 `0.000 m`、TF 为 `odom -> base_link`、watchdog 通过。
- `/world/smartclean_drive/control`、`/smartclean/odom` 和 `/smartclean/tf` 均由本轮 Gazebo 实例提供。
- 模型 SDF 与 World SDF 均通过 `ign sdf -k` 校验。

专项验证早期发现两项退出流程问题：看门狗没有接住 ROS launch 的外部关闭异常；清理脚本又向整个进程组重复发送 SIGINT。前者增加 `ExternalShutdownException` 处理，后者改为只通知 launch 父进程并由 launch 级联关闭，最终验证以退出码 0 且无关闭 traceback 完成。

## 当前边界与下一步

尚未完成：LiDAR `/scan`、传感器 frame、`map -> odom`、Nav2、动态障碍导航、任务 Action、YOLO、Web、LLM 和 RDK 实机验证。

下一主线里程碑为 **P4-M2：LiDAR + 完整 TF + Nav2 最小导航**。并行实验线仍可推进 P2 的五个固定环卫场景与批量 CSV 汇总。

## 关键节点交付

- 差速闭环代码、测试、技术文档和本日志已提交为 `6e75784`。
- `6e75784` 已通过普通快进推送到 GitHub `main`，没有使用强制推送。
- 当日全部成果、路径说明、启动方法和下一步已经汇总到 `docs/README0821.md`。
