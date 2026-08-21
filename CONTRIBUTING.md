# 共享仓库协作约定

本仓库根目录是团队公共汇总区。任何人在这里工作都必须保留可追溯记录。

## 开始前

1. 执行 `git status --short --branch`，确认是否存在他人的未提交修改。
2. 阅读根 `README.md`、目标模块的 README 和相关 `docs/`。
3. 不覆盖、不还原、不顺手格式化不属于当前任务的修改。

## 每次公共变更必须完成

1. 在 `logs/` 新增或追加本次变更记录。
2. 技术选择、架构、接口或指标定义发生变化时，同步更新 `docs/`。
3. 记录执行过的验证命令和真实结果；没有验证就明确写“未验证”。
4. 提交前检查 `git diff`，确保没有大文件、密钥、Token、账号或私有地址。

## 日志命名和内容

多人协作优先使用：

```text
logs/YYYY-MM-DD-主题.md
```

日志至少包含：时间与执行者、目标、变更文件、设计决定、验证命令与结果、遗留问题、下一步。

## 提交建议

一次提交只解决一类问题，并使用能说明目的的提交信息，例如：

```text
feat(sim): add deterministic grid cleaning loop
docs(architecture): define ROS2 adapter boundary
test(planning): cover blocked and unreachable paths
```

