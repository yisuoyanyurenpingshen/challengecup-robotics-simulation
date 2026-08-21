"""Pixel-based trash detection core (no ROS, no Gazebo ground truth).

This module implements the "合成Gazebo场景图像识别基线" (synthetic Gazebo
scene image recognition baseline): a color + contour + shape heuristic that
reads only image pixels. It is deliberately honest about its scope: the
thresholds are calibrated against the repository's local synthetic Gazebo
scene, and it is not a general real-world trash detector.

Calibration notes (see logs/2026-08-22-overnight-autonomous-work.md):
- The Gazebo RGB camera image is NOT vertically flipped. A 4-point fit of
  rendered blobs against the SDF poses gives pitch +0.148 rad (nose down),
  standard pinhole mapping, RMS error < 2 px.
- The horizon sits at raw row ~322; candidates are only searched below
  horizon_row (default 360) so the bright sky cannot produce false positives.
- Colors measured in the rendered scene (OpenCV HSV):
  bottle: H 95-130 S>=70 V>=60; can: H<10|H>170 S>=70 V>=60;
  leaves: H 40-90 S>=55 V>=40; white (cup/scrap): S<=60 V>=185.
- The white cup and paper scrap are separated by contour aspect ratio
  (cup is tall and narrow, scrap is a compact crumpled ball).
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np


@dataclass(frozen=True)
class DetectorConfig:
    """Tunable parameters of the color/shape baseline detector."""

    horizon_row: int = 360
    min_area: int = 50
    flip_vertical: bool = False
    # Hue ranges are OpenCV HSV degrees (0-179).
    bottle_hue: Tuple[int, int] = (95, 130)
    can_hue_hi: int = 10
    can_hue_lo: int = 170
    leaves_hue: Tuple[int, int] = (40, 90)
    strong_min_saturation: int = 70
    leaves_min_saturation: int = 55
    min_value: int = 60
    leaves_min_value: int = 40
    white_max_saturation: int = 60
    white_min_value: int = 185
    # Aspect windows: bottle/can/cup compare height/width, leaves and scrap
    # compare width/height.
    bottle_aspect: Tuple[float, float] = (1.2, 5.0)
    can_aspect: Tuple[float, float] = (1.2, 5.0)
    cup_aspect: Tuple[float, float] = (1.6, 6.0)
    leaves_aspect: Tuple[float, float] = (1.8, 8.0)
    scrap_aspect: Tuple[float, float] = (0.6, 1.8)
    # Reference values used to convert geometric agreement into scores.
    ideal_areas: Optional[dict] = None
    ideal_aspects: Optional[dict] = None

    def __post_init__(self) -> None:
        if self.ideal_areas is None:
            object.__setattr__(
                self,
                "ideal_areas",
                {
                    "plastic_bottle": 2100,
                    "aluminum_can": 420,
                    "fallen_leaves": 1560,
                    "paper_cup": 246,
                    "paper_scrap": 177,
                },
            )
        if self.ideal_aspects is None:
            # aspect key: height/width for bottle/can/cup,
            # width/height for leaves/scrap.
            object.__setattr__(
                self,
                "ideal_aspects",
                {
                    "plastic_bottle": 3.6,
                    "aluminum_can": 1.8,
                    "fallen_leaves": 3.0,
                    "paper_cup": 3.0,
                    "paper_scrap": 1.4,
                },
            )


@dataclass(frozen=True)
class TrashDetection:
    """One detection with diagnostics used for the confidence score."""

    class_name: str
    confidence: float
    bbox_xyxy: Tuple[float, float, float, float]
    area_px: float
    color_score: float
    shape_score: float
    size_score: float


CLASS_HUE_RULES = ("plastic_bottle", "aluminum_can", "fallen_leaves",
                   "paper_cup", "paper_scrap")


def _aspect(contour: np.ndarray) -> Tuple[float, float, float]:
    x, y, width, height = cv2.boundingRect(contour)
    if width <= 0 or height <= 0:
        return 0.0, 0.0, 0.0
    return height / float(width), width, height


def _gaussian_match(value: float, ideal: float, tolerance: float) -> float:
    """1.0 at value == ideal, decaying gaussian otherwise."""

    if tolerance <= 0:
        return 1.0 if value == ideal else 0.0
    delta = (value - ideal) / tolerance
    return float(np.exp(-0.5 * delta * delta))


class TrashDetector:
    """Detect trash in a BGR image using color masks, contours and shape."""

    def __init__(self, config: Optional[DetectorConfig] = None) -> None:
        self.config = config or DetectorConfig()

    def detect(self, bgr: np.ndarray) -> List[TrashDetection]:
        """Return detections for one BGR image (pixel data only)."""

        if bgr.ndim != 3 or bgr.shape[2] != 3 or bgr.size == 0:
            raise ValueError("detect expects a non-empty 3-channel BGR image")
        image = np.flipud(bgr) if self.config.flip_vertical else bgr
        height, width = image.shape[:2]
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hue, saturation, value = (
            hsv[:, :, 0],
            hsv[:, :, 1],
            hsv[:, :, 2],
        )

        region = np.zeros((height, width), dtype=np.uint8)
        top = min(max(int(self.config.horizon_row), 0), height)
        region[top:, :] = 1

        candidates = []

        bottle_mask = (
            (hue >= self.config.bottle_hue[0])
            & (hue <= self.config.bottle_hue[1])
            & (saturation >= self.config.strong_min_saturation)
            & (value >= self.config.min_value)
            & (region > 0)
        )
        candidates.extend(
            self._from_mask(bottle_mask, "plastic_bottle", image, hsv)
        )

        red_mask = (
            ((hue <= self.config.can_hue_hi) | (hue >= self.config.can_hue_lo))
            & (saturation >= self.config.strong_min_saturation)
            & (value >= self.config.min_value)
            & (region > 0)
        )
        candidates.extend(self._from_mask(red_mask, "aluminum_can", image, hsv))

        leaves_mask = (
            (hue >= self.config.leaves_hue[0])
            & (hue <= self.config.leaves_hue[1])
            & (saturation >= self.config.leaves_min_saturation)
            & (value >= self.config.leaves_min_value)
            & (region > 0)
        )
        candidates.extend(
            self._from_mask(leaves_mask, "fallen_leaves", image, hsv)
        )

        white_mask = (
            (saturation <= self.config.white_max_saturation)
            & (value >= self.config.white_min_value)
            & (region > 0)
        )
        for class_name in ("paper_cup", "paper_scrap"):
            candidates.extend(
                self._from_mask(white_mask, class_name, image, hsv)
            )

        return self._suppress(candidates)

    def _from_mask(
        self,
        mask: np.ndarray,
        class_name: str,
        image: np.ndarray,
        hsv: np.ndarray,
    ) -> List[TrashDetection]:
        binary = (mask > 0).astype(np.uint8) * 255
        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        detections = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < self.config.min_area:
                continue
            x, y, width, height = cv2.boundingRect(contour)
            if width <= 0 or height <= 0:
                continue
            if not self._aspect_accepts(class_name, height, width):
                continue
            bbox = (float(x), float(y), float(x + width), float(y + height))
            detection = self._score(
                class_name, mask, bbox, area, height, width
            )
            if detection is None:
                continue
            detections.append(detection)
        return detections

    def _aspect_accepts(self, class_name: str, height: int, width: int) -> bool:
        if class_name in ("plastic_bottle", "aluminum_can", "paper_cup"):
            low, high = {
                "plastic_bottle": self.config.bottle_aspect,
                "aluminum_can": self.config.can_aspect,
                "paper_cup": self.config.cup_aspect,
            }[class_name]
            ratio = height / float(width)
        else:
            low, high = {
                "fallen_leaves": self.config.leaves_aspect,
                "paper_scrap": self.config.scrap_aspect,
            }[class_name]
            ratio = width / float(height)
        return low <= ratio <= high

    def _score(
        self,
        class_name: str,
        mask: np.ndarray,
        bbox: Sequence[float],
        area: float,
        height: int,
        width: int,
    ) -> Optional[TrashDetection]:
        x_min, y_min, x_max, y_max = (int(round(v)) for v in bbox)
        box_area = float(max(1, (x_max - x_min) * (y_max - y_min)))
        mask_area = float(np.count_nonzero(mask[y_min:y_max, x_min:x_max]))
        color_score = min(1.0, mask_area / box_area)

        if class_name in ("plastic_bottle", "aluminum_can", "paper_cup"):
            aspect = height / float(width)
        else:
            aspect = width / float(height)
        ideal_aspect = float(self.config.ideal_aspects[class_name])
        tolerance = max(0.8, ideal_aspect * 0.45)
        shape_score = _gaussian_match(aspect, ideal_aspect, tolerance)

        ideal_area = float(self.config.ideal_areas[class_name])
        size_score = min(1.0, area / max(1.0, ideal_area))
        confidence = float(
            np.clip(
                0.55 * color_score + 0.25 * shape_score + 0.20 * size_score,
                0.0,
                1.0,
            )
        )
        return TrashDetection(
            class_name=class_name,
            confidence=confidence,
            bbox_xyxy=tuple(float(v) for v in bbox),
            area_px=area,
            color_score=color_score,
            shape_score=shape_score,
            size_score=size_score,
        )

    @staticmethod
    def _suppress(candidates: List[TrashDetection]) -> List[TrashDetection]:
        """Drop near-duplicate detections of the same class (IoU based)."""

        kept: List[TrashDetection] = []
        for candidate in sorted(
            candidates, key=lambda item: item.confidence, reverse=True
        ):
            duplicate = False
            for existing in kept:
                if existing.class_name != candidate.class_name:
                    continue
                if _iou(existing.bbox_xyxy, candidate.bbox_xyxy) > 0.5:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(candidate)
        return kept


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


CLASS_DRAW_COLORS = {
    "plastic_bottle": (255, 128, 0),
    "aluminum_can": (0, 0, 255),
    "fallen_leaves": (0, 200, 0),
    "paper_cup": (255, 255, 0),
    "paper_scrap": (0, 255, 255),
}


def annotate(bgr: np.ndarray, detections: Sequence[TrashDetection]) -> np.ndarray:
    """Draw class-colored boxes and labels onto a BGR image copy."""

    annotated = bgr.copy()
    for detection in detections:
        x_min, y_min, x_max, y_max = (int(round(v)) for v in detection.bbox_xyxy)
        color = CLASS_DRAW_COLORS.get(detection.class_name, (255, 255, 255))
        cv2.rectangle(annotated, (x_min, y_min), (x_max, y_max), color, 2)
        label = "{} {:.2f}".format(detection.class_name, detection.confidence)
        cv2.putText(
            annotated,
            label,
            (x_min, max(12, y_min - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
            cv2.LINE_AA,
        )
    return annotated
