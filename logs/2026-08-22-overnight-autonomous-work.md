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
- 视觉标定（后续感知用）：最终结论为**画面不需要翻转**。用 5 个紫色标记柱（0.12×0.12×0.7、z=0.35，hue 140-160）拟合出相机俯仰 θ=+0.148 rad（向下 8.5°，SDF roll/pitch 语义与先前假设相反），标准针孔映射（fx≈554.3、cx=320、cy=240）下 4 个已渲染 blob 拟合 RMS<2px；感知侧 `flip_vertical=False`。此处推翻本行更早草稿中的“垂直翻转”结论。
- 中断实验记录：删除 trash_plastic_bottle 后验证蓝色 blob 消失的因果实验在 launch 完成后被会话截断（进程已清理，结果未取得）；相机真实性已由原地旋转帧变化证明，后续 Phase 8 空场景测试会重新覆盖该因果链。

### 2026-08-22 02:0x Phase 7 提交与推送

- 提交 `7d7fe2b` `feat(gazebo): add verified RGB camera bridge and headless Xvfb rendering`（13 文件，+780/-14）。
- 提交前全量回归：install/test(65)/pytest(41)/verify/gazebo-verify/drive-verify/camera-verify/trash-verify 全部 exit=0；`git diff --check`、`bash -n scripts/*.sh`、`py_compile` 全过；无残留 Gazebo/Xvfb 进程。
- 普通推送成功：`06b5283..7d7fe2b main -> main`。
- `git rev-parse HEAD` == `git ls-remote origin refs/heads/main` == `7d7fe2bdd7a9c1960501f99a2ebc5d5c79d0e6aa`。

### 2026-08-22 Phase 8 图像垃圾识别（进行中 → 验证通过）

- 环境修复（识别包前置）：
  - `pixi.toml` 增加 `empy = "3.*"`（旧 empy 4.2.1 破坏 rosidl `em.BUFFERED_OPT`）与 `ros-humble-rosidl-generator-py`；`pixi.lock` 重新生成。
  - `scripts/ros2_build.sh` 增加 `-DPYTHON_EXECUTABLE=${CONDA_PREFIX}/bin/python3`（宿主 /usr/bin/python3.6 导致 cpython-36m typesupport + generate_py ModuleNotFound）。
  - 必须清除旧 `ros2_ws/build/smartclean_interfaces` 与 `install/smartclean_interfaces` 后重建，cpython-312 typesupport 生成后可用；`ros2 interface show` 与 Python bindings 复验通过。
- 相机几何修正：拟合解 pitch θ=+0.148 rad（相机向下 8.5°），不翻转，标准针孔映射（fx≈554.3），4 个渲染 blob RMS<2px。
- 场景可识别性修复：落叶改为 r=0.15/高0.06 圆堆（cylinder+两片 visual）、纸屑改为 r=0.06 球（crumpled ball）；太阳方向改到 `0.45 0.25 -0.86` 照到垃圾面向相机一侧，新增 `camera_fill` 补光（diffuse 0.30），ambient 0.35→0.42；5 垃圾位置 bottle(2.4,0)、cup(3.2,-1.1)、can(3.2,1.1)、leaves(2.9,-0.55)、scrap(3.9,0.75)，`configs/gazebo_scene.json` 同步；`test_trash_scene_contract.py` 增加 sphere 几何 span 解析。
- 真实渲染帧 `/tmp/cap4_frame.png`：5 个对象全部可检测（bottle/can/leaves/cup/scrap），地面 V≈156-170、天空 V≈243；horizon_row=360 屏蔽天空假阳性。
- 新增 `smartclean_interfaces`：`TrashDetection.msg`（schema_version/detection_id/class_name/confidence/bbox_xyxy[4]/image_stamp/source/position_valid/position[3]/position_frame_id/area_px）与 `TrashDetectionArray.msg`（Header+数组+processing_ms/fps）。
- 新增 `smartclean_perception`（ament_python）：
  - `detector_core.py`：DetectorConfig（horizon_row=360、min_area=50、flip_vertical=False、HSV 阈值）+ HSV 颜色/形状/面积评分 + IoU 去重 + annotate；置信度=0.55·颜色+0.25·形状+0.20·尺寸；自称「合成Gazebo场景图像识别基线」，不冒充通用识别。
  - `trash_detector_node.py`：订阅 /camera/image_raw（best_effort），发布 /smartclean/detections 与 /smartclean/debug/detection_image（有订阅者才发调试图）；source=smartclean_perception.color_baseline。
  - `synthetic_dataset.py`：确定性合成图生成（5 类 + all_five + empty，天空/地面 HSV 与真实渲染相符）+ evaluate()（GT 仅用于评估）。
  - `launch/perception.launch.py`：Include drive.launch.py（gui/rviz=false）+ detector 节点。
  - `onnx_adapter.py`：可插拔 ONNX 适配器（letterbox、NMS、类别映射、coords_normalized 反归一化），`_FakeSession` 单测不依赖真实权重。
  - 测试 28 项（detector_core 9 + synthetic_eval 3 + node_contract 5 + onnx_adapter 11）全部通过。
