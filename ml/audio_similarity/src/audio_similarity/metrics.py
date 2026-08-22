"""Automatic evaluation metrics (Phase 1 doc, section 14).

Genre overlap@k, same-artist rate@k, cross-factor Jaccard@k, and pairwise
score-correlation matrices over a deterministic sample of track pairs.
Genre is a weak diagnostic proxy only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .retrieval import Neighbor, RetrievalIndex


def _lookup(meta: pd.DataFrame, track_id: int, column: str) -> str:
    if track_id not in meta.index:
        return ""
    value = meta.at[track_id, column]
    return "" if pd.isna(value) else str(value)


def genre_overlap(
    neighbors: list[Neighbor],
    query_track_id: int,
    manifest: pd.DataFrame,
    k: int,
) -> float | None:
    """Fraction of top-k neighbors sharing the query's top-level genre."""
    meta = manifest.set_index("track_id")
    query_genre = _lookup(meta, query_track_id, "top_genre")
    if not query_genre:
        return None
    top_k = [n for n in neighbors if n.rank <= k]
    if not top_k:
        return None
    matches = sum(1 for n in top_k if _lookup(meta, n.track_id, "top_genre") == query_genre)
    return matches / len(top_k)


def same_artist_rate(
    neighbors: list[Neighbor],
    query_track_id: int,
    manifest: pd.DataFrame,
    k: int,
) -> float | None:
    """Fraction of top-k neighbors by the same artist as the query."""
    meta = manifest.set_index("track_id")
    query_artist = _lookup(meta, query_track_id, "artist")
    top_k = [n for n in neighbors if n.rank <= k]
    if not top_k:
        return None
    hits = sum(1 for n in top_k if _lookup(meta, n.track_id, "artist") == query_artist)
    return hits / len(top_k)


def jaccard_at_k(set_a: list[Neighbor], set_b: list[Neighbor], k: int) -> float | None:
    ids_a = {n.track_id for n in set_a if n.rank <= k}
    ids_b = {n.track_id for n in set_b if n.rank <= k}
    union = ids_a | ids_b
    if not union:
        return None
    return len(ids_a & ids_b) / len(union)


def pair_scores(
    index: RetrievalIndex,
    sample_ids: list[int],
    representations: tuple[str, ...],
    seed: int = 20260822,
    pairs_per_query: int = 20,
) -> pd.DataFrame:
    """Similarity scores for the SAME sampled pairs under every representation."""
    rng = np.random.default_rng(seed)
    all_ids = index.track_ids
    columns: dict[str, list[float]] = {rep: [] for rep in representations}

    for query in sample_ids:
        partners = rng.choice(
            all_ids[all_ids != query], size=min(pairs_per_query, len(all_ids) - 1), replace=False
        )
        qrow = index._id_to_row[int(query)]
        for partner in partners:
            prow = index._id_to_row[int(partner)]
            for rep in representations:
                matrix = index.matrices[rep]
                columns[rep].append(float(matrix[qrow] @ matrix[prow]))

    return pd.DataFrame(columns)


def correlation_matrices(
    index: RetrievalIndex,
    sample_ids: list[int],
    representations: tuple[str, ...],
    seed: int = 20260822,
    pairs_per_query: int = 20,
) -> dict[str, pd.DataFrame]:
    scores = pair_scores(index, sample_ids, representations, seed, pairs_per_query)
    return {
        "pearson": scores.corr(method="pearson"),
        "spearman": scores.corr(method="spearman"),
    }
