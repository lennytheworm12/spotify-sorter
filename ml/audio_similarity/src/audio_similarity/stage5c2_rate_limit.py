"""Serial media-acquisition rate limiting and bounded transient retries."""
from __future__ import annotations

import email.utils
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


HTTP_STATUS = re.compile(r"(?:HTTP(?: Error)?|status(?: code)?)[ :]+(\d{3})", re.I)
RETRY_AFTER = re.compile(r"Retry-After[ :=]+([^\s,;]+(?:, [^\r\n]+)?)", re.I)


@dataclass(frozen=True)
class AcquisitionRetryPolicy:
    minimum_start_spacing_seconds: float = 20.0
    maximum_attempts: int = 4
    exponential_base_seconds: float = 2.0
    exponential_cap_seconds: float = 30.0
    jitter_max_seconds: float = 1.0
    random_seed: str = "stage5c2-acquisition-jitter-v1"

    def __post_init__(self) -> None:
        if self.minimum_start_spacing_seconds < 20.0:
            raise ValueError("media acquisition spacing cannot be below 20 seconds")
        if not 1 <= self.maximum_attempts <= 4:
            raise ValueError("media acquisition attempts must be bounded to 1..4")
        if min(self.exponential_base_seconds, self.exponential_cap_seconds) < 0:
            raise ValueError("backoff values cannot be negative")
        if self.jitter_max_seconds < 0:
            raise ValueError("jitter cannot be negative")


