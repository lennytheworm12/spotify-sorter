"""Baseline B: FMA conventional features (Phase 1 doc, section 9).

Deliberately simple: numeric FMA features.csv -> median-fill missing ->
standardize -> L2 normalize -> cosine retrieval. Not a feature-engineering
project.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def load_conventional_features(
    features_csv: str | Path,
    track_ids: np.ndarray,
) -> tuple[np.ndarray, list[str]]:
    """Return (matrix [len(track_ids), d] aligned to sorted track_ids, feature names)."""
    frame = pd.read_csv(features_csv, index_col=0, header=[0, 1, 2])
    frame.columns = ["|".join(map(str, c)) for c in frame.columns]
    feature_cols = [c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
    feature_frame = frame[feature_cols].copy()
    feature_frame.index = feature_frame.index.astype(np.int64)
    feature_frame.index.name = "track_id"
    aligned = feature_frame.reindex(pd.Index(track_ids.astype(feature_frame.index.dtype)))
    matrix = np.array(aligned.to_numpy(dtype=np.float64), copy=True)

    # median-fill missing values (per feature), computed on the aligned subset
    medians = np.nanmedian(np.where(np.isfinite(matrix), matrix, np.nan), axis=0)
    medians = np.where(np.isfinite(medians), medians, 0.0)
    nan_mask = ~np.isfinite(matrix)
    matrix[nan_mask] = np.take(medians, np.where(nan_mask)[1])

    # standardize; guard zero-variance columns
    std = matrix.std(axis=0)
    std[std == 0] = 1.0
    matrix = (matrix - matrix.mean(axis=0)) / std

    return matrix.astype(np.float32), feature_cols
