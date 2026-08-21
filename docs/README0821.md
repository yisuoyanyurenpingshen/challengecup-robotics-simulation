# 2026-08-21 项目建设总说明

## 1. 先说结论

今天已经把最初只有目录说明的仓库，推进成一个**可运行、可测试、可回放、可通过 ROS2 通信、可在 Gazebo 中接收速度并产生里程计的无人清扫车工程基线**。

项目公共根目录固定为：

```text
/home/bktx/projects/challengecup-robotics-simulation
```

GitHub 仓库为：

```text
https://github.com/yisuoyanyurenpingshen/challengecup-robotics-simulation
```

- 分支：`main`
- 今天的 Gazebo 差速闭环关键节点：`6e75784`
- 该提交已普通推送到 GitHub，没有强制推送，也没有覆盖远端历史。
- 本文件位于 `docs/README0821.md`，是今天全部工作的统一入口。

目前能准确宣称的最高状态是：

> 已验证二维清扫算法闭环、ROS2 结果回放，以及 Gazebo 差速底盘运动闭环。

目前还不能宣称已经完成 Nav2 自主导航、视觉识别、RDK 板端或实车系统。后面仍有明确工作量，并不是整个挑战杯项目已经全部做完。

## 2. 今天完成了什么

| 里程碑 | 完成内容 | Git 提交 | 验证结果 |
| --- | --- | --- | --- |
| P0 工程框架 | 中文任务、栅格地图、垃圾/障碍/积水/行人、A*、重规划、清扫、返航、指标、CLI | `8cff48c` | 当时 15 项测试通过；默认任务完成、碰撞 0 |
| P1 覆盖与展示 | 指定区域全覆盖、蛇形候选、逐帧轨迹、自包含 HTML 动画 | `0fde5d6` | 当前二维核心 34 项测试通过；区域覆盖 53/53 |
| ROS2/Gazebo 环境基线 | 仓库内 Humble/Fortress 环境、ROS 回放桥、Gazebo World、`/clock` 桥、Docker/RDK 设计 | `60ef18c` | 三条回放 Topic 与 Gazebo 时钟冒烟通过 |
| GitHub 历史衔接 | 登录 GitHub，保留远端原历史并建立安全合并节点，上传完整工程 | `d9bd6ea` | 本地与远端 `main` 哈希一致；没有强推 |
| P4-M1 底盘闭环 | 差速清扫车 SDF、`/cmd_vel`、安全看门狗、`/odom`、TF、自动验收 | `6e75784` | 48 项 ROS 包测试及所有端到端回归通过 |

今天的完整工程思路不是一次把 YOLO、Nav2、LLM、Web 和 RDK 全堆进去，而是每完成一层，就给它留下稳定接口、自动测试、工程日志和明确边界。

## 3. 整体设计思路

### 3.1 两条已经打通的主链路

第一条是确定性算法链，用于快速开发、对比实验和比赛指标：

```text
中文指令 / JSON
       ↓
任务解析与约束校验
       ↓
命名区域 + 垃圾 + 障碍 + 积水 + 动态行人
       ↓
A* / 全覆盖规划 → 动态阻挡时重规划
       ↓
清扫 → 返航 → 指标 + JSON + 离线 HTML 动画
       ↓
ROS2 状态 / 轨迹 / 位姿回放
```

第二条是今天新增的真实物理步进底盘链：

```text
/cmd_vel
   ↓
速度安全看门狗
  - 默认 0.5 秒命令断流即停车
  - NaN / Inf 命令立即失效
  - 使用单调时钟，不受仿真暂停影响
   ↓
/smartclean/safe_cmd_vel
   ↓
ros_gz_bridge → Gazebo Fortress DiffDrive
                       ├── /odom
                       ├── /tf：odom -> base_link
                       └── /clock
```

下一步会把两条链继续接起来：Nav2 根据地图、LiDAR 和里程计产生 `/cmd_vel`，再通过已经验证的安全底盘链驱动车辆。

### 3.2 五条工程原则

