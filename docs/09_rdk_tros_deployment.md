# RDK X5/X3 与 TROS-Humble 部署设计

## 1. 部署基线

本项目的板端主目标是 **RDK X5**，兼容目标是 **RDK X3**。统一基线为：

- RDK OS 3.x；
- Ubuntu 22.04；
- TROS/ROS2 Humble；
- PC 与板端使用 `ROS_DOMAIN_ID=42`；
- PC 和 RDK 位于可互通的同一局域网。

D-Robotics 官方资料表明，RDK X5/X5 Module 运行 Ubuntu 22.04（Humble）；RDK X3/X3 Module 同时存在 Ubuntu 20.04（Foxy）和 Ubuntu 22.04（Humble）路线。因此 X3 只有升级到 RDK OS 3.x/Humble 后才属于本项目兼容范围。旧 X3 OS 2.x/Foxy 不能仅靠 `apt upgrade` 变成 Humble，应按官方流程重新烧录对应系统镜像。

截至 2026-08-21，本文是部署设计和验收口径：项目尚未在真实 X5/X3 上完成编译、DDS 跨机通信、BPU 推理、温度或性能实测。

## 2. PC 与 RDK 分工

```text
PC（Jammy/Humble）                         RDK X5/X3（OS 3.x/TROS-Humble）
┌────────────────────────┐                ┌──────────────────────────┐
│ 二维核心 / Gazebo       │                │ MIPI/USB 相机与板端驱动   │
│ 场景、任务与回放        │   ROS2/DDS     │ BPU 模型推理与后处理      │
│ 规划、Nav2、可视化      │◄──────────────►│ Detection / 健康状态发布  │
│ 指标、日志与答辩演示    │                │ 可选底盘与传感器接入       │
└────────────────────────┘                └──────────────────────────┘
```

分工原则：

- PC 承担高负载仿真、全局规划、指标统计、可视化和快速迭代。
- RDK 承担摄像头采集、BPU 推理、硬件相关预处理/后处理，以及后续真实传感器接入。
- 板端只发布标准化检测和健康信息，不直接绕过安全控制器输出底盘速度。
- 规划和任务语义仍属于平台无关核心；RDK 专有 SDK、模型文件和 BPU 内存管理只能出现在适配层。
- 当前 `smartclean_ros` 只是 PC 端结果回放桥，并不是已经部署到 RDK 的感知或底盘节点。

## 3. 板端准备

### 3.1 版本检查

拿到板卡后，先保存以下命令的输出到硬件验证日志：

```bash
cat /etc/version
cat /etc/os-release
cat /proc/device-tree/model
uname -m
```

验收条件是 OS 3.x、Ubuntu 22.04、`aarch64`，且板型与记录一致。不要只根据购买页面或包装判断板型和镜像版本。

### 3.2 激活 TROS

在 OS 3.x/Humble 板端使用：

```bash
source /opt/tros/humble/setup.bash
export ROS_DOMAIN_ID=42
ros2 doctor --report
```

每个终端只 source 一套 ROS 环境。不要在同一终端同时 source `/opt/tros/humble/setup.bash`、`/opt/ros/humble/setup.bash` 或其他 Foxy/Humble 环境，否则包前缀、Python 路径和动态库可能混用。

### 3.3 编译与传输

PC 是 `amd64`，RDK 是 `arm64`。x86 编译出来的二进制不能直接复制到 RDK 运行。建议按风险从低到高采用：

1. Python 业务包与源码复制到板端，在已激活的 TROS-Humble 环境中执行 `colcon build`；
2. 资源不足时，使用 D-Robotics 官方 `robot_dev_config` Docker 交叉编译环境，并严格匹配 X5/X3、OS 和 TROS 版本；
3. 只有确需修改 TROS 官方包时才构建整套 TROS 源码。

`smartclean_core` 已把仓库中的 `smartclean_sim` Python 核心正式安装到 ROS 前缀，`smartclean_ros` 也声明了对应运行依赖；清空开发用 `PYTHONPATH` 后的导入与 demo 配置加载已经在 PC 验证。板端构建仍必须传输完整仓库，因为该包装包从根目录源码生成安装内容；不能把 PC 的 `amd64` install 空间直接复制到 `arm64` RDK。板端 `colcon build` 成功后再 source 该板本机生成的 install 空间。

## 4. DDS 网络约定

PC 与 RDK 的最低通信条件：

- 位于同一可路由局域网，能够双向 `ping`；
- 两端均设置 `ROS_DOMAIN_ID=42`；
- 两端 ROS2 发行版均为 Humble；
- 防火墙、无线 AP 客户端隔离和 VLAN 不阻断 DDS 发现与 UDP 流量；
- 对同一 Topic 使用相容的消息类型和 QoS；
- 记录实际 RMW 实现与版本，跨机异常时先统一 RMW 再排查业务代码。

建议的首次跨机探针：

