"""Retrieval invariants (Phase 1 doc, sections 10, 11 'Search invariants')."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from audio_similarity.audio import preprocess_waveform
from audio_similarity.retrieval import RetrievalIndex, l2_normalize_rows
from audio_similarity.storage import EmbeddingStore
from tests.helpers import make_fake_encoder, synth_waveform


def build_index(tmp_path: Path, n: int = 12) -> tuple[RetrievalIndex, pd.DataFrame]:
    """Encode n synthetic tracks with the fake encoder; return (index, manifest)."""
    encoder, _ = make_fake_encoder()
    store = EmbeddingStore(tmp_path / "embeddings.parquet")
    manifest_rows = []
    for tid in range(1, n + 1):
        wav = preprocess_waveform(synth_waveform(1, seed=tid), 24000)
        result = encoder.encode_waveform(wav)
        store.append(
            [
                {
                    "track_id": tid,
                    "analysis_key": "k",
                    "melody": result.melody,
                    "rhythm": result.rhythm,
                    "timbre": result.timbre,
                    "mert_general": result.mert_general,
                    "melody_norm": 1.0,
                    "rhythm_norm": 1.0,
                    "timbre_norm": 1.0,
                    "mert_general_norm": 1.0,
                    "inference_ms": 0.0,
                    "preprocess_ms": 0.0,
                    "persist_ms": 0.0,
                    "device": "cpu",
                    "precision": "fp32",
                    "audio_sha256": str(tid),
                    "encoded_at": datetime.now(timezone.utc),
                }
            ]
        )
        # 4 artists cycling; genres cycle by 3 — some same-artist neighbors exist
        manifest_rows.append(
            {
                "track_id": tid,
                "artist": f"artist_{(tid - 1) % 4}",
                "top_genre": f"genre_{tid % 3}",
                "title": f"t{tid}",
            }
        )
    manifest = pd.DataFrame(manifest_rows)
    return RetrievalIndex(store.path, manifest), manifest


@pytest.fixture(scope="module")
def index_env(tmp_path_factory):
    return build_index(tmp_path_factory.mktemp("retrieval"))


def test_l2_normalize_rows():
    out = l2_normalize_rows(np.array([[3.0, 4.0], [0.0, 0.0]]))
    assert out[0].tolist() == [0.6, 0.8]
    assert np.isfinite(out).all()  # zero row guarded


def test_self_is_top1_before_exclusion(index_env):
    index, _ = index_env
    neighbors = index.search("melody", 5, k=5, include_self=True)
    assert neighbors[0].track_id == 5
    assert neighbors[0].score == pytest.approx(1.0, abs=1e-5)


def test_self_never_appears_after_exclusion(index_env):
    index, _ = index_env
    for rep in ("melody", "rhythm", "timbre", "mert_general"):
        neighbors = index.search(rep, 5, k=11)
        assert all(n.track_id != 5 for n in neighbors)
        assert len(neighbors) == 11


def test_scores_monotonically_nonincreasing(index_env):
    index, _ = index_env
    neighbors = index.search("timbre", 3, k=10)
    scores = [n.score for n in neighbors]
    assert all(a >= b - 1e-7 for a, b in zip(scores, scores[1:]))


def test_no_duplicate_neighbor_ids(index_env):
    index, _ = index_env
    neighbors = index.search("rhythm", 7, k=11)
    ids = [n.track_id for n in neighbors]
    assert len(ids) == len(set(ids))


def test_deterministic_for_identical_input(index_env):
    index, _ = index_env
    a = index.search("melody", 2, k=8)
    b = index.search("melody", 2, k=8)
    assert [(n.rank, n.track_id, n.score) for n in a] == [(n.rank, n.track_id, n.score) for n in b]


def test_ties_broken_by_track_id(index_env):
    """Identical vectors must yield deterministic id-ascending tie order."""
    index, _ = index_env
    # force three identical rows
    v = np.zeros(128, dtype=np.float32)
    v[0] = 1.0
    matrix = index.matrices["melody"]
    for tid in (10, 11, 12):
        matrix[index._id_to_row[tid]] = v
    neighbors = index.search("melody", 1, k=11)
    tail_ids = [n.track_id for n in neighbors[-3:]]
    assert tail_ids == [10, 11, 12]


def test_exclude_same_artist(index_env):
    index, _ = index_env
    plain = index.search("timbre", 1, k=11)
    excluded = index.search("timbre", 1, k=11, exclude_same_artist=True)

    query_artist = index.artists[1]
    assert any(index.artists[n.track_id] == query_artist for n in plain), "fixture lacks same-artist neighbors"
    assert all(index.artists[n.track_id] != query_artist for n in excluded)


def test_unknown_representation_raises(index_env):
    index, _ = index_env
    with pytest.raises(KeyError):
        index.search("nope", 1, k=3)


def test_conventional_matrix_aligned_and_searchable(tmp_path):
    from audio_similarity.retrieval import FACTOR_REPRESENTATIONS

    index, manifest = build_index(tmp_path)
    # recover the store path by rebuilding once more into a fresh dir
    store_path = tmp_path / "embeddings.parquet"
    conv_rng = np.random.default_rng(0)
    conv = conv_rng.normal(size=(len(index.track_ids), 20)).astype(np.float32)

    combined = RetrievalIndex(store_path, manifest, conventional_matrix=conv)
    neighbors = combined.search("conventional_features", 1, k=5)
    assert len(neighbors) == 5
    assert all(n.track_id != 1 for n in neighbors)
    assert "conventional_features" in combined.matrices
    assert set(FACTOR_REPRESENTATIONS) <= set(combined.matrices)


def test_conventional_matrix_wrong_length_raises(tmp_path):
    index, manifest = build_index(tmp_path)
    store_path = tmp_path / "embeddings.parquet"
    bad_conv = np.zeros((3, 10), dtype=np.float32)
    with pytest.raises(ValueError, match="align"):
        RetrievalIndex(store_path, manifest, conventional_matrix=bad_conv)
