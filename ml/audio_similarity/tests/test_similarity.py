"""Similarity math sanity: dot product of unit vectors == cosine similarity."""

from __future__ import annotations

import numpy as np
import pytest


def unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)


def test_dot_of_unit_vectors_equals_cosine():
    rng = np.random.default_rng(42)
    a = unit(rng.normal(size=128))
    b = unit(rng.normal(size=128))

    cosine = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    assert np.dot(a, b) == pytest.approx(cosine, abs=1e-12)
    assert -1.0 <= float(np.dot(a, b)) <= 1.0


def test_identical_vectors_score_one():
    v = unit(np.ones(128))
    assert float(np.dot(v, v)) == pytest.approx(1.0)


def test_opposite_vectors_score_minus_one():
    v = unit(np.ones(128))
    assert float(np.dot(v, -v)) == pytest.approx(-1.0)


def test_matrix_scores_match_pairwise_dots():
    rng = np.random.default_rng(0)
    E = unit(rng.normal(size=(10, 128)))
    q = unit(rng.normal(size=128))
    scores = E @ q
    expected = [float(np.dot(row, q)) for row in E]
    np.testing.assert_allclose(scores, expected, atol=1e-6)
