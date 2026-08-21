# 2026-08-21 P1 全覆盖清扫与离线动画

## 基本信息

- 时间：2026-08-21 11:39 CST
- 执行者：Codex（主代理及并行设计/研究子任务）
- 基线提交：`8cff48c`（提交信息 `0821`）
- 目标：在 P0 二维闭环上实现指定区域全覆盖、可靠逐帧轨迹和无需额外依赖的浏览器动画。

## GitHub 调研与依赖决定

实现前核验了以下上游：

- PythonRobotics `GridBasedSweepCPP` 和 `SpiralSpanningTreeCPP`（MIT）
- OpenNav Coverage（Apache-2.0）与 Fields2Cover（BSD-3-Clause）
- covplan（MIT）
- ETH polygon_coverage_planning（GPL-3.0-or-later）

最终没有复制、下载或 vendor 第三方源码。P1 参考 PythonRobotics 的扫描思路，在现有 `GridWorld + AStarPlanner` 上独立实现横向/纵向蛇形候选；重型 ROS/C++ 方案留到相应阶段评估。详细链接、许可证和拒绝理由见 `docs/05_open_source_research.md`。

动画最终采用纯标准库生成自包含 HTML/Canvas，而非新增 Matplotlib 或前端依赖。因此本里程碑不需要下载任何包；后续若需依赖，按 `envs/README.md` 在仓库内 `.venv/` 安装。

## 代码与配置变更

- `models.py`：任务新增 `clean_spots` / `clean_area` 模式。
- `grid.py`：新增显式命名区域和安全可通行区域查询。
- `planning.py`：新增横向/纵向蛇形候选与 A* 连接的 `CoveragePlanner`。
- `tasking.py`：明确“全覆盖”等中文词组进入 `clean_area`，普通清扫保持兼容。
- `simulation.py`：集成全覆盖执行；新增移动、等待、清扫、转换和终态的完整帧快照。
- `html_visualization.py`：新增无外链 HTML/Canvas 播放器，支持播放、暂停、重置、逐帧、时间轴和倍速。
- `cli.py`：新增 `--animate HTML_PATH`，可与 `--output`、`--show-map` 同时使用。
- `configs/demo.json`：增加教学楼门口显式区域，默认任务升级为全覆盖清扫。
- `results/demo_result.json`、`results/demo_animation.html`：生成可直接检查的基准产物。
- `envs/README.md`：清除基线提交中误粘贴的 heredoc 文本，改为当前环境和仓库内 `.venv/` 约定。
- 补齐覆盖规划、逐帧同步、HTML 安全、CLI 导出和默认场景集成测试。

技术文档：

- `docs/05_open_source_research.md`
- `docs/06_p1_coverage_and_animation.md`
- `docs/07_implementation_roadmap.md`

## 验证记录

```bash
python3 -m pytest -v
```

结果：34 项测试全部通过，覆盖地图、区域、A*、全覆盖、任务解析、动态重规划、逐帧同步、HTML 注入防护、CLI 和默认演示。

```bash
python3 scripts/run_demo.py \
  --show-map \
  --output results/demo_result.json \
  --animate results/demo_animation.html
```

结果：

- 状态：`COMPLETED`
- 垃圾：`4/4`
- 任务区域：`53/53`，覆盖率 `1.0`
- 路径长度：`102` 格
- 仿真步：`104`
- 动态重规划：`2` 次
- 碰撞：`0` 次
- 返航：成功
- 轨迹帧：`114`

产物：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `results/demo_result.json` | 74,573 bytes | `64211a75e24d9b3662e26163e0a19d2c7f9b8f4e9f8dc892d65fa579a773fede` |
| `results/demo_animation.html` | 62,520 bytes | `f8b8bed93cb59bc2e8e5dc4af867660a6ebd31bac8d7a9ffb63a98934d7d478e` |

再次输出到 `/tmp` 后使用 `cmp` 对比，两份 JSON 和 HTML 均完全一致，确认结果可复现。

```bash
python3 -m compileall -q src scripts tests
git diff --check
```

结果：通过。

浏览器烟雾测试尝试使用服务器 Firefox 136 无头截图。HTML 已成功加载到浏览器进程，但服务器没有可用 X/软件 framebuffer，Firefox 报 `RenderCompositorSWGL failed mapping default framebuffer`，未生成截图。因此当前已自动验证 HTML 结构、内嵌 JSON、无外链、脚本逃逸防护和确定性；最终视觉仍需在有桌面的浏览器中手动打开确认。

## Git 状态

- P0 基线在本次工作开始时已由用户/外部进程提交为 `8cff48c`。
- 向已配置的 GitHub `origin/main` 推送时被安全审查要求对具体远端和完整 payload 再次明确授权，因此没有绕过或强行上传。
- P1 已创建独立本地里程碑提交；具体 commit 以 `git log` 为准。远端推送待用户明确确认该仓库 URL 后执行。

## 下一步

按 `docs/07_implementation_roadmap.md` 进入 P2：建立至少 5 个固定场景、批量实验运行器、配置哈希和 CSV 汇总，为技术报告提供可追溯数据。
