"""Deterministic sampling tests (Phase 2 design sections 11-14).

Expected intervals are frozen exact values computed by hand from the
strategy definitions — not approximations.
"""

from __future__ import annotations

import pytest

from audio_similarity.sampling import (
    AudioSegment,
    InvalidTrackDurationError,
    get_strategy,
    sample_segments,
)


def intervals(segments: list[AudioSegment]) -> list[tuple[float, float]]:
    return [(s.actual_start_sec, s.actual_end_sec) for s in segments]


def assert_valid(segments: list[AudioSegment], duration: float):
    for seg in segments:
        assert 0 <= seg.actual_start_sec < seg.actual_end_sec <= duration + 1e-9
        assert seg.duration_sec > 0


# ---------------------------------------------------------------------------
# First30
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "duration,expected",
    [
        (10.0, [(0.0, 10.0)]),
        (29.0, [(0.0, 29.0)]),
        (30.0, [(0.0, 30.0)]),
        (31.0, [(0.0, 30.0)]),
        (60.0, [(0.0, 30.0)]),
        (180.0, [(0.0, 30.0)]),
        (600.0, [(0.0, 30.0)]),
    ],
)
def test_first30_exact_intervals(duration, expected):
    segs = sample_segments("t", duration, "first30")
    assert intervals(segs) == expected
    assert_valid(segs, duration)


# ---------------------------------------------------------------------------
# Center30
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "duration,expected",
    [
        (10.0, [(0.0, 10.0)]),           # shorter than window -> whole track
        (29.0, [(0.0, 29.0)]),
        (30.0, [(0.0, 30.0)]),
        (31.0, [(0.5, 30.5)]),           # shifted fully into bounds
        (60.0, [(15.0, 45.0)]),
        (180.0, [(75.0, 105.0)]),
        (600.0, [(285.0, 315.0)]),
    ],
)
def test_center30_exact_intervals(duration, expected):
    segs = sample_segments("t", duration, "center30")
    assert intervals(segs) == expected
    assert_valid(segs, duration)


# ---------------------------------------------------------------------------
# Three20 (centers 25% / 50% / 75%, window 20 s)
# ---------------------------------------------------------------------------


def test_three20_long_track_exact():
    segs = sample_segments("t", 600.0, "three20")
    assert intervals(segs) == [(140.0, 160.0), (290.0, 310.0), (440.0, 460.0)]


def test_three20_180s_exact():
    segs = sample_segments("t", 180.0, "three20")
    assert intervals(segs) == [(35.0, 55.0), (80.0, 100.0), (125.0, 145.0)]


def test_three20_60s_exact():
    segs = sample_segments("t", 60.0, "three20")
    assert intervals(segs) == [(5.0, 25.0), (20.0, 40.0), (35.0, 55.0)]


def test_three20_31s_shifted_windows():
    # each window shifted fully into valid bounds rather than truncated
    segs = sample_segments("t", 31.0, "three20")
    assert intervals(segs) == [(0.0, 20.0), (5.5, 25.5), (11.0, 31.0)]


def test_three20_30s_mixed():
    segs = sample_segments("t", 30.0, "three20")
    assert intervals(segs) == [(0.0, 20.0), (5.0, 25.0), (10.0, 30.0)]


def test_three20_10s_shorter_than_window_returns_whole_track_once():
    # 10 s < the 20 s window -> entire valid track exactly once
    segs = sample_segments("t", 10.0, "three20")
    assert intervals(segs) == [(0.0, 10.0)]


def test_three20_29s_windows_fit_normally():
    # 29 s >= the 20 s window -> normal placement applies (not the short-track rule)
    segs = sample_segments("t", 29.0, "three20")
    assert intervals(segs) == [(0.0, 20.0), (4.5, 24.5), (9.0, 29.0)]


# ---------------------------------------------------------------------------
# Three30 (centers 20% / 50% / 80%, window 30 s)
# ---------------------------------------------------------------------------


def test_three30_long_track_exact():
    segs = sample_segments("t", 600.0, "three30")
    assert intervals(segs) == [(105.0, 135.0), (285.0, 315.0), (465.0, 495.0)]


def test_three30_180s_exact():
    segs = sample_segments("t", 180.0, "three30")
    assert intervals(segs) == [(21.0, 51.0), (75.0, 105.0), (129.0, 159.0)]


def test_three30_60s_exact():
    segs = sample_segments("t", 60.0, "three30")
    assert intervals(segs) == [(0.0, 30.0), (15.0, 45.0), (30.0, 60.0)]


def test_three30_31s_shifted():
    segs = sample_segments("t", 31.0, "three30")
    assert intervals(segs) == [(0.0, 30.0), (0.5, 30.5), (1.0, 31.0)]


def test_three30_exactly_window_single_segment():
    segs = sample_segments("t", 30.0, "three30")
    assert intervals(segs) == [(0.0, 30.0)]


# ---------------------------------------------------------------------------
# Five20 (five evenly distributed 20 s windows)
# ---------------------------------------------------------------------------


def test_five20_600s_exact():
    segs = sample_segments("t", 600.0, "five20")
    assert intervals(segs) == [
        (0.0, 20.0), (145.0, 165.0), (290.0, 310.0), (435.0, 455.0), (580.0, 600.0),
    ]


def test_five20_180s_exact():
    segs = sample_segments("t", 180.0, "five20")
    assert intervals(segs) == [
        (0.0, 20.0), (40.0, 60.0), (80.0, 100.0), (120.0, 140.0), (160.0, 180.0),
    ]


