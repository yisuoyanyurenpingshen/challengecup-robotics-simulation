# 二维仿真快速开始

## 环境

- Python 3.8 或更高版本
- 默认演示不需要 ROS2、Gazebo、GPU 或第三方 Python 包

## 直接运行

在仓库根目录执行：

```bash
python3 scripts/run_demo.py --show-map
```

覆盖自然语言任务：

```bash
python3 scripts/run_demo.py \
  --task "清扫教学楼门口，优先处理塑料瓶，绕开积水和行人，完成后返航。"
```

保存详细结果：

```bash
python3 scripts/run_demo.py --output results/demo_result.json
```

## 开发安装

```bash
python3 -m pip install -e .
smartclean-sim --config configs/demo.json --show-map
```

## 测试

如果环境已安装 pytest：

```bash
pytest -q
```

## 结果说明

- `completion_rate`：当前任务目标中已清扫目标的比例。
- `coverage_rate`：轨迹访问过的唯一栅格占可通行栅格的比例。
- `path_length_cells`：机器人移动的栅格步数。
- `replans`：因为动态障碍或临时无路而重新规划的次数。
- `collisions`：碰撞次数；安全闭环的期望值为 0。
- `returned_to_dock`：最终是否位于回充点。

这些是二维仿真指标，不代表实车或工业指标。

