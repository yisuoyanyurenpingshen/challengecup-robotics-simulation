# 2026-08-21 ROS 2 Humble、Gazebo 与回放桥

## 基本信息

- 时间：2026-08-21 12:47 CST
- 执行者：Codex（主代理及并行 ROS 工作空间、Gazebo、文档审查子任务）
- 基线提交：`0fde5d62077bc38cbebcf6e1ab98e373399103bc`
- 目标：自主规划并在公共仓库内下载、配置、实现和验证 ROS 2 环境；建立二维核心到 ROS 2 的稳定桥接，以及可继续扩展的 Gazebo/RDK 边界。

## 最终结论

本轮落地了三层可独立验收的能力：

1. 仓库内 Pixi/RoboStack ROS 2 Humble 开发环境，不修改宿主机 `/opt/ros`；
2. `smartclean_core` + `smartclean_ros`，把既有二维核心正式安装到 ROS 前缀，并回放状态、轨迹和位姿；
3. `smartclean_gazebo`，启动无在线模型依赖的 Gazebo Fortress 最小环卫 World，并把仿真 `/clock` 桥接到 ROS 2。

当前仍不是机器人动力学、`/odom`、`/scan`、`/cmd_vel`、Nav2 或实车闭环。Docker 是已校验语法和固定基础镜像 digest 的正式蓝图，但本会话没有 Docker daemon 权限，未构建镜像。RDK 是有官方版本依据的部署设计，未做板端实测。

## 宿主审计与版本决策

| 项目 | 实际值 |
| --- | --- |
| 宿主系统 | Ubuntu 20.04.6 LTS，x86_64 |
| 宿主 Python | 3.8.10 |
| Docker / Compose 客户端 | 28.1.1 / 2.35.1 |
| Docker daemon | 当前 Codex 会话无 socket 权限，未验证构建 |
| 仓库可用空间 | 约 159 GiB |
| GPU | 当前会话无可用 NVIDIA 驱动 |

没有在 Focal 宿主机原生安装已经 EOL 的 ROS 2 Foxy。正式可移植主线选择 Ubuntu 22.04 + ROS 2 Humble + Gazebo Fortress；当前机器则使用仓库内 Pixi/RoboStack Humble 继续开发。依据：