- 端到端验证 `bash scripts/ros2.sh perception-verify`（`scripts/verify_perception.sh` + `scripts/perception_probe.py`）：
  - Phase A（smartclean_trash）：真实渲染帧识别到全部 5 类垃圾，bbox/类别/置信度合法，调试图有标注，检测消息非空。
  - Phase B（smartclean_empty.sdf，去垃圾副本）：连续 5 条检测消息全部为空（无虚假检测）。
  - exit=0；日志 `/tmp/p8_pverify2.log`。probe 静态断言 detector/node 不读 Gazebo 真值（gazebo_scene/configs/model:///subprocess/ign 等禁止符）；真值仅用于 Phase A 校验“检测类别∈场景类别”。
- 合成评估（build_scenes() 21 图）：overall P=1.0、R=1.0、FP=0、FN=0；CPU 单帧 mean 2.848ms、p95 2.924ms、FPS≈351。
- ONNX 权重调研（第一轮）：未找到同时满足「明确宽松许可证 + 5 类兼容 + 原始地址」的轻量垃圾 ONNX 权重（AGPL copyleft / 类别不兼容 / 未注明许可），本轮不下载、不装 onnxruntime。落地：`weights/model-card-template.json`、`scripts/download_onnx_model.sh`（幂等下载+SHA-256 校验）、`weights/README.md` 流程说明、`.gitignore` 放行模型卡模板。ONNX 权重绝不进 Git。
- 提交与推送：`feat(perception): add image-based trash detector`（哈希见下方「提交记录」）。
- 全量回归（提交前）：install / test（65+28 项新增）/ pytest tests（41）/ verify / gazebo-verify / drive-verify / camera-verify / trash-verify / perception-verify 全部 exit=0；`git diff --check`、`bash -n`、`py_compile` 通过；无残留 ign/Xvfb/bridge 进程。

## 提交记录（2026-08-22）

- `1227134` fix(scripts): make Gazebo verification portable —— 已推送，本地==origin==GitHub。
- `d342ad2` feat(gui): add Gazebo and RViz drive view —— 已推送。
- `06b5283` feat(gazebo): add local trash scene —— 已推送。
- `7d7fe2b` feat(gazebo): add verified RGB camera bridge and headless Xvfb rendering —— 已推送。
- `dfa3b29` feat(perception): add image-based trash detector —— 已推送。

### 2026-08-22 Phase 9 垃圾位置估计（深度反投影，验证通过）

- 方案：RGB-D 对齐深度反投影（第一优先方案）。相机传感器改为单个 `rgbd_camera`
  （RGB 640×480 10Hz + depth 640×480 10Hz，同一光心/内参，depth clip 0.05–20 m）。
