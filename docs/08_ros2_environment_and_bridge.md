# ROS2 环境与 SmartClean 回放桥

## 1. 结论与状态

截至 2026-08-21，项目采用两条互补的 ROS2 环境路径：

- **正式复现主线**：Ubuntu 22.04（Jammy）+ ROS2 Humble + Gazebo Fortress，封装在 `compose.ros2.yaml` 和 `containers/ros2-humble/Dockerfile` 中。这是后续团队协作、CI 和答辩复现采用的基线。
- **本机已验证路径**：在 Ubuntu 20.04.6 宿主机中，使用仓库内 Pixi 0.77.0 与 RoboStack Humble 环境完成安装、构建和通信验证。该路径不修改宿主机 `/opt/ros`，用于当前无 Docker daemon 权限时继续开发；项目内部把它列为 Tier 3 辅助路径，不替代 Jammy 容器正式基线。

当前 ROS2 成果是**确定性二维核心的只读回放桥**：它运行一次既有仿真，把状态、完整轨迹和逐帧位姿发布为 ROS2 Topic。它不是 Gazebo 车辆控制桥，也还没有接入 `/odom`、`/scan`、TF、`/cmd_vel` 或 Nav2 导航闭环。

| 项目 | 状态 | 已验证事实 |
| --- | --- | --- |
| 仓库内环境求解 | 已验证 | `pixi.lock` 已生成，可锁定依赖集合 |
| ROS2 Python 节点 | 已验证 | Python 3.12.13、`rclpy` 3.3.21 |
| ROS2 Desktop | 已安装、CLI 可发现 | RoboStack `ros-humble-desktop` 0.10.0；本轮未验证 RViz GUI |
| Nav2 与 SLAM 工具 | 已安装、未接入闭环 | Nav2 1.1.20、`slam_toolbox` 2.6.10 |
| ROS-Gazebo 集成包 | 已安装、基础冒烟通过 | `ros_gz` 0.244.24、Gazebo Fortress 6.16.0；`/clock` 桥通过 |
| ROS2 工作空间 | 已验证 | `colcon` 构建成功，19 项包测试通过 |
| DDS Topic 通信 | 已验证 | Topic 探针收到完整状态、轨迹与位姿 |
| Docker/Compose 配置 | 已生成、未运行验证 | Docker 客户端 28.1.1、Compose 2.35.1；当前代理会话无 daemon 权限 |
| Gazebo 最小 World | 已验证 | 本地 SDF 可解析；headless 启动并收到推进中的 ROS `/clock` |

## 2. 为什么选择 Humble + Fortress

宿主机是 Ubuntu 20.04.6，但不在宿主机原生安装 ROS2 Foxy，也不在系统 Python 中拼装 Humble，原因如下：

1. ROS2 Humble 的正式 Tier 1 平台是 Ubuntu 22.04 的 `amd64` 和 `arm64`，支持期到 2027 年 5 月；Ubuntu 20.04 对 Humble 仅是源码级 Tier 3 平台。
2. Gazebo 官方把 Fortress 列为 ROS2 Humble 的推荐组合；通过 `ros_gz` 使用默认配对，可以减少版本冲突。
3. RDK OS 3.x 同样基于 Ubuntu 22.04 与 TROS/ROS2 Humble，PC 与板端保持同一 ROS2 大版本，可避免 Foxy/Humble 的消息、QoS 和构建差异。
4. 容器固定 Jammy 用户态，Pixi 锁定当前本地依赖，两者都避免污染 Ubuntu 20.04 宿主机。

Humble 距离支持结束时间已经不长，但当前 RDK X3/X5 的共同产品基线仍是 Humble，因此本阶段优先保证 PC—RDK 一致性。后续升级 ROS2 发行版必须与 RDK OS/TROS 支持矩阵一起评估，不能只升级 PC。

## 3. 环境布局与隔离规则

```text
仓库根目录/
├── pixi.toml                         RoboStack 依赖与统一任务
├── pixi.lock                         当前已求解版本锁
├── .tools/bin/pixi                   仓库内 Pixi 可执行文件（不入 Git）
├── .tools/pixi-home/                 Pixi 本地状态（不入 Git）
├── .cache/pixi/                      下载缓存（不入 Git）
├── .pixi/                            实际环境前缀（不入 Git）
├── .ros/                             ROS 运行日志（不入 Git）
├── .gazebo/                          Gazebo 状态与控制台日志（不入 Git）
├── compose.ros2.yaml                 正式容器入口
├── containers/ros2-humble/Dockerfile Jammy/Humble 镜像定义
└── ros2_ws/
    ├── src/smartclean_core/           将平台无关核心安装到 ROS 前缀
    ├── src/smartclean_ros/            ROS2 回放桥源码
    ├── src/smartclean_gazebo/         Fortress 最小 World 与启动编排
    ├── build/                         colcon 构建目录（不入 Git）
    ├── install/                       colcon 安装目录（不入 Git）
    └── log/                           colcon 日志（不入 Git）
```

必须遵守以下隔离约束：

