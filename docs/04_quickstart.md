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

使用仓库内锁定环境运行核心测试：

```bash
bash scripts/ros2.sh run python -m pytest -q tests
```

## ROS 2 Humble 快速开始

ROS 环境与二维核心互相隔离。首次使用执行：

```bash
# 在仓库根目录执行
bash scripts/ros2.sh install
bash scripts/ros2.sh build
bash scripts/ros2.sh verify
bash scripts/ros2.sh gazebo-verify
bash scripts/ros2.sh drive-verify
```

`verify` 会自动启动桥接节点并订阅三个 Topic，只有同时满足以下条件才返回 0：

- 状态为 `COMPLETED`
- 垃圾清扫 `4/4`
- 区域覆盖率 `1.0`
- 碰撞 `0`
- 成功返航
- 收到 103 个轨迹位姿和逐帧机器人位姿

`gazebo-verify` 会在无界面模式启动本地 Fortress World，通过
`ros_gz_bridge` 收到非负且推进中的 `/clock` 后自动退出。

`drive-verify` 会启动差速清扫车，自动检查 `/cmd_vel` 前进、原地转向、
`/odom`、`odom -> base_link` TF，以及停止发命令后的自动停车；验证完成后
会清理本轮进程。

启动持续回放，保留这个终端：

```bash
bash scripts/ros2.sh demo replay_period_s:=0.1 loop_replay:=true
```

单独启动 Gazebo 最小场景，保留终端并用 `Ctrl+C` 停止：

```bash
bash scripts/ros2.sh gazebo
```

启动可控制的 Gazebo 差速清扫车，保留终端并用 `Ctrl+C` 停止：

```bash
bash scripts/ros2.sh drive
```

一次只输入一个命令。误把两条命令粘成
`bash scripts/ros2.sh drivebash scripts/ros2.sh drive` 时会看到用法提示；
正确写法就是单独的 `bash scripts/ros2.sh drive`。

另开一个新终端发送前进速度；按 `Ctrl+C` 停止发布后，底盘会在默认
0.5 秒内自动置零：

```bash
bash scripts/ros2.sh run ros2 topic pub --rate 10 /cmd_vel \
  geometry_msgs/msg/Twist \
  '{linear: {x: 0.25}, angular: {z: 0.0}}'
```

原地左转可用：

```bash
bash scripts/ros2.sh run ros2 topic pub --rate 10 /cmd_vel \
  geometry_msgs/msg/Twist \
  '{linear: {x: 0.0}, angular: {z: 0.6}}'
```

另开一个终端检查 ROS 图：

```bash
# 另一个终端也先进入仓库根目录
bash scripts/ros2.sh run ros2 node list
bash scripts/ros2.sh run ros2 topic list -t
bash scripts/ros2.sh run ros2 topic echo --once \
  --qos-reliability reliable \
  --qos-durability transient_local /smartclean/status
bash scripts/ros2.sh run ros2 topic echo --once \
  --qos-reliability reliable \
  --qos-durability transient_local /smartclean/trajectory
```

已发布接口：

| Topic | 消息 | 说明 |
| --- | --- | --- |
| `/smartclean/status` | `std_msgs/msg/String` | Schema v1 JSON 状态、指标和当前回放帧 |
| `/smartclean/trajectory` | `nav_msgs/msg/Path` | `map` 坐标系中的完整轨迹 |
| `/smartclean/robot_pose` | `geometry_msgs/msg/PoseStamped` | 按帧回放的当前位置 |
| `/cmd_vel` | `geometry_msgs/msg/Twist` | Gazebo 差速车标准速度入口 |
| `/odom` | `nav_msgs/msg/Odometry` | Gazebo 差速里程计，`odom -> base_link` |
| `/tf` | `tf2_msgs/msg/TFMessage` | 当前包含 `odom -> base_link` |
| `/clock` | `rosgraph_msgs/msg/Clock` | Gazebo 仿真时钟 |

打开完整环境 shell：

```bash
bash scripts/ros2.sh shell
source ros2_ws/install/setup.bash
```

退出 shell 使用 `exit`。不要在同一个终端再 source 系统 ROS 或其他 Conda 环境。

二维回放节点和 Gazebo 差速节点是两条独立入口：`demo` 用于确定性算法回放，`drive` 用于真实物理步进下的底盘接口验证。当前已经有机器人模型、差速动力学、`/cmd_vel`、`/odom` 和基础 TF；还没有 LiDAR、相机、`map -> odom` 定位或 Nav2 自主导航闭环。技术边界见 `docs/08_ros2_environment_and_bridge.md`。

## 结果说明

- `completion_rate`：当前任务目标中已清扫目标的比例。
- `coverage_rate`：`clean_area` 模式下为任务区域已访问安全格占区域安全格的比例；`clean_spots` 模式保留全图轨迹覆盖率口径。
- `path_length_cells`：机器人移动的栅格步数。
- `replans`：因为动态障碍或临时无路而重新规划的次数。
- `collisions`：碰撞次数；安全闭环的期望值为 0。
- `returned_to_dock`：最终是否位于回充点。

详细 JSON 中的 `trace.frames` 是动画使用的完整逐帧快照，包含仿真步、状态、机器人、动态障碍和垃圾清扫状态。

这些是二维仿真指标，不代表实车或工业指标。
