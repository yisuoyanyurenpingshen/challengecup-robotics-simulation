# SmartClean-Sim 模块接口约定

## 1. 文档目的

本文定义 SmartClean-Sim 核心模块之间的稳定数据契约。团队成员可以分别实现仿真、感知、规划、控制、交互或 RDK 适配，只要输入输出满足本文约定，就能独立替换和集成。

本文描述的是逻辑接口；实际 Python 类型、JSON Schema 和 ROS2 消息应由同一份字段定义生成或逐项测试，避免三套结构逐渐不一致。

## 0. 已实现接口与目标契约

第 3 节起的大部分对象是 ROS2/Gazebo/视觉接入阶段的目标契约。当前可运行 P0 有意保持最小，只实现下列 Python 接口：

```text
GridPosition(x, y)
TrashItem(item_id, kind, position, area)
CleaningTask(target_area, priority_classes, avoid_types, return_to_dock, mode)
GridWorld.from_dict(scenario)
AStarPlanner.plan(world, start, goal, avoid_types, extra_blocked)
CoveragePlanner.plan(world, start, target_area, avoid_types)
RuleBasedTaskParser.parse(instruction)
Simulator.from_config(config, task).run() -> SimulationResult
```

当前仓库配置使用整数 `schema_version: 1`。外部任务字段优先采用 `return_after_done`；P0 同时接受 `return_after_done` 和内部历史名称 `return_to_dock`，进入核心后统一映射为 `CleaningTask.return_to_dock`。

P0 栅格坐标原点在左上角，`x` 向右、`y` 向下，单位是“格”。后续 ROS2 `map` 坐标采用右手系、米制且 `y` 向上，适配器必须显式完成轴向和比例转换，禁止直接混用。

P1 已实现 `clean_spots` 和 `clean_area` 两种模式、显式命名栅格区域、全覆盖规划，以及 `SimulationResult.trace.frames` 完整回放快照。目标契约中的 `patrol`、连续位姿、固定 `dt` 和感知对象仍未实现。

ROS2 Humble 回放桥已经实现以下公开入口和只读输出：

```text
GridMapTransform.grid_to_map(grid_x, grid_y) -> (map_x_m, map_y_m)
load_and_run(config_path) -> BridgeRun
build_status_payload(run, frame_index) -> JSON-compatible dict
SmartCleanBridgeNode -> status(String JSON), trajectory(Path), robot_pose(PoseStamped)
```

这组**回放接口**只负责把确定性二维结果送入 ROS2，本身不接受 `/odom`、`/scan` 或 `/cmd_vel`。独立的 Gazebo 差速启动链已经接入 `/cmd_vel`、`/odom` 与 TF，但仍不具备 Nav2 自主导航语义。

## 2. 全局约定

### 2.1 版本与命名

- 对外 JSON/YAML 对象包含整数 `schema_version`，初始值为 `1`。
- 字段名统一使用英文 `snake_case`，枚举值使用大写英文或本文指定的小写字符串。
- 稳定对象必须有唯一字符串 ID，如 `task_id`、`scenario_id`、`object_id`。
- 新增可选字段属于兼容变更；删除字段、修改含义或单位必须升级主版本。
- 未知字段默认拒绝，确需向前兼容的适配器应显式记录忽略了哪些字段。

### 2.2 坐标与单位

- 世界坐标系名为 `map`，右手平面坐标：`x` 向右、`y` 向上。
- 长度使用米，时间使用秒，速度使用米/秒，角度使用弧度。
- `yaw` 以 `+x` 为零，逆时针为正，并规范化到 `[-π, π)`。
- 图像框使用像素坐标，只有经过标定或仿真真值转换后才能填写地图位置。
- 浮点比较使用配置中的容差，不直接用严格相等。
- 时间戳以仿真时间 `sim_time` 为核心排序依据；外部适配器可额外保留墙上时间。

### 2.3 错误返回

可失败接口统一返回结果对象或抛出项目定义异常，至少包含：