- 关键踩坑一：先尝试的「独立 depth_camera 传感器」曾因编辑脚本把传感器误嵌套进
  RGB 传感器导致被 Gazebo 静默忽略（无任何报错）；已修复并新增契约测试
  `test_sdf_declares_single_rgbd_sensor` 防止传感器嵌套回归。
- 关键踩坑二（Gazebo Fortress 6.16 实测行为）：`depth_camera`/`rgbd_camera` 的
  CameraInfo 焦距错误（k=277，真值应为 554.26，即少乘 2），且独立双相机时两个
  CameraInfo 会交错发布到同一 topic。结论：用单一 rgbd_camera + 由分辨率与 HFOV
  解析计算内参（`CameraIntrinsics.from_hfov`，fx=(w/2)/tan(30°)=554.26），不信任
  该版本 CameraInfo 的焦距字段；probe 显式记录该 quirk（270<k<285）。
- 桥接新增 `/camera/depth/image_rect_raw`（gz Image→sensor_msgs/Image，32FC1）
  ；depth 与 RGB 同一光学帧、像素级对齐，故为 image_rect_raw。
- `position_estimator.py`：depth_to_meters（16UC1 mm/32FC1 m）、patch_median_depth
  （忽略 0/NaN/Inf，图像边缘裁剪）、backproject_optical（fx≤0 拒绝）、
  transform_point（xyzw 四元数旋转+平移）、estimate_position（全管线，transform
  缺失/结果非有限时返回 None）。`TrashDetection.position_valid=false` 覆盖所有
  不可靠路径。
- 节点集成：订阅深度 + TF（先 map 后 odom，`position_frame_ids=["map","odom"]`），
  帧差 >0.5s 不用旧深度；`camera_hfov_deg=60.0` 参数化；use_depth 可关。
- 单元测试 15 项：正常深度/零深度/NaN/Inf/图像边缘/内参非法/TF 缺失/坐标变换/
  位置误差（纯数学 <0.01m）/非有限结果/配置默认值。
- E2E `bash scripts/ros2.sh position-verify`（`scripts/verify_position.sh` +
  `scripts/position_probe.py`）exit=0：
  - 深度 640×480 32FC1、时间戳推进、有效测距占比合格；
  - CameraInfo 到场且符合 6.16 已知行为；
  - camera_optical_frame→odom TF 连通；
  - 最佳估计 aluminum_can (3.17,1.09) vs 真值 (3.2,1.1)：误差 0.032 m < 0.45 m；
  - 静态断言估计器/节点不含任何真值读取路径；真值仅用于误差评估。
- 回归：build/test 109 项、pytest 41、verify/gazebo-verify/drive-verify/
  camera-verify/trash-verify/perception-verify/position-verify 全部 exit=0。
- 提交与推送：`feat(perception): add depth-based trash position estimation`
  （哈希见下方提交记录）。

---

## Phase 10：LiDAR 与完整 TF（2026-08-22 09:20–09:50 CST）

### 目标
- 2D LiDAR `/scan`（sensor_msgs/LaserScan，360 样本，10Hz，0.1–12m）；
- TF 链：map → odom → base_footprint → base_link → lidar_link / camera_link → camera_optical_frame；
- 新增 `bash scripts/ros2.sh lidar-verify` 全自动验收；原 `/cmd_vel`、`/odom`、看门狗不回归。

### 关键设计决策（实测驱动）
- **传感器类型必须 `gpu_lidar`**：conda ignition-sensors 6.6.3 对 `type="lidar"`
  直接报 “Sensor type LIDAR not supported yet. Try using a GPU LIDAR”。
  已实测 `gpu_lidar` 正常发布 `/smartclean/lidar/scan`（360 样本）。
- **DiffDrive child_frame_id 改为 `base_footprint`**：新增 ground-level 空 link
  `base_footprint`（fixed joint，base_link 抬高 +0.25）；DiffDrive 发布
  odom→base_footprint（经 `/smartclean/tf` 桥），robot_state_publisher 只发布
  base_footprint 以下。单一 TF 单一发布者，map→odom 留给 AMCL（Phase 11）。
