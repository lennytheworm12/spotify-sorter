"""Metrics shared by Stage 2B selection and held-out evaluation."""

from __future__ import annotations

from typing import Any

import numpy as np

from .stage2b_contract import ContractError


def accuracy_contributions(margins: np.ndarray, labels: np.ndarray) -> np.ndarray:
    margins = np.asarray(margins, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int64)
    if margins.shape != labels.shape or not np.isfinite(margins).all() or not set(labels).issubset({0, 1}):
        raise ContractError("invalid margins/labels")
    signed = margins * (2 * labels - 1)
    return np.where(signed > 0, 1.0, np.where(signed < 0, 0.0, 0.5))


def query_macro_accuracy(margins: np.ndarray, labels: np.ndarray, query_ids: np.ndarray) -> dict[str, Any]:
    contributions = accuracy_contributions(margins, labels)
    query_ids = np.asarray(query_ids)
    if query_ids.shape != labels.shape:
        raise ContractError("query IDs do not align with labels")
    per_query = {
        str(query): float(contributions[query_ids == query].mean())
        for query in sorted(set(query_ids.tolist()))
    }
    if not per_query:
        raise ContractError("query-macro accuracy has no represented queries")
    return {"query_macro_accuracy": float(np.mean(list(per_query.values()))), "per_query_accuracy": per_query}


def binary_log_loss(probabilities: np.ndarray, labels: np.ndarray) -> float:
    probabilities = np.asarray(probabilities, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.float64)
    if probabilities.shape != labels.shape or not np.isfinite(probabilities).all():
        raise ContractError("invalid probabilities/labels")
    clipped = np.clip(probabilities, 1e-15, 1 - 1e-15)
    return float(-np.mean(labels * np.log(clipped) + (1 - labels) * np.log(1 - clipped)))
