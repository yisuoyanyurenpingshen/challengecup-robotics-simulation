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

### Phase 6 Gazebo 本地垃圾场景

- 分类收敛到 2D 核心单一来源：`smartclean_sim.models.TRASH_CLASSES`（兼容扩展 paper_cup、aluminum_can），tasking 中文别名、终端符号与 HTML 动画同步扩展，41 项核心测试不回归。
- 新增 5 个本地垃圾模型（models/trash_*）：塑料瓶(蓝/圆柱0.08×0.28)、纸杯(白/0.084×0.15)、易拉罐(红/0.066×0.13)、落叶(绿/扁圆0.26×0.016)、纸屑(白/扁盒0.14×0.11×0.012)，static、有碰撞、无 mesh/http/Fuel。
- 新增 `worlds/smartclean_trash.sdf`（同一清扫车 + 5 垃圾实例）；真值 `configs/gazebo_scene.json`（稳定 object_id、class_name、model_name、世界坐标；仅用于评估与任务编排，不作为感知输入）。
- 新增 `trash-verify`（`scripts/verify_trash_scene.sh` + `scripts/trash_scene_probe.py`）：真实启动 World，断言 control 服务与全部 6 个实体在场。
- 踩坑：`ign model --list` 行首带 `- ` 前缀，探针解析后已修正；`ign sdf -k` 无法解析 `model://` include（服务器资源路径才能解析），改为真实启动验证。
- 验证：`bash scripts/ros2.sh trash-verify` exit=0（机器人 + 5 个垃圾模型全部在场）；6 项场景契约测试通过；所有模型 `ign sdf -k` Valid。

### Phase 7 RGB 相机（已验证，渲染通路已打通）

- 已落地：`camera_link`（pose 0.45 0 0.45 0 -0.15 0）+ `camera_optical_frame` + RGB camera 传感器（640×480、10Hz、HFOV 60°、R8G8B8、topic /smartclean/camera/image + camera_info）写入 `model.sdf`；`drive.launch.py` 增加可关闭 `camera:=true` 桥接（/camera/image_raw、/camera/camera_info）；`trash-verify`、`camera-verify` 入口。
- 关键修复一（headless 回归保护）：Sensors 系统会初始化 OGRE2 渲染，无 GLX 时 `ign gazebo -s` 直接 SIGABRT(-6)。因此把基础 `config/server.config` 保持不含 Sensors，新增 `config/server_sensors.config`（仅 camera:=true 时使用）。测试 `test_server_configs_split_sensors_from_headless_baseline` 固化此不变量，drive-verify 不回归。
- 关键修复二（Xvfb GLX）：conda-forge `xorg-x11-server-xvfb-conda-x86_64` 是 cos7 构建、无 GLX 扩展（OGRE2 拒绝初始化）。改为 `scripts/fetch_xvfb.sh`：`apt-get download xvfb`（focal 2:1.20.13-1ubuntu1~20.04.20）→ `dpkg-deb -x` 提取宿主 Xvfb 到 `.tools/xvfb-bin/Xvfb`（Git 忽略目录，不修改系统）。该 Xvfb 带 GLX（`xdpyinfo | grep '^    GLX'` 确认）。宿主的 Xvfb 是双重 fork 包装，`xvfb_stop` 需进程组杀 + 按“二进制路径+显示号”pkill 补杀，防孤儿 X。
- 关键修复三（pipefail 陷阱）：`xdpyinfo | grep -q GLX` 在 `set -o pipefail` 下因 grep -q 提前退出触发 SIGPIPE 被误判失败；改为先捕获完整输出再 `grep -q ... <<<`。
- 关键修复四（QoS）：`/tf_static` 必须用 TRANSIENT_LOCAL durable QoS 订阅，volatile 拿不到 RSP 静态 TF。
- 关键修复五（假渲染防御）：camera_probe 不止比对帧首部 4096 字节，还让车经 /cmd_vel→watchdog→DiffDrive 原地旋转 4 秒（0.6 rad/s），断言整帧数据变化——证明相机真实渲染世界而非静态帧。
- 验证结果（全部 exit=0）：
  - `bash scripts/ros2.sh camera-verify`：PASS。图像 640×480 rgb8、平均像素约 196/255、17+ 帧时间戳推进、原地旋转画面变化、CameraInfo fx≈554.3、TF base_footprint→camera_optical_frame 连通、动态 /tf 仍含 odom→base_link。
  - `bash scripts/ros2.sh test`：65 tests 通过（新增 5 项相机契约测试）。
  - `bash scripts/ros2.sh run python -m pytest -q tests`：41 passed。
  - `bash scripts/ros2.sh verify` / `gazebo-verify` / `drive-verify` / `trash-verify`：exit=0。
- 踩坑补充：`ign topic -l` 输出在 setsid launch 下正常；`ign topic -p --req` 必须与 `--timeout` 同时给出。
- 视觉标定（后续感知用）：实测相机画面为上下镜像（垂直翻转）。用 5 个紫色标记柱（0.12×0.12×0.7、z=0.35，hue 140-160）验证像素↔世界映射：把行坐标 y 映射为 480-y 后与 trash 世界坐标吻合。不修改 SDF/CameraInfo（fx=554.3 已标定），感知侧统一做一次 `flip(image, 0)` 修正，并如实记录为“Gazebo 渲染特性”。
- 中断实验记录：删除 trash_plastic_bottle 后验证蓝色 blob 消失的因果实验在 launch 完成后被会话截断（进程已清理，结果未取得）；相机真实性已由原地旋转帧变化证明，后续 Phase 8 空场景测试会重新覆盖该因果链。
