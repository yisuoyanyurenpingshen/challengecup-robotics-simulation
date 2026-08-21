# P1 开源方案调研与引入决策

## 调研信息

- 调研日期：2026-08-21
- 目标：在实现全覆盖清扫和轨迹动画前，先核验 GitHub 上已有实现、许可证、依赖和适配成本。
- 结论：P1 不直接复制或整仓下载第三方代码；参考成熟算法思想，在现有 `GridWorld + AStarPlanner` 接口上独立实现，并使用纯标准库生成自包含 HTML 动画。

## 候选项目

| 项目 | 能力与许可证 | 本项目决策 |
| --- | --- | --- |
| [PythonRobotics GridBasedSweepCPP](https://github.com/AtsushiSakai/PythonRobotics/blob/master/PathPlanning/GridBasedSweepCPP/grid_based_sweep_coverage_path_planner.py) | 成熟的二维栅格扫描示例；仓库采用 [MIT License](https://github.com/AtsushiSakai/PythonRobotics/blob/master/LICENSE) | 参考蛇形扫描思想，不复制源码 |
| [PythonRobotics Spiral-STC](https://github.com/AtsushiSakai/PythonRobotics/tree/master/PathPlanning/SpiralSpanningTreeCPP) | 带障碍栅格全覆盖；MIT | 作为复杂障碍场景的后续算法参考 |
| [OpenNav Coverage](https://github.com/open-navigation/opennav_coverage) | 面向 ROS2/Nav2 的完整覆盖服务器；Apache-2.0 | 留到 ROS2 阶段评估，不进入纯 Python P1 |
| [Fields2Cover](https://github.com/Fields2Cover/Fields2Cover) | 农业机器人覆盖规划库；BSD-3-Clause，C++/Python 依赖较重 | 后期对比，不作为当前依赖 |
| [covplan](https://github.com/sanjeevrs2000/covplan) | 面向多边形/经纬度区域；MIT，依赖科学计算与优化库 | 不适合当前离散校园栅格 P1 |
| [ETH polygon_coverage_planning](https://github.com/ethz-asl/polygon_coverage_planning) | Boustrophedon 多边形分解；GPL-3.0-or-later，并含额外求解器约束 | 与当前项目许可和短期依赖目标不匹配，不引入 |

## 为什么不直接搬运 PythonRobotics

- 上游输入是连续多边形边界，本项目已经有离散 `GridWorld`。
- 上游依赖自身 `GridMap`、NumPy、SciPy 和 Matplotlib；本项目 P0 只依赖标准库。
- 上游运动与转弯语义不等同于当前严格四邻域模型。
- 本项目还要求动态障碍、在线重规划、任务区域和可复现实验数据契约。
- 整文件复制会引入大量无用接口和额外许可证维护成本。

因此 P1 采用“蛇形候选顺序 + 已有 A* 连接”的独立实现。若未来复制或实质改写任何第三方代码，必须在源码中标明来源，并新增 `THIRD_PARTY_NOTICES.md` 保存相应版权和许可证文本。

## 动画方案决策

调研过 Matplotlib `FuncAnimation` 方案；当前服务器已有相关库，但团队成员和演示电脑不一定具备相同环境。P1 最终选择纯标准库输出一个自包含 HTML 文件：

- Canvas、CSS、JavaScript、场景和逐帧数据全部内联。
- 不使用 CDN、远程字体、图片或运行时网络请求。
- 浏览器直接打开即可播放、暂停、逐帧和调整速度。
- 渲染器只消费仿真快照，不重新运行算法，确保画面和指标来自同一次运行。

该选择没有复制第三方动画代码，也不新增运行依赖。