1. **先有可测闭环，再增加复杂能力。** 二维核心在没有 ROS、GPU、网络或开发板时仍能运行。
2. **核心与平台解耦。** ROS2、Gazebo、YOLO、LLM、Web、RDK 都通过适配层接入，不在各处复制规划状态机。
3. **环境留在仓库。** Pixi、ROS、缓存、Gazebo 日志均放在项目目录内；大型运行目录由 Git 忽略。
4. **安全在控制链末端兜底。** 上层命令失联或数值非法时，底盘入口主动归零。
5. **每一步都可证明。** 每个里程碑都有测试、端到端探针、`docs/` 技术口径和 `logs/` 工程记录。

## 4. 每个路径下面做了什么

### 4.1 根目录与二维算法

| 路径 | 用途 |
| --- | --- |
| `README.md` | 全项目首页、当前能力、最短启动命令和能力边界 |
| `CONTRIBUTING.md` | 公共目录协作、日志、文档、测试和提交规则 |
| `configs/demo.json` | 教学楼门口演示场景：命名区域、垃圾、静态障碍、积水、动态行人、任务 |
| `scripts/run_demo.py` | 不安装项目包也能直接启动二维演示 |
| `setup.cfg`、`setup.py` | Python 包安装与 `smartclean-sim` 命令入口 |
| `src/smartclean_sim/models.py` | 位置、垃圾、任务、轨迹帧和仿真结果数据模型 |
| `src/smartclean_sim/config.py` | JSON 配置加载与校验 |
| `src/smartclean_sim/grid.py` | 栅格世界、命名区域、障碍和安全可通行判定 |
| `src/smartclean_sim/planning.py` | 确定性 A* 与区域蛇形全覆盖规划 |
| `src/smartclean_sim/tasking.py` | 中文任务解析；普通清扫和全覆盖清扫语义 |
| `src/smartclean_sim/simulation.py` | 清扫、返航、动态障碍预测、等待/重规划和逐帧状态推进 |
| `src/smartclean_sim/rendering.py` | 终端 ASCII 地图与路径展示 |
| `src/smartclean_sim/html_visualization.py` | 生成无网络依赖的 HTML/Canvas 动画播放器 |
| `src/smartclean_sim/cli.py` | CLI 参数、指标输出、JSON 与动画导出 |
| `tests/` | 二维地图、规划、解析、仿真、CLI、HTML 和集成测试，共 34 项 |
| `results/demo_result.json` | 已跟踪的默认二维演示结构化结果 |
| `results/demo_animation.html` | 可离线打开的默认演示动画 |

### 4.2 仓库内 ROS2 环境

| 路径 | 用途 |
| --- | --- |
| `pixi.toml` | 声明 ROS2 Humble、Nav2、SLAM Toolbox、`ros_gz`、Gazebo、pytest 等依赖和统一任务 |
| `pixi.lock` | 固定实际依赖集合，保证下一次安装不静默漂移 |
| `scripts/bootstrap_ros2_env.sh` | 下载并校验仓库内 Pixi，然后严格按锁文件安装 |
| `scripts/ros2.sh` | 所有 ROS/Gazebo 操作的统一入口；不用手工拼环境变量 |
| `scripts/ros2_build.sh` | 构建 `ros2_ws/src` 下的三个 ROS 包 |
| `scripts/ros2_test.sh` | 运行 ROS 与 Gazebo 契约测试并汇总 JUnit 结果 |
| `envs/README.md` | 当前机器、精确大版本、隔离规则和常用命令 |

以下目录实际位于项目根目录内，但被 Git 忽略，不会上传大型二进制或凭据：

| 本地目录 | 内容 |
| --- | --- |
| `.tools/` | Pixi、GitHub CLI 和本项目的 GitHub 登录配置 |
| `.cache/pixi/` | 下载缓存 |
| `.pixi/` | 实际 ROS2/Gazebo 环境；先前记录约 5.1 GiB |
| `.ros/` | ROS2 运行日志 |
| `.gazebo/` | Gazebo 控制台日志和显式录制 |
| `ros2_ws/build/`、`install/`、`log/` | colcon 构建、安装与测试产物 |

### 4.3 ROS2 工作空间

