# results：轻量实验结果

本目录保存经过筛选、可由 Git 跟踪的实验摘要和演示结果。

允许保存 Markdown、TXT、CSV、JSON、自包含 HTML，以及少量 PNG/JPG/JPEG 图片。不保存大型视频、原始图片集、训练输出目录或模型权重。

建议每份结果记录：

- 实验名称与时间
- Git commit
- 场景和任务配置
- 数据集与权重版本（如适用）
- 执行命令
- 指标及其定义
- 仿真、板端或实车的结果类型

生成二维演示结果：

```bash
python3 scripts/run_demo.py --output results/demo_result.json
python3 scripts/run_demo.py --animate results/demo_animation.html
```
