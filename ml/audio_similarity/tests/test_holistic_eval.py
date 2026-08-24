"""Stage 15-16 tests: candidate unions, blinded trials, provenance separation."""

from __future__ import annotations

from pathlib import Path

import json

import numpy as np
import pandas as pd
import pytest

from audio_similarity.holistic_eval import (
    build_trials,
    top_k,
    write_blinded_sheets,
)


def _fake_embeddings(tmp_path: Path, n=30, dim=8):
    rng = np.random.default_rng(0)
    rows = []
    vecs = {}
    for tid in range(1, n + 1):
        v = rng.normal(size=dim)
        v /= np.linalg.norm(v)
        vecs[tid] = v
        rows.append({"track_id": tid, "analysis_key": "k", "status": "SUCCESS",
                     "embedding": list(v)})
    path = tmp_path / "enc.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    return load_embeddings(path)[0]


def test_top_k_excludes_self_deterministic_order():
    rng = np.random.default_rng(2)
    ids = list(range(1, 21))
    matrix = rng.normal(size=(20, 6))
    matrix[0] = matrix[5]  # duplicate neighbor
    tops = top_k(ids, matrix, 1, k=5)
    assert len(tops) == 5
    assert all(tid != 1 for tid, _ in tops)
    scores = [s for _, s in tops]
    assert scores == sorted(scores, reverse=True)
    again = top_k(ids, matrix.copy(), 1, k=5)
    assert again == tops


def test_union_collects_per_encoder_tops_and_claims():
    unions = {
        1: type("Q", (), {
            "query_id": 1,
            "per_encoder": {"muq": [(10, 0.9), (11, 0.8)], "clap": [(12, 0.85)]},
            "claimed": {1, 10, 11, 12},
        })(),
    }
    trials, prov = build_trials(unions, pd.DataFrame(
        [{"track_id": t, "title": f"t{t}", "artist": f"a{t}"} for t in range(1, 30)]
    ), n_trials_per_query=3, seed=1)
    assert len(trials) == 2  # disagree + anchor; competitive skipped (clap has rank-1 only)
    # blinded: no model names in human-facing columns
    text = str(pd.DataFrame(trials).to_dict())
    assert "muq" not in text.lower() and "clap" not in text.lower()
    # provenance keeps source info server-side
    assert any("disagree" in v["kind"] for v in prov["trials"].values())


def test_trial_side_randomization_is_seeded(tmp_path):
    unions = {
        1: type("Q", (), {
            "query_id": 1,
            "per_encoder": {"e1": [(10, 0.9)], "e2": [(11, 0.85)]},
            "claimed": {1, 10, 11},
        })(),
    }
    manifest = pd.DataFrame(
        [{"track_id": t, "title": f"t{t}", "artist": f"a{t}"} for t in range(1, 25)]
    )
    t1, p1 = build_trials(unions, manifest, n_trials_per_query=2, seed=7)
    t2, p2 = build_trials(unions, manifest, n_trials_per_query=2, seed=7)
    assert [(a["a_title"], a["b_title"]) for a in t1] == [(b["a_title"], b["b_title"]) for b in t2]
    t3, _ = build_trials(unions, manifest, n_trials_per_query=2, seed=99)
    assert [(a["a_title"], a["b_title"]) for a in t1] != [(c["a_title"], c["b_title"]) for c in t3]


def test_anchor_negative_comes_from_outside_candidates(tmp_path):
    unions = {
        1: type("Q", (), {
            "query_id": 1,
            "per_encoder": {"e1": [(2, 0.9)]},
            "claimed": {1, 2},
        })(),
    }
    manifest = pd.DataFrame(
        [{"track_id": t, "title": f"t{t}", "artist": f"a{t}"} for t in range(1, 40)]
    )
    trials, prov = build_trials(unions, manifest, n_trials_per_query=4, seed=3)
    anchor_rows = [p for p in prov["trials"].values() if p["kind"] == "anchor_negative"]
    assert anchor_rows
    for p in anchor_rows:
        assert p["candidate_b"] not in unions[1].claimed or p["candidate_b"] == 1


def test_write_blinded_sheets_roundtrip(tmp_path):
    trials = [{"trial_id": "1:H1", "query_track_id": 1, "a_title": "A", "a_artist": "x",
               "b_title": "B", "b_artist": "y", "question": "q", "choice": "", "note": ""}]
    prov = {"trials": {"1:H1": {"query_track_id": 1}}, "seed": 1}
    write_blinded_sheets(trials, prov, tmp_path)
    frame = pd.read_csv(tmp_path / "holistic_trials.csv", dtype=str)
    assert list(frame.columns) == ["trial_id", "query_track_id", "a_title", "a_artist",
                                   "b_title", "b_artist", "question", "choice", "note"]
    keys = json.loads((tmp_path / "holistic_trial_keys.json").read_text())
    assert "trials" in keys