| 路径 | 用途 |
| --- | --- |
| `ros2_ws/src/smartclean_core/` | 把根目录的零 ROS 依赖算法和 demo 配置安装进 ROS 前缀 |
| `ros2_ws/src/smartclean_ros/smartclean_ros/bridge_core.py` | 调用二维核心并生成回放数据 |
| `ros2_ws/src/smartclean_ros/smartclean_ros/conversions.py` | 左上原点整数格到右手米制 `map` 格中心转换 |
| `ros2_ws/src/smartclean_ros/smartclean_ros/bridge_node.py` | 发布状态、完整路径和逐帧位姿 |
| `ros2_ws/src/smartclean_ros/launch/demo.launch.py` | 编排二维结果回放节点 |
| `ros2_ws/src/smartclean_ros/smartclean_ros/cmd_vel_guard_core.py` | 不依赖 ROS 的速度新鲜度、有限数值与超时归零逻辑 |
| `ros2_ws/src/smartclean_ros/smartclean_ros/cmd_vel_guard_node.py` | 20 Hz ROS2 速度安全中继 |
| `ros2_ws/src/smartclean_ros/test/` | 回放、坐标转换和速度安全契约测试 |

### 4.4 Gazebo 世界与差速清扫车

| 路径 | 用途 |
| --- | --- |
| `ros2_ws/src/smartclean_gazebo/config/server.config` | 显式指定 Fortress server systems，不依赖用户目录配置 |
| `ros2_ws/src/smartclean_gazebo/worlds/smartclean_smoke.sdf` | 最小本地环卫 World，用于 `/clock` 基础冒烟 |
| `ros2_ws/src/smartclean_gazebo/launch/smoke.launch.py` | 启动最小 World 和时钟桥 |
| `ros2_ws/src/smartclean_gazebo/models/smartclean_robot/model.sdf` | 45 kg 清扫车主体、碰撞/惯性、左右轮、支撑轮和 DiffDrive plugin |
| `ros2_ws/src/smartclean_gazebo/models/smartclean_robot/model.config` | 本地模型元数据与 SDF 入口 |
| `ros2_ws/src/smartclean_gazebo/worlds/smartclean_drive.sdf` | 差速车运动验证 World；只引用本仓库模型 |
| `ros2_ws/src/smartclean_gazebo/launch/drive.launch.py` | 启动 World、四条 ROS-Gazebo bridge 和安全看门狗 |
| `ros2_ws/src/smartclean_gazebo/test/test_model_contract.py` | 检查模型、关节、惯性、Topic、frame 和离线资源契约 |
| `scripts/gazebo_smoke.sh`、`verify_gazebo.sh` | 启动并自动验收最小 World 与 `/clock` |
| `scripts/gazebo_drive.sh` | 持续启动差速车闭环 |
| `scripts/gazebo_drive_probe.py` | 主动发送速度并检查前进、转向、里程计、TF 和停车 |
| `scripts/verify_gazebo_drive.sh` | 使用隔离 domain/partition 启动探针并可靠清理本轮子进程 |

这些模型和 World 不使用 Gazebo Fuel，运行时不会再临时下载网上模型。

### 4.5 Docker、RDK、文档和日志

| 路径 | 用途 |
| --- | --- |
| `compose.ros2.yaml` | Ubuntu 22.04 / ROS2 Humble 正式容器入口 |
| `containers/ros2-humble/Dockerfile` | 固定官方 ROS 基础镜像的容器蓝图；尚未取得 daemon 权限做真实 build |
| `docs/00_project_charter.md` | 项目范围、阶段、已经完成和不能宣称的内容 |
| `docs/02_system_architecture.md` | 分层、数据流、状态机、ROS/Gazebo/RDK 边界 |
| `docs/03_module_interfaces.md` | 核心对象、Topic、frame、速度安全与外部适配契约 |
| `docs/04_quickstart.md` | 二维、ROS2、Gazebo 和差速车的操作命令 |
| `docs/05_open_source_research.md` | 开源候选、许可证和采用/不采用原因 |
| `docs/06_p1_coverage_and_animation.md` | 全覆盖算法、帧数据和动画设计 |
| `docs/07_implementation_roadmap.md` | P2/P3/P4/P5 路线和验收门槛 |
| `docs/08_ros2_environment_and_bridge.md` | Humble/Fortress 决策、环境隔离、回放和差速链详解 |
| `docs/09_rdk_tros_deployment.md` | RDK X5/X3、OS 3.x、TROS-Humble 与板端验收设计 |
| `logs/2026-08-21-framework-bootstrap.md` | P0 框架搭建记录 |
| `logs/2026-08-21-p1-coverage-animation.md` | P1 覆盖与动画记录 |
| `logs/2026-08-21-ros2-humble-gazebo-bridge.md` | 环境下载、ROS 回放、Gazebo 时钟与 RDK 设计记录 |
| `logs/2026-08-21-github-history-reconciliation.md` | GitHub 登录、无共同祖先历史衔接与安全上传记录 |
| `logs/2026-08-21-gazebo-diff-drive-loop.md` | 本轮差速车、安全看门狗、故障修正和验证记录 |

