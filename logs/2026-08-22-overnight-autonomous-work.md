# 2026-08-21/22 通宵自治工作日志

## 基本信息

- 开始时间：2026-08-21 23:51 CST（跨夜工作，文件以 08-22 命名）
- 执行者：Codex（通宵自治总工程师）
- 开始 commit：`6c5d718ec6768702ce950cd00086e3218d4c60d6`（HEAD，origin/main 一致）
- GitHub：https://github.com/yisuoyanyurenpingshen/challengecup-robotics-simulation
- 目标分支：main
- 授权范围：自主设计、编码、下载仓库内依赖、测试、记录、创建提交并普通推送（禁止 force push）

## 当前目录结构（开始时）

- 仓库干净：`git status --short` 为空；HEAD 与 origin/main 均为 `6c5d718`。
- `src/smartclean_sim/`：二维核心（34 项测试）。
- `ros2_ws/src/`：`smartclean_core`、`smartclean_ros`（回放桥+看门狗）、`smartclean_gazebo`（World、差速车、launch）。
- `scripts/`：统一入口 `ros2.sh`；验证脚本 `verify_gazebo.sh`、`verify_gazebo_drive.sh`。
- 锁定环境：Pixi 0.77.0 / ROS2 Humble（RoboStack）/ Gazebo Fortress 6.16.0 / ros_gz 0.244.24 / Nav2 1.1.20。

## 环境审计（开始前）

- 日期：2026-08-21 23:51 CST；宿主机 Ubuntu 20.04.6。
- 本会话无可用 DISPLAY（存在 X0/X1/X1001/X2 但均属其他用户且无 Xauthority；无 Xvfb）。
  GUI 功能按参数化实现并做契约验证；真实窗口渲染需要用户桌面会话确认。
- Pixi 环境内已有：cv2 4.13.0、numpy 2.5.2、rviz2、ign gazebo 6.16.0。
- ros_gz_bridge 0.244.24 支持 Image/CameraInfo/LaserScan/PointCloud 转换。
- Nav2 全家桶（bringup/amcl/map_server/controller/planner/lifecycle/bt_navigator）可用。
- 磁盘可用约 159 GiB。

## 当前可运行能力（基线）

- 二维核心闭环 + 离线动画；ROS2 回放桥；Gazebo 差速底盘闭环（/cmd_vel → 看门狗 → DiffDrive → /odom + odom→base_link TF）。
- 尚未完成：LiDAR、相机、完整 TF、Nav2、感知、任务闭环。

## 已知问题（开始前）

1. `scripts/verify_gazebo_drive.sh` 用 `rg -Fxq` 做 World/Topic 行匹配；普通 Pixi 运行环境无 `rg`，
   功能探针成功后误报“未发现 smartclean_drive World 控制服务”。
2. 用户误粘贴 `drivebash scripts/ros2.sh drive` 两个命令；需要在 README/错误提示写清楚正确命令。
3. 无 GUI/RViz 启动入口；无 robot_description；无垃圾场景、相机、LiDAR、Nav2、感知。

## 本夜任务队列

- [ ] P1 修复 rg 误报 + 最小 PATH 回归 + 正确命令提示（commit: fix(scripts)）
- [ ] P2 drive-gui：Gazebo GUI + RViz + robot_state_publisher + 本地 URDF/Xacro（feat(gui)）
- [ ] P3 Gazebo 本地垃圾场景 + 真值标签（feat(gazebo)）
- [ ] P4 RGB 相机 + camera-verify（feat(gazebo)）
- [ ] P5 像素级垃圾识别基线 smartclean_perception + perception-verify（feat(perception)）
- [ ] P6 垃圾位置估计（深度优先、地面射线兜底）
- [ ] P7 LiDAR + 完整 TF + lidar-verify（feat(gazebo)）
- [ ] P8 Nav2 最小导航 + nav2-verify（feat(nav2)）
- [ ] P9 识别—导航—清扫闭环 trash-mission + trash-mission-verify（feat(mission)）
- [ ] P10 五场景批量实验（如有时间）
- [ ] P11 README0822 交接文档

## 关键节点命令与结果

### 开始

