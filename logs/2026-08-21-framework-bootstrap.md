# 2026-08-21 SmartClean-Sim 公共框架搭建

## 基本信息

- 时间：2026-08-21 10:53 CST
- 执行者：Codex（主代理及并行只读/文档子任务）
- 基线提交：`727784c`
- 目标：扫描已有目录与 README，在不覆盖现有未提交内容的前提下，建立可运行、可测试、可扩展的竞赛项目框架。

## 扫描结论

- 初始仓库只有目录说明和 Git 搭建记录，没有源码、配置、测试或运行入口。
- `envs/README.md` 在本次工作开始前已有未提交修改，并含疑似误粘贴的 heredoc 文本；本次没有修改、还原或格式化该文件。
- 根 README、`logs/README.md` 和 Git 搭建记录存在未闭合代码块、残留 `EOF` 或过时状态描述；除受保护的 `envs/README.md` 外已整理。
- 当前服务器为 Python 3.8.10；基础闭环不依赖 ROS2、GPU、网络或第三方 Python 包。

## 本次变更

- 建立 `src/smartclean_sim/`：领域模型、栅格世界、A*、任务解析、仿真执行、终端渲染、配置和 CLI。
- 新增 `configs/demo.json`：教学楼门口、垃圾、积水、静态障碍和动态行人场景。
- 新增 `scripts/run_demo.py`：无需安装即可运行默认演示。
- 新增 `setup.cfg`、`setup.py`：兼容当前 Python 3.8 / setuptools 45 环境的 editable install 和命令行入口。
- 新增 `tests/`：覆盖地图、规划、任务解析、动态障碍重规划、清扫返航和默认演示可复现性。
- 重写根 README，补充 `CONTRIBUTING.md`，更新 configs/docs/logs/results/scripts 目录说明。
- 新增项目章程、系统架构、模块接口和快速开始文档；整理旧 Git 搭建记录。
- 扩展 `.gitignore`：忽略 Python、打包和 ROS2 构建产物，允许轻量 JSON 结果及 Markdown 数据集卡/模型卡。

## 关键设计决定

1. P0 采用纯标准库的确定性二维栅格闭环，先保证可运行和可测试。
2. ROS2、Gazebo、YOLO、LLM、Web 和 RDK 作为适配层规划，不宣称已经实现或验证。
3. LLM 只能生成受校验的结构化任务，不能直接输出底盘控制命令。
4. 动态障碍始终作为物理安全障碍；任务中的 `avoid_types` 用于积水等语义危险区。
5. 外部 `return_after_done` 映射到内部 `CleaningTask.return_to_dock`，兼容已有示例口径。
6. 因当前 pip/setuptools 较旧且网络不可作为前提，使用 `setup.cfg + setup.py`，避免 editable install 强制下载新构建依赖。

技术依据和扩展约束见：

- `docs/00_project_charter.md`
- `docs/02_system_architecture.md`
- `docs/03_module_interfaces.md`
- `docs/04_quickstart.md`

## 验证记录

```bash
python3 -m pytest -q
```

结果：15 项测试通过。

```bash
python3 scripts/run_demo.py --show-map
```

结果：任务 `COMPLETED`；清扫 `4/4`；完成率 `1.0`；覆盖率 `0.566`；路径长度 `32` 格；动态重规划 `1` 次；碰撞 `0` 次；成功返航。

```bash
python3 -m compileall -q src scripts tests
git diff --check
```

结果：均通过，无语法错误或空白错误。

在 `/tmp` 新建干净虚拟环境后执行 `python -m pip install --no-deps -e .`，再运行 `smartclean-sim --config configs/demo.json`；结果成功。最初保留 `pyproject.toml` 时，旧 pip 会尝试联网安装构建依赖，已改为兼容当前环境的 setuptools 配置并重新验证。

## 已知边界与下一步

- 当前垃圾位置来自场景真值，尚未接入 YOLO 感知。
- 当前是整数栅格和离散步进，尚无车辆动力学、定位误差或高保真传感器。
- 当前“覆盖率”是轨迹访问栅格占可通行栅格的比例，尚未实现专用全覆盖规划器。
- 下一步建议先实现覆盖规划和轻量可视化，再建立 ROS2/Gazebo 适配工作空间；获得 RDK 后再进行模型转换和板端实测。

