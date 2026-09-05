from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from audio_similarity.stage5c2_rate_limit import (
    AcquisitionFailed,
    AcquisitionRetryPolicy,
    RateLimitedAcquirer,
    classify_acquisition_failure,
)


TRACK = {
    "spotify_track_id": "spotify-id",
    "selected_youtube_video_id": "abcdefghijk",
}


class _Clock:
    def __init__(self) -> None:
        self.value = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


class _Failure(RuntimeError):
    def __init__(self, message: str, **diagnostics) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


class _SequenceAcquirer:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def acquire(self, _track, _output_dir):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _wrapper(outcomes, *, clock=None, policy=None):
    clock = clock or _Clock()
    return RateLimitedAcquirer(
        _SequenceAcquirer(outcomes),
        policy=policy or AcquisitionRetryPolicy(jitter_max_seconds=0),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        utc_now=lambda: "2026-09-04T00:00:00+00:00",
        wall_now=lambda: datetime(2026, 9, 4, tzinfo=timezone.utc),
    ), clock


def test_serial_attempt_starts_are_spaced_at_least_20_seconds(tmp_path: Path) -> None:
    success = {"provider_result": "SUCCESS", "warnings": []}
    wrapper, clock = _wrapper([success, success])
    wrapper.acquire(TRACK, tmp_path)
    wrapper.acquire(TRACK, tmp_path)
    assert clock.sleeps == [20.0]
    assert wrapper.attempts[1]["previous_request_start_delta_seconds"] == 20.0
    assert wrapper.attempts[1]["minimum_spacing_compliant"] is True


def test_resumed_process_preserves_previous_start_spacing(tmp_path: Path) -> None:
    clock = _Clock()
    wrapper = RateLimitedAcquirer(
        _SequenceAcquirer([{"provider_result": "SUCCESS", "warnings": []}]),
        policy=AcquisitionRetryPolicy(jitter_max_seconds=0),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        utc_now=lambda: "2026-09-04T00:00:10+00:00",
        initial_elapsed_since_previous_start_seconds=7.0,
    )
    wrapper.acquire(TRACK, tmp_path)
    assert clock.sleeps == [13.0]
    assert wrapper.attempts[0]["previous_request_start_delta_seconds"] == 20.0
    assert wrapper.attempts[0]["minimum_spacing_compliant"] is True


def test_retry_is_rate_limited_and_retry_after_is_honored(tmp_path: Path) -> None:
    failure = _Failure("HTTP Error 429", http_status=429, retry_after_seconds=31)
    success = {"provider_result": "SUCCESS", "warnings": []}
    wrapper, clock = _wrapper([failure, success])
    result = wrapper.acquire(TRACK, tmp_path)
    assert clock.sleeps == [31.0]
    assert result["acquisition_attempts"][0]["retry_reason"] == "PROVIDER_RATE_LIMITED"
    assert result["acquisition_attempts"][1]["previous_request_start_delta_seconds"] == 31.0


def test_exponential_backoff_is_bounded_and_jitter_never_reduces_spacing(
    tmp_path: Path,
) -> None:
    failures = [_Failure("HTTP Error 503") for _ in range(3)]
    success = {"provider_result": "SUCCESS", "warnings": []}
    policy = AcquisitionRetryPolicy(
        exponential_base_seconds=50,
        exponential_cap_seconds=25,
        jitter_max_seconds=0,
    )
    wrapper, clock = _wrapper([*failures, success], policy=policy)
    wrapper.acquire(TRACK, tmp_path)
    assert clock.sleeps == [25.0, 25.0, 25.0]
    assert all(delta >= 20 for delta in clock.sleeps)


@pytest.mark.parametrize("status", [429, 500, 502, 503, 599])
def test_transient_http_failures_are_retryable(status: int) -> None:
    result = classify_acquisition_failure(_Failure(f"HTTP Error {status}"))
    assert result["retryable"] is True


@pytest.mark.parametrize(
    "message",
    ["Private video", "Video unavailable", "invalid video ID", "unsupported URL"],
)
def test_permanent_failures_are_not_retried(message: str, tmp_path: Path) -> None:
    wrapper, _ = _wrapper([_Failure(message)])
    with pytest.raises(AcquisitionFailed) as captured:
        wrapper.acquire(TRACK, tmp_path)
    assert captured.value.retryable is False
    assert len(captured.value.attempts) == 1


def test_retries_stop_after_four_total_attempts(tmp_path: Path) -> None:
    wrapper, _ = _wrapper([_Failure("timed out") for _ in range(4)])
    with pytest.raises(AcquisitionFailed) as captured:
        wrapper.acquire(TRACK, tmp_path)
    assert len(captured.value.attempts) == 4
    assert captured.value.attempts[-1]["final_outcome"] == "FAILED"
