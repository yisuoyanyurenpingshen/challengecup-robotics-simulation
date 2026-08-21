# 二维仿真快速开始

## 环境

- Python 3.8 或更高版本
- 默认演示不需要 ROS2、Gazebo、GPU 或第三方 Python 包

## 直接运行

在仓库根目录执行：

```bash
python3 scripts/run_demo.py \
  --show-map \
  --output results/demo_result.json \
  --animate results/demo_animation.html
```

默认任务会先按优先级处理垃圾，再全覆盖教学楼门口的 53 个安全可通行格，避开积水和动态行人，最后返航。

动画生成后可直接双击 `results/demo_animation.html`，或执行：

```bash
firefox results/demo_animation.html
```

HTML 文件包含播放/暂停、前后单帧、重置、时间轴和播放倍速，不需要 Web 服务或网络连接。

覆盖自然语言任务：

```bash
python3 scripts/run_demo.py \
  --task "清扫教学楼门口，优先处理塑料瓶，绕开积水和行人，完成后返航。"
```

上面的普通指令使用 `clean_spots`，只清扫已知垃圾。明确要求全覆盖：

```bash
python3 scripts/run_demo.py \
  --task "全覆盖清扫教学楼门口，绕开积水和行人，完成后返航。" \
  --animate results/custom_animation.html
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
- `coverage_rate`：`clean_area` 模式下为任务区域已访问安全格占区域安全格的比例；`clean_spots` 模式保留全图轨迹覆盖率口径。
- `path_length_cells`：机器人移动的栅格步数。
- `replans`：因为动态障碍或临时无路而重新规划的次数。
- `collisions`：碰撞次数；安全闭环的期望值为 0。
- `returned_to_dock`：最终是否位于回充点。

详细 JSON 中的 `trace.frames` 是动画使用的完整逐帧快照，包含仿真步、状态、机器人、动态障碍和垃圾清扫状态。

这些是二维仿真指标，不代表实车或工业指标。
