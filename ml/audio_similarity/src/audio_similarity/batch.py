"""Resumable batch encoding pipeline (Phase 1 doc, sections 12, 24).

Correctness-first: batch_size=1 reference path, per-track failures recorded
explicitly, atomic checkpointed persistence, resume skips only rows whose
(track_id, analysis_key) matches the current model/preprocessing identity.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from .audio import AudioDecodeError, DurationInvalidError, preprocess_file
from .merit_encoder import MeritEncoder, ModelOutputInvalidError
from .storage import EmbeddingStore, FailureStore, analysis_key


class BatchInterrupted(Exception):
    """Injected fault used by interruption/resume tests."""


FAILURE_RETRYABLE = {
    "DECODE_FAILED": False,
    "DURATION_INVALID": False,
    "MODEL_FAILED": True,
    "OUTPUT_INVALID": False,
}


@dataclass
class BatchSummary:
    attempted: int = 0
    skipped_completed: int = 0
    succeeded: int = 0
    failed: int = 0
    wall_time_sec: float = 0.0
    per_track_sec: list[float] = field(default_factory=list)
    peak_ram_mb: float = 0.0
    peak_vram_mb: float = 0.0

    def percentiles(self) -> dict:
        if not self.per_track_sec:
            return {"p50_seconds_per_track": None, "p95_seconds_per_track": None}
        arr = np.asarray(self.per_track_sec)
        return {
            "p50_seconds_per_track": float(np.percentile(arr, 50)),
            "p95_seconds_per_track": float(np.percentile(arr, 95)),
            "tracks_per_hour": float(len(arr) / max(arr.sum(), 1e-9) * 3600),
        }

    def to_dict(self) -> dict:
        peak_ram_mb = 0.0
        try:
            import resource

            peak_ram_mb = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
        except Exception:
            pass
        return {
            "attempted": self.attempted,
            "skipped_completed": self.skipped_completed,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "wall_time_sec": round(self.wall_time_sec, 3),
            **self.percentiles(),
            "peak_vram_mb": round(self.peak_vram_mb, 1),
            "peak_ram_mb": round(peak_ram_mb, 1),
        }


def classify_failure(exc: Exception) -> str:
    if isinstance(exc, DurationInvalidError):
        return "DURATION_INVALID"
    if isinstance(exc, AudioDecodeError):
        return "DECODE_FAILED"
    if isinstance(exc, ModelOutputInvalidError):
        return "OUTPUT_INVALID"
    return "MODEL_FAILED"


def run_batch(
    manifest_rows: list[dict],
    encoder: MeritEncoder,
    embedding_store: EmbeddingStore,
    failure_store: FailureStore,
    audio_root: Path | str,
    checkpoint_every: int = 10,
    fail_after: int | None = None,
    progress_callback=None,
) -> BatchSummary:
    """Encode manifest rows; resumable; never drops a failed track silently.

    ``fail_after`` injects a deterministic fault for interruption tests.
    """
    key = analysis_key(encoder.provenance.to_dict())
    done_ids = embedding_store.completed_track_ids(key)
    failed_ids = failure_store.failed_track_ids(key)

    audio_root = Path(audio_root)
    summary = BatchSummary()
    start = time.perf_counter()

    pending_embedding_rows: list[dict] = []
    pending_failure_rows: list[dict] = []

    def flush() -> None:
        if pending_embedding_rows:
            embedding_store.append(list(pending_embedding_rows))
            pending_embedding_rows.clear()
        if pending_failure_rows:
            failure_store.append(list(pending_failure_rows))
            pending_failure_rows.clear()

    for index, row in enumerate(manifest_rows):
        if fail_after is not None and summary.attempted >= fail_after:
            raise BatchInterrupted(f"injected fault after {summary.attempted} attempts")
        track_id = int(row["track_id"])
        if track_id in done_ids:
            summary.skipped_completed += 1
            continue
        # prior failures are retried on resume (retryable ones especially);
        # non-retryable decode failures are re-attempted cheaply and re-logged
        _ = failed_ids  # kept for observability; failures are not terminal skips

        summary.attempted += 1
        track_start = time.perf_counter()
        try:
            t0 = time.perf_counter()
            wav = preprocess_file(audio_root / row["relative_audio_path"])
            preprocess_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            result = encoder.encode_waveform(wav)
            inference_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            pending_embedding_rows.append(
                {
                    "track_id": track_id,
                    "analysis_key": key,
                    "melody": result.melody.astype(np.float32),
                    "rhythm": result.rhythm.astype(np.float32),
                    "timbre": result.timbre.astype(np.float32),
                    "mert_general": result.mert_general.astype(np.float32),
                    "melody_norm": result.diagnostics["melody_norm"],
                    "rhythm_norm": result.diagnostics["rhythm_norm"],
                    "timbre_norm": result.diagnostics["timbre_norm"],
                    "mert_general_norm": result.diagnostics["mert_general_norm"],
                    "inference_ms": inference_ms,
                    "preprocess_ms": preprocess_ms,
                    "persist_ms": (time.perf_counter() - t0) * 1000 + inference_ms,  # placeholder refined below
                    "device": result.diagnostics["device"],
                    "precision": result.diagnostics["precision"],
                    "audio_sha256": row.get("audio_sha256"),
                    "encoded_at": datetime.now(timezone.utc),
                }
            )
            persist_ms = (time.perf_counter() - t0) * 1000
            pending_embedding_rows[-1]["persist_ms"] = persist_ms

            summary.succeeded += 1
            done_ids.add(track_id)
        except Exception as exc:  # noqa: BLE001 — every failure is classified, never silent
            code = classify_failure(exc)
            pending_failure_rows.append(
                {
                    "track_id": track_id,
                    "analysis_key": key,
                    "relative_audio_path": str(row.get("relative_audio_path", "")),
                    "failure_code": code,
                    "exception_class": type(exc).__name__,
                    "message": str(exc)[:500],
                    "retryable": FAILURE_RETRYABLE[code],
                    "failed_at": datetime.now(timezone.utc),
                }
            )
            summary.failed += 1

        elapsed = time.perf_counter() - track_start
        summary.per_track_sec.append(elapsed)
        if progress_callback:
            progress_callback(summary.attempted, summary.succeeded, summary.failed)

        if checkpoint_every and len(pending_embedding_rows) + len(pending_failure_rows) >= checkpoint_every:
            flush()

    flush()
    if torch.cuda.is_available():
        summary.peak_vram_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)
    summary.wall_time_sec = time.perf_counter() - start
    return summary