```json
{
  "code": "NO_FEASIBLE_PATH",
  "message": "目标区域被禁行区完全阻断",
  "details": {
    "area_id": "teaching_building_gate"
  }
}
```

错误码用于程序判断，`message` 用于日志和界面展示。禁止调用方通过匹配错误文本判断逻辑。

## 3. 核心数据模型

以下 JSON 是字段契约示例，不代表必须使用 JSON 在进程内传输。

### 3.1 `Pose2D`

```json
{
  "frame_id": "map",
  "x": 1.25,
  "y": 3.5,
  "yaw": 0.0
}
```

约束：`x`、`y` 必须位于地图边界内；机器人可达性由场景或规划校验，不由 `Pose2D` 自身判断。

### 3.2 `Polygon2D`

```json
{
  "polygon_id": "water_zone_01",
  "points": [
    {"x": 2.0, "y": 1.0},
    {"x": 3.0, "y": 1.0},
    {"x": 3.0, "y": 2.0},
    {"x": 2.0, "y": 2.0}
  ]
}
```

约束：至少三个不同点，不允许自相交；首点不要求在数组末尾重复。

### 3.3 `TaskSpec`

```json
{
  "schema_version": 1,
  "task_id": "task_demo_001",
  "mode": "clean_area",
  "target_area": "teaching_building_gate",
  "target_points": [],
  "priority_classes": ["fallen_leaves", "plastic_bottle"],
  "avoid_zone_ids": ["water_zone_01"],
  "return_after_done": true,
  "max_duration_s": 600.0,
  "metadata": {
    "source": "demo_json"
  }
}
```

字段约束：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `schema_version` | string | 是 | 数据契约版本 |
| `task_id` | string | 是 | 单次任务唯一 ID |
| `mode` | enum | 是 | `clean_area`、`clean_spots` 或 `patrol` |
| `target_area` | string/null | 条件 | `clean_area` 时必填，必须引用场景区域 |
| `target_points` | Pose2D[] | 条件 | `clean_spots` 时至少一个 |
| `priority_classes` | string[] | 否 | 越靠前优先级越高，不得含重复值 |
| `avoid_zone_ids` | string[] | 否 | 引用场景中的禁行或代价区域 |
| `return_after_done` | boolean | 是 | 完成后是否返航 |
| `max_duration_s` | number/null | 否 | 正数；为空表示使用系统上限 |
| `metadata` | object | 否 | 追踪来源，不得影响核心决策 |

`TaskSpec` 是 LLM、Web、CLI 和 ROS2 任务入口的共同边界。校验失败的任务不得进入执行队列。

### 3.4 `ScenarioSpec`

```json
{
  "schema_version": 1,
  "scenario_id": "campus_demo",
  "seed": 42,
  "map": {
    "width_m": 20.0,
    "height_m": 12.0,
    "resolution_m": 0.1
  },
  "robot": {
    "start_pose": {"frame_id": "map", "x": 1.0, "y": 1.0, "yaw": 0.0},
    "dock_pose": {"frame_id": "map", "x": 0.8, "y": 0.8, "yaw": 0.0},
    "radius_m": 0.3,
    "cleaning_radius_m": 0.45,
    "max_linear_speed_mps": 0.8,
    "max_angular_speed_rps": 1.2
  },
  "areas": [],
  "static_obstacles": [],
  "dynamic_obstacles": [],
  "litter_objects": [],
  "forbidden_zones": []
}
```

场景加载必须完成：唯一 ID、边界、几何合法性、对象重叠、机器人初始碰撞、引用完整性和数值范围校验。动态障碍行为也必须由场景 `seed` 和仿真时间完全决定。

### 3.5 `Observation`

```json
{
  "schema_version": 1,
  "observation_id": "obs_000120",
  "sim_time": 12.0,
  "frame_id": "robot_base",
  "source": "simulator",
  "robot_pose": {"frame_id": "map", "x": 4.1, "y": 2.7, "yaw": 0.2},
  "image_ref": null,
  "range_samples": [],
  "ground_truth_ref": "world_tick_120"
}
```

