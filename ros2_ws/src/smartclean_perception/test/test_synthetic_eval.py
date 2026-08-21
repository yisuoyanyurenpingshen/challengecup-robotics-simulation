"""Evaluation thresholds for the synthetic Gazebo-scene image baseline."""

from smartclean_perception.synthetic_dataset import (
    build_scenes,
    default_detector,
    evaluate,
)


def test_precision_recall_thresholds() -> None:
    report = evaluate(build_scenes(), default_detector())
    for class_name, stats in report["per_class"].items():
        assert stats["precision"] >= 0.95, (class_name, stats)
        assert stats["recall"] >= 0.95, (class_name, stats)
        assert stats["fn"] == 0, (class_name, stats)
    assert report["overall_fp"] == 0
    assert report["overall_fn"] == 0


def test_empty_scenes_have_no_false_positives() -> None:
    detector = default_detector()
    for scene in build_scenes():
        if scene.label == "empty":
            assert detector.detect(scene.image) == []


def test_cpu_latency_budget() -> None:
    report = evaluate(build_scenes(), default_detector())
    assert report["cpu_mean_ms"] < 50.0, report
    assert report["cpu_p95_ms"] < 100.0, report
    assert report["fps"] > 20.0, report