- **`scan_frame_republisher` 新节点**：Gazebo Fortress 传感器帧带作用域
  `smartclean_robot/lidar_link/lidar`，与 TF 树 `lidar_link` 不一致。
  smartclean_ros 新增节点：`/scan_raw` → `/scan` 并改写 frame_id=lidar_link，
  避免 Nav2/AMCL/RViz 查帧失败。逻辑抽成纯函数 `remap_frame_id()`。
- lidar_link 位于 base_link 前上 (0.05, 0, +0.47)；URDF 镜像同步（joint z=+0.22）。

### 新增/修改文件
- `models/smartclean_robot/model.sdf`：base_footprint link（含 0.02m 极小 collision，
  满足「所有 link 必须有 collision」契约）+ lidar_joint/lidar_link + gpu_lidar；
- `launch/drive.launch.py`：`lidar:=true` 参数、lidar_bridge、scan_frame_republisher；
- `smartclean_ros/scan_frame_republisher_node.py` + setup.py 入口 + 3 条单测
  （纯函数 + 真实 rclpy 往返：frame 被改写、其余字段不变）；
- `scripts/verify_lidar.sh` + `scripts/lidar_probe.py`：/scan 360 样本、角度/距离
  参数、有限测距、时间戳推进、odom→lidar_link TF、旋转后 ranges 变化≥5 个 >0.02m、
  看门狗/RSP 存活；
- 契约测试：`test_lidar_contract.py`、`test_model_contract.py`（child=base_footprint、
  gpu_lidar、每 link 有 collision）、`test_camera_contract.py`、`test_gui_contract.py`
  同步更新；
- `scripts/gazebo_drive_probe.py`、`scripts/camera_probe.py`：TF 断言改为
  odom→base_footprint（与 DiffDrive 新 child 一致）；
- `scripts/ros2.sh` + `pixi.toml`：注册 `lidar-verify`。

### 验证结果（全部 exit=0）
- `bash scripts/ros2.sh lidar-verify`：`[lidar-probe] PASS`；
- `bash scripts/ros2.sh test`：先失败 1 条（base_footprint 无 collision），补
  极小 collision 后修复；全包通过（smartclean_gazebo 8/8 等）；
- `drive-verify`：forward=0.589m、turn=0.971rad、stop_drift=0.000m、
  TF=odom->base_footprint、watchdog=passed；
- `camera-verify`、`trash-verify`、`perception-verify`、`position-verify`、
  `verify`、`gazebo-verify`、`sim-test`：全部 exit=0；
- `ign sdf -k` Valid；`git diff --check` 干净；无残留 Gazebo/Xvfb/桥进程。

### 提交
- `feat(gazebo): add lidar and complete robot tf` -> `054c5148f0b19c9c6714dea5c50999c0ae38a377`（本地==origin/main==GitHub）。

---

## Phase 11：Nav2 最小自主导航（2026-08-22 09:50–10:20 CST）

### 目标
- 与 Gazebo World 坐标一致的静态地图 + map_server + AMCL + Nav2 全家桶；
- `bash scripts/ros2.sh nav2`（可 `gui:=true rviz:=true`）与 `bash scripts/ros2.sh nav2-verify`；
- 验证真实移动、Nav2 来源的 `/cmd_vel`、/plan、到达误差、停车与子进程清理。

### 设计
- **静态地图** `maps/smartclean_arena.{pgm,yaml}`：20×16 m 全场、0.05 m/px（400×320），
  origin=(-10,-8)（map 帧=世界帧，机器人起点即 map (0,0)）；静态障碍（north_planter
  圆柱 r0.8、waste_bin 0.75×0.75）与 World 一致，各加 0.08 m 裕量；垃圾不写入静态
  地图（由 LiDAR 运行时观测）；边缘画 2 像素边界防驶出。由 `scripts/generate_nav2_map.py`
  确定性生成（numpy，无 PIL/Fuel 依赖）。
