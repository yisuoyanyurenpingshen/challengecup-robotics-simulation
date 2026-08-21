"""Deterministic synthetic image set for the color-baseline detector.

The images mimic the measured appearance of the repository's local Gazebo
scene (gray ground, pale sky, five colored trash objects). They are generated
programmatically with fixed seeds so the evaluation is reproducible, and they
carry ground-truth boxes used ONLY for evaluation statistics.

This is a "合成Gazebo场景图像识别基线" test set: it does not claim to
represent real-world camera footage.
"""

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import cv2
import numpy as np

from .detector_core import DetectorConfig, TrashDetector

IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
HORIZON = 322

# Measured from rendered frames (BGR).
GROUND_BGR = np.array([139.0, 155.0, 155.0])
SKY_BGR = np.array([236.0, 210.0, 181.0])

# (class, HSV center, object geometry kind, default size (w,h))
# Object colors measured from the lit scene (OpenCV HSV).
OBJECT_SPECS = {
    "plastic_bottle": {"hsv": (105, 170, 180), "kind": "rect", "size": (24, 89)},
    "aluminum_can": {"hsv": (3, 165, 190), "kind": "rect", "size": (16, 29)},
    "fallen_leaves": {"hsv": (45, 120, 140), "kind": "ellipse", "size": (73, 24)},
    "paper_cup": {"hsv": (25, 8, 195), "kind": "rect", "size": (10, 30)},
    "paper_scrap": {"hsv": (26, 8, 221), "kind": "ellipse", "size": (18, 13)},
}

# Ground-truth placement for the all-five scene (pixel centers measured in
# the rendered trash world).
ALL_FIVE_LAYOUT = {
    "plastic_bottle": (320, 415),
    "aluminum_can": (91, 404),
    "fallen_leaves": (449, 422),
    "paper_cup": (549, 402),
    "paper_scrap": (196, 388),
}


@dataclass(frozen=True)
class GroundTruth:
    class_name: str
    bbox_xyxy: Tuple[float, float, float, float]


@dataclass(frozen=True)
class SyntheticScene:
    image: np.ndarray
    truths: Tuple[GroundTruth, ...]
    label: str


def _draw_object(
    image: np.ndarray,
    class_name: str,
    center: Tuple[int, int],
    scale: float,
    rng: np.random.Generator,
) -> Tuple[float, float, float, float]:
    spec = OBJECT_SPECS[class_name]
    width = max(3, int(round(spec["size"][0] * scale)))
    height = max(3, int(round(spec["size"][1] * scale)))
    hue, sat, val = spec["hsv"]
    hsv_noise = np.zeros((height, width, 3), dtype=np.uint8)
    hsv_noise[:, :, 0] = np.clip(hue + rng.normal(0, 4, (height, width)), 0, 179)
    hsv_noise[:, :, 1] = np.clip(sat + rng.normal(0, 10, (height, width)), 0, 255)
    hsv_noise[:, :, 2] = np.clip(val + rng.normal(0, 12, (height, width)), 0, 255)
    patch = cv2.cvtColor(hsv_noise, cv2.COLOR_HSV2BGR)

    x_min = center[0] - width // 2
    y_min = center[1] - height // 2
    x_max = x_min + width
    y_max = y_min + height
    mask = np.zeros((height, width), dtype=np.uint8)
    if spec["kind"] == "rect":
        mask[:, :] = 255
    else:
        cv2.ellipse(mask, (width // 2, height // 2), (width // 2, height // 2),
                    0, 0, 360, 255, -1)
    region = image[y_min:y_max, x_min:x_max]
    region[mask > 0] = patch[mask > 0]
    return (float(x_min), float(y_min), float(x_max), float(y_max))


def _background(rng: np.random.Generator) -> np.ndarray:
    image = np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH, 3), dtype=np.uint8)
    sky = SKY_BGR + rng.normal(0, 4, (IMAGE_HEIGHT, IMAGE_WIDTH, 3))
    ground = GROUND_BGR + rng.normal(0, 5, (IMAGE_HEIGHT, IMAGE_WIDTH, 3))
    image[:HORIZON, :, :] = np.clip(sky[:HORIZON, :, :], 0, 255)
    image[HORIZON:, :, :] = np.clip(ground[HORIZON:, :, :], 0, 255)
    return image


def _single_scene(
    class_name: str, rng: np.random.Generator, seed_index: int
) -> SyntheticScene:
    image = _background(rng)
    # Single-object layouts keep trash in the ground region with some
    # per-seed position and size jitter.
    positions = [(320, 430), (180, 420), (460, 425)]
    center = positions[seed_index % len(positions)]
    scale = 1.0 + 0.1 * ((seed_index % 3) - 1)
    box = _draw_object(image, class_name, center, scale, rng)
    return SyntheticScene(
        image=image,
        truths=(GroundTruth(class_name, box),),
        label="single_{}".format(class_name),
    )


