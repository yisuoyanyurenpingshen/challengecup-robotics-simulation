# scripts：可执行入口与工具

本目录保存演示、实验、数据处理和维护脚本。

当前脚本：

- `run_demo.py`：自动加入 `src/` 到模块路径，运行二维默认演示，无需提前安装项目包。

使用方法：

```bash
python3 scripts/run_demo.py --show-map
python3 scripts/run_demo.py --help
```

脚本约定：

- 从仓库根目录运行，路径不得硬编码为个人目录。
- 提供 `--help`，错误时返回非零退出码。
- 不在脚本中保存密钥、Token 或私有服务器配置。
- 新脚本应在本 README 中补充用途和最小命令。
