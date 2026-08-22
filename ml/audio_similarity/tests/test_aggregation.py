"""Aggregation contract tests (Phase 2 design sections 15-16)."""

from __future__ import annotations

import numpy as np
import pytest

from audio_similarity.aggregation import (
    UNIT_NORM_TOLERANCE,
    DEFAULT_AGGREGATOR,
    DimensionMismatchError,
    EmptyAggregationError,
    MeanL2Aggregator,
    NonFiniteEmbeddingError,
    ZeroNormAggregateError,
    assert_unit_norm,
    mean_l2,
)


def vec(*values: float) -> np.ndarray:
    return np.asarray(values, dtype=np.float64)


def test_single_vector_returns_same_normalized_vector():
    v = vec(3.0, 4.0)
    out = mean_l2([v])
    np.testing.assert_allclose(out, [0.6, 0.8])


def test_identical_vectors_aggregate_to_same_vector():
    unit = np.asarray([1.0, 0.0])
    out = mean_l2([unit, unit, unit])
    np.testing.assert_allclose(out, unit)


def test_orthogonal_vectors_average_to_diagonal():
    out = mean_l2([vec(1.0, 0.0), vec(0.0, 1.0)])
    expected = np.asarray([1.0, 1.0]) / np.linalg.norm([1.0, 1.0])
    np.testing.assert_allclose(out, expected)


def test_permutation_invariance():
    rng = np.random.default_rng(7)
    embeddings = [rng.normal(size=16) for _ in range(9)]
    a = mean_l2(embeddings)
    b = mean_l2([embeddings[i] for i in rng.permutation(len(embeddings))])
    np.testing.assert_allclose(a, b)


def test_output_is_finite_unit_vector():
    rng = np.random.default_rng(0)
    out = mean_l2([rng.normal(size=128) * 10 for _ in range(5)])
    assert np.isfinite(out).all()
    assert abs(float(np.linalg.norm(out)) - 1.0) <= UNIT_NORM_TOLERANCE


def test_opposite_vectors_raise_zero_norm():
    with pytest.raises(ZeroNormAggregateError):
        mean_l2([vec(1.0, 1.0), vec(-1.0, -1.0)])


def test_zero_vector_input_raises_zero_norm():
    with pytest.raises(ZeroNormAggregateError):
        mean_l2([np.zeros(8)])


def test_empty_input_raises():
    with pytest.raises(EmptyAggregationError):
        mean_l2([])


def test_dimension_mismatch_raises():
    with pytest.raises(DimensionMismatchError):
        mean_l2([vec(1.0, 2.0), vec(1.0, 2.0, 3.0)])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_inputs_raise(bad):
    with pytest.raises(NonFiniteEmbeddingError):
        mean_l2([vec(1.0, 2.0), vec(bad, 0.5)])


# ---------------------------------------------------------------------------
# named strategy object
# ---------------------------------------------------------------------------


def test_meanl2_strategy_object_contract():
    aggregator = MeanL2Aggregator()
    result = aggregator.aggregate([vec(3.0, 4.0), vec(3.0, 4.0)])
    assert result.identity == "mean_l2_v1"
    assert result.strategy_name == "mean_l2"
    assert result.strategy_version == 1
    assert result.n_segments == 2
    np.testing.assert_allclose(result.song_embedding, [0.6, 0.8], atol=UNIT_NORM_TOLERANCE)
    assert_unit_norm(result.song_embedding)


def test_default_aggregator_is_mean_l2_v1():
    assert DEFAULT_AGGREGATOR.identity == "mean_l2_v1"