def test_five20_60s_exact():
    segs = sample_segments("t", 60.0, "five20")
    assert intervals(segs) == [
        (0.0, 20.0), (10.0, 30.0), (20.0, 40.0), (30.0, 50.0), (40.0, 60.0),
    ]


def test_five20_30s_even_distribution():
    segs = sample_segments("t", 30.0, "five20")
    assert intervals(segs) == [
        (0.0, 20.0), (2.5, 22.5), (5.0, 25.0), (7.5, 27.5), (10.0, 30.0),
    ]


def test_five20_10s_whole_track():
    segs = sample_segments("t", 10.0, "five20")
    assert intervals(segs) == [(0.0, 10.0)]


# ---------------------------------------------------------------------------
# Dense30Hop15 reference strategy
# ---------------------------------------------------------------------------


def test_dense_600s_terminal_window_is_full_length():
    segs = sample_segments("t", 600.0, "dense30_hop15")
    ivals = intervals(segs)
    assert len(segs) == 39  # starts 0..570 step 15; terminal anchors onto last
    assert ivals[0] == (0.0, 30.0)
    assert ivals[-1] == (570.0, 600.0)
    for a, b in zip(ivals, ivals[1:]):
        assert b[0] - a[0] == 15.0  # uniform hop, no duplicates


def test_dense_180s_exact_count_and_coverage():
    segs = sample_segments("t", 180.0, "dense30_hop15")
    ivals = intervals(segs)
    assert len(segs) == 11
    assert ivals[-1] == (150.0, 180.0)


def test_dense_60s_exact():
    segs = sample_segments("t", 60.0, "dense30_hop15")
    assert intervals(segs) == [(0.0, 30.0), (15.0, 45.0), (30.0, 60.0)]


def test_dense_45s_terminal_anchor_dedupes():
    # regular windows (0,30),(15,45); terminal anchor (15,45) duplicates -> skipped
    segs = sample_segments("t", 45.0, "dense30_hop15")
    assert intervals(segs) == [(0.0, 30.0), (15.0, 45.0)]


def test_dense_44_5s_adds_full_terminal_window_not_tiny_one():
    # only (0,30) fits regularly; terminal anchor is a FULL window (14.5,44.5)
    segs = sample_segments("t", 44.5, "dense30_hop15")
    ivals = intervals(segs)
    assert ivals == [(0.0, 30.0), (14.5, 44.5)]
    assert segs[-1].duration_sec == 30.0  # never a tiny final window


def test_dense_31s():
    segs = sample_segments("t", 31.0, "dense30_hop15")
    assert intervals(segs) == [(0.0, 30.0), (1.0, 31.0)]


@pytest.mark.parametrize("duration", [10.0, 29.0, 30.0])
def test_dense_at_or_below_window_single_window(duration):
    segs = sample_segments("t", duration, "dense30_hop15")
    assert intervals(segs) == [(0.0, duration)]


# ---------------------------------------------------------------------------
# invariants / determinism / provenance / errors
# ---------------------------------------------------------------------------


ALL_STRATEGIES = [
    "first30", "center30", "three20", "three30", "five20", "dense30_hop15",
]


@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
@pytest.mark.parametrize("duration", [10.0, 29.0, 30.0, 31.0, 60.0, 180.0, 600.0])
def test_bounds_invariant_all_strategies(strategy, duration):
    segs = sample_segments("t", duration, strategy)
    assert_valid(segs, duration)
    assert [s.segment_index for s in segs] == list(range(len(segs)))


@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_determinism_and_stable_identity(strategy):
    a = sample_segments("track-42", 123.456, strategy)
    b = sample_segments("track-42", 123.456, strategy)
    assert a == b
    assert all(s.strategy_name == strategy for s in a)
    assert all(s.strategy_version == get_strategy(strategy).version for s in a)


def test_strategy_version_identity_is_explicit():
    assert get_strategy("first30").identity == "first30_v1"
    assert get_strategy("dense30_hop15").identity == "dense30_hop15_v1"


def test_provenance_fields_present():
    segs = sample_segments("track-x", 200.0, "three20", source_audio_hash="abc123")
    for seg in segs:
        assert seg.source_audio_hash == "abc123"
        assert seg.track_id == "track-x"
        d = seg.to_dict()
        assert d["duration_sec"] == pytest.approx(seg.actual_end_sec - seg.actual_start_sec)


def test_synthetic_hash_fallback_when_no_source_hash():
    segs = sample_segments("track-y", 200.0, "first30")
    assert segs[0].source_audio_hash is not None
    other = sample_segments("track-z", 200.0, "first30")
    assert segs[0].source_audio_hash != other[0].source_audio_hash


@pytest.mark.parametrize("bad", [0.0, -5.0, float("nan"), float("inf"), None, "60"])
def test_invalid_duration_raises_typed_failure(bad):
    with pytest.raises(InvalidTrackDurationError):
        sample_segments("t", bad, "first30")


def test_fractional_duration_supported():
    segs = sample_segments("t", 61.37, "center30")
    start, end = intervals(segs)[0]
    assert start == pytest.approx((61.37 - 30) / 2, abs=1e-6)
    assert end == pytest.approx(start + 30.0, abs=1e-6)


def test_unknown_strategy_rejected():
    with pytest.raises(KeyError):
        sample_segments("t", 100.0, "first45")


def test_requested_version_mismatch_rejected():
    with pytest.raises(KeyError):
        get_strategy("first30", version=99)