- **AMCL**：`set_initial_pose` + `initial_pose=(0,0,0)`（实测该 Humble 版
  libamcl_core 支持 `initial_pose.x/y/z/yaw`）；map→odom 由 AMCL 提供，Gazebo
  DiffDrive 与 RSP 职责不变。
- **nav2.launch.py**：Include drive.launch（trash world、lidar:=true、看门狗
  timeout 放宽到 1.0s）+ nav2_bringup localization/navigation（use_sim_time:=true、
  autostart:=true、use_composition:=False）。
- **params** `config/nav2_params.yaml`：基于 Humble 官方样例，footprint
  [±0.45,±0.31]、xy_goal_tolerance 0.25、max_vel_x 0.26、acc_lim 匹配
  DiffDrive 0.8/1.5/2.0 上限、laser_max_range 12。
- **探针** `scripts/nav2_probe.py`：/scan(360、lidar_link)→/odom→完整 TF→/map→
  AMCL map→odom（20s 无则发一次 /initialpose 兜底）→action 就绪→双目标
  (1.5,2.5)、(-2.5,1.0)→每目标断言 /plan、/odom 位移>0.2m、/cmd_vel 发布者为
  velocity_smoother/controller_server、到达误差<0.40m→最终 1.5s 停车
  （位移<0.03m、速度<0.02m/s）。探针从不发布 /cmd_vel。

### 关键踩坑（均已修复并留契约）
1. 地图 `mode: trinary` 下 free 像素必须是 254（205 被解析为 unknown→全图无
   自由空间，planner 无法规划）；已改生成器并断言 PGM 值域 {0,254}。
2. AMCL `initial_pose` 是 map 帧坐标（=世界坐标），不是像素坐标；错误地设为
   (10,8) 导致机器人被判定在 map 边界外。
3. nav2_bringup 的 `PythonExpression(['not ', use_composition])` 会 eval
   `'not false'` 报 NameError——`use_composition` 必须传 Python 字面量 `"False"`。
4. ROS_DOMAIN_ID 上限 232，verify 脚本 domain 基数调为 30+pid%100。
5. 该 rclpy 无 `Subscription.get_publishers_info()`，改用
   `Node.get_publishers_info_by_topic()`。

### 验证结果
- `bash scripts/ros2.sh nav2-verify` exit=0：
  - 目标 1 (1.5,2.5)：/plan=True、/odom 移动、max_speed=0.260 m/s、
    cmd_vel 来源=['velocity_smoother']、到达误差 0.223 m；
  - 目标 2 (-2.5,1.0)：到达误差 0.224 m；
  - 最终停车：1.5s 位移 0.0000 m、速度 0.000 m/s。
- 新增 5 条 nav2 契约测试；CMakeLists 补注册 camera/lidar/nav2 契约（此前
  camera/lidar 契约文件未被 colcon 运行）。

### 第二轮排查：TF“jump back in time”风暴 + 热启动目标被拒（2026-08-22 10:20–11:20 CST）
第一版 nav2-verify 曾通过，随后发现两类不稳定问题，全部修复：

**问题 A：/clock 乱序导致 tf2 报 `Detected jump back in time`，AMCL/planner 失效**
- 根因：`parameter_bridge` 的 Ignition 订阅回调由传输线程池分发，高频率
  `/clock` 转发可能乱序；任何 use_sim_time 消费者（tf2、AMCL、Nav2）都假设节点
  时钟单调。
- 修复：新增 `smartclean_ros/smartclean_ros/clock_monotonic_relay_node.py`
  （console script `smartclean_clock_relay`）：订阅 `/clock_raw`（桥改名），丢弃
  倒退时间戳，只发布严格单调的 `/clock`。drive.launch 中桥的 `/clock` 重映射为
  `/clock_raw`，中继成为唯一 `/clock` 发布者。
