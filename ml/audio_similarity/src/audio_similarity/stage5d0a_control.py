"""Persistent queue, pacing, and circuit-breaker controls for Stage 5D.0A."""
from __future__ import annotations

import random
import json
import fcntl
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .stage5b1a_models import Stage5B1AValidationError
from .stage5b1b_artifacts import atomic_json
from .stage5d0a_manifest import (
    BATCH_MANIFEST_SCHEMA,
    MAX_BATCH_SIZE,
    document_sha256,
)


TERMINAL_STATES = frozenset(
    {"COMPLETE", "MANUAL_TAIL", "ACQUISITION_FAILED", "MATERIALIZATION_FAILED"}
)
ACTIVE_STATES = frozenset(
    {
        "PENDING",
        "DISCOVERING",
        "RESOLVED",
        "ACQUIRING",
        "SOURCE_RETAINED",
        "MATERIALIZING",
    }
)
ALL_STATES = TERMINAL_STATES | ACTIVE_STATES
CHALLENGE_CATEGORIES = frozenset(
    {"LOGIN_REQUIRED", "VERIFICATION_REQUIRED", "CAPTCHA_CHALLENGE", "ANTI_BOT_CHALLENGE"}
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TrackJobPacingPolicy:
    minimum_seconds: float = 30.0
    maximum_seconds: float = 60.0
    random_seed: str = "stage5d0a-track-job-pacing-v1"

    def __post_init__(self) -> None:
        if self.minimum_seconds < 30:
            raise ValueError("track-job pacing cannot be below 30 seconds")
        if self.maximum_seconds < self.minimum_seconds:
            raise ValueError("track-job pacing maximum is below its minimum")
        if self.maximum_seconds > 60:
            raise ValueError("ordinary track-job pacing cannot exceed 60 seconds")


class TrackJobLimiter:
    """Enforce one randomized outer deadline across each network-facing track job."""

    def __init__(
        self,
        policy: TrackJobPacingPolicy | None = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        last_start: float | None = None,
    ) -> None:
        self.policy = policy or TrackJobPacingPolicy()
        self._monotonic = monotonic
        self._sleep = sleep
        self._rng = rng or random.Random(self.policy.random_seed)
        self.last_start = last_start
        self.next_delay = self._new_delay()
        self.starts: list[dict[str, Any]] = []

    def _new_delay(self) -> float:
        return self._rng.uniform(self.policy.minimum_seconds, self.policy.maximum_seconds)

    def wait_and_start(
        self, track_id: str, *, required_backoff_seconds: float = 0.0
    ) -> dict[str, Any]:
        if required_backoff_seconds < 0:
            raise ValueError("required backoff cannot be negative")
        now = self._monotonic()
        elapsed = None if self.last_start is None else now - self.last_start
        remaining = 0.0 if elapsed is None else max(0.0, self.next_delay - elapsed)
        required = max(remaining, required_backoff_seconds)
        if required:
            self._sleep(required)
        started = self._monotonic()
        prior_delta = None if self.last_start is None else started - self.last_start
        ordinary_delay = self.next_delay
        self.last_start = started
        self.next_delay = self._new_delay()
        row = {
            "track_id": track_id,
            "started_monotonic": started,
            "previous_start_delta_seconds": prior_delta,
            "ordinary_required_spacing_seconds": ordinary_delay,
            "external_backoff_seconds": required_backoff_seconds,
            "actual_wait_seconds": required,
            "spacing_compliant": (
                True if prior_delta is None else prior_delta + 1e-9 >= ordinary_delay
            ),
            "next_ordinary_spacing_seconds": self.next_delay,
        }
        self.starts.append(row)
        return row


class PersistentCircuitBreaker:
    """Persist conservative provider degradation signals across worker restarts."""

    def __init__(
        self,
        state: dict[str, Any] | None = None,
        *,
        first_429_cooldown_seconds: float = 900.0,
        consecutive_challenge_limit: int = 2,
    ) -> None:
        self.state = state or {
            "status": "CLOSED",
            "opened_reason": None,
            "opened_at": None,
            "http_429_count": 0,
            "consecutive_challenge_count": 0,
            "first_429_cooldown_seconds": first_429_cooldown_seconds,
            "events": [],
        }
        self.challenge_limit = consecutive_challenge_limit

    def record(self, track_id: str, category: str) -> dict[str, Any]:
        event = {"track_id": track_id, "category": category, "timestamp": _now()}
        self.state["events"].append(event)
        cooldown = 0.0
        if category == "PROVIDER_RATE_LIMITED":
            self.state["http_429_count"] += 1
            self.state["consecutive_challenge_count"] = 0
            if self.state["http_429_count"] >= 2:
                self._open("SECOND_HTTP_429_AFTER_COOLDOWN")
            else:
                cooldown = float(self.state["first_429_cooldown_seconds"])
        elif category in CHALLENGE_CATEGORIES:
            self.state["consecutive_challenge_count"] += 1
            if self.state["consecutive_challenge_count"] >= self.challenge_limit:
                self._open("REPEATED_VERIFICATION_OR_CHALLENGE")
        else:
            self.state["consecutive_challenge_count"] = 0
        return {"circuit_status": self.state["status"], "cooldown_seconds": cooldown}

    def _open(self, reason: str) -> None:
        self.state["status"] = "OPEN"
        self.state["opened_reason"] = reason
        self.state["opened_at"] = _now()


def initial_runtime_state(batch_manifest: dict[str, Any]) -> dict[str, Any]:
    if batch_manifest.get("schema_version") != BATCH_MANIFEST_SCHEMA:
        raise Stage5B1AValidationError("invalid Stage 5D batch manifest")
    if batch_manifest.get("batch_number") != 1:
        raise Stage5B1AValidationError("Stage 5D.0A may initialize only Batch 0001")
    tracks = batch_manifest.get("tracks")
    if not isinstance(tracks, list) or len(tracks) > MAX_BATCH_SIZE:
        raise Stage5B1AValidationError("invalid Batch 0001 track count")
    return {
        "schema_version": "stage5d0a-runtime-state-v1",
        "batch_number": 1,
        "batch_manifest_sha256": document_sha256(batch_manifest),
        "created_at": _now(),
        "updated_at": _now(),
        "stop_requested": False,
        "worker_status": "STOPPED",
        "circuit_breaker": PersistentCircuitBreaker().state,
        "tracks": {
            row["spotify_track_id"]: {
                "state": "PENDING",
                "attempt_count": 0,
                "updated_at": _now(),
                "failure_category": None,
            }
            for row in tracks
        },
    }


def persist_runtime_state(path: str | Path, state: dict[str, Any]) -> None:
    target = Path(path)
    if state.get("schema_version") != "stage5d0a-runtime-state-v1":
        raise Stage5B1AValidationError("invalid Stage 5D runtime state")
    if state.get("batch_number") != 1 or len(state.get("tracks", {})) > MAX_BATCH_SIZE:
        raise Stage5B1AValidationError("runtime state exceeds Stage 5D.0A scope")
    if any(row.get("state") not in ALL_STATES for row in state["tracks"].values()):
        raise Stage5B1AValidationError("runtime state contains an invalid track state")
    state["updated_at"] = _now()
    atomic_json(target, state)


def request_graceful_stop(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    state = json.loads(target.read_text(encoding="utf-8"))
    state["stop_requested"] = True
    persist_runtime_state(target, state)
    return state


def request_resume(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    state = json.loads(target.read_text(encoding="utf-8"))
    if state.get("circuit_breaker", {}).get("status") == "OPEN":
        raise Stage5B1AValidationError(
            "cannot resume while the provider circuit breaker is open"
        )
    state["stop_requested"] = False
    persist_runtime_state(target, state)
    return state


def runtime_status(state: dict[str, Any]) -> dict[str, Any]:
    counts = {name: 0 for name in sorted(ALL_STATES)}
    for row in state["tracks"].values():
        counts[row["state"]] += 1
    return {
        "batch": "0001",
        "worker_status": state["worker_status"],
        "stop_requested": state["stop_requested"],
        "track_state_counts": counts,
        "terminal_count": sum(counts[name] for name in TERMINAL_STATES),
        "total_count": len(state["tracks"]),
        "circuit": state["circuit_breaker"],
    }


def run_batch_one(
    batch_manifest: dict[str, Any],
    runtime_path: str | Path,
    processor: Any,
    *,
    limiter: TrackJobLimiter | None = None,
) -> dict[str, Any]:
    """Run at most Batch 0001 once, checkpointing every state transition.

    The processor boundary deliberately separates catalog-independent queue safety from
    provider/materialization work. ``inspect(track)`` must return whether a network job
    is required; ``process(track, condition)`` returns a terminal state and diagnostics.
    """
    if batch_manifest.get("schema_version") != BATCH_MANIFEST_SCHEMA:
        raise Stage5B1AValidationError("invalid Stage 5D batch manifest")
    if batch_manifest.get("batch_number") != 1:
        raise Stage5B1AValidationError("Stage 5D.0A may run only Batch 0001")
    tracks = batch_manifest.get("tracks", [])
    if len(tracks) > MAX_BATCH_SIZE:
        raise Stage5B1AValidationError("Stage 5D.0A cannot process over 500 tracks")
    path = Path(runtime_path)
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Stage5B1AValidationError(
                "another Stage 5D Batch 0001 worker is active"
            ) from exc
        try:
            return _run_batch_one_locked(
                batch_manifest, path, processor, tracks, limiter=limiter
            )
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _run_batch_one_locked(
    batch_manifest: dict[str, Any],
    path: Path,
    processor: Any,
    tracks: list[dict[str, Any]],
    *,
    limiter: TrackJobLimiter | None,
) -> dict[str, Any]:
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("batch_manifest_sha256") != document_sha256(batch_manifest):
        raise Stage5B1AValidationError("runtime state does not match Batch 0001")
    if state.get("circuit_breaker", {}).get("status") == "OPEN":
        return runtime_status(state)
    active_limiter = limiter or TrackJobLimiter()
    breaker = PersistentCircuitBreaker(state["circuit_breaker"])
    pending_backoff = 0.0
    state["worker_status"] = "RUNNING"
    persist_runtime_state(path, state)
    try:
        for track in tracks:
            spotify_id = track["spotify_track_id"]
            row = state["tracks"][spotify_id]
            if row["state"] in TERMINAL_STATES:
                continue
            if state["stop_requested"] or breaker.state["status"] == "OPEN":
                break
            condition = processor.inspect(track)
            if condition not in {
                "SOURCE_AND_REPRESENTATION_PRESENT",
                "SOURCE_PRESENT_REPRESENTATION_MISSING",
                "REPRESENTATION_PRESENT_SOURCE_MISSING",
                "BOTH_MISSING",
            }:
                raise Stage5B1AValidationError("processor returned an invalid cache state")
            network_required = condition in {
                "REPRESENTATION_PRESENT_SOURCE_MISSING",
                "BOTH_MISSING",
            }
            if network_required:
                start = active_limiter.wait_and_start(
                    spotify_id, required_backoff_seconds=pending_backoff
                )
                state.setdefault("network_job_starts", []).append(start)
                pending_backoff = 0.0
            row["state"] = "DISCOVERING" if condition == "BOTH_MISSING" else (
                "ACQUIRING" if network_required else "MATERIALIZING"
            )
            row["attempt_count"] += 1
            row["cache_condition"] = condition
            row["updated_at"] = _now()
            persist_runtime_state(path, state)
            try:
                outcome = processor.process(track, condition)
            except Exception as exc:
                row["state"] = "ACQUISITION_FAILED" if network_required else (
                    "MATERIALIZATION_FAILED"
                )
                row["failure_category"] = type(exc).__name__
                row["failure_detail"] = str(exc)[:2000]
                row["updated_at"] = _now()
                persist_runtime_state(path, state)
                continue
            terminal = outcome.get("state")
            if terminal not in TERMINAL_STATES:
                raise Stage5B1AValidationError(
                    "processor must return a terminal per-track state"
                )
            row.update(
                {
                    "state": terminal,
                    "failure_category": outcome.get("failure_category"),
                    "failure_detail": outcome.get("failure_detail"),
                    "result": outcome.get("result", {}),
                    "updated_at": _now(),
                }
            )
            signal = outcome.get("provider_signal")
            if signal:
                circuit = breaker.record(spotify_id, signal)
                pending_backoff = max(
                    pending_backoff, float(circuit["cooldown_seconds"])
                )
            state["circuit_breaker"] = breaker.state
            persist_runtime_state(path, state)
    finally:
        state["worker_status"] = (
            "CIRCUIT_OPEN"
            if breaker.state["status"] == "OPEN"
            else "STOPPED"
            if state["stop_requested"]
            else "COMPLETE"
            if all(row["state"] in TERMINAL_STATES for row in state["tracks"].values())
            else "INTERRUPTED"
        )
        state["circuit_breaker"] = breaker.state
        persist_runtime_state(path, state)
    return runtime_status(state)


def batch_metrics(state: dict[str, Any]) -> dict[str, Any]:
    """Summarize a persisted runtime checkpoint without disturbing the worker."""
    status = runtime_status(state)
    starts = state.get("network_job_starts", [])
    deltas = [
        float(row["previous_start_delta_seconds"])
        for row in starts
        if row.get("previous_start_delta_seconds") is not None
    ]
    results = [row.get("result", {}) for row in state["tracks"].values()]
    signals = state.get("circuit_breaker", {}).get("events", [])
    track_counts = status["track_state_counts"]
    if status["circuit"]["status"] == "OPEN":
        verdict = "BATCH_500_CIRCUIT_BREAKER_STOPPED"
    elif status["worker_status"] == "COMPLETE":
        warning_count = sum(bool(result.get("provider_warnings")) for result in results)
        verdict = (
            "BATCH_500_COMPLETED_WITH_PROVIDER_WARNINGS"
            if warning_count
            else "BATCH_500_HEALTHY"
        )
    else:
        verdict = "BATCH_500_PIPELINE_FAILED"
    return {
        "schema_version": "stage5d0a-batch-metrics-v1",
        "batch_number": 1,
        "requested_batch_size": len(state["tracks"]),
        "complete_tracks": track_counts["COMPLETE"],
        "manual_tail": track_counts["MANUAL_TAIL"],
        "acquisition_failures": track_counts["ACQUISITION_FAILED"],
        "materialization_failures": track_counts["MATERIALIZATION_FAILED"],
        "network_track_jobs": len(starts),
        "total_downloaded_bytes": sum(
            int(result.get("downloaded_bytes", 0)) for result in results
        ),
        "cache_skips": sum(
            row.get("cache_condition") == "SOURCE_AND_REPRESENTATION_PRESENT"
            for row in state["tracks"].values()
        ),
        "source_retained_count": sum(
            bool(result.get("source_retained")) for result in results
        ),
        "representation_complete_count": sum(
            bool(result.get("representation_complete")) for result in results
        ),
        "minimum_track_start_spacing_seconds": min(deltas) if deltas else None,
        "mean_track_start_spacing_seconds": statistics.mean(deltas) if deltas else None,
        "median_track_start_spacing_seconds": (
            statistics.median(deltas) if deltas else None
        ),
        "maximum_track_start_spacing_seconds": max(deltas) if deltas else None,
        "all_track_start_spacings_at_least_30_seconds": all(
            value >= 30 for value in deltas
        ),
        "http_429_count": sum(
            event["category"] == "PROVIDER_RATE_LIMITED" for event in signals
        ),
        "anti_bot_challenge_count": sum(
            event["category"] in CHALLENGE_CATEGORIES for event in signals
        ),
        "circuit_breaker_opened": status["circuit"]["status"] == "OPEN",
        "circuit_breaker_reason": status["circuit"].get("opened_reason"),
        "batch_0002_started": False,
        "verdict": verdict,
    }