## 5. 你现在怎么启动

所有命令都在一个没有 source 其他 ROS/Conda 环境的新终端中执行。

### 5.1 第一次准备环境

```bash
cd /home/bktx/projects/challengecup-robotics-simulation
bash scripts/ros2.sh install
bash scripts/ros2.sh build
```

当前机器已经安装完成，通常不需要重复下载。换新机器时第一次安装会比较慢，并占用数 GiB 空间，但内容仍在本项目目录内，不需要 `sudo`。

### 5.2 最推荐：一条命令看差速闭环是否正常

```bash
cd /home/bktx/projects/challengecup-robotics-simulation
bash scripts/ros2.sh drive-verify
```

看到类似下面两行就表示成功：

```text
Gazebo 差速闭环验证通过：forward=... m, turn=... rad, stop_drift=... m, TF=odom->base_link, watchdog=passed
Gazebo 差速 World 验证通过：/world/smartclean_drive/control
```

这个验证是无界面的，会自己启动、测试、停车和退出，适合先确认环境没有问题。

### 5.3 手动控制差速车

终端 1：

```bash
cd /home/bktx/projects/challengecup-robotics-simulation
bash scripts/ros2.sh drive
```

终端 2，持续向前：

```bash
cd /home/bktx/projects/challengecup-robotics-simulation
bash scripts/ros2.sh run ros2 topic pub --rate 10 /cmd_vel \
  geometry_msgs/msg/Twist \
  '{linear: {x: 0.25}, angular: {z: 0.0}}'
```

终端 3，观察里程计：

```bash
cd /home/bktx/projects/challengecup-robotics-simulation
bash scripts/ros2.sh run ros2 topic echo /odom
```

检查 TF：

```bash
bash scripts/ros2.sh run ros2 run tf2_ros tf2_echo odom base_link
```

在终端 2 按 `Ctrl+C` 停止发送命令后，车辆应在 0.5 秒内自动停止。最后在终端 1 按 `Ctrl+C` 关闭 Gazebo。

当前 `drive` 默认是 headless server，因此主要从终端里看里程计与探针结果；图形化 Gazebo/RViz 启动还没有作为本轮验收入口固化。

### 5.4 运行二维清扫动画

```bash
cd /home/bktx/projects/challengecup-robotics-simulation
python3 scripts/run_demo.py \
  --show-map \
  --output results/demo_result.json \
  --animate results/demo_animation.html
```

然后用有桌面的浏览器打开：

```bash
firefox results/demo_animation.html
```

### 5.5 运行完整验证

```bash
cd /home/bktx/projects/challengecup-robotics-simulation
bash scripts/ros2.sh install
bash scripts/ros2.sh test
bash scripts/ros2.sh verify
bash scripts/ros2.sh gazebo-verify
bash scripts/ros2.sh drive-verify
bash scripts/ros2.sh run python -m pytest -q tests
```

不要在同一终端先执行 `source /opt/ros/...` 或 `/opt/tros/...`；也不要依赖宿主机裸 `pytest`，统一从 `scripts/ros2.sh` 进入锁定环境。

## 6. 今天最终验证到了什么程度