```bash
git status --short  # 干净
git log --oneline --decorate -12  # HEAD=6c5d718
git push --dry-run origin main  # Everything up-to-date, exit=0
```

### 基线验证

（待补充）

## 失败与根因

（待补充）

## 未完成内容

（待补充）

## 下一步

（待补充）

## 关键节点命令与结果（持续追加）

### 2026-08-21 23:53 基线验证

- `bash scripts/ros2.sh install`：`pixi install --locked` 成功。
- `bash scripts/ros2.sh test`：48 tests, 0 errors, 0 failures, 0 skipped。
- `bash scripts/ros2.sh run python -m pytest -q tests`：34 passed（含新增 test_script_portability.py 共 41 项）。
- `bash scripts/ros2.sh verify`：exit=0（状态 COMPLETED、轨迹与位姿收到）。
- `bash scripts/ros2.sh gazebo-verify`：exit=0（/clock 从 2000000 ns 推进到 3000000 ns，World 服务存在）。
- `bash scripts/ros2.sh drive-verify`：（进行中，修复后需 exit=0）

### 修复 rg 误报（问题一）

- 根因：`scripts/verify_gazebo_drive.sh` 三处 `ign service/topic -l | rg -Fxq ...`；Pixi 运行环境无 `rg`，功能探针成功后误报 World/Topic 缺失。
- `verify_gazebo.sh` 已使用 `grep -Fxq`，无此问题；保持不动。
- 修复：三处改为 `grep -Fxq`，断言内容不变（World 控制服务、/smartclean/odom、/smartclean/tf、进程存活检查全部保留）。
- 新增 `tests/test_script_portability.py`：
  - 全脚本禁止引用 rg/codex/gh/hub 等私有工具；
  - verify 脚本必须使用 `grep -Fxq` 精确整行匹配；
  - `bash -n` 全部脚本；
  - 用 `PATH=/usr/bin:/bin` 实际运行 grep -Fxq 断言（最小 PATH 回归）。
- 问题二：`scripts/ros2.sh` 用法提示加入正确命令示例与 `drivebash ...` 误粘贴警示；README.md 与 docs/04_quickstart.md 同步说明。

### 2026-08-22 00:05 Phase 4 提交与推送

- 提交 `1227134` `fix(scripts): make Gazebo verification portable`。
- `git fetch origin main` 无新提交；普通推送成功：`6c5d718..1227134 main -> main`。
- `git rev-parse HEAD` == `git ls-remote origin refs/heads/main` == `1227134ffb32a5652b352e2ece4d84796a39febd`。

### Phase 5 drive-gui（进行中）

- 新增 `ros2_ws/src/smartclean_gazebo/urdf/smartclean_drive.urdf`：base_footprint → base_link（z+0.25）→ 双轮/caster/camera_link/camera_optical_frame/lidar_link；纯本地几何，无 mesh、无 http。
- 新增 `ros2_ws/src/smartclean_gazebo/rviz/smartclean_drive.rviz`：Grid/TF/RobotModel//odom//scan//camera/image_raw/调试图，fixed frame=odom。
- `drive.launch.py` 新增 `gui`、`rviz` 参数（默认 false，headless 不回归）；TimerAction 延迟启动 GUI 客户端（`ign gazebo -g`）与 RViz2。
- `scripts/gazebo_drive_gui.sh`：无 DISPLAY 时输出中文提示并 exit 2；否则 launch `gui:=true rviz:=true`。
- `scripts/ros2.sh` 增加 `drive-gui`；`pixi.toml` 增加 `gazebo-drive-gui` task（不改变锁文件）。
- 验证：
  - `ros2 launch smartclean_gazebo drive.launch.py --print-description` 成功列出 server/bridge/guard/rsp/两个 TimerAction。
  - RSP+URDF 实测 TF：base_footprint→base_link→camera_link→camera_optical_frame、base_link→lidar_link；无 odom 帧。
  - 新增 9 项 GUI 契约测试，包测试 16 项全部通过。
  - `drive-gui` 无 DISPLAY：中文提示，exit=2。
  - RViz2 在 QT_QPA_PLATFORM=offscreen 下仍要求 GLX X 显示（OGRE RenderingAPIException），本会话无法做窗口级验证，如实记录。
