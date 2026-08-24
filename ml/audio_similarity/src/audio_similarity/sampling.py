"""Deterministic full-song segment sampling (Phase 2A, design sections 11-14).

Sampling is a pure function of (track_id, track_duration_sec, strategy).
No encoder, audio decoding, or MERIT dependency lives here.

Every produced segment satisfies the invariant:

    0 <= start < end <= track_duration

Edge policy (design section 12):
    duration < window        -> return the entire valid track
    center window spills out -> shift the full window into valid bounds

Dense terminal policy v1: windows are emitted at fixed hops from 0 while a
complete window fits; exactly one terminal window anchored at the track end
is added unless it duplicates the last emitted window. No tiny final window.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Callable

# seconds resolution used for all arithmetic; keeps outputs stable across runs
_EPSILON = 1e-9


class InvalidTrackDurationError(ValueError):
    """Raised for non-finite or non-positive track durations."""


@dataclass(frozen=True)
class AudioSegment:
    """Provenance-complete sampled window of a longer track."""

    track_id: str | int
    segment_index: int
    track_duration_sec: float

    requested_start_sec: float
    requested_end_sec: float

    actual_start_sec: float
    actual_end_sec: float

    strategy_name: str
    strategy_version: int

    source_audio_hash: str | None = None

    @property
    def duration_sec(self) -> float:
        return self.actual_end_sec - self.actual_start_sec

    def to_dict(self) -> dict:
        d = {
            "track_id": self.track_id,
            "segment_index": self.segment_index,
            "track_duration_sec": self.track_duration_sec,
            "requested_start_sec": self.requested_start_sec,
            "requested_end_sec": self.requested_end_sec,
            "actual_start_sec": self.actual_start_sec,
            "actual_end_sec": self.actual_end_sec,
            "duration_sec": self.duration_sec,
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "source_audio_hash": self.source_audio_hash,
        }
        return d


def _validate_duration(track_duration_sec: float) -> float:
    if not isinstance(track_duration_sec, (int, float)) or isinstance(track_duration_sec, bool):
        raise InvalidTrackDurationError(f"track duration must be numeric, got {type(track_duration_sec)}")
    duration = float(track_duration_sec)
    if not math.isfinite(duration) or duration <= 0:
        raise InvalidTrackDurationError(f"track duration must be finite and > 0, got {duration}")
    return duration


def _round(value: float) -> float:
    return round(float(value), 6)


def _clip_window_to_track(
    requested_start: float,
    window: float,
    duration: float,
) -> tuple[float, float]:
    """Shift a complete window into [0, duration]; truncate only if duration < window."""
    if duration <= window + _EPSILON:
        return 0.0, duration
    start = min(max(requested_start, 0.0), duration - window)
    end = start + window
    # final safety clamp against floating drift
    if end > duration:
        start, end = max(0.0, duration - window), duration
    return _round(start), _round(end)


def _center_window(duration: float, center_fraction: float, window: float) -> tuple[float, float]:
    requested_start = duration * center_fraction - window / 2.0
    return _clip_window_to_track(requested_start, window, duration)


# ---------------------------------------------------------------------------
# Strategy implementations: each returns [(requested_start, requested_end)]
# before bounds-clipping; clipping happens uniformly afterwards.
# ---------------------------------------------------------------------------


def _first30(duration: float, cfg: dict) -> list[tuple[float, float]]:
    return [(0.0, min(cfg["window"], duration))]


def _center30(duration: float, cfg: dict) -> list[tuple[float, float]]:
    center = duration / 2.0
    w = cfg["window"]
    return [(max(0.0, center - w / 2.0), min(duration, center + w / 2.0))]


def _fraction_windows(
    duration: float,
    fractions: list[float],
    window: float,
) -> list[tuple[float, float]]:
    return [(duration * f - window / 2.0, duration * f + window / 2.0) for f in fractions]


def _three20(duration: float, cfg: dict) -> list[tuple[float, float]]:
    return _fraction_windows(duration, cfg["center_fractions"], cfg["window"])


def _three30(duration: float, cfg: dict) -> list[tuple[float, float]]:
    return _fraction_windows(duration, cfg["center_fractions"], cfg["window"])


def _five20(duration: float, cfg: dict) -> list[tuple[float, float]]:
    w = cfg["window"]
    count = cfg["count"]
    # evenly distributed across the valid placement range
    if duration <= w + _EPSILON:
        return [(0.0, duration)]
    span = duration - w
    centers = [span * k / (count - 1) + w / 2.0 for k in range(count)]
    return [(c - w / 2.0, c + w / 2.0) for c in centers]


def _dense30_hop15(duration: float, cfg: dict) -> list[tuple[float, float]]:
    w = cfg["window"]
    hop = cfg["hop"]
    if duration <= w + _EPSILON:
        return [(0.0, duration)]

    starts: list[float] = []
    start = 0.0
    while start + w <= duration + _EPSILON:
        starts.append(start)
        start += hop

    # terminal anchor: one window ending exactly at track end unless it
    # duplicates the last regular window (no tiny final segment, ever)
    terminal_start = _round(max(0.0, duration - w))
    if not starts or terminal_start > starts[-1] + _EPSILON:
        starts.append(terminal_start)

    return [(s, s + w) for s in starts]


@dataclass(frozen=True)
class SamplingStrategy:
    name: str
    version: int
    fn: Callable[[float, dict], list[tuple[float, float]]] = field(repr=False, compare=False)
    config: dict = field(default_factory=dict)

    @property
    def identity(self) -> str:
        return f"{self.name}_v{self.version}"


def _center5(duration: float, cfg: dict) -> list[tuple[float, float]]:
    w = cfg["window"]
    center = duration / 2.0
    return [(max(0.0, center - w / 2.0), min(duration, center + w / 2.0))]


STRATEGIES: dict[str, SamplingStrategy] = {
    s.name: s
    for s in [
        SamplingStrategy("first30", 1, _first30, {"window": 30.0}),
        SamplingStrategy("center30", 1, _center30, {"window": 30.0}),
        SamplingStrategy("center5", 1, _center5, {"window": 5.0}),
        SamplingStrategy("three20", 1, _three20, {"center_fractions": [0.25, 0.50, 0.75], "window": 20.0}),
        SamplingStrategy("three30", 1, _three30, {"center_fractions": [0.20, 0.50, 0.80], "window": 30.0}),
        SamplingStrategy("five20", 1, _five20, {"count": 5, "window": 20.0}),
        SamplingStrategy("dense30_hop15", 1, _dense30_hop15, {"window": 30.0, "hop": 15.0}),
    ]
}

DEFAULT_STRATEGY_NAMES = [
    "first30",
    "center30",
    "center5",
    "three20",
    "three30",
    "five20",
    "dense30_hop15",
]


def get_strategy(name: str, version: int | None = None) -> SamplingStrategy:
    if name not in STRATEGIES:
        raise KeyError(f"unknown sampling strategy '{name}'; known: {sorted(STRATEGIES)}")
    strategy = STRATEGIES[name]
    if version is not None and version != strategy.version:
        raise KeyError(f"strategy '{name}' has no version {version}")
    return strategy


def audio_hash_for_track(source_audio_hash: str | None, track_id: str | int) -> str | None:
    """Stable short provenance token when a real file hash is unavailable."""
    if source_audio_hash:
        return source_audio_hash
    digest = hashlib.sha256(f"synthetic:{track_id}".encode()).hexdigest()
    return digest[:16]


def sample_segments(
    track_id: str | int,
    track_duration_sec: float,
    strategy: SamplingStrategy | str = "three20",
    source_audio_hash: str | None = None,
) -> list[AudioSegment]:
    """Deterministically produce provenance-complete segments for one track."""
    duration = _validate_duration(track_duration_sec)
    if isinstance(strategy, str):
        strategy = get_strategy(strategy)

    segments: list[AudioSegment] = []
    seen: set[tuple[float, float]] = set()
    resolved_hash = source_audio_hash if source_audio_hash is not None else audio_hash_for_track(None, track_id)

    raw_windows = sorted(strategy.fn(duration, strategy.config), key=lambda w: (w[0], w[1]))
    index = 0
    for requested_start, requested_end in raw_windows:
        actual_start, actual_end = _clip_window_to_track(requested_start, requested_end - requested_start, duration)
        key = (actual_start, actual_end)
        if key in seen or actual_end - actual_start <= _EPSILON:
            continue
        seen.add(key)
        segments.append(
            AudioSegment(
                track_id=track_id,
                segment_index=index,
                track_duration_sec=_round(duration),
                requested_start_sec=_round(requested_start),
                requested_end_sec=_round(min(requested_end, duration)),
                actual_start_sec=actual_start,
                actual_end_sec=actual_end,
                strategy_name=strategy.name,
                strategy_version=strategy.version,
                source_audio_hash=resolved_hash,
            )
        )
        index += 1

    if not segments:
        raise InvalidTrackDurationError(f"sampling produced no segments for duration {duration}")

    for seg in segments:
        assert 0 <= seg.actual_start_sec < seg.actual_end_sec <= duration + _EPSILON, (
            f"bounds invariant violated: {seg}"
        )
    return segments
