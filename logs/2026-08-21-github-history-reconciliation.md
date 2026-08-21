# 2026-08-21 GitHub 历史衔接与仓库内日志修正

## 基本信息

- 时间：2026-08-21 22:08 CST
- 执行者：Codex
- GitHub 仓库：`yisuoyanyurenpingshen/challengecup-robotics-simulation`
- 本地衔接前提交：`60ef18cad405ca89bb1e1d247ccac71ba0e6644f`
- 远端衔接前提交：`5cef22ceb159833fef4c1bdd26421262ed762f98`
- 目标：在不强制推送、不覆盖远端文件的前提下，把本地完整工程上传到用户指定的 GitHub 仓库。

## GitHub 登录与工具

- 系统没有预装 GitHub CLI，因此从 GitHub 官方 Release 下载 `gh 2.98.0` 到 Git 已忽略的 `.tools/`。
- 下载归档使用同版本官方 checksums 文件完成 SHA-256 校验，校验结果为成功。
- 使用 GitHub 官方设备码流程登录账号；日志不记录一次性代码、Token、密码或凭据内容。
- 凭据位于 Git 已忽略的 `.tools/gh-config/`，没有写入提交，也没有修改全局 Git credential helper。

## 历史冲突与处理决策

首次普通 `git push origin main` 被 GitHub 拒绝，因为远端已有提交。抓取后确认：

- 远端有 10 个仅远端提交，本地有 5 个仅本地提交；两条历史没有共同祖先。
- 远端当前树只有 11 个初始化文件；这些路径在本地当前树中全部存在。
- `datasets/README.md` 和 `weights/README.md` 与远端一致，其余公共 README、`.gitignore` 和 Git 搭建记录均已在本地继续扩展。
- 没有执行 `--force`、`--force-with-lease`、reset 或删除远端分支。

采用以下方式建立双亲合并节点：

```bash
git merge --no-commit --strategy=ours --allow-unrelated-histories origin/main
```

这里的 `ours` 只用于选择合并提交的文件树，不会删除远端提交历史。合并前本地树哈希和待提交合并索引树哈希均为：

```text
af7242284cfa159acf8f75290fc9a457cbb1cd3e
```

因此远端旧文件没有覆盖当前工程，同时远端 10 个旧提交仍会成为合并提交的第二父链，可继续追溯。

## 验证中发现并修正的问题

受限沙箱内首次运行 Gazebo 时，Ignition Common 尝试把默认控制台日志写到用户目录 `~/.ignition/`，因此启动失败。已在 `pixi.toml` 的激活环境中增加：

```text
IGN_LOG_PATH=$PIXI_PROJECT_ROOT/.gazebo/ignition
```

并同步更新 `docs/08_ros2_environment_and_bridge.md`。现在 ROS 日志、Gazebo 默认日志和显式录制都位于仓库内的 Git 忽略目录。

宿主环境没有全局 `pytest`；直接运行 `.tools/bin/pixi` 也不会自动继承项目脚本设置的仓库内缓存变量。最终验证统一使用 `scripts/ros2.sh` 入口，避免依赖用户级 Python、Pixi 配置或缓存目录。

## 验证结果

```bash
bash scripts/ros2.sh install
```

结果：`pixi install --locked` 成功，manifest 与 `pixi.lock` 一致。

```bash
.tools/bin/pixi run sim-test
```

结果：二维核心 34 项测试全部通过。

```bash
bash scripts/ros2.sh verify
```

结果：ROS 2 Topic 端到端验证通过，`status=COMPLETED`、`path_poses=103`、`coverage=1.0`、`collisions=0`。

```bash
bash scripts/ros2.sh gazebo-verify
```

结果：Gazebo Fortress `/clock` 从 `2000000 ns` 推进到 `3000000 ns`，`/world/smartclean_smoke/control` 存在，Gazebo server 与 bridge 均干净退出。

## 安全边界与后续

- 最终推送只允许普通快进更新；如果远端在验证期间再次变化，应重新 fetch 和比较，禁止自动强推。
- `.tools/gh-config/` 含登录凭据且已被 `.gitignore` 排除；不得复制到 `docs/`、`logs/` 或提交中。
- 推送后必须用远端 `refs/heads/main` 哈希与本地 `HEAD` 比对，哈希一致才可报告上传完成。

## 最终上传结果

- 普通 `git push origin main` 已成功，没有使用强制推送。
- 本地 `main`、本地远端跟踪分支 `origin/main` 与 GitHub `main` 最终均指向 `d9bd6ea411069f836b79aa74cddf339b2590f70f`。
- GitHub 的原有提交历史保留在合并提交第二父链中，当前完整工程位于第一父链工作树。
