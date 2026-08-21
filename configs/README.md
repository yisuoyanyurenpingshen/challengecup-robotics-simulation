# configs：可跟踪配置

本目录保存不含密钥、体积较小且可复现实验的配置。

当前配置：

- `demo.json`：二维教学楼门口命名区域、垃圾目标、动态行人、全覆盖自然语言任务和最大步数。

约定：

- 配置必须声明 `schema_version`。
- `areas` 使用显式 `[x, y]` 列表定义命名区域；障碍和任务要求避开的危险格会在覆盖时自动过滤。
- 二维核心坐标使用 `[x, y]`，原点位于地图左上角，`x` 向右、`y` 向下。
- 配置中的路径应相对仓库根目录，不写个人绝对路径。
- 账号、密码、API Token、SSH 密钥和服务器私有参数不得进入仓库。
- 修改配置结构时必须同步更新 `docs/03_module_interfaces.md` 和变更日志。

运行默认配置：

```bash
python3 scripts/run_demo.py --config configs/demo.json
```
