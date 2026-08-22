"""Exact nearest-neighbor retrieval (Phase 1 doc, section 10).

Cosine-only, exact search — no ANN in Phase 1. All stored vectors are
L2-normalized, so scores = E @ q is exact cosine similarity.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

REPRESENTATIONS = ("melody", "rhythm", "timbre", "mert_general", "conventional_features")
FACTOR_REPRESENTATIONS = ("melody", "rhythm", "timbre", "mert_general")


@dataclass
class Neighbor:
    rank: int
    track_id: int
    score: float


def l2_normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class RetrievalIndex:
    """Exact search over one analysis key's embeddings + metadata."""

    def __init__(
        self,
        embeddings_parquet: str | Path,
        manifest: pd.DataFrame,
        conventional_matrix: np.ndarray | None = None,
        representations: tuple[str, ...] = FACTOR_REPRESENTATIONS,
    ):
        table = pq.read_table(embeddings_parquet)
        rows = table.to_pylist()
        if not rows:
            raise ValueError("embedding store is empty")

        # keep only current-key rows; a store may hold multiple model versions
        keys = {r["analysis_key"] for r in rows}
        if len(keys) > 1:
            raise ValueError(f"store holds {len(keys)} analysis keys; rebuild per key")

        self.track_ids = np.asarray([int(r["track_id"]) for r in rows], dtype=np.int64)
        order = np.argsort(self.track_ids, kind="stable")
        self.track_ids = self.track_ids[order]

        self.matrices: dict[str, np.ndarray] = {}
        for rep in representations:
            if rep == "conventional_features":
                continue
            column = np.asarray(
                [np.asarray(r[rep], dtype=np.float32) for r in rows], dtype=np.float32
            )[order]
            self.matrices[rep] = l2_normalize_rows(column)

        if conventional_matrix is not None:
            conv = np.asarray(conventional_matrix, dtype=np.float32)
            if len(conv) != len(self.track_ids):
                raise ValueError("conventional matrix must align with embedding rows")
            self.matrices["conventional_features"] = l2_normalize_rows(conv)

        meta = manifest.set_index("track_id")
        self.artists = {
            int(tid): str(meta.at[tid, "artist"]) if tid in meta.index else ""
            for tid in self.track_ids
        }
        self._id_to_row = {tid: i for i, tid in enumerate(self.track_ids)}

    def vector(self, representation: str, track_id: int) -> np.ndarray:
        return self.matrices[representation][self._id_to_row[track_id]]

    @staticmethod
    def _deterministic_top_k(scores: np.ndarray, ids: np.ndarray, k: int) -> list[tuple[float, int]]:
        # stable sort on descending score, tie-broken by track id ascending;
        # masked (-inf) rows drop out rather than filling the tail
        finite = np.isfinite(scores)
        order = np.lexsort((ids[finite], -scores[finite]))[:k]
        return [(float(scores[finite][i]), int(ids[finite][i])) for i in order]

    def search(
        self,
        representation: str,
        query_track_id: int,
        k: int,
        exclude_same_artist: bool = False,
        include_self: bool = False,
    ) -> list[Neighbor]:
        if representation not in self.matrices:
            raise KeyError(f"unknown representation '{representation}'")
        matrix = self.matrices[representation]
        query = matrix[self._id_to_row[query_track_id]]
        scores = matrix @ query

        disallowed = set() if include_self else {query_track_id}
        if exclude_same_artist:
            query_artist = self.artists.get(int(query_track_id), "")
            disallowed.update(
                int(tid)
                for tid in self.track_ids
                if tid != query_track_id and self.artists.get(int(tid)) == query_artist and query_artist
            )

        mask = np.isin(self.track_ids, list(disallowed))
        candidate_scores = np.where(mask, -np.inf, scores)
        top = self._deterministic_top_k(candidate_scores, self.track_ids, k)
        return [Neighbor(rank=i + 1, track_id=tid, score=s) for i, (s, tid) in enumerate(top)]

    def neighbor_frame(
        self,
        representation: str,
        query_track_id: int,
        k: int,
        exclude_same_artist: bool = False,
        manifest: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        neighbors = self.search(representation, query_track_id, k, exclude_same_artist)
        records = [
            {"rank": n.rank, "track_id": n.track_id, "cosine_similarity": round(n.score, 6)}
            for n in neighbors
        ]
        frame = pd.DataFrame(records)
        if manifest is not None:
            meta = manifest.set_index("track_id")
            for col in ("title", "artist", "top_genre"):
                frame[col] = [meta.at[t, col] if t in meta.index else "" for t in frame["track_id"]]
        return frame
