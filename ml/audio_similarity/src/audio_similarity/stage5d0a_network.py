"""Persistent serial track deadlines and per-request provider circuit control."""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

from .stage5b1b_artifacts import atomic_json
from .stage5c2_rate_limit import classify_acquisition_failure


class WorkerStopped(RuntimeError):
    pass


class CircuitOpen(WorkerStopped):
    pass


class ProviderGovernor:
    """The worker holds the media-cache lock; stop commands only write a separate flag."""

    def __init__(self, directory: Path, *, now=None, sleep=time.sleep, rng=None):
        self.directory = directory
        self.path = directory / "network_state.json"
        self.stop_path = directory / "stop.requested"
        wall_origin, monotonic_origin = time.time(), time.monotonic()
        self.now = now or (lambda: wall_origin + time.monotonic() - monotonic_origin)
        self.sleep = sleep
        self.rng = rng or random.SystemRandom()
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {
            "schema_version": "stage5d0a-network-v1", "circuit": "CLOSED",
            "next_job_deadline": 0, "next_request_deadline": 0, "cooldown_deadline": 0,
            "last_job_start": None, "last_media_start": None,
            "jobs": [], "requests": [], "http_429_count": 0,
            "challenge_tracks": [], "degraded_tracks": [],
        }
        if self.state.get("schema_version") != "stage5d0a-network-v1":
            raise ValueError("invalid persistent network state")

    def save(self):
        atomic_json(self.path, self.state)

    def check(self):
        if self.state["circuit"] == "OPEN":
            raise CircuitOpen(self.state["circuit_reason"])
        if self.stop_path.exists():
            raise WorkerStopped("graceful stop requested")

    def wait(self, deadline):
        while self.now() < deadline:
            self.check()
            self.sleep(min(1.0, deadline - self.now()))
        self.check()

    def start_job(self, spotify_id):
        self.wait(max(self.state["next_job_deadline"], self.state["cooldown_deadline"]))
        start = self.now()
        delay = self.rng.uniform(30, 60)
        previous = self.state["last_job_start"]
        self.state["jobs"].append({"spotify_track_id": spotify_id, "start_unix": start,
                                   "previous_start_delta_seconds": None if previous is None else start - previous,
                                   "next_spacing_seconds": delay})
        self.state["last_job_start"] = start
        self.state["next_job_deadline"] = start + delay
        self.save()

    def open_circuit(self, reason):
        self.state.update(circuit="OPEN", circuit_reason=reason, opened_at_unix=self.now())
        self.save()
        raise CircuitOpen(reason)

    def call(self, spotify_id, kind, identity, operation):
        """Bound retries to four attempts and persist every response before waiting."""
        previous = [row for row in self.state["requests"] if
                    (row["spotify_track_id"], row["kind"], row["identity"]) == (spotify_id, kind, identity)]
        # Resume cannot reset a failed/in-flight operation's retry budget.
        used = 0
        for row in previous:
            used = 0 if row["status"] == "SUCCESS" else used + 1
        if used >= 4:
            raise RuntimeError(f"persistent retry budget exhausted for {kind}")
        for attempt in range(used + 1, 5):
            waiting_started = self.now()
            deadlines = [self.state["next_request_deadline"], self.state["cooldown_deadline"]]
            if kind == "MEDIA" and self.state["last_media_start"] is not None:
                deadlines.append(self.state["last_media_start"] + 30)
            if attempt > 1:
                deadlines.append(self.state["next_job_deadline"])
            self.wait(max(deadlines))
            start = self.now()
            row = {"spotify_track_id": spotify_id, "kind": kind, "identity": identity,
                   "attempt": attempt, "start_unix": start, "status": "IN_FLIGHT",
                   "actual_wait_seconds": start - waiting_started,
                   "required_deadline_unix": max(deadlines)}
            self.state["requests"].append(row)
            if kind == "MEDIA":
                self.state["last_media_start"] = start
            self.state["next_request_deadline"] = start + self.rng.uniform(1, 2)
            self.save()
            try:
                result = operation()
                warnings = result.get("warnings", []) if isinstance(result, dict) else getattr(result, "warnings", [])
                row["warnings"] = list(warnings)
                serious = [warning for warning in warnings if any(token in str(warning).casefold()
                           for token in ("http error 429", "http 429", "sign in to confirm", "captcha", "not a bot"))]
                if serious:
                    raise RuntimeError("; ".join(serious))
            except WorkerStopped:
                raise
            except Exception as exc:
                chain = []
                cause = exc
                while cause is not None and len(chain) < 5:
                    chain.append(str(cause))
                    cause = cause.__cause__
                message = " | ".join(dict.fromkeys(chain))
                diagnostic_error = RuntimeError(message)
                diagnostic_error.diagnostics = dict(getattr(exc, "diagnostics", {}) or {})
                diagnostic_error.diagnostics.setdefault("warnings", row.get("warnings", []))
                failure = classify_acquisition_failure(diagnostic_error)
                text = message.casefold()
                challenge = any(term in text for term in (
                    "sign in to confirm", "login_required", "captcha", "not a bot",
                    "verify you", "verification required", "unusual traffic"))
                row.update(status="FAILED", elapsed_seconds=self.now() - start,
                           error=message[:2000], challenge=challenge, **failure)
                self.save()
                if failure["http_status"] == 429:
                    self.state["http_429_count"] += 1
                    self.state["cooldown_deadline"] = max(
                        self.state["cooldown_deadline"], self.now() + 900,
                        self.now() + (failure["retry_after_seconds"] or 0))
                    self.save()
                    if self.state["http_429_count"] >= 2:
                        self.open_circuit("SECOND_YOUTUBE_HTTP_429")
                if challenge:
                    affected = self.state["challenge_tracks"]
                    if spotify_id not in affected:
                        affected.append(spotify_id)
                    self.save()
                    if len(affected) >= 2:
                        self.open_circuit("CONSECUTIVE_UNRELATED_TRACK_VERIFICATION_FAILURES")
                    raise
                if any(term in text for term in ("anti-abuse", "rate limit exceeded")):
                    self.open_circuit("EXPLICIT_PROVIDER_ANTI_ABUSE_RESPONSE")
                if not failure["retryable"] or attempt == 4:
                    raise
                delay = max(min(30, 2 ** attempt) + self.rng.uniform(0, 1),
                            failure["retry_after_seconds"] or 0)
                row["backoff_seconds"] = delay
                self.state["next_request_deadline"] = max(
                    self.state["next_request_deadline"], self.now() + delay)
                self.save()
            else:
                row.update(status="SUCCESS", elapsed_seconds=self.now() - start)
                self.save()
                return result

    def finish_job(self, *, success):
        if success:
            self.state["challenge_tracks"] = []
            self.state["degraded_tracks"] = []
            self.save()
            return
        if not self.state["jobs"]:
            return
        spotify_id = self.state["jobs"][-1]["spotify_track_id"]
        failed = [row for row in self.state["requests"] if row["spotify_track_id"] == spotify_id and row["status"] == "FAILED"]
        if not any(row.get("challenge") for row in failed):
            self.state["challenge_tracks"] = []
        if any(row.get("retryable") or row.get("http_status") == 403 for row in failed):
            affected = self.state["degraded_tracks"]
            if spotify_id not in affected:
                affected.append(spotify_id)
            if len(affected) >= 3:
                self.open_circuit("THREE_CONSECUTIVE_TRACK_PROVIDER_FAILURES")
        else:
            self.state["degraded_tracks"] = []
        self.save()