- 在一个终端中只激活一套 ROS 环境。进入 Pixi 前不要 `source /opt/ros/*/setup.bash` 或 `/opt/tros/*/setup.bash`。
- RoboStack 官方明确提示，Conda/Pixi 环境不能与 apt 安装的 ROS 环境混用，否则 `PYTHONPATH` 等变量会相互干扰。
- `pixi.lock` 必须进入 Git；`.pixi/`、`.tools/`、`.cache/`、构建产物和 ROS 日志不得进入 Git。
- 不手工修改 `.pixi/` 内文件。新增依赖只改 `pixi.toml`，重新求解后同时提交 `pixi.lock`。
- 项目固定 `ROS_DOMAIN_ID=42`；PC、容器和 RDK 通信时必须保持一致。

## 4. 启动和验证

### 4.1 当前可直接使用的 Pixi 路径

在仓库根目录打开一个**没有 source 其他 ROS 环境**的新终端：

```bash
# 首次下载并安装仓库内环境；后续会复用 pixi.lock
./scripts/ros2.sh install

# 构建并运行 19 项包测试
./scripts/ros2.sh test

# 启动桥接节点并运行 Topic 探针
./scripts/ros2.sh verify

# 启动 Gazebo 并自动验证 ROS 仿真时钟
./scripts/ros2.sh gazebo-verify

# 分步开发或持续启动演示
./scripts/ros2.sh build
./scripts/ros2.sh demo
./scripts/ros2.sh gazebo
```

`./scripts/ros2.sh shell` 会进入已激活环境；临时执行单条命令可用：

```bash
./scripts/ros2.sh run ros2 doctor --report
./scripts/ros2.sh run ros2 topic list
```

验证标准不是“命令退出码为 0”这一项，而是同时满足：

- `smartclean_ros` 可由 `colcon` 构建并安装；
- 19 项包测试全部通过；
- 探针在 20 秒内收到三条目标 Topic；
- 状态为 `COMPLETED`，4 个目标全部清除，覆盖率为 1.0，碰撞数为 0，且已经返航；
- `Path` 至少有两个位姿，轨迹和位姿的 `frame_id` 均为 `map`。

两个自动探针会仅在自身进程内选择临时 ROS domain；Gazebo 探针还使用唯一
Ignition partition，并检查本轮子进程仍存活及
`/world/smartclean_smoke/control` 服务存在，避免被其他已运行节点误判为通过。
正常开发、PC—RDK 通信仍使用项目约定的 domain 42。

Gazebo 使用独立门槛：SDF 必须通过解析，Fortress 以 headless 模式启动，
`ros_gz_bridge` 必须在超时内把推进中的仿真 `/clock` 送到 ROS2。当前最小
World 已满足这个门槛；这不代表机器人、传感器或控制闭环已经完成。

### 4.2 正式 Docker 路径

主线镜像以官方 `ros:humble-ros-base-jammy` 为基础，并把 2026-08-21 查询到的多架构镜像索引固定为 `sha256:75dd3aba34a3838dadbb31a9f7bef769bdfa8713e6cec686fc868db2981b0987`；其上安装 ROS 演示节点、Nav2、SLAM Toolbox、`ros_gz`、`colcon` 和 pytest。获得 Docker daemon 权限后，在仓库根目录执行：

```bash
export SMARTCLEAN_UID="$(id -u)"
export SMARTCLEAN_GID="$(id -g)"
docker compose -f compose.ros2.yaml build ros2
docker compose -f compose.ros2.yaml run --rm ros2 bash scripts/ros2_build.sh
docker compose -f compose.ros2.yaml run --rm ros2 bash scripts/ros2_test.sh
docker compose -f compose.ros2.yaml run --rm ros2 bash scripts/verify_ros2.sh
```

当前仅确认本机 Docker 28.1.1 和 Compose 2.35.1 客户端可用；代理会话无权访问 daemon，所以以上容器命令仍需在具备 daemon 权限的终端独立验证。基础镜像已经内容寻址，但构建时的 `apt` 仓库仍可能更新；首次成功构建后必须保存最终镜像 digest 与 `dpkg-query` 包清单。不得把 Dockerfile 构建成功写入阶段成果，直到上述命令有真实日志。

### 4.3 Gazebo Fortress 最小场景

`smartclean_gazebo` 是数据型 ROS 包，包含本地 SDF World、server plugin 配置和 headless launch。
场景只使用仓库内定义的地面、服务建筑、垃圾站、隔离岛、花坛和路桩，
不依赖 Gazebo Fuel 或在线模型下载。运行入口：

```bash
# 自动启动、等待 /clock、断言后退出
./scripts/ros2.sh gazebo-verify

# 持续运行；Ctrl+C 停止
./scripts/ros2.sh gazebo

# 需要诊断时才录制到仓库忽略目录；长时间运行会增长磁盘占用
./scripts/ros2.sh gazebo record:=true
```

