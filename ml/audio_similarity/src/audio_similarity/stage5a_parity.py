"""FMA Small parity gate against the frozen Stage 4 K=3 artifact."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from .stage4a_dual_scoring import normalized_mean


class Stage5AParityError(ValueError):
    """Raised when Stage 5A does not reproduce frozen Stage 4 vectors."""


def _segments(path: str | Path, track_ids: set[int] | None) -> dict[int, dict[int, np.ndarray]]:
    db = sqlite3.connect(path)
    try:
        rows = db.execute(
            "SELECT track_id, center_sec, embedding FROM segments WHERE status='ok' AND center_sec IN (5,15,25) ORDER BY track_id, center_sec"
        )
        result: dict[int, dict[int, np.ndarray]] = {}
        for track_id, center, blob in rows:
            track_id = int(track_id)
            if track_ids is not None and track_id not in track_ids:
                continue
            result.setdefault(track_id, {})[int(center)] = np.frombuffer(blob, dtype="<f4").copy()
        return result
    finally:
        db.close()


def verify_fma_small_parity(
    *,
    clap_cache: str | Path,
    muq_cache: str | Path,
    frozen_aggregates: str | Path,
    track_ids: list[int] | None = None,
    atol: float = 2e-6,
) -> dict:
    selected = set(track_ids) if track_ids is not None else None
    clap = _segments(clap_cache, selected)
    muq = _segments(muq_cache, selected)
    frozen = pd.read_parquet(frozen_aggregates)
    frozen = frozen[frozen["representation"] == "UNIFORM3_DUAL_MEAN"]
    if selected is not None:
        frozen = frozen[frozen["track_id"].isin(selected)]
    frozen = frozen.set_index("track_id")
    expected_ids = set(int(value) for value in frozen.index)
    if set(clap) != expected_ids or set(muq) != expected_ids:
        raise Stage5AParityError(
            f"track accounting mismatch: frozen={len(expected_ids)}, clap={len(clap)}, muq={len(muq)}"
        )

    metrics = {}
    for name, cached, column in (
        ("clap", clap, "clap_embedding"),
        ("muq", muq, "muq_embedding"),
    ):
        maximum = 0.0
        minimum_cosine = 1.0
        for track_id in sorted(expected_ids):
            centers = cached[track_id]
            if set(centers) != {5, 15, 25}:
                raise Stage5AParityError(f"{name} track {track_id} is missing a frozen K=3 segment")
            actual = normalized_mean(np.stack([centers[center] for center in (5, 15, 25)]))
            expected = np.asarray(frozen.loc[track_id, column], dtype=np.float32)
            maximum = max(maximum, float(np.max(np.abs(actual - expected))))
            minimum_cosine = min(minimum_cosine, float(np.dot(actual, expected)))
        if maximum > atol:
            raise Stage5AParityError(f"{name} maximum absolute error {maximum} exceeds {atol}")
        metrics[name] = {
            "tracks": len(expected_ids),
            "maximum_absolute_error": maximum,
            "minimum_cosine": minimum_cosine,
            "tolerance": atol,
            "passed": True,
        }
    inputs = [Path(clap_cache), Path(muq_cache), Path(frozen_aggregates)]
    return {
        "schema_version": "stage5a-fma-small-parity-v1",
        "tracks": len(expected_ids),
        "centers_sec": [5, 15, 25],
        "method": "UNIFORM3_DUAL_MEAN",
        "clap": metrics["clap"],
        "muq": metrics["muq"],
        "input_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs
        },
        "passed": True,
    }


def write_parity_report(result: dict, output_path: str | Path) -> None:
    Path(output_path).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