| 验证 | 最终结果 |
| --- | --- |
| 锁定环境安装 | `pixi install --locked` 成功，manifest 与 lock 一致 |
| ROS 包构建 | `smartclean_core`、`smartclean_ros`、`smartclean_gazebo` 全部成功 |
| ROS 包测试 | 48 tests，0 errors、0 failures、0 skipped |
| 二维核心测试 | 34 项通过 |
| 二维默认任务 | `COMPLETED`，垃圾 4/4，区域 53/53，覆盖率 1.0，碰撞 0，成功返航 |
| ROS2 回放 | `status=COMPLETED`、`path_poses=103`、覆盖率 1.0、碰撞 0 |
| Gazebo 时钟 | `/clock` 从 2,000,000 ns 推进到 3,000,000 ns；World 服务存在 |
| Gazebo 差速车 | 前进 0.593 m、转向 0.982 rad、停车漂移 0.000 m |
| TF 与安全 | `odom -> base_link` 收到；断流看门狗通过 |
| SDF | 清扫车模型与 drive World 均输出 `Valid.` |
| 静态检查 | shell 语法、Python 编译、`git diff --check` 全部通过 |

这些数字是本机仿真验证结果，不是实车性能指标。

## 7. 还没有做完什么

下面这些仍是后续任务，不能在答辩材料里写成已完成：

- Gazebo LiDAR `/scan`、相机、传感器噪声与标定；
- `map -> odom -> base_link` 完整 TF 与定位；
- Nav2 地图、规划器、控制器、恢复行为和自动到点；
- 动态行人条件下的物理导航、停车与重规划；
- ROS2 清扫任务 Action、反馈、取消、暂停、返航和急停复位；
- YOLO/ONNX 垃圾识别与图像坐标到地图坐标；
- Web 控制台和受 Schema 约束的 LLM 任务分解；
- RDK X5/X3 板端 BPU 转换、DDS 跨机、性能与温度实测；
- Docker 镜像真实构建与容器内回归；
- 至少五个固定环卫场景、批量实验 CSV、对比图和比赛报告数据。

## 8. 下一步是什么

下一条技术主线定为 **P4-M2：LiDAR + 完整 TF + Nav2 最小导航**，建议按下面顺序继续：

1. 给 `smartclean_robot` 增加 `lidar_link` 和 2D 激光雷达，桥接标准 `/scan`。
2. 固化 `base_footprint`、`base_link`、`lidar_link`，补齐 `map -> odom -> base_link -> lidar_link` TF 契约。
3. 增加可跟踪的地图、Nav2 参数和一条最小 bringup launch。
4. 自动发送一个导航目标，检查路径、速度、到达误差和命令断流停车。
5. 增加静态障碍与动态障碍用例，确保旧的 34 项二维测试和 48 项 ROS 测试不回归。

与这条主线并行，可以推进 **P2 场景与实验体系**：道路、停车场、狭窄通道、积水密集区、多行人共五类场景，再做批量运行、配置哈希和 CSV 汇总。这样既能继续补机器人能力，也能尽早形成挑战杯报告需要的对比数据。

再后面依次是：P3 YOLO/ONNX 感知，P5 LLM/Web/RDK。RDK 硬件到手后再做板端验证，避免把设计稿当成实测结果。

## 9. 你后续需要做什么

你现在不需要再手工安装 ROS，也不需要自己拼环境。建议只做三件事：

1. 先执行 `bash scripts/ros2.sh drive-verify`，确认你自己的终端看到同样的通过结果。
2. 打开 `results/demo_animation.html`，直观看二维清扫、覆盖、避障和返航过程。
3. 决定比赛展示优先级：先要“Nav2 自主导航画面”，还是先要“五场景实验报表”。如果没有额外指示，默认按上面的 P4-M2 主线继续，同时逐步补 P2 场景。

团队成员开始改动前应先读根 `README.md`、`CONTRIBUTING.md` 和本文件。公共目录每次变更仍要在 `logs/` 写明目标、文件、验证与遗留问题；接口或技术路线变化同时更新 `docs/`。

## 10. 常用 Git 检查

```bash
cd /home/bktx/projects/challengecup-robotics-simulation
git status
git log --oneline --decorate -8
git remote -v
```

当前 GitHub 登录配置保存在被忽略的 `.tools/gh-config/`，没有进入 Git。不要把 Token、设备码、密码、数据集、模型权重、ROS 环境或构建产物提交到仓库。
