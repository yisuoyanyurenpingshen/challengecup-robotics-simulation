# src：核心源码

`smartclean_sim` 是不依赖 ROS2、Gazebo、GPU 或网络的二维仿真基线。

| 文件 | 职责 |
| --- | --- |
| `models.py` | 栅格位置、垃圾、任务和指标数据模型 |
| `grid.py` | 地图边界、障碍、危险区、垃圾状态和邻接关系 |
| `planning.py` | 确定性四邻域 A* |
| `tasking.py` | 中文规则解析、结构化任务校验和字段兼容 |
| `simulation.py` | 清扫、动态障碍安全重规划、返航和运行结果 |
| `rendering.py` | 终端 ASCII 路线图 |
| `config.py` | JSON 配置加载与版本校验 |
| `cli.py` | 命令行编排 |

依赖规则：核心模块不能导入 ROS2、YOLO、LLM 或 RDK SDK；外部平台只能通过后续适配层调用核心公开接口。接口变化必须同步更新 `docs/03_module_interfaces.md`、测试和工程日志。

