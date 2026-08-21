# weights：模型权重说明

本文件夹只存放模型卡与说明，不直接上传大型权重文件。大型权重文件
（.pt、.pth、.onnx、.engine）全部放在被 Git 忽略的 `weights/downloads/`。

## 当前状态（2026-08-22）

**项目当前没有任何已导入的识别权重。** 正在运行的识别层是
`smartclean_perception` 中的「合成Gazebo场景图像识别基线」（HSV 颜色 +
轮廓/形状 + 面积评分），它只读取相机像素，不需要权重文件。

第一轮公开轻量垃圾 YOLO/ONNX 权重调研结论：

- 未找到同时满足「明确宽松许可证 + 与项目 5 类垃圾兼容 + 有原始下载地址」的权重。
- 发现的候选要么是 AGPL 类 copyleft 许可证（不适合本项目），要么类别与
  `fallen_leaves/plastic_bottle/paper_scrap/paper_cup/aluminum_can` 不兼容，
  要么没有注明许可证。
- 因此本轮**没有下载任何权重、没有安装 onnxruntime**，合成视觉基线作为
  唯一识别来源继续推进主线。找到合规权重后，再走下面的接入流程。

## 接入合规 ONNX 权重的流程

1. 复制 `weights/model-card-template.json`，填写真实来源 URL、许可证、
   SHA-256、类别映射与阈值。
2. 下载并校验（幂等，哈希不符会失败并清理）：

   ```bash
   bash scripts/download_onnx_model.sh weights/<你的模型卡>.json
   ```

3. 权重落在 `weights/downloads/<file_name>`（Git 忽略目录，绝不入库）。
4. 把模型卡 JSON 提交到 Git，作为来源/许可证/哈希的审计记录。
5. 在感知节点接入 `smartclean_perception.onnx_adapter.OnnxDetector`，
   并在合成数据集与真实渲染帧上重新评估 precision/recall/耗时后才能替换
   颜色基线。

约束：

- 禁止提交 AGPL 类 copyleft、未注明许可证或来源不明的权重。
- 禁止把 `weights/downloads/` 内任何文件加入 Git。
- 未经重新评估，不得把 ONNX 输出直接当作「现实环境通用识别」宣传。
