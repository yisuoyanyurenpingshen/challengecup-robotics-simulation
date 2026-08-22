# 交接文档：通宵自治工作（2026-08-22）→ 下一位 Codex 代理

> 目的：让你（朋友的 Codex）不重复踩坑，直接继续 Phase 12（识别→导航→清扫闭环）。
> 最后更新：2026-08-22 11:30 CST。主线已推送到 GitHub main。

## 0. 一句话状态

- Phase 1–11 全部完成、验收、提交并推送到 `origin/main`。
- **Phase 12 `trash-mission`（检测→导航→清扫→指标更新→返航）尚未开始。**
- Phase 13（五场景批量实验）尚未开始。
- 最终交接文档 `docs/README0822.md`（21 项）尚未生成。
- 当前 HEAD `ad17b60`，已推送：本地 == origin/main == GitHub main。

## 1. 任务来源与主线

用户原始任务（要点）：
修复脚本 → 可弹出的 Gazebo/RViz 演示 → 本地垃圾场景 → RGB 相机 → 像素级识别 →
深度位置估计 → 2D LiDAR+完整 TF → Nav2 最小导航 → **trash-mission 闭环** →
五场景实验 → 最终 README0822 交接。每阶段：测试→记录→提交→普通推送（禁止 force push）。

## 2. 已完成的阶段与提交（本地==origin==GitHub）

| 提交 | 内容 | 验收证据 |
|---|---|---|
| `1227134` | fix(scripts) rg→grep -Fqx 便携化，drive-verify 不再误报 | drive-verify exit=0 |
| `d342ad2` | feat(gui) Gazebo GUI + RViz + 本地 URDF + `drive-gui` | 启动契约测试 |
| `06b5283` | feat(gazebo) 本地垃圾场景（4 类模型、SDF、真值标签） | trash-verify |
| `7d7fe2b` | feat(gazebo) RGB 相机 640x480@10Hz + camera_optical TF | camera-verify |
| `dfa3b29` | feat(perception) 真实像素 OpenCV 合成场景识别基线 | P/R=1.0, 2.85ms/帧 |
| `4801fe7` | feat(perception) 深度反投影位置估计 | 位置误差 0.032m |
| `054c514` | feat(gazebo) 2D LiDAR + 完整 TF | lidar-verify |
| `5ce5cb9` | fix(gazebo) footprint 碰撞盒抬高整车→车轮悬空，移入车体 | 真值位移证据 |
| `5d58976` | **feat(nav2) 验证过的导航闭环 + 单调时钟中继** | nav2-verify（见 §3） |
| `415ec18` | docs(nav2) 地图生成器坐标注释修正 | — |
| `ad17b60` | docs(handoff) 日志收尾 + 本交接文档 | 本地==origin==GitHub |
| 日志 | `5ca0d37`/`5473f56` 等 docs(log) 提交 | — |

交接基线：`6c5d718`（用户给出的起点）。

## 3. 全量验收（改动后重跑，全部 exit=0）

```bash
bash scripts/ros2.sh install
bash scripts/ros2.sh test            # 137 tests, 0 failures（colcon）
bash scripts/ros2.sh verify          # ROS 回放 Topic 验证
bash scripts/ros2.sh gazebo-verify   # /clock
bash scripts/ros2.sh drive-verify    # 差速闭环 + World 断言
bash scripts/ros2.sh run python -m pytest -q tests   # 41 项 2D 核心
bash scripts/ros2.sh camera-verify
bash scripts/ros2.sh perception-verify
bash scripts/ros2.sh position-verify
bash scripts/ros2.sh lidar-verify
bash scripts/ros2.sh nav2-verify
```

末轮 `nav2-verify` 关键数字：双目标到达误差 0.155–0.172 m；/plan=True；
`/cmd_vel` 发布者 `velocity_smoother`；/odom 实际移动；最终停车位移 0.0000 m；
`/clock` 单调 PASS（零倒退）；launch 日志零 `jump back`；无残留进程。