`ground_truth_ref` 仅供模拟感知和评估使用，真实感知适配器不得读取仿真真值作弊。图像大对象使用引用或内存句柄传递，不嵌入事件 JSON。

### 3.6 `Detection`

```json
{
  "schema_version": 1,
  "detection_id": "det_000012",
  "sim_time": 12.0,
  "source": "mock",
  "class_name": "plastic_bottle",
  "confidence": 0.97,
  "bbox_xyxy_px": [120.0, 80.0, 210.0, 190.0],
  "position": {"frame_id": "map", "x": 5.2, "y": 3.1, "yaw": 0.0},
  "position_valid": true,
  "attributes": {}
}
```

约束：

- `confidence` 范围为 `[0, 1]`。
- 没有可靠深度或标定时，`position` 为 `null` 且 `position_valid=false`，不可伪造地图坐标。
- YOLO、Mock 和 RDK 后处理必须输出相同字段语义。
- 检测列表按 `class_name`、位置和 `detection_id` 做稳定排序后进入确定性核心。

### 3.7 `WorldSnapshot`

`WorldSnapshot` 是只读规划输入，至少包含：

- `snapshot_id`、`sim_time` 和地图版本。
- 当前机器人状态。
- 膨胀后的占用网格或等价可通行表示。
- 已知垃圾目标及其清扫状态。
- 静态、动态障碍和禁行区。
- 当前任务允许访问的区域。

规划器不得持有并修改仿真世界；世界发生变化后由编排器创建新快照。

### 3.8 `Plan` 与 `PlanResult`

```json
{
  "ok": true,
  "plan": {
    "plan_id": "plan_task_demo_001_02",
    "task_id": "task_demo_001",
    "world_snapshot_id": "snapshot_000120",
    "created_at_sim_time": 12.0,
    "waypoints": [
      {"frame_id": "map", "x": 4.1, "y": 2.7, "yaw": 0.2},
      {"frame_id": "map", "x": 4.5, "y": 2.9, "yaw": 0.1}
    ],
    "target_object_ids": ["litter_003"],
    "estimated_length_m": 3.8,
    "planner_name": "coverage_astar",
    "planner_version": "1"
  },
  "error": null
}
```

无路径时返回 `ok=false`、`plan=null` 和结构化错误。计划必须记录所依据的世界快照，执行器据此判断是否需要重规划。

### 3.9 `RobotState`

```json
{
  "schema_version": 1,
  "robot_id": "cleaner_01",
  "sim_time": 12.0,
  "pose": {"frame_id": "map", "x": 4.1, "y": 2.7, "yaw": 0.2},
  "linear_speed_mps": 0.4,
  "angular_speed_rps": 0.0,
  "task_state": "NAVIGATING",
  "active_task_id": "task_demo_001",
  "active_plan_id": "plan_task_demo_001_02",
  "battery_percent": 88.0,
  "progress": 0.42,
  "last_error": null
}
```

`progress` 范围为 `[0, 1]`，其计算方法应在指标文档中固定。没有电池模型时可以使用常量，但必须在结果元数据中标为模拟值。

### 3.10 `ControlCommand`

```json
{
  "schema_version": 1,
  "command_id": "cmd_000120",
  "sim_time": 12.0,
  "linear_velocity_mps": 0.4,
  "angular_velocity_rps": 0.1,
  "cleaning_enabled": false,
  "valid_for_s": 0.1,
  "reason": "follow_waypoint"
}
```

命令由安全限制器统一裁剪。过期命令、来源不明命令以及暂停、失败或急停状态下的非零命令必须被拒绝并记录事件。

### 3.11 `DomainEvent`

```json
{
  "schema_version": 1,
  "event_id": "evt_000445",
  "event_type": "StateChanged",
  "sim_time": 12.0,
  "task_id": "task_demo_001",
  "source": "task_executor",
  "payload": {
    "from_state": "PLANNING",
    "to_state": "NAVIGATING",
    "reason": "plan_ready"
  }
}
```

