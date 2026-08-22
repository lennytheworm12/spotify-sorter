"""Parquet-backed embedding/failure stores with checkpoint-safe atomic writes.

Phase 1 doc sections 8 (persisted representation), 12 (resumable batch),
24 (data-quality behavior).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

EMBEDDING_DIM = 128
GENERAL_DIM = 5120


def analysis_key(provenance_dict: dict) -> str:
    """Stable identity of (model revisions, head hashes, preprocessing)."""
    canonical = json.dumps(provenance_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _embedding_schema(general_dim: int | None = GENERAL_DIM) -> pa.Schema:
    fields = [
        ("track_id", pa.int64()),
        ("analysis_key", pa.string()),
    ]
    factor_fields = [
        (name, pa.list_(pa.float32(), EMBEDDING_DIM))
        for name in ("melody", "rhythm", "timbre")
    ]
    diag_fields = [
        ("melody_norm", pa.float32()),
        ("rhythm_norm", pa.float32()),
        ("timbre_norm", pa.float32()),
        ("mert_general_norm", pa.float32()),
        ("inference_ms", pa.float32()),
        ("preprocess_ms", pa.float32()),
        ("persist_ms", pa.float32()),
        ("device", pa.string()),
        ("precision", pa.string()),
        ("audio_sha256", pa.string()),
        ("encoded_at", pa.timestamp("us", tz="UTC")),
    ]
    if general_dim:
        fields.append(("mert_general", pa.list_(pa.float32(), general_dim)))
    return pa.schema(fields + factor_fields + diag_fields)


FAILURE_SCHEMA = pa.schema(
    [
        ("track_id", pa.int64()),
        ("analysis_key", pa.string()),
        ("relative_audio_path", pa.string()),
        ("failure_code", pa.string()),
        ("exception_class", pa.string()),
        ("message", pa.string()),
        ("retryable", pa.bool_()),
        ("failed_at", pa.timestamp("us", tz="UTC")),
    ]
)


def append_atomic(path: Path, schema: pa.Schema, rows: list[dict]) -> None:
    """Append rows and atomically replace the file (checkpoint safety)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = pa.Table.from_pylist(rows, schema=schema)
    existing = pq.read_table(path) if path.exists() else schema.empty_table()
    combined = pa.concat_tables([existing, new])
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(combined, tmp)
    tmp.replace(path)


class EmbeddingStore:
    """Completed MERIT analyses keyed by (track_id, analysis_key)."""

    def __init__(self, path: str | Path, include_general_baseline: bool = True):
        self.include_general_baseline = include_general_baseline
        self.schema = _embedding_schema(GENERAL_DIM if include_general_baseline else None)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def completed_track_ids(self, key: str) -> set[int]:
        if not self.path.exists():
            return set()
        table = pq.read_table(self.path, columns=["track_id", "analysis_key"])
        ids = table.column("track_id").to_pylist()
        keys = table.column("analysis_key").to_pylist()
        return {tid for tid, k in zip(ids, keys) if k == key}

    def table(self) -> pa.Table:
        if not self.path.exists():
            return self.schema.empty_table()
        return pq.read_table(self.path)

    def append(self, rows: list[dict]) -> None:
        if not rows:
            return
        append_atomic(self.path, self.schema, rows)

    def count(self, key: str | None = None) -> int:
        if not self.path.exists():
            return 0
        table = pq.read_table(self.path, columns=["track_id", "analysis_key"])
        if key is None:
            return table.num_rows
        return sum(1 for k in table.column("analysis_key").to_pylist() if k == key)


class FailureStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def failed_track_ids(self, key: str) -> set[int]:
        if not self.path.exists():
            return set()
        table = pq.read_table(self.path, columns=["track_id", "analysis_key"])
        return {
            tid
            for tid, k in zip(table.column("track_id").to_pylist(), table.column("analysis_key").to_pylist())
            if k == key
        }

    def append(self, rows: list[dict]) -> None:
        if not rows:
            return
        append_atomic(self.path, FAILURE_SCHEMA, rows)

    def to_dicts(self) -> list[dict]:
        if not self.path.exists():
            return []
        return pq.read_table(self.path).to_pylist()