def _all_five_scene(rng: np.random.Generator, seed_index: int) -> SyntheticScene:
    image = _background(rng)
    truths = []
    for class_name, (x, y) in ALL_FIVE_LAYOUT.items():
        scale = 1.0 + 0.08 * ((seed_index % 3) - 1)
        box = _draw_object(image, class_name, (x, y), scale, rng)
        truths.append(GroundTruth(class_name, box))
    return SyntheticScene(
        image=image, truths=tuple(truths), label="all_five"
    )


def _empty_scene(rng: np.random.Generator) -> SyntheticScene:
    return SyntheticScene(image=_background(rng), truths=(), label="empty")


def build_scenes(seeds: Sequence[int] = (0, 1, 2)) -> List[SyntheticScene]:
    """Return the deterministic synthetic evaluation set."""

    scenes: List[SyntheticScene] = []
    for seed_index, seed in enumerate(seeds):
        rng = np.random.default_rng(seed)
        for class_name in OBJECT_SPECS:
            scenes.append(_single_scene(class_name, rng, seed_index))
        scenes.append(_all_five_scene(rng, seed_index))
        scenes.append(_empty_scene(rng))
    return scenes


def _iou(box_a: Sequence[float], box_b: Sequence[float]) -> float:
    x_min = max(box_a[0], box_b[0])
    y_min = max(box_a[1], box_b[1])
    x_max = min(box_a[2], box_b[2])
    y_max = min(box_a[3], box_b[3])
    if x_max <= x_min or y_max <= y_min:
        return 0.0
    intersection = (x_max - x_min) * (y_max - y_min)
    area_a = max(1e-6, (box_a[2] - box_a[0]) * (box_a[3] - box_a[1]))
    area_b = max(1e-6, (box_b[2] - box_b[0]) * (box_b[3] - box_b[1]))
    return intersection / float(area_a + area_b - intersection)


def evaluate(
    scenes: Sequence[SyntheticScene],
    detector: TrashDetector,
    iou_threshold: float = 0.3,
) -> Dict[str, object]:
    """Compute precision/recall/FN/FP and CPU latency on the scene set."""

    per_class: Dict[str, Dict[str, float]] = {
        name: {"tp": 0, "fp": 0, "fn": 0, "gt": 0}
        for name in OBJECT_SPECS
    }
    for scene in scenes:
        detections = detector.detect(scene.image)
        matched_truths = set()
        for detection in detections:
            best_iou = 0.0
            best_index = -1
            for index, truth in enumerate(scene.truths):
                if index in matched_truths:
                    continue
                if truth.class_name != detection.class_name:
                    continue
                current = _iou(detection.bbox_xyxy, truth.bbox_xyxy)
                if current > best_iou:
                    best_iou = current
                    best_index = index
            if best_index >= 0 and best_iou >= iou_threshold:
                per_class[detection.class_name]["tp"] += 1
                matched_truths.add(best_index)
            else:
                per_class[detection.class_name]["fp"] += 1
        for index, truth in enumerate(scene.truths):
            per_class[truth.class_name]["gt"] += 1
            if index not in matched_truths:
                per_class[truth.class_name]["fn"] += 1

    class_report = {}
    total_tp = total_fp = total_fn = total_gt = 0
    for class_name, stats in sorted(per_class.items()):
        tp = stats["tp"]
        fp = stats["fp"]
        fn = stats["fn"]
        gt = stats["gt"]
        total_tp += tp
        total_fp += fp
        total_fn += fn
        total_gt += gt
        precision = tp / float(tp + fp) if (tp + fp) else 1.0
        recall = tp / float(gt) if gt else 1.0
        class_report[class_name] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "gt": gt,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
        }
    overall_precision = (
        total_tp / float(total_tp + total_fp) if (total_tp + total_fp) else 1.0
    )
    overall_recall = total_tp / float(total_gt) if total_gt else 1.0

    # CPU latency on the all-five scene over repeated runs.
    latency_scene = next(
        (s for s in reversed(scenes) if s.label == "all_five"), scenes[-1]
    )
    latencies_ms = []
    for _ in range(30):
        detector.detect(latency_scene.image)  # warm-up excluded below
    for _ in range(30):
        start = cv2.getTickCount()
        detector.detect(latency_scene.image)
        end = cv2.getTickCount()
        latencies_ms.append((end - start) * 1000.0 / cv2.getTickFrequency())
    latencies_ms.sort()
    mean_ms = float(np.mean(latencies_ms))
    p95_ms = float(np.percentile(latencies_ms, 95))
    fps = 1000.0 / mean_ms if mean_ms > 0 else float("inf")

    return {
        "schema_version": 1,
        "baseline_name": "合成Gazebo场景图像识别基线",
        "images": len(scenes),
        "iou_threshold": iou_threshold,
        "per_class": class_report,
        "overall_precision": round(overall_precision, 4),
        "overall_recall": round(overall_recall, 4),
        "overall_fp": total_fp,
        "overall_fn": total_fn,
        "cpu_mean_ms": round(mean_ms, 3),
        "cpu_p95_ms": round(p95_ms, 3),
        "fps": round(fps, 2),
    }


def default_detector() -> TrashDetector:
    return TrashDetector(DetectorConfig())