首批稳定事件类型：

- `TaskAccepted`、`TaskRejected`、`StateChanged`
- `PlanCreated`、`PlanInvalidated`、`ReplanRequested`
- `ObstacleObserved`、`CollisionDetected`
- `LitterDetected`、`LitterCleaned`
- `CommandApplied`、`SafetyStopApplied`
- `TaskCompleted`、`TaskFailed`

事件按 `(sim_time, event_id)` 稳定排序。指标、日志、Web 和 ROS2 状态发布均消费事件，不在核心路径中反向修改事件。

### 3.12 `RunSummary`

```json
{
  "schema_version": 1,
  "run_id": "run_campus_demo_42",
  "scenario_id": "campus_demo",
  "task_id": "task_demo_001",
  "seed": 42,
  "status": "COMPLETED",
  "sim_duration_s": 146.2,
  "path_length_m": 78.4,
  "coverage_rate": 0.91,
  "litter_clearance_rate": 1.0,
  "collision_count": 0,
  "avoidance_count": 3,
  "replan_count": 1,
  "perception_source": "mock",
  "limitations": ["2d_kinematic_simulation", "mock_perception"]
}
```

摘要必须携带局限性，便于区分二维仿真、Gazebo 仿真和实车/RDK 实测结果。

### 3.13 ROS2 垃圾任务状态与清扫事件（schema 1）

Phase 12 的任务编排使用两个自定义消息：

- `/smartclean/mission/state`：`smartclean_interfaces/msg/TrashMissionState`。
  它发布任务状态、结构化失败码、活动目标，以及任务内稳定的
  `discovered_trash_ids` / `cleaned_ids` / `remaining_trash_ids`。
- `/smartclean/mission/litter_cleaned`：`smartclean_interfaces/msg/LitterCleaned`。
  它同时携带最近一次图像检测 ID、稳定轨迹 ID、目标与机器人位置、清扫距离，
  以及仿真清扫执行器的实体删除确认。

图像节点的 `TrashDetection.detection_id` 只保证单次检测会话内唯一，并且每帧都会
变化，不能直接作为任务进度 ID。任务编排器必须只使用检测消息中的
`position_valid=true` 地图位置，通过同类空间最近邻关联生成稳定 `track_id`；任何
Gazebo 场景真值都不得参与目标发现、排序或导航。

`LitterCleaned` 的发布是一个有顺序的安全门：Nav2 目标状态必须为
`STATUS_SUCCEEDED`，实测清扫工具到目标的距离必须位于清扫半径内，机器人必须连续
停车，然后 Gazebo/实车清扫执行器必须返回成功。任一条件失败时，只能发布带
`failure_code` 的任务状态；不得提前删除实体、更新 `cleaned_ids` 或伪造清扫事件。

## 4. 模块调用接口

以下签名用于约束职责，命名可在实现前统一确认，但语义不得私自改变。

### 4.1 场景加载器

```text
ScenarioLoader.load(path) -> ScenarioSpec
ScenarioValidator.validate(spec) -> ValidationResult
WorldFactory.create(spec) -> SimWorld
```

读取与校验分离，测试可以直接构造 `ScenarioSpec`。配置非法时，在世界创建前一次性返回可定位的错误列表。

### 4.2 仿真世界

```text
SimWorld.observe() -> Observation
SimWorld.snapshot(detections) -> WorldSnapshot
SimWorld.step(command, dt) -> list[DomainEvent]
SimWorld.is_terminal() -> bool
```

`step` 是修改世界状态的唯一入口。`dt` 必须等于运行配置中的固定步长，除非测试明确验证非法输入。

### 4.3 感知器

```text
Perception.detect(observation) -> list[Detection]
Perception.health() -> ComponentHealth
```

必须至少实现：

- `MockPerception`：确定性、无需 GPU，用于基准测试。
- `YoloPerceptionAdapter`：负责预处理、推理、后处理和类别映射。
- `RdkPerceptionAdapter`：负责 BPU 模型和板端资源，输出相同 `Detection`。