launch 只建立 Gazebo 到 ROS 的 `/clock` 桥。Gazebo 的录制数据库与控制台
日志在 `record:=true` 时写入唯一的 `.gazebo/log/run-<PID>/`；默认关闭全状态录制，
避免长时间运行持续增长 `state.tlog`。ROS launch 日志固定在 `.ros/log/`，
这些仓库内运行目录均由 Git 忽略。RoboStack 的录制功能需要显式的
`IGN_TRANSPORT_LOG_SQL_PATH`，该路径已经由 `pixi.toml` 激活配置提供。
Physics、User Commands 和 Scene Broadcaster 的 server 配置也随包安装并由
launch 显式指定，不依赖用户目录里已有的 Gazebo 配置。Gazebo 上游仍可能
在 `~/.ignition/gazebo/log/` 建立默认控制台日志；完整状态录制才使用项目内
`.gazebo/`，二进制、依赖、模型和项目配置均留在仓库内。

## 5. ROS2 回放桥

### 5.1 工作方式

`smartclean_bridge` 启动后按以下顺序工作：

```text
configs/demo.json
      │
      ▼
既有 SmartClean 二维核心运行一次
      │
      ├── 运行摘要 ──→ /smartclean/status
      ├── 完整轨迹 ──→ /smartclean/trajectory
      └── 逐帧位置 ──→ /smartclean/robot_pose
```

桥接层没有复制规划和状态机，只调用 `smartclean_sim` 的公开加载、任务与仿真入口。ROS2 不可用时，原 CLI 仿真仍可独立运行。

### 5.2 已实现 Topic

| Topic | ROS2 类型 | QoS | 当前语义 |
| --- | --- | --- | --- |
| `/smartclean/status` | `std_msgs/msg/String` | Reliable、Transient Local、depth 1 | UTF-8 JSON；包含 schema、任务状态、帧序号、事件、指标和比率 |
| `/smartclean/trajectory` | `nav_msgs/msg/Path` | Reliable、Transient Local、depth 1 | 一次运行的完整米制 `map` 轨迹 |
| `/smartclean/robot_pose` | `geometry_msgs/msg/PoseStamped` | Reliable、Transient Local、depth 1 | 按回放周期发布当前帧位置；晚加入者取得最近一帧 |

`/smartclean/status` 暂用 `String` 承载 JSON，是为了尽早打通协议与 RDK 网络。`status` / `task_state` 是当前回放帧；预先计算出的整次运行结果只出现在名称明确的 `run_result_status`、`final_metrics` 和 `final_rates` 中，避免初始帧被误判为已经完成。进入任务控制和多节点集成前，应迁移到 `smartclean_interfaces` 的版本化自定义消息；迁移期间必须保持字段语义和契约测试。

### 5.3 栅格到 `map` 坐标

二维核心使用左上角原点、`x` 向右、`y` 向下的整数格；ROS 使用右手系、米制、`y` 向上。桥接器发布的是**格中心**而不是格角点：

```text
map_x = origin_x_m + (grid_x + 0.5) × cell_size_m
map_y = origin_y_m + (grid_height - grid_y - 0.5) × cell_size_m
```

转换前会校验网格尺寸、分辨率、原点和坐标边界。当前回放只具备离散位置，姿态统一为单位四元数 `w=1`，不能据此声称已经发布真实车体朝向。

### 5.4 节点参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `config_path` | `configs/demo.json` | 场景与任务配置 |
| `frame_id` | `map` | 轨迹和位姿坐标系 |
| `cell_size_m` | `1.0` | 每个核心栅格对应的米数 |
| `origin_x_m` / `origin_y_m` | `0.0` | 完整栅格左下角在 `map` 中的位置 |
| `replay_period_s` | `0.2` | 相邻回放帧的发布时间间隔 |
| `loop_replay` | `false` | 结束后是否从首帧循环 |

## 6. 当前边界与下一步门槛

当前明确没有完成：

- 机器人 URDF/SDF、差速驱动、LiDAR、相机和碰撞物理；
- `/odom`、TF、`/scan`、`/cmd_vel` 与 Nav2 的定位—规划—控制闭环；
- 除 `/clock` 外的 ROS-Gazebo 双向 Topic、机器人控制与传感器数据桥；
- ROS2 Action 的任务提交、反馈、取消、返航和急停；
- PC 与真实 RDK 的 DDS 跨机通信和板端 BPU 推理。

Gazebo headless 与 `/clock` 门槛已经通过。下一阶段只有在机器人模型与差速驱动、ROS-Gazebo 控制/传感器双向 Topic、Nav2 最小导航和停止安全测试分别留下可复现日志后，才能将状态升级为“机器人闭环已验证”。

## 7. 官方依据

以下资料访问于 2026-08-21：

- [ROS2 Humble 发行说明与支持平台](https://docs.ros.org/en/humble/Releases/Release-Humble-Hawksbill.html)
- [ROS2 发行版生命周期](https://docs.ros.org/en/humble/Releases.html)
- [Gazebo 与 ROS 的官方配对说明](https://gazebosim.org/docs/latest/ros_installation/)
- [Gazebo Fortress ROS2 集成](https://gazebosim.org/docs/fortress/ros2_integration/)
- [ROS 官方 Docker 镜像](https://hub.docker.com/_/ros)
- [RoboStack Getting Started](https://robostack.github.io/GettingStarted.html)
- [Pixi 环境说明](https://pixi.prefix.dev/latest/workspace/environment/)