## 4. 如何继续（新机器 / 本机）

本机（推荐直接继续）：
```bash
cd /home/bktx/projects/challengecup-robotics-simulation
git status --short && git log --oneline -3   # 应先看到干净的树与 ad17b60
```

新机器从零开始：
```bash
git clone https://github.com/yisuoyanyurenpingshen/challengecup-robotics-simulation
cd challengecup-robotics-simulation
bash scripts/ros2.sh install      # 下载并安装仓库内锁定的 pixi ROS2 Humble 环境（需网络，约数 GB）
bash scripts/ros2.sh build
bash scripts/fetch_xvfb.sh        # 无显示器机器跑传感器验证需要本地 Xvfb
bash scripts/ros2.sh nav2-verify  # 冒烟确认环境可用
```

常用入口（统一经 `bash scripts/ros2.sh <cmd>`）：
`drive` / `drive-gui` / `nav2`（可 `gui:=true rviz:=true`）/
`drive-verify` `camera-verify` `perception-verify` `position-verify`
`lidar-verify` `nav2-verify`。
无 DISPLAY 时 GUI 命令会给中文提示并拒绝启动，headless 不受影响。

## 5. 关键环境事实与踩坑（不要重复）

1. **运行框**：所有 ROS 命令必须走 `bash scripts/ros2.sh run bash -lc 'source ros2_ws/install/setup.bash && ...'`；
   host python 是 3.8，pixi 内是 3.12；别在宿主环境直接跑 ROS。
2. **/clock 乱序**：`parameter_bridge` 可能乱序转发高频 /clock，tf2 会报
   `Detected jump back in time` 并清空 TF 缓冲。已用 `smartclean_clock_relay`
   （/clock_raw→/clock 严格单调）修复。**不要移除 relay 或把桥改回直接发布 /clock。**
3. **Nav2 热启动**：action server 在 CONFIGURING 阶段即可见，早发目标会被拒；
   `nav2_probe.py` 已加 lifecycle ACTIVE 门控，新代码发目标前照做。
4. **底盘悬空**：`base_footprint` 的契约碰撞盒不得接触地面（当前在 z=0.25 车体内）。
5. **`verify_ros2.sh`**：直接执行安装后的 console script（`ros2 run` 包装器会留孤儿进程），
   cleanup 用 SIGINT→TERM→KILL 阶梯；`bridge_node.py` 捕获 ExternalShutdownException。
6. Nav2 参数：`use_composition` 必须传字符串 `"False"`；map `mode: trinary` 要求 free=254；
   AMCL `initial_pose` 是 map 帧坐标；ROS_DOMAIN_ID ≤232。
7. 进程清理：`pgrep -af "ign gazebo|Xvfb :|ros2 launch|parameter_bridge|smartclean_bridge"`；
   kill 用 INT→TERM→KILL。
8. Git：只普通 `git push origin main`；推送后核对
   `git rev-parse HEAD` == `git ls-remote origin refs/heads/main`；
   gh 凭据经 `GH_CONFIG_DIR="$PWD/.tools/gh-config" "$PWD/.tools/bin/gh"`，绝不打印 token。

## 6. 未完成：Phase 12 trash-mission（下一步第一优先）

要求（用户原话要点）：
`bash scripts/ros2.sh trash-mission` 与 `trash-mission-verify`。流程：
Gazebo+RViz → 相机看到垃圾 → 识别输出类别/框/置信度 → 可靠地图位置 →
按 priority_classes 选目标 → 生成不压垃圾的安全接近点 → NavigateToPose →
真实到达 cleaning_radius 内停车 → 删除/隐藏 Gazebo 垃圾实体 →
发布 LitterCleaned 事件 → 更新 cleaned_ids / remaining_trash_ids → 下一个 →
全部完成后返航停车。

