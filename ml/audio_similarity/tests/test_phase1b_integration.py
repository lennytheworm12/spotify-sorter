"""Phase 1B end-to-end integration: frozen cases -> features -> scoring ->
analyses -> artifacts. Synthetic, network-free, no MERIT."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from audio_similarity.mir_features import FeatureCache, TrackFeatures
from audio_similarity.phase1b_analyze import (
    AnalysisContext,
    EmbeddingLookup,
    background_distributions,
    load_human_joins,
    score_master_table,
)
from audio_similarity.phase1b_report import (
    construct_validity_comparisons,
    correlation_matrix,
    disagreement_analysis,
    factor_specificity_report,
    original_phase1_gate,
)


def _fake_features(rng: np.random.Generator, audio_hash: str) -> TrackFeatures:
    chroma = np.abs(rng.normal(size=(12, 40))) + 0.05
    return TrackFeatures(
        audio_hash=audio_hash,
        chroma_mean=chroma.mean(axis=1),
        chroma_sequence=chroma.astype(np.float32),
        onset_envelope=np.abs(rng.normal(size=30)).astype(np.float32),
        periodicity_profile=np.abs(rng.normal(size=64)).astype(np.float32),
        tempo_bpm=float(rng.integers(90, 180)),
        timbre_vector=np.abs(rng.normal(size=48)).astype(np.float32),
    )


@pytest.fixture
def env(tmp_path: Path):
    rng = np.random.default_rng(5)
    tmp = tmp_path / "p1b"
    tmp.mkdir()

    # manifest: query 1 (Rock, artist_a) + candidates 2..12
    rows = []
    for tid in range(1, 13):
        rows.append(
            {
                "track_id": tid,
                "relative_audio_path": f"{tid:03d}/{tid:06d}.wav",
                "audio_sha256": f"h{tid}",
                "decode_status": "SUCCESS",
                "duration_sec": 30.0,
                "title": f"t{tid}", "artist": f"artist_{tid % 3}",
                "top_genre": "Rock" if tid <= 6 else "Pop",
            }
        )
    manifest_path = tmp / "manifest.parquet"
    pd.DataFrame(rows).to_parquet(manifest_path, index=False)

    # embeddings: melody-similar pairs (1,7), rhythm-similar pairs (1,8)
    def vec(seed: int, dim: int) -> list[float]:
        g = np.random.default_rng(seed)
        v = g.normal(size=dim)
        return list(v / np.linalg.norm(v))

    emb_rows = []
    for tid in range(1, 13):
        emb_rows.append(
            {
                "track_id": tid, "analysis_key": "k",
                "melody": vec(100 if tid in (1, 7) else tid, 4),
                "rhythm": vec(200 if tid in (1, 8) else tid, 4),
                "timbre": vec(300 if tid in (1, 9) else tid, 4),
                "mert_general": vec(tid + 400, 4),
            }
        )
    emb_path = tmp / "emb.parquet"
    pd.DataFrame(emb_rows).to_parquet(emb_path, index=False)

    # key file: frozen melody top-5 for query 1
    keys = pd.DataFrame([
        {"cell_id": f"1:melody:{r}", "representation": "merit_melody", "neighbor_track_id": t}
        for r, t in enumerate([7, 9, 10, 11, 12], start=1)
    ])
    keys.to_csv(tmp / "keys.csv", index=False)

    # human ratings: likes neighbor rank1, dislikes rank2
    ratings = pd.DataFrame([
        {"cell_id": "1:melody:1", "rating": "3"},
        {"cell_id": "1:melody:2", "rating": "0"},
    ])
    ratings.to_csv(tmp / "judgments.csv", index=False)

    # feature cache: distinct features per track, structured so track 7's
    # chroma resembles track 1's (melody agreement), track 9 differs
    cache = FeatureCache(tmp / "cache")
    base_chroma = np.abs(rng.normal(size=(12, 30))) + 0.1
    for tid in range(1, 13):
        chroma = base_chroma * (1.0 if tid == 7 else 0.5 + 0.5 * rng.random()) \
            + rng.normal(size=(12, 30)) * 0.05
        cache.put(TrackFeatures(
            audio_hash=f"h{tid}",
            chroma_mean=chroma.mean(axis=1).astype(np.float32),
            chroma_sequence=chroma.astype(np.float32),
            onset_envelope=np.abs(rng.normal(size=30)).astype(np.float32),
            periodicity_profile=np.abs(rng.normal(size=64)).astype(np.float32),
            timbre_vector=np.abs(rng.normal(size=48)).astype(np.float32),
            tempo_bpm=120.0,
        ))
    return {
        "manifest": manifest_path, "embeddings": emb_path, "keys": tmp / "keys.csv",
        "ratings": tmp / "judgments.csv", "cache": cache, "tmp": tmp,
    }


def test_end_to_end_scoring_and_artifacts(env):
    cases_payload = {
        "cases": [
            {
                "query_id": 1,
                "factor": "melody",
                "merit_target_neighbors": [7, 9, 10, 11, 12],
                "merit_other_neighbors": {},
                "mert_general_neighbors": [2, 3, 4, 5, 6],
                "conventional_neighbors": [8, 2, 3, 5, 6],
                "random_negatives": [4, 5, 6, 2, 3],
                "hard_negatives": [8, 2, 4, 5, 6],
            }
        ]
    }
    cases_path = env["tmp"] / "cases.json"
    cases_path.write_text(json.dumps(cases_payload))

    lookup = EmbeddingLookup(env["embeddings"])
    calibration = BackgroundCalibrationStub()
    ctx = AnalysisContext(
        manifest=pd.read_parquet(env["manifest"]),
        lookup=lookup,
        cache=env["cache"],
        calibration=calibration,
        human_joins=load_human_joins(env["ratings"], env["keys"]),
    )

    master = score_master_table(cases_path, ctx)
    # 5 merit target + mert 5 + conventional 5 + random 5 + hard 5 = 25 rows
    assert len(master) == 25
    assert set(master["retrieval_source"].unique()) == {
        "merit_target", "mert_general", "conventional", "random_negative", "hard_negative"}

    # human join by exact identity
    r1 = master[(master["candidate_id"] == 7) & (master["retrieval_source"] == "merit_target")].iloc[0]
    r2 = master[(master["candidate_id"] == 9) & (master["retrieval_source"] == "merit_target")].iloc[0]
    assert r1["human_rating"] == "3" and bool(r1["human_valid"])
    assert r2["human_rating"] == "0"

    # analyses run and produce sane outputs
    spec = factor_specificity_report(master)
    assert set(spec) >= {"melody"}
    comparisons = construct_validity_comparisons(master)
    assert "melody" in comparisons and comparisons["melody"]
    corr = correlation_matrix(master)
    assert not corr.empty
    dis = disagreement_analysis(master)
    assert "groups" in dis


class BackgroundCalibrationStub:
    """Deterministic stub calibration for integration testing."""

    _dists = None

    def __init__(self):
        if BackgroundCalibrationStub._dists is None:
            rng = np.random.default_rng(0)
            BackgroundCalibrationStub._dists = {
                name: np.abs(rng.normal(size=500))
                for name in ("chroma_global_cos", "chroma_dtw_sim", "transposition_best_cos",
                             "onset_cos_fixed", "onset_dtw_sim", "tempogram_cos", "timbre_cos")
            }
        from audio_similarity.mir_metrics import BackgroundCalibration
        self._impl = BackgroundCalibration(self._dists)

    def percentiles(self, values):
        return self._impl.percentiles(values)

