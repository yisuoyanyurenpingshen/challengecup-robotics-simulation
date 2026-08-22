"""Static and unit tests for the monotonic simulation-clock relay."""

from pathlib import Path

from smartclean_ros.clock_monotonic_relay_node import ClockMonotonicFilter
from smartclean_ros.clock_monotonic_relay_node import stamp_newer

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_entry_point_exists() -> None:
    setup = (PACKAGE_ROOT / "setup.py").read_text(encoding="utf-8")
    assert '"smartclean_clock_relay = "' in setup
    assert '"smartclean_ros.clock_monotonic_relay_node:main"' in setup


def test_stamp_newer_compares_sec_then_nanosec() -> None:
    assert stamp_newer((1, 0), (0, 999_999_999))
    assert stamp_newer((1, 2), (1, 1))
    assert not stamp_newer((1, 1), (1, 1))
    assert not stamp_newer((1, 0), (1, 1))
    assert not stamp_newer((0, 999_999_999), (1, 0))


def test_filter_publishes_strictly_monotonic_stream() -> None:
    stamp_filter = ClockMonotonicFilter()
    stream = [
        (0, 0),
        (0, 1),
        (0, 2),
        (0, 1),  # late duplicate / out-of-order delivery
        (0, 2),
        (1, 0),
        (1, 0),  # duplicate of the current head
        (2, 500),
        (2, 499),
        (3, 0),
    ]
    accepted = [stamp_filter.update(item) for item in stream]
    assert accepted == [True, True, True, False, False, True, False, True, False, True]
    assert stamp_filter.received == len(stream)
    assert stamp_filter.published == 6
    assert stamp_filter.dropped == 4
    assert stamp_filter.last == (3, 0)


def test_filter_first_message_always_published() -> None:
    stamp_filter = ClockMonotonicFilter()
    assert stamp_filter.update((0, 0))
    assert stamp_filter.published == 1
    assert stamp_filter.dropped == 0


def test_filter_rejects_backwards_jump_then_recovers() -> None:
    stamp_filter = ClockMonotonicFilter()
    assert stamp_filter.update((10, 0))
    assert not stamp_filter.update((9, 999_999_999))
    assert stamp_filter.update((10, 1))
    assert stamp_filter.published == 2
    assert stamp_filter.dropped == 1
    assert stamp_filter.last == (10, 1)