感知器故障不能静默返回空列表；应通过健康状态或结构化异常区分“未检测到目标”和“模块不可用”。

### 4.4 规划器

```text
Planner.plan(snapshot, task) -> PlanResult
Planner.replan(snapshot, task, previous_plan, reason) -> PlanResult
Planner.is_plan_valid(plan, snapshot) -> bool
```

规划器必须是纯输入到输出或表现为纯函数：不能推进仿真、发布速度命令或修改任务状态。

### 4.5 控制器与安全限制器

```text
Controller.compute(robot_state, waypoint, dt) -> ControlCommand
SafetyLimiter.apply(command, robot_state, snapshot) -> ControlCommand
```

所有自主控制命令在发布到 ROS2 `/cmd_vel` 前必须经过领域 `SafetyLimiter`。传输链末端还必须经过 `CmdVelGuard`：命令断流或包含非有限数值时强制输出零速度。急停优先级最高，其次是故障、暂停、碰撞风险和普通速度限制。

### 4.6 任务解析器

```text
TaskParser.parse(text, context) -> TaskParseResult
TaskValidator.validate(task, scenario) -> ValidationResult
```

`RuleTaskParser` 是离线基线；`LlmTaskParserAdapter` 只生成候选任务。两者必须共用 `TaskValidator`。解析失败时返回缺失字段或非法引用，禁止填造不存在的场景区域。

### 4.7 任务执行器

```text
TaskExecutor.submit(task) -> CommandResult
TaskExecutor.pause() -> CommandResult
TaskExecutor.resume() -> CommandResult
TaskExecutor.cancel() -> CommandResult
TaskExecutor.request_return() -> CommandResult
TaskExecutor.emergency_stop() -> CommandResult
TaskExecutor.reset() -> CommandResult
TaskExecutor.tick(snapshot, detections, sim_time) -> ExecutionDecision
```

`ExecutionDecision` 至少包含目标任务状态、活动计划/航点、是否启用清扫、重规划请求和原因。命令重复提交应幂等或返回明确冲突，不得产生两个相同任务。

### 4.8 指标采集器

```text
MetricsCollector.on_event(event) -> None
MetricsCollector.snapshot() -> MetricsSnapshot
MetricsCollector.finalize(run_context) -> RunSummary
```

指标采集器只能消费事件和只读上下文，不可控制任务状态。`finalize` 对同一事件序列必须产生相同摘要。

## 5. 适配器契约

### 5.1 ROS2

当前已实现并通过 Topic 探针的回放契约：

| Topic | ROS2 类型 | QoS | 语义 |
|---|---|---|---|
| `/smartclean/status` | `std_msgs/msg/String` | Reliable、Transient Local、depth 1 | UTF-8 JSON 状态、事件和指标；`schema_version=1` |
| `/smartclean/trajectory` | `nav_msgs/msg/Path` | Reliable、Transient Local、depth 1 | 完整仿真轨迹，`frame_id=map` |
| `/smartclean/robot_pose` | `geometry_msgs/msg/PoseStamped` | Reliable、Transient Local、depth 1 | 当前回放帧的格中心位置，`frame_id=map`；晚加入者可取得最近一帧 |

当前已实现并通过动力学探针的 Gazebo 差速契约：

| Topic | ROS2 类型 | 方向 | 语义 |
|---|---|---|---|
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 控制器/人工 → 安全看门狗 | 标准外部速度入口；当前差速底盘使用 `linear.x` 与 `angular.z` |
| `/smartclean/safe_cmd_vel` | `geometry_msgs/msg/Twist` | 看门狗 → ROS-Gazebo bridge | 内部安全速度，不作为上层控制入口 |
| `/odom` | `nav_msgs/msg/Odometry` | Gazebo → ROS2 | 差速里程计；`header.frame_id=odom`，`child_frame_id=base_link` |
| `/tf` | `tf2_msgs/msg/TFMessage` | Gazebo → ROS2 | 当前发布 `odom -> base_link` |
| `/clock` | `rosgraph_msgs/msg/Clock` | Gazebo → ROS2 | 推进中的仿真时钟 |

