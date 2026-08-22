"""Automatic metric tests (Phase 1 doc, section 14)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from audio_similarity.metrics import (
    correlation_matrices,
    genre_overlap,
    jaccard_at_k,
    pair_scores,
    same_artist_rate,
)
from audio_similarity.retrieval import Neighbor


def make_manifest() -> pd.DataFrame:
    rows = []
    for tid in range(1, 11):
        rows.append(
            {
                "track_id": tid,
                "artist": "same" if tid <= 3 else f"a{tid}",
                "top_genre": "rock" if tid % 2 else "pop",
                "title": f"t{tid}",
            }
        )
    return pd.DataFrame(rows)


def neighbors_for(ids: list[int]) -> list[Neighbor]:
    return [Neighbor(rank=i + 1, track_id=tid, score=1.0 / (i + 1)) for i, tid in enumerate(ids)]


def test_genre_overlap_counts_matching_genres():
    manifest = make_manifest()
    # query 1 (odd -> rock); neighbors 2(pop) 3(rock) 4(pop) -> overlap@3 = 1/3
    result = genre_overlap(neighbors_for([2, 3, 4]), 1, manifest, k=3)
    assert result == pytest.approx(1 / 3)
    # all-rock neighborhood scores 1.0
    assert genre_overlap(neighbors_for([3, 5, 7]), 1, manifest, k=3) == pytest.approx(1.0)


def test_genre_overlap_none_when_query_genre_missing():
    manifest = make_manifest()
    manifest.loc[manifest["track_id"] == 1, "top_genre"] = ""
    assert genre_overlap(neighbors_for([2, 3]), 1, manifest, k=2) is None


def test_same_artist_rate():
    manifest = make_manifest()
    # query 1 ("same"); neighbors include artists same,same,a4 -> rate@3 = 2/3
    result = same_artist_rate(neighbors_for([2, 3, 4]), 1, manifest, k=3)
    assert result == pytest.approx(2 / 3)
    # with artist exclusion downstream this should drop to 0
    result_excl = same_artist_rate(neighbors_for([4, 5, 6]), 1, manifest, k=3)
    assert result_excl == 0.0


def test_jaccard_at_k():
    a = neighbors_for([1, 2, 3, 4])
    b = neighbors_for([1, 2, 5, 6])
    assert jaccard_at_k(a, b, k=2) == pytest.approx(1.0)  # {1,2} identical at top-2
    assert jaccard_at_k(a, b, k=3) == pytest.approx(2 / 4)  # |{1,2}| / |{1,2,3,5}|


def test_jaccard_empty_returns_none():
    a: list[Neighbor] = []
    b: list[Neighbor] = []
    assert jaccard_at_k(a, b, k=5) is None


class FakeIndex:
    """Minimal RetrievalIndex duck-type: deterministic orthogonal-ish vectors."""

    def __init__(self, n: int = 10, dim: int = 8):
        rng = np.random.default_rng(7)
        self.track_ids = np.arange(1, n + 1)
        base = rng.normal(size=(n, dim))
        self.matrices = {
            "melody": base / np.linalg.norm(base, axis=1, keepdims=True),
            "rhythm": rng.normal(size=(n, dim)) / np.sqrt(dim),
            "timbre": np.eye(n, dim)[:n],
        }
        self._id_to_row = {int(tid): i for i, tid in enumerate(self.track_ids)}


def test_pair_scores_same_pairs_across_representations():
    index = FakeIndex()
    scores = pair_scores(index, sample_ids=[1, 2], representations=("melody", "rhythm"), pairs_per_query=5)
    assert scores.shape == (10, 2)
    assert scores["melody"].notna().all()


def test_correlation_matrices_symmetric_diagonal_one():
    index = FakeIndex()
    result = correlation_matrices(index, sample_ids=[1, 2, 3], representations=("melody", "rhythm"))
    pearson = result["pearson"]
    assert pearson.loc["melody", "melody"] == pytest.approx(1.0)
    assert pearson.loc["melody", "rhythm"] == pytest.approx(pearson.loc["rhythm", "melody"])
    assert -1.0 <= float(pearson.loc["melody", "rhythm"]) <= 1.0
    assert set(result) == {"pearson", "spearman"}


def test_correlation_perfectly_identical_columns_score_one(tmp_path):
    class SameMatrix(FakeIndex):
        def __init__(self):
            super().__init__()
            m = self.matrices["melody"]
            self.matrices["rhythm"] = m.copy()

    index = SameMatrix()
    result = correlation_matrices(index, sample_ids=[1], representations=("melody", "rhythm"), pairs_per_query=8)
    assert result["pearson"].loc["melody", "rhythm"] == pytest.approx(1.0)
