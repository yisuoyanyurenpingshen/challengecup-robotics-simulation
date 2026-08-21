"""Pluggable ONNX detector adapter for future model-based layers.

The synthetic color baseline remains the active detector. This adapter is a
prepared integration point for a lightweight, clearly-licensed trash YOLO
ONNX model: it implements the same pixel-only contract (BGR in, detections
out), runs on ONNX Runtime CPU, and never reads Gazebo ground truth.

Status: adapter logic is unit-tested with an injected fake session. No
weights are committed; see weights/model-card-template.json and
scripts/download_onnx_model.sh for the weight acquisition flow.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import cv2
import numpy as np

from .detector_core import TrashDetection

CANONICAL_CLASSES = (
    "fallen_leaves",
    "plastic_bottle",
    "paper_scrap",
    "paper_cup",
    "aluminum_can",
)


@dataclass(frozen=True)
class OnnxDetectorConfig:
    model_path: str
    model_card_path: Optional[str] = None
    conf_threshold: float = 0.25
    iou_threshold: float = 0.45
    class_map: Optional[Dict[int, str]] = None
    input_size: Sequence[int] = (640, 640)
    # YOLOv8-style ONNX heads emit coordinates normalized to [0, 1].
    # Set False only for non-standard models that emit pixel coordinates.
    coords_normalized: bool = True


def _letterbox(
    bgr: np.ndarray, target_size: Sequence[int]
) -> tuple:
    """Resize with aspect preservation, padding bottom-right (YOLO style)."""

    height, width = bgr.shape[:2]
    target_w, target_h = target_size[0], target_size[1]
    scale = min(target_w / float(width), target_h / float(height))
    new_w = int(round(width * scale))
    new_h = int(round(height * scale))
    resized = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((target_h, target_w, 3), 114, dtype=np.uint8)
    canvas[:new_h, :new_w] = resized
    return canvas, scale


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> List[int]:
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        first = order[0]
        keep.append(int(first))
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(boxes[first, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[first, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[first, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[first, 3], boxes[rest, 3])
        inter_w = np.maximum(0.0, xx2 - xx1)
        inter_h = np.maximum(0.0, yy2 - yy1)
        intersection = inter_w * inter_h
        area_first = max(
            1e-6,
            (boxes[first, 2] - boxes[first, 0]) * (boxes[first, 3] - boxes[first, 1]),
        )
        area_rest = (boxes[rest, 2] - boxes[rest, 0]) * (
            boxes[rest, 3] - boxes[rest, 1]
        )
        union = area_first + area_rest - intersection
        iou = intersection / np.maximum(1e-6, union)
        order = rest[iou <= iou_threshold]
    return keep


class OnnxDetector:
    """Run a YOLOv8-style [1, 4+nc, N] ONNX output on CPU."""

    def __init__(self, config: OnnxDetectorConfig, session: Any = None) -> None:
        self.config = config
        if config.model_card_path:
            card = json.loads(Path(config.model_card_path).read_text(encoding="utf-8"))
            if config.class_map is None:
                config = OnnxDetectorConfig(
                    model_path=config.model_path,
                    model_card_path=config.model_card_path,
                    conf_threshold=float(card.get("conf_threshold", 0.25)),
                    iou_threshold=float(card.get("iou_threshold", 0.45)),
                    class_map={
                        int(key): value for key, value in card["class_map"].items()
                    },
                    input_size=tuple(int(v) for v in card.get("input_size", [640, 640])),
                )
            self.config = config
        if session is None:
            import onnxruntime  # deferred: only needed when weights exist

            session = onnxruntime.InferenceSession(
                self.config.model_path, providers=["CPUExecutionProvider"]
            )
        self._session = session
        if not self.config.class_map:
            raise ValueError("OnnxDetector requires a non-empty class_map")

    def detect(self, bgr: np.ndarray) -> List[TrashDetection]:
        if bgr.ndim != 3 or bgr.shape[2] != 3 or bgr.size == 0:
            raise ValueError("detect expects a non-empty 3-channel BGR image")
        original_height, original_width = bgr.shape[:2]
        canvas, scale = _letterbox(bgr, self.config.input_size)
        blob = (
            canvas.astype(np.float32) / 255.0
        ).transpose(2, 0, 1)[None, ...]
        input_name = self._session.get_inputs()[0].name
        outputs = self._session.run(None, {input_name: blob})
        output = np.asarray(outputs[0], dtype=np.float32).copy()
        if output.ndim != 3:
            raise ValueError("unexpected ONNX output rank {}".format(output.ndim))
        if self.config.coords_normalized:
            canvas_height, canvas_width = canvas.shape[:2]
            output[:, 0, :] *= canvas_width
            output[:, 2, :] *= canvas_width
            output[:, 1, :] *= canvas_height
            output[:, 3, :] *= canvas_height
        return self._parse_output(output, original_width, original_height, scale)

    def _parse_output(
        self, output: np.ndarray, width: int, height: int, scale: float
    ) -> List[TrashDetection]:
        # YOLOv8 layout: (1, 4 + num_classes, num_anchors).
        if output.ndim != 3:
            raise ValueError("unexpected ONNX output rank {}".format(output.ndim))
        num_classes = output.shape[1] - 4
        transposed = output[0].T  # (num_anchors, 4 + num_classes)
        boxes = transposed[:, :4].copy()
        class_scores = transposed[:, 4:]
        if class_scores.size == 0:
            return []
        class_ids = class_scores.argmax(axis=1)
        scores = class_scores[np.arange(class_scores.shape[0]), class_ids]

        # Convert cxcywh to xyxy in padded coordinates.
        boxes[:, 0] -= boxes[:, 2] / 2.0
        boxes[:, 1] -= boxes[:, 3] / 2.0
        boxes[:, 2] += boxes[:, 0]
        boxes[:, 3] += boxes[:, 1]

        keep = _nms(boxes, scores, self.config.iou_threshold)
        detections = []
        for index in keep:
            score = float(scores[index])
            if score < self.config.conf_threshold:
                continue
            class_name = self.config.class_map.get(int(class_ids[index]))
            if class_name is None:
                continue
            if class_name not in CANONICAL_CLASSES:
                continue
            x_min = float(np.clip(boxes[index, 0] / scale, 0, width))
            y_min = float(np.clip(boxes[index, 1] / scale, 0, height))
            x_max = float(np.clip(boxes[index, 2] / scale, 0, width))
            y_max = float(np.clip(boxes[index, 3] / scale, 0, height))
            if x_max <= x_min or y_max <= y_min:
                continue
            detections.append(
                TrashDetection(
                    class_name=class_name,
                    confidence=score,
                    bbox_xyxy=(x_min, y_min, x_max, y_max),
                    area_px=float((x_max - x_min) * (y_max - y_min)),
                    color_score=score,
                    shape_score=1.0,
                    size_score=1.0,
                )
            )
        return detections


class _FakeSession:
    """Minimal stand-in for onnxruntime.InferenceSession used in tests.

    The stored output uses the standard YOLOv8 layout ``(1, 4 + nc, N)`` with
    coordinates normalized to [0, 1]; ``run`` passes it through unchanged so
    the adapter's own denormalization path is exercised.
    """

    def __init__(self, output: np.ndarray) -> None:
        self._output = output
        self._inputs = [_FakeInput()]

    def get_inputs(self) -> List[Any]:
        return self._inputs

    def run(self, unused: Any, feed: Dict[str, np.ndarray]) -> List[np.ndarray]:
        return [self._output.astype(np.float32).copy()]


class _FakeInput:
    name = "images"