- [ROS REP-2000 支持平台](https://www.ros.org/reps/rep-2000.html)
- [ROS 2 发行版生命周期](https://docs.ros.org/en/humble/Releases.html)
- [Gazebo 与 ROS 官方配对](https://gazebosim.org/docs/latest/ros_installation/)
- [Pixi Robotics / RoboStack Tier 3 说明](https://pixi.prefix.dev/dev/robotics/)
- [RoboStack Humble 仓库](https://github.com/RoboStack/ros-humble)
- [D-Robotics TROS 通信与平台矩阵](https://developer.d-robotics.cc/tros_doc/en/quick_demo/demo_communication)
- [D-Robotics RDK X3/X5 TROS/ROS FAQ](https://developer.d-robotics.cc/rdk_x_doc/FAQ/tros_ros)

RDK 主目标定为 X5，X3 仅在 OS 3.x / Ubuntu 22.04 / TROS-Humble 下兼容；PC 和板端正常通信统一使用 `ROS_DOMAIN_ID=42`。

## 下载与仓库内环境

安装入口为 `scripts/bootstrap_ros2_env.sh`。脚本把环境管理器、缓存和实际前缀全部放在 Git 忽略目录：

```text
.tools/       Pixi 可执行文件、下载归档和 Pixi 状态
.cache/pixi/  包下载缓存
.pixi/        实际 ROS 2 环境前缀
.ros/         ROS 运行日志
.gazebo/      可选 Gazebo 录制
```

Pixi 固定为 0.77.0，下载自官方 GitHub Release；归档 SHA-256：

```text
bff2f77ef23178f0c73c7ddbc90ca57c68f8b75a5bd85ce8e7404f33b32852d5
```

最终环境关键版本：

| 组件 | 版本 |
| --- | --- |
| Python | 3.12.13 |
| ROS 2 | Humble |
| `rclpy` | 3.3.21 |
| ROS Desktop | 0.10.0 |
| Nav2 / `nav2_bringup` | 1.1.20 |
| SLAM Toolbox | 2.6.10 |
| `ros_gz` | 0.244.24 |
| Gazebo Fortress | 6.16.0 |
| colcon common extensions | 0.3.0 |
| pytest | 8.4.2 |
| vcstool | 1.1.7 |

安装结束时占用约：`.pixi` 5.1 GiB、`.cache/pixi` 1.1 GiB、`.tools` 182 MiB。精确依赖集合由 `pixi.lock` 跟踪；安装脚本使用 `pixi install --locked`，锁文件与 manifest 不一致时会失败而不是静默重新求解。

## 代码与配置变更

### 环境与统一入口

- 新增 `pixi.toml`、`pixi.lock`，固定 Humble、Desktop、Nav2、SLAM Toolbox、`ros_gz`、Gazebo、colcon、pytest 和 vcstool。
- 新增 `scripts/ros2.sh`，统一提供 `install`、`build`、`test`、`demo`、`verify`、`gazebo`、`gazebo-verify`、`doctor`、`run`、`shell`。
- 新增构建、测试、回放、Topic 探针、Gazebo 时钟探针和自动清理脚本。
- 更新 `.gitignore` / `.dockerignore`，排除环境、缓存、构建产物和运行日志。

### ROS 2 工作空间

- `smartclean_core`：用 `ament_cmake_python` 把根目录 `smartclean_sim` 与 demo 配置安装到 ROS 前缀；`smartclean_ros` 明确声明依赖。
- `smartclean_ros`：运行既有确定性仿真，发布：
  - `/smartclean/status`：Reliable + Transient Local，schema v1 JSON；
  - `/smartclean/trajectory`：Reliable + Transient Local 的 `nav_msgs/Path`；
  - `/smartclean/robot_pose`：Reliable + Transient Local 的最近回放位姿。
- 状态语义加固：`status` / `task_state` 表示当前回放帧；预计算的最终结果只出现在 `run_result_status`、`final_metrics`、`final_rates`，避免首帧 `PLANNING` 被误判为已完成。
- 栅格到 ROS `map` 使用格中心与 y 轴翻转：

```text
map_x = origin_x_m + (grid_x + 0.5) * cell_size_m
map_y = origin_y_m + (grid_height - grid_y - 0.5) * cell_size_m
```

- Topic 使用相对名称，允许后续 namespace / 多车隔离；默认 demo 配置来自安装后的 `smartclean_core` share 目录，不再依赖启动时当前工作目录。

### Gazebo Fortress

- `smartclean_gazebo` 提供本地 SDF World 与 server plugin 配置：地面、服务建筑、垃圾站、隔离岛、花坛和路桩，不访问 Gazebo Fuel，也不依赖用户目录里已有的 server 配置。
- launch 直接使用 `ExecuteProcess(shell=False)` 参数数组启动 `ign gazebo`，不再把用户路径拼入 shell 字符串。
- `world_path` 必须是存在的绝对文件，`record_path` 必须是绝对路径。
- 默认关闭全状态录制，避免 1 ms 仿真步长持续增长磁盘；显式 `record:=true` 时写入唯一 `.gazebo/log/run-<PID>/`，且不使用可能删除旧目录的 overwrite 选项。
- RoboStack 录制所需 SQL schema 路径由 `IGN_TRANSPORT_LOG_SQL_PATH` 显式配置。
- Gazebo 上游在默认无录制模式下仍可能创建 `~/.ignition/gazebo/log/` 控制台日志；项目二进制、依赖、模型、server 配置和可选状态录制均已放在仓库范围内。
- 自动验证使用临时 ROS domain 和唯一 Ignition partition，检查两个递增 `/clock` 样本、本轮 launch 存活、目标 World 控制服务存在，并通过独立进程组清理所有子进程。

### Docker 与部署文档

- 新增 `compose.ros2.yaml` 与 `containers/ros2-humble/Dockerfile`。
- 官方 ROS 多架构基础镜像索引固定为：

```text
ros:humble-ros-base-jammy@sha256:75dd3aba34a3838dadbb31a9f7bef769bdfa8713e6cec686fc868db2981b0987
```

- Compose 使用宿主 UID/GID，避免挂载目录产生 root 文件；host network / IPC 只用于可信 DDS 开发环境，不作为不可信代码沙箱。
- 新增 ROS 2 环境/桥接文档和 RDK X5/X3 TROS-Humble 部署设计，并同步更新根 README、架构、接口、快速开始、路线图及各目录 README。

## 验证记录

### 锁定安装

```bash
bash scripts/bootstrap_ros2_env.sh
```

结果：`pixi install --locked` 成功，环境位于 `.pixi/envs/default`。

### 构建与 ROS 包测试

```bash
bash scripts/ros2.sh test
```

结果：`smartclean_core`、`smartclean_gazebo`、`smartclean_ros` 三个包构建成功；`smartclean_ros` 19 项测试全部通过，`0 errors / 0 failures / 0 skipped`。

清空开发用 `PYTHONPATH`、source 安装空间并切换到 `/tmp` 后再次导入：

```text
smartclean_sim -> ros2_ws/install/smartclean_core/lib/python3.12/site-packages/
demo config    -> ros2_ws/install/smartclean_core/share/smartclean_core/config/demo.json
result         -> COMPLETED, 114 frames
```

这确认桥接器不再只靠仓库根目录 `PYTHONPATH` 偶然运行。

### ROS 2 三 Topic 端到端

```bash
bash scripts/ros2.sh verify
```

在正常主机网络权限下结果：

```text
status=COMPLETED
path_poses=103
coverage=1.0
collisions=0
```

探针等待当前回放帧真正进入 `COMPLETED`，同时校验最终清扫 `4/4`、返航、轨迹/位姿 `frame_id=map`。桥接子进程仍存活检查通过。Codex 文件沙箱内直接运行时 Fast DDS 会先报告 UDP socket 权限限制，但退化通道仍能通信；在正常主机权限下重跑没有该警告。

### Gazebo World 与时钟

```bash
bash scripts/ros2.sh gazebo-verify
```

结果：

```text
/clock: 2,000,000 ns -> 3,000,000 ns
/world/smartclean_smoke/control: 存在
Gazebo server 与 parameter_bridge: 收到 SIGINT 后干净退出
```

另外短暂运行 `bash scripts/ros2.sh gazebo record:=true` 后手动 `Ctrl+C`：

```text
.gazebo/log/run-615631/state.tlog          61,440 bytes
.gazebo/log/run-615631/server_console.log   8,466 bytes
```

录制数据库可写；Gazebo 对部分 SDF World 组件给出不影响仿真和 `/clock` 的序列化 warning。默认启动不录制，因此不出现该 warning，也不会持续增长状态数据库。

### 二维核心与静态检查

```bash
bash scripts/ros2.sh run python -m pytest -q tests
```

结果：34 项二维核心测试全部通过。

以下检查也全部通过：

- 所有 shell 脚本 `bash -n`；
- `python -m compileall -q src scripts ros2_ws/src`；
- `ign sdf -k smartclean_smoke.sdf`，输出 `Valid.`；
- `docker compose -f compose.ros2.yaml config --quiet`；
- `git diff --check`；
- Pixi、缓存、ROS/Gazebo 日志和 colcon 产物均被 Git 忽略。

Docker 客户端通过官方 registry 查询到并固定基础镜像 digest，但 daemon socket 无权限；因此没有执行 Dockerfile build、容器内测试或容器 Gazebo。`apt` 仓库仍可能随时间更新，首次真实构建还要保存最终镜像 digest 与 `dpkg-query` 包清单。

## 遇到的问题与处理

- 初始 TOML `$schema` 键需要加引号；已修正并由 Pixi 解析。
- ROS/colcon setup 脚本与 `set -u` 不兼容；source 时局部关闭 nounset，之后立即恢复。
- `tests_require` 产生弃用警告；改用 `extras_require`。
- Docker socket 即使在当前沙箱外调用仍因用户权限被拒绝，且 `sudo -n` 需要密码；保留未验证边界，没有伪造构建结果。
- Codex 默认沙箱限制 Fast DDS / Ignition 的 UDP socket；关键通信与 Gazebo 验证均在获批的正常主机权限下重跑。
- Gazebo 录制首次未找到 SQL schema；显式设置 `IGN_TRANSPORT_LOG_SQL_PATH` 后记录成功。
- 审查发现 `ros_gz_sim` 上游 launch 使用 `shell=True`；本项目改为本地 `shell=False` 启动，消除路径含空格失效和命令注入风险。
- 审查发现回放初始帧混入最终状态、默认录制可能涨盘、验证可能被已有节点误通过、核心仅靠 `PYTHONPATH`；均在提交前完成结构性修复并重新验证。

## 未验证边界

- RViz/rqt GUI；
- Docker 镜像构建与容器内测试；
- Gazebo 机器人 URDF/SDF、差速驱动、LiDAR、相机、碰撞与双向控制 Topic；
- `/odom`、TF、`/scan`、`/cmd_vel`、Nav2 和 ROS Action 闭环；
- YOLO/ONNX、LLM、Web；
- RDK X5/X3 板端编译、DDS 跨机、BPU 精度/性能/温度和真实底盘。

## Git 状态与下一步

- 本日志与代码、锁文件、文档一同进入独立本地关键节点提交，实际 commit 以 `git log` 为准。
- 没有推送远端：此前安全审查要求用户对具体 GitHub URL 与完整 payload 明确授权，本轮不绕过该边界。
- 下一阶段优先实现 Gazebo 差速机器人模型、`/cmd_vel`—轮速—`/odom` 最小闭环，再接 LiDAR/TF 与 Nav2；同时保持二维 34 项和 ROS 19 项回归测试持续通过。
