"""Unit tests for the pluggable ONNX detector adapter (fake session only).

No real weights are required: these tests verify the pixel-only integration
path (letterbox -> session -> parse -> detections) with an injected stand-in
session that follows the YOLOv8 [1, 4+nc, N] normalized-output convention.
"""

import json

import numpy as np
import pytest

from smartclean_perception.onnx_adapter import (
    CANONICAL_CLASSES,
    OnnxDetector,
    OnnxDetectorConfig,
    _letterbox,
    _nms,
)


CLASS_MAP = {index: name for index, name in enumerate(CANONICAL_CLASSES)}


def _make_output(entries, num_classes=5):
    """Build a YOLOv8-style (1, 4+nc, N) output.

    Each entry is (cx, cy, w, h, class_id, score) in normalized coordinates.
    """

    output = np.zeros((1, 4 + num_classes, len(entries)), dtype=np.float32)
    for column, (cx, cy, w, h, class_id, score) in enumerate(entries):
        output[0, 0, column] = cx
        output[0, 1, column] = cy
        output[0, 2, column] = w
        output[0, 3, column] = h
        output[0, 4 + class_id, column] = score
    return output


class _IdentitySession:
    def __init__(self, output):
        self._output = np.asarray(output, dtype=np.float32)
        self._inputs = [_IdentityInput()]

    def get_inputs(self):
        return self._inputs

    def run(self, unused, feed):
        return [self._output.copy()]


class _IdentityInput:
    name = "images"


def _detector(entries, conf=0.25, iou=0.45, class_map=None):
    config = OnnxDetectorConfig(
        model_path="/nonexistent/model.onnx",
        conf_threshold=conf,
        iou_threshold=iou,
        class_map=CLASS_MAP if class_map is None else class_map,
    )
    return OnnxDetector(config, session=_IdentitySession(_make_output(entries)))


def test_letterbox_preserves_aspect_and_pads() -> None:
    image = np.full((240, 320, 3), 128, dtype=np.uint8)
    canvas, scale = _letterbox(image, (640, 640))
    assert canvas.shape == (640, 640, 3)
    assert scale == pytest.approx(2.0)
    # Top-left content area keeps the resized image; the padding strip is gray.
    assert canvas[0, 0, 0] == 128
    assert canvas[620, 0, 0] == 114


def test_letterbox_upscales_small_images() -> None:
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    canvas, scale = _letterbox(image, (64, 64))
    assert canvas.shape == (64, 64, 3)
    assert scale == pytest.approx(6.4)


def test_nms_keeps_high_score_and_drops_overlap() -> None:
    boxes = np.array(
        [[0, 0, 10, 10], [1, 1, 11, 11]], dtype=np.float32
    )
    scores = np.array([0.9, 0.5], dtype=np.float32)
    assert _nms(boxes, scores, 0.45) == [0]


def test_nms_keeps_non_overlapping_boxes() -> None:
    boxes = np.array(
        [[0, 0, 10, 10], [50, 50, 60, 60]], dtype=np.float32
    )
    scores = np.array([0.9, 0.8], dtype=np.float32)
    assert sorted(_nms(boxes, scores, 0.45)) == [0, 1]


def test_detect_maps_normalized_output_back_to_original_image() -> None:
    # 320x240 image letterboxed into 640x640 with scale 2.0. A detection
    # centered on the canvas with width 100/height 80 maps to 50x40 in the
    # original frame.
    image = np.full((240, 320, 3), 60, dtype=np.uint8)
    detector = _detector([(0.5, 0.5, 100.0 / 640.0, 80.0 / 640.0, 1, 0.8)])
    detections = detector.detect(image)
    assert len(detections) == 1
    detection = detections[0]
    assert detection.class_name == "plastic_bottle"
    assert detection.confidence == pytest.approx(0.8)
    x_min, y_min, x_max, y_max = detection.bbox_xyxy
    assert x_min == pytest.approx(135.0, abs=1.0)
    assert y_min == pytest.approx(140.0, abs=1.0)
    assert x_max == pytest.approx(185.0, abs=1.0)
    assert y_max == pytest.approx(180.0, abs=1.0)


def test_detect_filters_below_confidence() -> None:
    image = np.full((240, 320, 3), 60, dtype=np.uint8)
    detector = _detector([(0.5, 0.5, 0.1, 0.1, 0, 0.1)], conf=0.25)
    assert detector.detect(image) == []


def test_detect_drops_unknown_class_ids() -> None:
    image = np.full((240, 320, 3), 60, dtype=np.uint8)
    restricted_map = {0: "plastic_bottle"}
    detector = _detector(
        [(0.5, 0.5, 0.1, 0.1, 3, 0.9)], class_map=restricted_map
    )
    assert detector.detect(image) == []


def test_detect_rejects_non_bgr_input() -> None:
    detector = _detector([(0.5, 0.5, 0.1, 0.1, 0, 0.9)])
    with pytest.raises(ValueError):
        detector.detect(np.zeros((64, 64), dtype=np.uint8))
    with pytest.raises(ValueError):
        detector.detect(np.zeros((0, 64, 3), dtype=np.uint8))


def test_config_requires_non_empty_class_map() -> None:
    config = OnnxDetectorConfig(
        model_path="/nonexistent/model.onnx", class_map={}
    )
    with pytest.raises(ValueError):
        OnnxDetector(config, session=_IdentitySession(_make_output([])))


def test_model_card_overrides_thresholds_and_class_map(tmp_path) -> None:
    card = tmp_path / "card.json"
    card.write_text(
        json.dumps(
            {
                "class_map": {"0": "paper_cup"},
                "conf_threshold": 0.6,
                "iou_threshold": 0.3,
                "input_size": [320, 320],
            }
        ),
        encoding="utf-8",
    )
    config = OnnxDetectorConfig(
        model_path="/nonexistent/model.onnx",
        model_card_path=str(card),
    )
    detector = OnnxDetector(config, session=_IdentitySession(_make_output([])))
    assert detector.config.class_map == {0: "paper_cup"}
    assert detector.config.conf_threshold == pytest.approx(0.6)
    assert detector.config.iou_threshold == pytest.approx(0.3)
    assert tuple(detector.config.input_size) == (320, 320)


def test_detect_handles_empty_anchor_output() -> None:
    image = np.full((240, 320, 3), 60, dtype=np.uint8)
    detector = OnnxDetector(
        OnnxDetectorConfig(
            model_path="/nonexistent/model.onnx", class_map=CLASS_MAP
        ),
        session=_IdentitySession(np.zeros((1, 9, 0), dtype=np.float32)),
    )
    assert detector.detect(image) == []