class AcquisitionFailed(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        category: str,
        retryable: bool,
        attempts: list[dict[str, Any]],
    ) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable
        self.attempts = attempts
        self.diagnostics = {
            "failure_category": category,
            "retryable": retryable,
            "attempts": attempts,
            "warnings": [warning for row in attempts for warning in row.get("provider_warnings", [])],
            "errors": [row["provider_error"] for row in attempts if row.get("provider_error")],
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_status(message: str, diagnostics: dict[str, Any]) -> int | None:
    raw = diagnostics.get("http_status")
    if isinstance(raw, int):
        return raw
    match = HTTP_STATUS.search(message)
    return int(match.group(1)) if match else None


def _retry_after(message: str, diagnostics: dict[str, Any], wall_now: Callable[[], datetime]) -> float | None:
    raw = diagnostics.get("retry_after_seconds")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw >= 0:
        return float(raw)
    match = RETRY_AFTER.search(message)
    if not match:
        return None
    value = match.group(1).strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, (parsed - wall_now()).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def classify_acquisition_failure(
    exc: Exception,
    *,
    wall_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    diagnostics = getattr(exc, "diagnostics", {})
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    message = str(exc)
    lowered = message.casefold()
    status = _http_status(message, diagnostics)
    if status == 429:
        category, retryable = "PROVIDER_RATE_LIMITED", True
    elif status is not None and 500 <= status <= 599:
        category, retryable = "ACQUISITION_FAILED", True
    elif any(
        token in lowered
        for token in (
            "timed out",
            "timeout",
            "connection reset",
            "connection aborted",
            "temporary failure",
            "temporarily unavailable",
            "name resolution",
            "dns",
            "remote end closed",
        )
    ):
        category, retryable = "ACQUISITION_FAILED", True
    elif any(
        token in lowered
        for token in (
            "private video",
            "video unavailable",
            "this video is unavailable",
            "invalid video id",
            "copyright",
            "unsupported url",
            "members-only",
        )
    ):
        category, retryable = "MEDIA_UNAVAILABLE", False
    else:
        category, retryable = "ACQUISITION_FAILED", False
    return {
        "category": category,
        "retryable": retryable,
        "http_status": status,
        "retry_after_seconds": _retry_after(message, diagnostics, wall_now),
        "warnings": list(diagnostics.get("warnings", [])),
        "errors": [str(value) for value in diagnostics.get("errors", [message])],
    }


class RateLimitedAcquirer:
    """Wrap an exact-ID acquirer with one global serial start-rate boundary."""

    def __init__(
        self,
        acquirer: Any,
        *,
        policy: AcquisitionRetryPolicy | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        utc_now: Callable[[], str] = _utc_now,
        wall_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        rng: random.Random | None = None,
    ) -> None:
        self.acquirer = acquirer
        self.policy = policy or AcquisitionRetryPolicy()
        self._monotonic = monotonic
        self._sleep = sleep
        self._utc_now = utc_now
        self._wall_now = wall_now
        self._rng = rng or random.Random(self.policy.random_seed)
        self._last_start: float | None = None
        self.attempts: list[dict[str, Any]] = []

    def _wait_until_allowed(self, requested_backoff: float) -> tuple[float, float]:
        now = self._monotonic()
        remaining_spacing = (
            0.0
            if self._last_start is None
            else max(0.0, self.policy.minimum_start_spacing_seconds - (now - self._last_start))
        )
        required = max(remaining_spacing, requested_backoff)
        before = self._monotonic()
        if required > 0:
            self._sleep(required)
        return required, self._monotonic() - before

    def acquire(self, track: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        per_track: list[dict[str, Any]] = []
        requested_backoff = 0.0
        for attempt_number in range(1, self.policy.maximum_attempts + 1):
            required_delay, actual_delay = self._wait_until_allowed(requested_backoff)
            started = self._monotonic()
            prior_delta = None if self._last_start is None else started - self._last_start
            self._last_start = started
            attempt = {
                "track_id": track["spotify_track_id"],
                "video_id": track["selected_youtube_video_id"],
                "attempt_number": attempt_number,
                "request_start_timestamp": self._utc_now(),
                "previous_request_start_delta_seconds": prior_delta,
                "minimum_spacing_seconds": self.policy.minimum_start_spacing_seconds,
                "minimum_spacing_compliant": (
                    True
                    if prior_delta is None
                    else prior_delta + 1e-9 >= self.policy.minimum_start_spacing_seconds
                ),
                "required_delay_before_attempt_seconds": required_delay,
                "actual_delay_before_attempt_seconds": actual_delay,
                "retry_reason": None,
                "retry_after_seconds": None,
                "calculated_backoff_seconds": requested_backoff,
                "provider_warnings": [],
                "provider_error": None,
                "final_outcome": None,
            }
            started_perf = self._monotonic()
            try:
                result = self.acquirer.acquire(track, output_dir)
                attempt["provider_warnings"] = list(result.get("warnings", []))
                attempt["final_outcome"] = "SUCCESS"
                attempt["acquisition_duration_seconds"] = self._monotonic() - started_perf
                per_track.append(attempt)
                self.attempts.append(attempt)
                return result | {"acquisition_attempts": per_track}
            except Exception as exc:
                failure = classify_acquisition_failure(exc, wall_now=self._wall_now)
                attempt["provider_warnings"] = failure["warnings"]
                attempt["provider_error"] = str(exc)[:2000]
                attempt["http_status"] = failure["http_status"]
                attempt["retry_after_seconds"] = failure["retry_after_seconds"]
                attempt["retry_reason"] = failure["category"]
                attempt["acquisition_duration_seconds"] = self._monotonic() - started_perf
                should_retry = failure["retryable"] and attempt_number < self.policy.maximum_attempts
                attempt["final_outcome"] = "RETRY_SCHEDULED" if should_retry else "FAILED"
                per_track.append(attempt)
                self.attempts.append(attempt)
                if not should_retry:
                    raise AcquisitionFailed(
                        str(exc),
                        category=failure["category"],
                        retryable=failure["retryable"],
                        attempts=per_track,
                    ) from exc
                exponential = min(
                    self.policy.exponential_cap_seconds,
                    self.policy.exponential_base_seconds * (2 ** (attempt_number - 1)),
                )
                jitter = self._rng.uniform(0.0, self.policy.jitter_max_seconds)
                requested_backoff = max(
                    exponential + jitter,
                    failure["retry_after_seconds"] or 0.0,
                )
                attempt["exponential_backoff_seconds"] = exponential
                attempt["jitter_seconds"] = jitter
                attempt["calculated_backoff_seconds"] = requested_backoff
        raise AssertionError("bounded acquisition loop terminated unexpectedly")