速度安全契约：

- 默认以 20 Hz 发布最后一条安全命令。
- 从最后一条有效输入开始 0.5 秒未收到新命令时输出全零 `Twist`。
- 任一分量为 NaN 或 Inf 时立即废弃缓存并输出全零命令。
- 超时计时使用 ROS2 `STEADY_TIME`，不因仿真暂停或时钟复位而失效。
- 看门狗只负责新鲜度与数值有效性；速度/加速度上限由底盘插件和后续领域安全限制器共同约束。

状态 JSON 的稳定顶层字段为：

```text
schema_version, scenario_name, status, task_state, run_result_status,
frame_index, frame_count, sim_step, action,
robot_grid_position, cleaned_ids, remaining_trash_ids, events,
progress, final_metrics, final_rates
```

`status` / `task_state` 表示当前回放帧，不能提前使用最终结果；
`run_result_status`、`final_metrics` 和 `final_rates` 明确表示这次确定性
运行的最终汇总。`progress` 只包含当前帧可证明的进度字段。

当前格坐标转换规则为：

```text
map_x = origin_x_m + (grid_x + 0.5) * cell_size_m
map_y = origin_y_m + (grid_height - grid_y - 0.5) * cell_size_m
```

其中 `origin_x_m`、`origin_y_m` 表示完整栅格左下角，发布位置位于格中心。转换必须拒绝非正栅格尺寸、非正分辨率、非有限原点和越界格坐标。当前核心没有连续朝向，`PoseStamped` 暂用单位四元数，调用方不得把它解释为实车航向。

当前和后续导航闭环的目标映射：

| 核心对象 | ROS2 接口 |
|---|---|
| `ControlCommand` | `geometry_msgs/msg/Twist`，运动入口已接入；清扫开关另用项目消息或服务 |
| `RobotState.pose` | `nav_msgs/msg/Odometry` / TF；当前只有 `odom -> base_link`，`map -> odom` 待定位模块提供 |
| 范围观测 | `sensor_msgs/msg/LaserScan` |
| 图像观测 | `sensor_msgs/msg/Image` |
| `Detection[]` | `smartclean_interfaces/msg/DetectionArray` |
| `RobotState` | `smartclean_interfaces/msg/RobotState` |
| `TaskSpec` 与执行反馈 | `smartclean_interfaces/action/CleanArea` |
| `RunSummary` | `smartclean_interfaces/msg/RunMetrics` 或结果文件 |

转换函数必须成对测试：核心对象转 ROS2 消息再转回后，除允许的时间戳精度外语义应保持不变。当前 `String` JSON 是过渡接口；增加任务控制或板端感知后，应迁移到 `smartclean_interfaces` 自定义消息，并提供 schema 迁移与兼容测试。

ROS2 环境固定 `ROS_DOMAIN_ID=42`。PC、容器和 RDK 需要跨机通信时，消息类型、domain、RMW 与 QoS 必须相容；不得把“能发现 Topic”当成“已通过消息契约”。

### 5.2 YOLO

YOLO 适配器输入图像和相机元数据，输出 `Detection[]`。模型类别索引必须通过版本化映射表转换为项目类别名。置信度阈值、NMS 阈值、输入尺寸和权重标识必须进入运行元数据。

若没有深度或外参，YOLO 只能给出二维框，`position_valid=false`；地图定位应由独立定位/投影组件完成。

### 5.3 LLM

LLM 请求只提供完成任务所需的场景区域、允许枚举和安全规则，避免发送敏感配置。响应必须是单个候选 `TaskSpec`，经过以下顺序处理：

1. JSON 语法解析。
2. Schema 和字段类型校验。
3. 枚举、区域引用和数值范围校验。
4. 安全策略校验。
5. 生成新的内部 `task_id` 并保留来源追踪。

任一步失败都不得进入执行器。禁止 LLM 输出或调用速度、急停复位等底层控制接口。

### 5.4 RDK