已有资产（可直接复用）：
- 垃圾真值与类别：`configs/gazebo_scene.json`（含 cleaning_radius=0.45、dock=(0,0)）；
- 识别输出：`/smartclean/detections`（vision_msgs/Detection2DArray，含 bbox/class/confidence）；
- 位置估计：`/smartclean/detections` 的 position 字段（Phase 9 已做深度反投影+TF 到 map）；
- Nav2 调用模板：`scripts/nav2_probe.py` 的 ActionClient 写法（加 lifecycle 门控）；
- 删除垃圾：Gazebo 实体用 ign transport 的 `world_control`/entity service 或
  `/world/smartclean_trash/remove` 类服务；若桥接麻烦，可桥一个 ROS service 到
  ign msgs.Entity（ros_gz_bridge 支持 `ros_gz_interfaces/srv/DeleteEntity`？实际以
  已装 ros_gz 版本支持为准，先 `ls .pixi/envs/default/share/ros_gz_interfaces/srv`）。
- 任务编排骨架：`scripts/` 下现有 verify_*.sh 的 Xvfb/独立 domain/清理模式。

禁止项（验收会查）：读真值绕过识别、未到就删垃圾、定时宣布清扫完成、
只导航不更新状态、只删不导航、手工 /cmd_vel 冒充 Nav2。

验收清单（原任务）：
初始垃圾>0、图像有效、真实检测有效、≥1 个 position_valid 目标、Nav2 收到目标、
车辆实际移动、到达清扫半径、垃圾真正 cleaned、remaining 下降、无碰撞、
完成或返回结构化原因、watchdog 有效、最终停车、按任务返航、子进程全清。

建议实施顺序：
1) 先手写 `trash_mission_controller`（smartclean_ros 或新包），把
   detections→position_valid 目标→安全接近点→NavigateToPose 串起来（复用 nav2.launch 作为底座）；
2) 垃圾删除先做最小可行（ign service / 桥），被阻塞就先实现“到达后隐藏+状态更新”
   并如实记录，不造假；
3) 最后写 verify 脚本（独立 domain/partition，全量断言）。

## 7. 未完成：Phase 13 与最终交接

- Phase 13：道路/停车场/狭窄通道/积水密集区/多动态行人五场景批量实验，CSV/JSON、
  配置哈希、完成率/覆盖率/路径长度/重规划/碰撞/返航指标。
- 最终：`docs/README0822.md`（21 项：起止 commit、GitHub 最终哈希、每阶段提交状态、
  新增文件、GUI/相机/识别/LiDAR/Nav2 参数、识别 P/R/延迟、清扫成功数、验收命令、
  失败与根因、未完成、下一步、git status、三端一致性），并更新 `docs/README.md`。
- 持续日志：`logs/2026-08-22-overnight-autonomous-work.md`（当前已写到 Phase 11）。

## 8. 每阶段强制流程（保持）

1) `git status --short`；2) 专项测试；3) 全量回归（§3 命令 + 本阶段新增 verify）；
4) `bash -n`（.sh）/ `python3 -m py_compile`（.py）/ `ign sdf -k`（.sdf）/ `git diff --check`；
5) 确认无残留 Gazebo/RViz/Nav2/bridge 进程；6) 更新 docs/logs；
7) 只暂存本轮文件，清晰提交；8) `git fetch origin main` 后普通 `git push origin main`；
9) 核对 `git rev-parse HEAD` == `git ls-remote origin refs/heads/main`。

## 9. 当前工作区状态（截至本文档）

- 已提交并推送：`5ce5cb9`、`5d58976`、`415ec18`、`ad17b60`。
- `git status --short` 干净（本文档落盘后为空输出）。
- 不在版本控制且应保持：`.pixi/`、`.tools/`、`.cache/`、`weights/downloads/`、
  `ros2_ws/{build,install,log}/`（见 .gitignore）。
