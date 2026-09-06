from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from audio_similarity.stage5f1_analysis import analyze_rated_pairs, node_bootstrap
from audio_similarity.stage5f1_inputs import frozen_matrices, frozen_tracks, snapshot_compatible_labels


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_original100_sources_and_frozen_matrices_are_exact():
    project_root = PROJECT_ROOT
    tracks = frozen_tracks(project_root, "original100")
    assert len(tracks) == len({row["spotify_track_id"] for row in tracks}) == 100
    matrices = frozen_matrices(project_root, [row["spotify_track_id"] for row in tracks])
    assert set(matrices) == {"a_clap", "muq", "a_combined"}
    assert all(matrix.shape == (100, 100) for matrix in matrices.values())


def test_rating_snapshot_reuses_current_and_historical_evidence():
    project_root = PROJECT_ROOT
    snapshot = snapshot_compatible_labels(project_root, frozen_tracks(project_root, "original100"))
    assert snapshot["counts"]["evidence_rows"] >= 1219
    assert snapshot["counts"]["resolved_numeric_pairs"] > 100
    assert not (set(snapshot["resolved_labels"]) & set(snapshot["conflicts"]))


def test_analysis_never_executes_reranking():
    tracks = [{"spotify_track_id": str(index), "artist_credit": f"artist-{index}", "activity": {"status": "VALID"}, "percussion": {"status": "VALID"}, "source_level": {"status": "VALID"}, "pulse": {"status": "VALID"}} for index in range(50)]
    pairs = []
    for index in range(40):
        pairs.append({
            "pair_id": str(index), "left_spotify_id": str(index), "right_spotify_id": str(index + 1),
            "a_clap": 0.9, "muq": 0.8, "base_combined": 0.9,
            "activity_similarity": 0.2 if index < 20 else 0.9,
            "human_rating": 1 if index < 20 else 5,
        })
    result = analyze_rated_pairs(pairs, tracks, __import__("audio_similarity.energy_motion_config", fromlist=["EvaluationConfig"]).EvaluationConfig(bootstrap_replicates=100))
    assert result["reranking_executed"] is False
    assert result["production_activation"] is False
