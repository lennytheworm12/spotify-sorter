"""Phase 1B Stage B tests: frozen inputs and deterministic control groups."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from audio_similarity.phase1b_freeze import (
    build_cases,
    load_frozen_merit_retrievals,
    sample_hard_negatives,
    sample_random_negatives,
)
@pytest.fixture
def mini(tmp_path: Path):
    """Small manifest + embeddings + key file mirroring the real layout."""
    rows = []
    audio_root = tmp_path / "audio"
    genres = ["Rock", "Pop", "Jazz"]
    for tid in range(1, 41):
        rows.append(
            {
                "track_id": tid,
                "relative_audio_path": f"{tid:03d}/{tid:06d}.wav",
                "audio_sha256": f"h{tid}",
                "file_size_bytes": 100,
                "decode_status": "SUCCESS",
                "duration_sec": 30.0 + (tid % 5) * 0.1,
                "title": f"t{tid}",
                "artist": f"artist_{tid % 6}",
                "album": "",
                "top_genre": genres[tid % 3],
                "fma_split": "test",
                "subset": "small",
            }
        )
    manifest = pd.DataFrame(rows)
    manifest_path = tmp_path / "manifest.parquet"
    manifest.to_parquet(manifest_path, index=False)

    # embeddings for all 40 tracks, 4-dim per factor
    rng = np.random.default_rng(0)
    from datetime import datetime, timezone

    emb_rows = []
    for tid in range(1, 41):
        vec = rng.normal(size=8)
        vec /= np.linalg.norm(vec)
        emb_rows.append(
            {
                "track_id": tid,
                "analysis_key": "k",
                "melody": vec[:2],
                "rhythm": vec[2:4],
                "timbre": vec[4:6],
                "mert_general": rng.normal(size=2),
                "melody_norm": 1.0, "rhythm_norm": 1.0, "timbre_norm": 1.0,
                "mert_general_norm": 1.0,
                "inference_ms": 0.0, "preprocess_ms": 0.0, "persist_ms": 0.0,
                "device": "cpu", "precision": "fp32",
                "audio_sha256": f"h{tid}",
                "encoded_at": datetime.now(timezone.utc),
            }
        )
    import pyarrow as pa
    import pyarrow.parquet as pq
    schema = pa.schema([
        ("track_id", pa.int64()), ("analysis_key", pa.string()),
        ("melody", pa.list_(pa.float64())), ("rhythm", pa.list_(pa.float64())),
        ("timbre", pa.list_(pa.float64())), ("mert_general", pa.list_(pa.float64())),
        ("melody_norm", pa.float32()), ("rhythm_norm", pa.float32()),
        ("timbre_norm", pa.float32()), ("mert_general_norm", pa.float32()),
        ("inference_ms", pa.float32()), ("preprocess_ms", pa.float32()),
        ("persist_ms", pa.float32()), ("device", pa.string()), ("precision", pa.string()),
        ("audio_sha256", pa.string()), ("encoded_at", pa.timestamp("us", tz="UTC")),
    ])
    pq.write_table(pa.Table.from_pylist(emb_rows, schema=schema), tmp_path / "emb.parquet")

    keys = pd.DataFrame([
        {"cell_id": "1:melody:1", "representation": "merit_melody", "neighbor_track_id": 7},
        {"cell_id": "1:melody:2", "representation": "merit_melody", "neighbor_track_id": 13},
        {"cell_id": "1:rhythm:1", "representation": "merit_rhythm", "neighbor_track_id": 21},
    ])
    keys.to_csv(tmp_path / "keys.csv", index=False)

    conv = rng.normal(size=(40, 6)).astype(np.float32)

    return {
        "manifest": manifest, "manifest_path": manifest_path,
        "embeddings": tmp_path / "emb.parquet", "keys": tmp_path / "keys.csv",
        "conv_matrix": conv,
    }


def test_load_frozen_retrievals_parses_cell_ids(mini):
    frozen = load_frozen_merit_retrievals(mini["keys"])
    melody_row = frozen[frozen["factor"] == "melody"].iloc[0]
    assert melody_row["query_id"] == 1
    assert melody_row["neighbors"] == [7, 13]


def test_build_cases_groups_and_exclusions(mini):
    cases = build_cases(
        mini["manifest_path"], mini["embeddings"], mini["keys"],
        conventional_matrix=mini["conv_matrix"],
        queries_csv=None,
    )
    assert len(cases) == 2  # melody + rhythm rows in key file
    case = cases[0]
    assert case.merit_target_neighbors == [7, 13]
    assert set(case.merit_other_neighbors) == {"rhythm"}
    # exclusions: no overlap between random negatives and claimed sets
    claimed = set(case.merit_target_neighbors) | {21} | set(case.mert_general_neighbors) \
        | set(case.conventional_neighbors) | {1}
    assert not (set(case.random_negatives) & claimed)


def test_hard_negative_constraints(mini):
    manifest = mini["manifest"]
    rng = np.random.default_rng(1)
    negs = sample_hard_negatives(rng, manifest, query_id=1, exclude={1}, k=5)
    meta = manifest.set_index("track_id")
    assert len(negs) == 5
    for tid in negs:
        assert meta.at[tid, "top_genre"] == meta.at[1, "top_genre"]
        assert meta.at[tid, "artist"] != meta.at[1, "artist"]
    assert len(set(negs)) == 5


def test_random_negative_determinism(mini):
    rng_a = np.random.default_rng(42)
    rng_b = np.random.default_rng(42)
    pool = np.arange(1, 41)
    a = sample_random_negatives(rng_a, pool, exclude={1, 2}, k=5)
    b = sample_random_negatives(rng_b, pool, exclude={1, 2}, k=5)
    assert a == b
