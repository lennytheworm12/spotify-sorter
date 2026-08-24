"""Resumable holistic benchmark encoding (Stage 1A design sections 11-12).

One frozen excerpt (center5_v1 @ 24 kHz) per track; adapters produce one
normalized embedding each. Rows are keyed by:

    (track_id, audio_sha256, excerpt_strategy, encoder_id, preprocessing)

Storage: one Parquet per encoder, atomic-append checkpoints, explicit
failure rows. Different encoder versions never mix.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def benchmark_key(encoder_id: str, revision: str, excerpt_strategy: str, preprocessing: str) -> str:
    identity = "|".join([encoder_id, revision or "", excerpt_strategy, preprocessing])
    return hashlib.sha256(identity.encode()).hexdigest()[:16]


EMBEDDING_SCHEMA_BASE = [
    ("track_id", pa.int64()),
    ("analysis_key", pa.string()),
    ("audio_sha256", pa.string()),
    ("embedding", None),  # filled per encoder (list float32 of dim)
    ("status", pa.string()),
    ("failure_code", pa.string()),
    ("error_message", pa.string()),
    ("encode_ms", pa.float32()),
    ("encoded_at", pa.timestamp("us", tz="UTC")),
]


class HolisticEmbeddingStore:
    def __init__(self, path: str | Path, dim: int):
        self.path = Path(path)
        self.dim = int(dim)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fields = []
        for name, typ in EMBEDDING_SCHEMA_BASE:
            fields.append((name, pa.list_(pa.float32(), self.dim) if name == "embedding" else typ))
        self.schema = pa.schema(fields)

    def _read(self) -> pd.DataFrame:
        if not self.path.exists():
            return pd.DataFrame()
        try:
            return pq.read_table(self.path).to_pandas()
        except Exception:
            return pd.DataFrame()

    def completed_track_ids(self, key: str) -> set[int]:
        frame = self._read()
        if frame.empty:
            return set()
        done = frame[(frame["analysis_key"] == key) & (frame["status"] == "SUCCESS")]
        return set(int(t) for t in done["track_id"])

    def append(self, rows: list[dict]) -> None:
        if not rows:
            return
        new = pa.Table.from_pylist(rows, schema=self.schema)
        existing = pq.read_table(self.path) if self.path.exists() else self.schema.empty_table()
        combined = pa.concat_tables([existing, new])
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        pq.write_table(combined, tmp)
        tmp.replace(self.path)

    def embeddings_for_key(self, key: str) -> dict[int, np.ndarray]:
        frame = self._read()
        out: dict[int, np.ndarray] = {}
        for _, row in frame[frame["analysis_key"] == key].iterrows():
            if row["status"] != "SUCCESS":
                continue
            out[int(row["track_id"])] = np.asarray(row["embedding"], dtype=np.float32)
        return out


@dataclass
class BatchStats:
    attempted: int = 0
    skipped_completed: int = 0
    succeeded: int = 0
    failed: int = 0
    wall_sec: float = 0.0
    timings: list[float] = None

    def __post_init__(self):
        if self.timings is None:
            self.timings = []

    def summary(self) -> dict:
        arr = np.asarray(self.timings) if self.timings else np.array([])
        return {
            "attempted": self.attempted,
            "skipped_completed": self.skipped_completed,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "wall_sec": round(self.wall_sec, 1),
            "p50_s_per_clip": float(np.percentile(arr, 50)) if len(arr) else None,
            "p95_s_per_clip": float(np.percentile(arr, 95)) if len(arr) else None,
            "clips_per_hour": round(len(arr) / max(arr.sum(), 1e-9) * 3600) if len(arr) else None,
        }


def run_holistic_batch(
    encoder,
    encoder_id: str,
    revision: str,
    manifest_rows: list[dict],
    audio_root: Path,
    store_path: Path,
    excerpt_strategy: str = "center5",
    checkpoint_every: int = 25,
    progress_callback=None,
) -> BatchStats:
    from audio_similarity.audio import preprocess_file

    key = benchmark_key(encoder_id, revision, excerpt_strategy, "pp-v1")
    store = HolisticEmbeddingStore(store_path, encoder.embedding_dim)
    done = store.completed_track_ids(key)

    stats = BatchStats()
    pending: list[dict] = []
    t_start = time.perf_counter()

    def flush():
        if pending:
            store.append(list(pending))
            pending.clear()

    for row in manifest_rows:
        tid = int(row["track_id"])
        if tid in done:
            stats.skipped_completed += 1
            continue
        stats.attempted += 1
        t0 = time.perf_counter()
        try:
            wav = preprocess_file(audio_root / row["relative_audio_path"])
            start, end = _excerpt_bounds(wav, excerpt_strategy)
            result = encoder.encode_segment(wav[start:end], 24000)
            pending.append(
                {
                    "track_id": tid,
                    "analysis_key": key,
                    "audio_sha256": str(row.get("audio_sha256") or ""),
                    "embedding": result.embedding.astype(np.float32),
                    "status": "SUCCESS",
                    "failure_code": "",
                    "error_message": "",
                    "encode_ms": (time.perf_counter() - t0) * 1000,
                    "encoded_at": datetime.now(timezone.utc),
                }
            )
            stats.succeeded += 1
            stats.timings.append(time.perf_counter() - t0)
        except Exception as exc:
            code = type(exc).__name__
            pending.append(
                {
                    "track_id": tid,
                    "analysis_key": key,
                    "audio_sha256": str(row.get("audio_sha256") or ""),
                    "embedding": [0.0] * encoder.embedding_dim,
                    "status": "FAILED",
                    "failure_code": code[:60],
                    "error_message": str(exc)[:300],
                    "encode_ms": (time.perf_counter() - t0) * 1000,
                    "encoded_at": datetime.now(timezone.utc),
                }
            )
            stats.failed += 1

        if progress_callback:
            progress_callback(stats.attempted, stats.succeeded, stats.failed)
        if checkpoint_every and len(pending) >= checkpoint_every:
            flush()

    flush()
    stats.wall_sec = time.perf_counter() - t_start
    return stats


def _excerpt_bounds(wav: np.ndarray, strategy: str, sr: int = 24000) -> tuple[int, int]:
    """Deterministic excerpt bounds on an already-decoded waveform."""
    duration = len(wav) / sr
    seg = sample_segments("t", duration, strategy)[0]
    start = int(seg.actual_start_sec * sr)
    end = int(seg.actual_end_sec * sr)
    return max(0, start), min(len(wav), end)


# local import to avoid circular dependency at module load
from .sampling import sample_segments  # noqa: E402
