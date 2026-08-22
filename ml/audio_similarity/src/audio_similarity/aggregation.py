"""Segment embedding aggregation (Phase 2 design sections 15-16).

A0 MeanL2 v1: arithmetic mean of segment embeddings, then L2 normalize.
Permutation invariant; never silently normalizes invalid input.

For multi-factor representations (MERIT), apply per factor independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import math

import numpy as np


class AggregationInputError(ValueError):
    """Base class for invalid aggregation inputs."""


class EmptyAggregationError(AggregationInputError):
    """Raised when no segment embeddings are provided."""


class DimensionMismatchError(AggregationInputError):
    """Raised when segment embeddings have inconsistent dimensions."""


class NonFiniteEmbeddingError(AggregationInputError):
    """Raised when inputs contain NaN or Inf."""


class ZeroNormAggregateError(AggregationInputError):
    """Raised when the aggregate vector has zero norm (cannot normalize)."""


UNIT_NORM_TOLERANCE = 1e-6  # documented tolerance for the output unit-norm check


class AggregationStrategy(Protocol):
    name: str
    version: int

    def aggregate(self, embeddings: list[np.ndarray]) -> np.ndarray: ...


@dataclass(frozen=True)
class AggregationResult:
    song_embedding: np.ndarray
    strategy_name: str
    strategy_version: int
    n_segments: int

    @property
    def identity(self) -> str:
        return f"{self.strategy_name}_v{self.strategy_version}"


def _validated_matrix(embeddings: list[np.ndarray]) -> np.ndarray:
    if not embeddings:
        raise EmptyAggregationError("cannot aggregate an empty segment list")
    try:
        matrix = np.asarray([np.asarray(e, dtype=np.float64) for e in embeddings], dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise DimensionMismatchError(f"segment embeddings could not form a matrix: {exc}") from exc
    if matrix.ndim != 2:
        raise DimensionMismatchError(f"expected 2-D segment matrix, got shape {matrix.shape}")
    return matrix


def _check_finite(matrix: np.ndarray) -> None:
    if not np.isfinite(matrix).all():
        bad_positions = np.argwhere(~np.isfinite(matrix))
        raise NonFiniteEmbeddingError(f"non-finite values at positions {bad_positions[:5].tolist()}")


def mean_l2(embeddings: list[np.ndarray]) -> np.ndarray:
    """A0 MeanL2 v1 core: mean then L2 normalize, with typed failures."""
    matrix = _validated_matrix(embeddings)
    _check_finite(matrix)

    mean = matrix.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    if norm <= 0.0 or not math.isfinite(norm):
        raise ZeroNormAggregateError(
            "aggregate vector has zero/non-finite norm; refusing to normalize"
        )
    return mean / norm


@dataclass(frozen=True)
class MeanL2Aggregator:
    """Named strategy object so experiment configs can reference it by identity."""

    name: str = "mean_l2"
    version: int = 1

    @property
    def identity(self) -> str:
        return f"{self.name}_v{self.version}"

    def aggregate(self, embeddings: list[np.ndarray]) -> AggregationResult:
        vector = mean_l2(list(embeddings))
        return AggregationResult(
            song_embedding=vector.astype(np.float32),
            strategy_name=self.name,
            strategy_version=self.version,
            n_segments=len(embeddings),
        )


DEFAULT_AGGREGATOR = MeanL2Aggregator()


def assert_unit_norm(vector: np.ndarray, tolerance: float = UNIT_NORM_TOLERANCE) -> None:
    norm = float(np.linalg.norm(vector))
    assert abs(norm - 1.0) <= tolerance, f"unit-norm violation: {norm}"