- 守卫：`nav2_probe.py` 全程计数 `/clock` 倒退并断言为 0；
  `verify_nav2.sh` 对 launch.log `grep "Detected jump back"` 发现即失败。
- 结果：nav2-verify 中 /clock 56063 条消息零倒退（末值 56.064s）；实测本机
  中继丢弃数=0，属于防御性保障。

**问题 B：热启动下目标被 Nav2 拒绝（action server 在 CONFIGURING 阶段即可见）**
- 根因：Nav2 生命周期管理器激活前 action server 已可见，此时发目标会被拒；
  冷启动时探针前置检查耗时足够掩盖竞态，热启动（~15s 就绪）暴露。
- 修复：`nav2_probe.py` 新增 lifecycle 门控——轮询 planner_server /
  controller_server / bt_navigator 的 `get_state` 服务直到
  PRIMARY_STATE_ACTIVE(3) 才发送目标。

**附带修复 1：底盘悬空（车轮空转，实体不动）**
- 根因：`model.sdf` 给 base_footprint 的 0.02m 碰撞盒在 z=0 接触地面，把整车
  抬高约 0.005m，四轮悬空；/odom 由轮速积分仍更新，但 Gazebo 真值不动。
- 修复：footprint_collision 移到 `<pose>0 0 0.25 0 0 0</pose>`（与 base_link
  重叠，self_collide=false）。
- 证据：/world/smartclean_trash/dynamic_pose/info 旋转 4s 后真值 (0.188,-0.099)。

**附带修复 2：`verify_ros2.sh` 孤儿 bridge + 管道卡死**
- 根因：`ros2 run` 包装器是独立进程，SIGTERM 不会可靠转发给真正的 bridge；
  rclpy 的 SIGTERM 处理器也不唤醒阻塞中的 DDS wait set，残留进程持有管道写端，
  使 `| tail` 永不 EOF。
- 修复：直接执行 `install/.../smartclean_bridge` console script；cleanup 改为
  SIGINT→SIGTERM→SIGKILL 阶梯；bridge_node.py 捕获 ExternalShutdownException
  消除退出 traceback。验证后 exit=0 且无残留进程。

**附带修复 3：探针退出竞态**
- `nav2_probe.py` 原先让 TransformListener 使用探针节点 + spin_thread，退出时
  action client 与 TF 执行器 wait set 竞态导致 RCLError/`terminate called`。
- 修复：TF listener 使用独立节点 + 自管 SingleThreadedExecutor 线程，
  teardown 时 shutdown 后 join，输出干净、exit=0。

### 最终验证（全部 exit=0，改动后重跑）
- `install` / `test`（137 项，0 失败）/ `verify` / `gazebo-verify` /
  `drive-verify` / `python -m pytest -q tests`（41 项）/ `camera-verify` /
  `perception-verify` / `lidar-verify` / `nav2-verify`。
- nav2-verify 末轮：目标 1 到达误差 0.155–0.172 m、目标 2 误差 0.155–0.166 m、
  停车 0.0000 m、/clock 单调 PASS、Nav2 lifecycle 全部 ACTIVE、无 jump-back、
  无残留进程。

### 提交
- `fix(gazebo): keep wheels grounded with raised footprint collision`
- `feat(nav2): add verified navigation loop`
- `docs(log): record nav2 commit hash`（哈希见文末提交记录）。

---

## 文末提交记录（Phase 11 收尾，2026-08-22）

| 提交 | 内容 |
|---|---|
| `5ce5cb9` | fix(gazebo): 底盘悬空（footprint 碰撞盒移入车体） |
| `5d58976` | feat(nav2): 验证过的导航闭环（含单调时钟中继与 lifecycle 门控） |
| `415ec18` | docs(nav2): 地图生成器坐标注释修正 |

交接文档（给下一位 Codex 代理）：`logs/2026-08-22-handoff-to-next-agent.md`。
Phase 12 trash-mission 与 Phase 13 未开始，详见交接文档 §6/§7。
