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
    frame = pd.read_csv(features_csv)
    feature_cols = [c for c in frame.columns if c != "track_id" and pd.api.types.is_numeric_dtype(frame[c])]
    frame = frame.set_index("track_id")[feature_cols]

    aligned = frame.reindex(pd.Index(track_ids.astype(frame.index.dtype)))
    matrix = aligned.to_numpy(dtype=np.float64)

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
