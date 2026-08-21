"""Unit tests for the pixel-based trash detector core."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from smartclean_perception.detector_core import (
    CLASS_DRAW_COLORS,
    DetectorConfig,
    TrashDetector,
    annotate,
)
from smartclean_perception.synthetic_dataset import (
    OBJECT_SPECS,
    _draw_object,
    _empty_scene,
    build_scenes,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _detector() -> TrashDetector:
    return TrashDetector(DetectorConfig())


def test_single_class_scenes_detected_with_correct_class() -> None:
    detector = _detector()
    for scene in build_scenes():
        if not scene.label.startswith("single_"):
            continue
        expected_class = scene.truths[0].class_name
        detections = detector.detect(scene.image)
        assert len(detections) >= 1, "no detection in {}".format(scene.label)
        classes = {item.class_name for item in detections}
        assert expected_class in classes, scene.label


def test_all_five_scene_detects_every_class() -> None:
    detector = _detector()
    for scene in build_scenes():
        if scene.label != "all_five":
            continue
        detections = detector.detect(scene.image)
        classes = {item.class_name for item in detections}
        assert classes == set(OBJECT_SPECS), classes


def test_empty_scene_has_no_detections() -> None:
    detector = _detector()
    rng = np.random.default_rng(0)
    scene = _empty_scene(rng)
    assert detector.detect(scene.image) == []


def test_detection_fields_are_sane() -> None:
    detector = _detector()
    for scene in build_scenes():
        height, width = scene.image.shape[:2]
        for detection in detector.detect(scene.image):
            assert 0.0 <= detection.confidence <= 1.0
            x_min, y_min, x_max, y_max = detection.bbox_xyxy
            assert 0.0 <= x_min < x_max <= width
            assert 0.0 <= y_min < y_max <= height
            assert detection.area_px > 0


def test_flip_vertical_flag_mirrors_analysis() -> None:
    """flip_vertical=True analyses a vertically mirrored frame identically."""

    detector = _detector()
    flipped_detector = TrashDetector(DetectorConfig(flip_vertical=True))
    for scene in build_scenes():
        if scene.label != "all_five":
            continue
        normal = detector.detect(scene.image)
        mirrored = cv2.flip(scene.image, 0)
        flipped = flipped_detector.detect(mirrored)
        assert len(normal) == len(flipped)
        normal_classes = sorted(item.class_name for item in normal)
        flipped_classes = sorted(item.class_name for item in flipped)
        assert normal_classes == flipped_classes


def test_annotate_changes_image_and_uses_class_colors() -> None:
    detector = _detector()
    for scene in build_scenes():
        if scene.label != "all_five":
            continue
        detections = detector.detect(scene.image)
        annotated = annotate(scene.image, detections)
        assert not np.array_equal(annotated, scene.image)
        color_counts = []
        for color in CLASS_DRAW_COLORS.values():
            match = np.all(
                np.abs(annotated.astype(np.int16) - np.array(color)) < 12,
                axis=2,
            )
            color_counts.append(int(np.count_nonzero(match)))
        assert sum(color_counts) > 200, color_counts


def test_detector_never_reads_scene_ground_truth() -> None:
    """The detector core must be pure image pixels: no ground-truth IO."""

    core = (PACKAGE_ROOT / "smartclean_perception" / "detector_core.py").read_text(
        encoding="utf-8"
    )
    node = (
        PACKAGE_ROOT / "smartclean_perception" / "trash_detector_node.py"
    ).read_text(encoding="utf-8")
    for path, text in (("detector_core.py", core), ("trash_detector_node.py", node)):
        assert "gazebo_scene" not in text, path
        assert "configs/" not in text, path
        assert "model://" not in text, path
        assert "subprocess" not in text, path
        assert "ign " not in text, path
        assert "ignition" not in text, path
        assert "rclpy" not in core


def test_rejects_invalid_input() -> None:
    detector = _detector()
    with pytest.raises(ValueError):
        detector.detect(np.zeros((10, 10), dtype=np.uint8))
    with pytest.raises(ValueError):
        detector.detect(np.zeros((0, 0, 3), dtype=np.uint8))


def test_iou_suppression_merges_duplicates() -> None:
    """Two overlapping same-class masks produce a single detection."""

    rng = np.random.default_rng(4)
    scene = _empty_scene(rng)
    _draw_object(scene.image, "plastic_bottle", (320, 430), 1.0, rng)
    _draw_object(scene.image, "plastic_bottle", (322, 431), 1.0, rng)
    detections = _detector().detect(scene.image)
    bottles = [d for d in detections if d.class_name == "plastic_bottle"]
    assert len(bottles) == 1, bottles
