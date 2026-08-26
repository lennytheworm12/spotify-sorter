"""Version-isolated, segment-granular Stage 4 Parquet cache."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .stage4_scoring import bounded_recurrence_mean, uniform_mean

SEGMENT_COLUMNS = ["corpus", "track_id", "source_sha256", "canonical_pcm_sha256", "encoder_id", "encoder_checkpoint_sha256", "encoder_revision", "preprocessing_version", "sampling_version", "segment_index", "start_sample", "end_sample", "start_sec", "end_sec", "embedding_dtype", "embedding_dimension", "normalized_segment_embedding", "embedding_sha256", "analysis_key", "status", "failure", "encode_ms", "created_at"]
GEOMETRY_FIELDS = ["source_sha256", "canonical_pcm_sha256", "encoder_id", "encoder_checkpoint_sha256", "encoder_revision", "preprocessing_version", "sampling_version", "embedding_dtype", "embedding_dimension"]


class SegmentCacheError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def analysis_key(fields: dict[str, Any]) -> str:
    missing = set(GEOMETRY_FIELDS) - set(fields)
    if missing:
        raise SegmentCacheError(f"analysis key missing fields: {sorted(missing)}")
    return hashlib.sha256(canonical_json({key: fields[key] for key in GEOMETRY_FIELDS})).hexdigest()


def embedding_bytes(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype="<f4").tobytes(order="C")


def validated_embedding(vector: np.ndarray, dimension: int = 512) -> tuple[list[float], str]:
    x = np.asarray(vector, dtype=np.float32)
    if x.shape != (dimension,) or not np.isfinite(x).all():
        raise SegmentCacheError(f"expected finite ({dimension},) embedding")
    norm = float(np.linalg.norm(x))
    if norm <= 0:
        raise SegmentCacheError("zero-norm embedding")
    x = (x / norm).astype(np.float32)
    raw = embedding_bytes(x)
    return x.tolist(), hashlib.sha256(raw).hexdigest()


class SegmentCache:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read(self) -> pd.DataFrame:
        if not self.path.exists():
            return pd.DataFrame(columns=SEGMENT_COLUMNS)
        frame = pd.read_parquet(self.path)
        missing = set(SEGMENT_COLUMNS) - set(frame.columns)
        if missing:
            raise SegmentCacheError(f"cache missing columns: {sorted(missing)}")
        return frame[SEGMENT_COLUMNS]

    def append(self, rows: list[dict[str, Any]]) -> None:
        old = self.read()
        additions = []
        existing = set(zip(old.track_id.astype(str), old.analysis_key.astype(str), old.segment_index.astype(str))) if len(old) else set()
        for supplied in rows:
            row = dict(supplied)
            row.setdefault("created_at", int(time.time()))
            row.setdefault("failure", "")
            row.setdefault("status", "ok")
            row.setdefault("embedding_dtype", "float32")
            if row.get("status") == "ok":
                values, digest = validated_embedding(row["normalized_segment_embedding"], int(row["embedding_dimension"]))
                row["normalized_segment_embedding"], row["embedding_sha256"] = values, digest
            else:
                row["normalized_segment_embedding"], row["embedding_sha256"] = [], ""
            expected_key = analysis_key(row)
            if row.get("analysis_key", expected_key) != expected_key:
                raise SegmentCacheError("analysis key does not match frozen geometry")
            row["analysis_key"] = expected_key
            identity = (str(row["track_id"]), expected_key, str(row["segment_index"]))
            if identity in existing:
                raise SegmentCacheError(f"duplicate segment cache row {identity}")
            existing.add(identity)
            missing = set(SEGMENT_COLUMNS) - set(row)
            if missing:
                raise SegmentCacheError(f"segment row missing: {sorted(missing)}")
            additions.append({key: row[key] for key in SEGMENT_COLUMNS})
        combined = pd.concat([old, pd.DataFrame(additions)], ignore_index=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        combined.to_parquet(temp, index=False)
        temp.replace(self.path)

    def complete_tracks(self, key: str) -> set[str]:
        frame = self.read()
        frame = frame[(frame.analysis_key == key) & (frame.status == "ok")]
        counts = frame.groupby("track_id").segment_index.agg(lambda x: len(set(x)))
        return set(counts[counts == 5].index.astype(str))


def regenerate_aggregates(frame: pd.DataFrame) -> list[dict[str, Any]]:
    output = []
    okay = frame[frame.status == "ok"]
    for (track_id, key), group in okay.groupby(["track_id", "analysis_key"], sort=True):
        group = group.sort_values("segment_index")
        if group.segment_index.tolist() != [0, 1, 2, 3, 4]:
            continue
        segments = np.stack(group.normalized_segment_embedding.map(np.asarray))
        uniform = uniform_mean(segments)
        recurrence, weights = bounded_recurrence_mean(segments)
        for version, vector, rec_weights in (("uniform_mean_v1", uniform, []), ("bounded_recurrence_mean_v1", recurrence, weights.tolist())):
            raw = embedding_bytes(vector)
            output.append({"track_id": str(track_id), "segment_analysis_key": key, "aggregation_version": version, "K": 5, "recurrence_weights": rec_weights, "global_embedding": vector.tolist(), "global_embedding_sha256": hashlib.sha256(raw).hexdigest(), "created_at": int(time.time())})
    return output
