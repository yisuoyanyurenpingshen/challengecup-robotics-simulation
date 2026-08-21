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
- 面向 ROS2、Gazebo、YOLO、LLM 和 RDK 的稳定适配边界

当前实现是算法与接口基线，不代表 ROS2、RDK 或实车能力已经完成验证。状态边界见 [项目章程](docs/00_project_charter.md)。

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
pytest -q
```

更多命令和指标解释见 [快速开始](docs/04_quickstart.md)。

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

后续适配：Gazebo / ROS2 / Nav2 / YOLO / Web / LLM / RDK BPU
```

技术分层、数据流和扩展规则见：

- [系统架构](docs/02_system_architecture.md)
- [模块接口约定](docs/03_module_interfaces.md)
- [P1 覆盖与动画设计](docs/06_p1_coverage_and_animation.md)
- [后续实施路线](docs/07_implementation_roadmap.md)

## 目录结构

```text
configs/       可跟踪的场景和任务配置
datasets/      数据集卡与存放说明，不保存大型原始数据
docs/          项目章程、架构、接口和技术笔记
envs/          环境安装与版本说明，不保存虚拟环境
logs/          每次公共目录变更的工程日志
results/       轻量实验摘要、JSON、图片和自包含 HTML 动画
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

核心代码保持 Python 3.8 兼容。ROS2 工作空间将在相应环境确认后单独建立，避免未验证依赖阻断基础闭环。

## 公共目录协作要求

在此仓库做任何变更前先查看 `git status`，不要覆盖其他人的未提交内容。每次公共变更必须：

1. 在 `logs/` 记录目标、改动文件、验证结果和遗留问题。
2. 涉及架构、接口、指标或技术选择时同步更新 `docs/`。
3. 不提交数据集、模型权重、视频、虚拟环境、密钥、Token 或服务器私有配置。
4. 提交前检查 `git diff` 并执行与改动相称的测试。

完整约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。