RDK 适配器封装模型加载、BPU 内存、预处理、推理和后处理。板端与 PC 端共享：

- 类别名称和索引映射。
- 输入尺寸、色彩空间和归一化定义。
- `Detection` 字段与坐标语义。
- 固定测试图片及期望结果容差。

量化造成的精度差异应记录在对比结果中，不允许为板端另建一套业务类别或规划接口。

板端基线为 RDK OS 3.x、Ubuntu 22.04 和 TROS-Humble；X5 是主目标，X3 是兼容目标。旧 X3 OS 2.x/Foxy 不属于当前接口兼容范围。PC 与 RDK 在同一网络和 domain 42 中通信，板端只能 source `/opt/tros/humble/setup.bash` 或同一终端中的一套等价 ROS 环境，禁止与 `/opt/ros` 或 Foxy 前缀混用。

`amd64` PC 构建产物不能直接作为 `arm64` RDK 二进制部署。包必须在板端 TROS 环境构建，或使用与板型、RDK OS 和 TROS 版本严格匹配的 D-Robotics 官方交叉编译环境。完整步骤和验收清单见 `09_rdk_tros_deployment.md`。

### 5.5 Web/CLI

建议的逻辑操作：

- 提交结构化任务或自然语言任务。
- 查询当前 `RobotState`、计划和指标。
- 暂停、恢复、取消、返航和急停。
- 订阅状态、路径、检测和事件流。

Web 与 CLI 都调用任务执行器的公开命令接口，不直接修改状态字段。急停复位必须是独立操作，不能复用普通 `resume`。

## 6. 确定性与并发约定

- 核心单步循环是唯一状态写入者；适配器线程不得直接修改世界。
- 外部命令进入有序队列，并在下一仿真步开始时统一应用。
- 同一仿真时间的命令按接收序号排序，优先级为：急停、取消、暂停、返航、恢复、新任务。
- 感知结果必须带对应观测时间；过期结果按配置丢弃并记录事件。
- 规划可以异步计算，但结果必须携带 `world_snapshot_id`；过时计划不得执行。
- 测试比较运行结果时，同时校验 seed、场景/任务哈希、事件序列和指标。

## 7. 最小集成验收契约

基础 smoke test 不依赖网络、ROS2 或 GPU，流程为：

1. 加载固定 demo 场景和 `seed=42`。
2. 加载并校验一个 `clean_area` 任务。
3. 使用 `MockPerception`、覆盖规划器和二维控制器启动闭环。
4. 至少遇到一个动态障碍并产生避障或重规划事件。
5. 清除目标垃圾，按任务要求返航。
6. 任务进入 `COMPLETED`，碰撞数为零。
7. 连续运行两次，事件序列和 `RunSummary` 一致。

ROS2 回放桥另有一组已通过的集成验收：工作空间可构建、48 项 `colcon` 测试通过；探针在 20 秒内收到状态、完整轨迹和位姿，并等待当前回放帧进入 `COMPLETED`；最终目标清除率与覆盖率均为 1.0、碰撞为 0 且已经返航。

Gazebo 有两层独立验收：最小 World `/clock` 冒烟；以及差速清扫车前进、原地转向、`/odom`、`odom -> base_link` TF、命令断流停车和 World 服务探针。后一层已经覆盖底盘动力学，但不覆盖 LiDAR、`map -> odom`、Nav2、RDK 或真实底盘。

接口实现的最低测试范围：

- 每个数据对象的合法/非法输入校验。
- 状态机正常路径、暂停恢复、取消、无路径和急停复位。
- 场景引用和坐标边界校验。
- 规划器无路径时的结构化错误。
- 安全限制器在所有停止状态下强制零速度。
- Mock、YOLO 和 RDK 检测输出的契约一致性。
- LLM 非法 JSON、越权字段和不存在区域的拒绝行为。
- 相同 seed 的重放一致性。

修改本文中的字段或行为时，提交必须同时包含契约测试和迁移说明；任何模块不得通过读取其他模块私有字段绕过公开接口。