```bash
# PC：先启动现有回放桥
./scripts/ros2.sh demo loop_replay:=true

# RDK：在另一个终端检查发现与消息
source /opt/tros/humble/setup.bash
export ROS_DOMAIN_ID=42
ros2 node list
ros2 topic echo /smartclean/status std_msgs/msg/String --once \
  --qos-reliability reliable \
  --qos-durability transient_local
ros2 topic echo /smartclean/trajectory nav_msgs/msg/Path --once \
  --qos-reliability reliable \
  --qos-durability transient_local
ros2 topic echo /smartclean/robot_pose geometry_msgs/msg/PoseStamped --once \
  --qos-reliability reliable --qos-durability transient_local
```

如果跨机发现失败，按“IP 双向可达 → domain 是否一致 → RMW 是否一致 → 防火墙/组播 → QoS/类型”顺序排查，不先修改业务节点。

## 5. 接口演进

当前 PC 回放桥已经提供：

| Topic | 类型 | RDK 当前用途 |
| --- | --- | --- |
| `/smartclean/status` | `std_msgs/msg/String`（JSON） | 验证跨机发现与状态订阅 |
| `/smartclean/trajectory` | `nav_msgs/msg/Path` | 验证米制 `map` 轨迹传输 |
| `/smartclean/robot_pose` | `geometry_msgs/msg/PoseStamped` | 验证逐帧位置回放 |

RDK 感知接入时新增的稳定契约应至少包含：检测 ID、仿真/采集时间、类别、置信度、像素框、地图位置是否有效、推理来源和模型版本。没有标定、深度或可靠 TF 时必须设置 `position_valid=false`，禁止根据二维图像框伪造地图坐标。

板端图像优先采用相机驱动提供的标准消息，检测结果迁移到版本化 `smartclean_interfaces/msg/DetectionArray`。大图像不嵌入 JSON 状态；任务、检测、状态和底盘控制应分离为不同 Topic/Action。

## 6. 实机验收清单

只有全部留下机器可读结果和工程日志，才能声称相应能力“板端已验证”：

1. 记录板型、OS、TROS、内核、RMW 和包版本。
2. PC 与 RDK 双向网络可达，并在 domain 42 中互相发现节点。
3. 现有三条回放 Topic 跨机探针成功，消息类型、`frame_id` 和 QoS 符合契约。
4. 固定图片在 PC 浮点模型与 RDK BPU 模型上分别推理，记录类别、框、置信度误差。
5. 相机连续采集与 BPU 推理不少于约定时长，记录 FPS、端到端时延、CPU、内存、BPU 占用和温度。
6. 断网、节点退出、感知故障和过期消息不能导致非零危险速度命令。
7. 如接底盘，单独完成 `/cmd_vel` 限速、超时归零、急停和人工接管测试。

目前上述项目均待真实硬件验证；PC 端 ROS Topic 探针不能替代板端或实车测试。

## 7. 主要风险

| 风险 | 后果 | 控制措施 |
| --- | --- | --- |
| X3 仍是 OS 2.x/Foxy | 无法与项目 Humble 基线直接复用 | 烧录 OS 3.x；禁止混合发行版临时拼接 |
| x86/arm64 混淆 | 二进制无法运行或 ABI 错误 | 板端原生构建或使用匹配版本的官方交叉编译环境 |
| TROS 与标准 ROS 混用 | Python、动态库和包索引冲突 | 每终端只 source 一套环境并记录前缀 |
| 无线网络阻断 DDS 发现 | Topic 列表为空或偶发丢失 | 固定 domain/RMW，检查组播、AP 隔离和防火墙 |
| QoS 不相容 | 已发现 Topic 但收不到数据 | 接口文档固定可靠性、持久性和深度，加入探针测试 |
| 图像和点云带宽过高 | 延迟、抖动和丢帧 | 板端推理，只上传检测；需要图像时限帧率与压缩 |
| BPU 量化精度下降 | 漏检或误检影响规划 | 固定数据集做 PC/板端对照并设验收容差 |
| 长时间推理过热降频 | FPS 不稳定 | 散热、性能模式和温度监控纳入实测 |

## 8. 官方依据

以下资料访问于 2026-08-21：

- [D-Robotics：TROS 数据通信与支持平台](https://developer.d-robotics.cc/tros_doc/en/quick_demo/demo_communication)
- [D-Robotics：RDK X3/X5 TROS/ROS 开发 FAQ](https://developer.d-robotics.cc/rdk_x_doc/FAQ/tros_ros)
- [D-Robotics：TROS 环境准备](https://developer.d-robotics.cc/rdk_doc/en/Robot_development/quick_start/preparation/)
- [D-Robotics：TROS 源码与交叉编译](https://developer.d-robotics.cc/tros_doc/en/Quick_start/cross_compile)
- [D-Robotics：RDK X 系列发布记录](https://developer.d-robotics.cc/rdk_x_doc/en/Release_Note/release_note)
