# SmartClean-Sim

面向 RDK 国产机器人平台的智慧环卫无人清扫车仿真与边缘部署验证系统。

- 榜题编号：DG-202604
- 题目名称：面向智慧环卫场景的国产系统无人清扫车关键技术攻关
- 发榜单位：北京地平线信息科技有限公司

## 当前成果

仓库已经具备一个可直接运行、可自动测试的二维最小闭环：

- 中文清扫指令转结构化任务
- 垃圾、静态障碍、积水禁行区和动态行人的场景模型
- 确定性四邻域 A* 路径规划
- 按优先级清扫、指定区域全覆盖、动态障碍预测、重规划和返航
- 完成率、覆盖率、路径长度、重规划次数、碰撞次数等指标
- 可离线打开、可播放和逐帧检查的自包含 HTML 动画
- 仓库内可复现的 ROS 2 Humble Desktop、Nav2、SLAM Toolbox 与 `ros_gz` 环境
- 将二维闭环发布为状态、完整轨迹和逐帧位姿的 ROS 2 回放桥
- Gazebo Fortress 本地智慧环卫最小 World 与 ROS `/clock` 自动冒烟验证
- Gazebo 差速清扫车模型、`/cmd_vel` 安全看门狗、`/odom` 与 `odom -> base_link` TF 闭环
- 面向 Gazebo、YOLO、LLM 和 RDK 的稳定适配边界

当前已验证二维算法、ROS 2 回放桥和 Gazebo 差速运动闭环；标准 `/cmd_vel` 能驱动车辆，里程计与 TF 可回读，命令断流 0.5 秒后会自动停车。LiDAR、完整 `map -> odom -> base_link` TF、Nav2、实车控制和 RDK 板端实测仍未完成。状态边界见 [项目章程](docs/00_project_charter.md)。

## 立即运行

环境要求：Python 3.8 或更高版本。默认演示仅使用标准库。

```bash
python3 scripts/run_demo.py \
  --show-map \
  --output results/demo_result.json \
  --animate results/demo_animation.html
```

终端会输出指标和路线图。动画生成后，用浏览器打开：

```bash
firefox results/demo_animation.html
```

运行测试：

```bash
bash scripts/ros2.sh run python -m pytest -q tests
```

更多命令和指标解释见 [快速开始](docs/04_quickstart.md)。

## ROS 2 一键验证

当前机器已完成仓库内安装。新机器首次执行会把 Pixi、ROS 2 和缓存下载到本仓库的忽略目录，不需要 `sudo`：

```bash
bash scripts/ros2.sh install
bash scripts/ros2.sh build
bash scripts/ros2.sh verify
bash scripts/ros2.sh gazebo-verify
bash scripts/ros2.sh drive-verify
```

启动清扫轨迹回放节点：

```bash
bash scripts/ros2.sh demo loop_replay:=true
```

启动无界面的 Gazebo 最小场景（按 `Ctrl+C` 停止）：

```bash
bash scripts/ros2.sh gazebo
```

启动可接收 `/cmd_vel` 的 Gazebo 差速清扫车（按 `Ctrl+C` 停止）：

```bash
bash scripts/ros2.sh drive
```

> 注意：一次只输入一个命令。若把两条命令误粘贴成一行（例如
> `bash scripts/ros2.sh drivebash scripts/ros2.sh drive`），只会得到用法提示，
> 正确命令是单独的 `bash scripts/ros2.sh drive`。

在另一个新终端持续发送前进命令：

```bash
bash scripts/ros2.sh run ros2 topic pub --rate 10 /cmd_vel \
  geometry_msgs/msg/Twist \
  '{linear: {x: 0.25}, angular: {z: 0.0}}'
```

停止命令发布后，安全看门狗会在默认 0.5 秒内把底盘速度置零。

另开终端检查：

```bash
bash scripts/ros2.sh run ros2 node list
bash scripts/ros2.sh run ros2 topic list -t
```

详细启动方式、Topic 和环境边界见 [快速开始](docs/04_quickstart.md) 与 [ROS 2 环境和桥接设计](docs/08_ros2_environment_and_bridge.md)。

## 系统路线

```text
自然语言 / JSON 任务
          ↓
任务解析与安全校验
          ↓
垃圾目标排序 → A* → 区域蛇形覆盖 → 动态避障 / 重规划
          ↓                              ↑
        二维世界 ──────────────────── 动态行人
          ↓
清扫、返航、指标、逐帧轨迹与离线动画

已接入：ROS2 状态 / 轨迹 / 位姿回放
已接入：Gazebo 最小场景 / ROS 仿真时钟
已接入：/cmd_vel → 安全看门狗 → Gazebo 差速驱动 → /odom + TF
下一步：LiDAR / 完整 TF / Nav2 控制 / YOLO / Web / LLM / RDK BPU
```

技术分层、数据流和扩展规则见：

- [系统架构](docs/02_system_architecture.md)
- [模块接口约定](docs/03_module_interfaces.md)
- [P1 覆盖与动画设计](docs/06_p1_coverage_and_animation.md)
- [后续实施路线](docs/07_implementation_roadmap.md)

## 目录结构

```text
configs/       可跟踪的场景和任务配置
containers/    Ubuntu 22.04 / ROS 2 Humble 标准容器蓝图
datasets/      数据集卡与存放说明，不保存大型原始数据
docs/          项目章程、架构、接口和技术笔记
envs/          环境安装与版本说明，不保存虚拟环境
logs/          每次公共目录变更的工程日志
results/       轻量实验摘要、JSON、图片和自包含 HTML 动画
ros2_ws/       ROS 2 工作空间、桥接节点与仿真包
scripts/       演示、实验和维护入口
src/           SmartClean-Sim Python 源码
tests/         自动化测试
weights/       模型卡与权重说明，不保存大型模型文件
```

## 开发安装

```bash
python3 -m pip install -e .
smartclean-sim --config configs/demo.json --show-map
```

核心代码保持 Python 3.8 兼容并继续零 ROS 依赖。ROS 2 适配器位于独立 `ros2_ws/`，当前锁定环境由 `pixi.toml` 与 `pixi.lock` 描述，不会阻断基础 CLI 闭环。

## 公共目录协作要求

在此仓库做任何变更前先查看 `git status`，不要覆盖其他人的未提交内容。每次公共变更必须：

1. 在 `logs/` 记录目标、改动文件、验证结果和遗留问题。
2. 涉及架构、接口、指标或技术选择时同步更新 `docs/`。
3. 不提交数据集、模型权重、视频、虚拟环境、密钥、Token 或服务器私有配置。
4. 提交前检查 `git diff` 并执行与改动相称的测试。

完整约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。
