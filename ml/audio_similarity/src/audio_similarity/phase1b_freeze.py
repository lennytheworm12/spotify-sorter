"""Phase 1B — cross-reference construct validation (design sections 7-8, 26 Stage A/B).

Freezes the evaluation inputs: the existing 24 Phase 1 queries, their frozen
MERIT top-5 factor retrievals (from the blinded-eval key files), equivalent
general-MERT and conventional-feature retrievals, deterministic random
negatives, and matched hard negatives.

Nothing here reranks or regenerates MERIT. Group A is read verbatim from the
Phase 1 key files so the cross-reference measures exactly what humans judged.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

FACTORS = ("melody", "rhythm", "timbre")
N_RANDOM_NEGATIVES = 5
N_HARD_NEGATIVES = 5
RANDOM_SEED = 20260823
HARD_NEGATIVE_SEED = 20260823


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class CrossReferenceCase:
    query_id: int
    factor: str
    merit_target_neighbors: list[int]          # Group A (frozen Phase 1 retrieval)
    merit_other_neighbors: dict[str, list[int]]  # Group B {factor: ids}
    mert_general_neighbors: list[int]           # Group C
    conventional_neighbors: list[int]           # Group D
    random_negatives: list[int]                 # Group E
    hard_negatives: list[int]                   # Group F

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "factor": self.factor,
            "merit_target_neighbors": self.merit_target_neighbors,
            "merit_other_neighbors": {k: v for k, v in self.merit_other_neighbors.items()},
            "mert_general_neighbors": self.mert_general_neighbors,
            "conventional_neighbors": self.conventional_neighbors,
            "random_negatives": self.random_negatives,
            "hard_negatives": self.hard_negatives,
        }


def load_frozen_merit_retrievals(key_factor_csv: str | Path) -> pd.DataFrame:
    """Frozen Group A/B retrievals straight from the Phase 1 eval keys.

    cell_id format: '<query_id>:<factor>:<rank>'.
    """
    keys = pd.read_csv(key_factor_csv)
    parts = keys["cell_id"].str.split(":", expand=True)
    keys = keys.assign(
        query_track_id=parts[0].astype(int),
        target_factor=parts[1],
        neighbor_rank=parts[2].astype(int),
    )
    rows = []
    for (qid, factor), group in keys.groupby(["query_track_id", "target_factor"]):
        ranked = group.sort_values("neighbor_rank")
        rows.append(
            {
                "query_id": int(qid),
                "factor": str(factor),
                "neighbors": [int(t) for t in ranked["neighbor_track_id"]],
            }
        )
    return pd.DataFrame(rows)


def _top_k_from_index(index, representation: str, query_id: int, k: int = 5) -> list[int]:
    return [n.track_id for n in index.search(representation, int(query_id), k=k)]


def sample_random_negatives(
    rng: np.random.Generator,
    candidate_pool: np.ndarray,
    exclude: set[int],
    k: int,
) -> list[int]:
    pool = np.array([t for t in candidate_pool if int(t) not in exclude])
    chosen = rng.choice(pool, size=min(k, len(pool)), replace=False)
    return [int(t) for t in chosen]


def sample_hard_negatives(
    rng: np.random.Generator,
    manifest: pd.DataFrame,
    query_id: int,
    exclude: set[int],
    k: int,
    duration_tolerance_sec: float = 3.0,
) -> list[int]:
    """Same top-level genre, different artist, near-identical clip length."""
    meta = manifest.set_index("track_id")
    if query_id not in meta.index:
        return []
    qrow = meta.loc[query_id]
    pool = manifest[
        (manifest["top_genre"] == qrow["top_genre"])
        & (manifest["artist"] != qrow["artist"])
        & (manifest["decode_status"] == "SUCCESS")
        & (~manifest["track_id"].isin(exclude))
    ]
    if "duration_sec" in pool.columns and pd.notna(qrow.get("duration_sec")):
        target_dur = float(qrow["duration_sec"])
        dur = pd.to_numeric(pool["duration_sec"], errors="coerce")
        close = (dur - target_dur).abs() <= duration_tolerance_sec
        filtered = pool[close]
        pool = filtered if len(filtered) >= k else pool
    if pool.empty:
        return []
    chosen = rng.choice(pool["track_id"].to_numpy(), size=min(k, len(pool)), replace=False)
    return [int(t) for t in sorted(chosen)]


def build_cases(
    manifest_path: str | Path,
    embeddings_path: str | Path,
    key_factor_csv: str | Path,
    conventional_features_csv: str | Path | None = None,
    queries_csv: str | Path | None = None,
    n_random: int = N_RANDOM_NEGATIVES,
    n_hard: int = N_HARD_NEGATIVES,
    seed: int = RANDOM_SEED,
    hard_seed: int = HARD_NEGATIVE_SEED,
    conventional_matrix: np.ndarray | None = None,
) -> list[CrossReferenceCase]:
    from audio_similarity.manifest import load_manifest
    from audio_similarity.retrieval import RetrievalIndex
    from audio_similarity.conventional_features import load_conventional_features

    manifest = load_manifest(manifest_path)
    # align to actually-encoded clips (3 FMA files are undecodable)
    import pyarrow.parquet as pq

    encoded_ids = set(pq.read_table(embeddings_path, columns=["track_id"]).column("track_id").to_pylist())
    manifest = manifest[manifest["track_id"].isin(encoded_ids)].reset_index(drop=True)
    if conventional_matrix is None:
        assert conventional_features_csv is not None, "need conventional features source"
        conventional_matrix, _ = load_conventional_features(
            conventional_features_csv, manifest["track_id"].to_numpy()
        )
    index = RetrievalIndex(embeddings_path, manifest, conventional_matrix=conventional_matrix)

    frozen = load_frozen_merit_retrievals(key_factor_csv)
    if queries_csv and Path(queries_csv).exists():
        allowed_queries = set(pd.read_csv(queries_csv)["track_id"].astype(int))
        frozen = frozen[frozen["query_id"].isin(allowed_queries)]

    rng = np.random.default_rng(seed)
    hard_rng = np.random.default_rng(hard_seed)
    all_track_ids = index.track_ids

    cases: list[CrossReferenceCase] = []
    for _, row in frozen.sort_values(["query_id", "factor"]).iterrows():
        qid = int(row["query_id"])
        factor = str(row["factor"])
        target = [int(t) for t in row["neighbors"]]
        others: dict[str, list[int]] = {}
        for f in FACTORS:
            if f == factor:
                continue
            match = frozen[(frozen["query_id"] == qid) & (frozen["factor"] == f)]
            if not match.empty:
                others[f] = [int(t) for t in match["neighbors"].iloc[0]]

        mert_top5 = _top_k_from_index(index, "mert_general", qid)
        conv_top5 = _top_k_from_index(index, "conventional_features", qid)

        claimed = set(target) | {t for lst in others.values() for t in lst} \
            | set(mert_top5) | set(conv_top5) | {qid}
        random_negs = sample_random_negatives(rng, all_track_ids, claimed, n_random)

        hard_exclude = claimed | set(random_negs)
        hard_negs = sample_hard_negatives(hard_rng, manifest, qid, hard_exclude, n_hard)

        cases.append(
            CrossReferenceCase(
                query_id=qid,
                factor=factor,
                merit_target_neighbors=target,
                merit_other_neighbors=others,
                mert_general_neighbors=mert_top5,
                conventional_neighbors=conv_top5,
                random_negatives=random_negs,
                hard_negatives=hard_negs,
            )
        )
    return cases


def freeze_config(
    output_path: str | Path,
    *,
    manifest_path: str,
    embeddings_path: str,
    key_factor_csv: str,
    conventional_features_csv: str,
    queries_csv: str,
    human_ratings_path: str | None = None,
    extra: dict | None = None,
) -> dict:
    """Write the frozen Phase 1B configuration with artifact hashes."""
    config = {
        "experiment_id": "phase1b_cross_reference_v1",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "seeds": {"random_negatives": RANDOM_SEED, "hard_negatives": HARD_NEGATIVE_SEED},
        "artifact_hashes": {
            "manifest": sha256_file(manifest_path),
            "embeddings": sha256_file(embeddings_path),
            "key_factor": sha256_file(key_factor_csv),
            "conventional_features_source": sha256_file(conventional_features_csv),
            "queries": sha256_file(queries_csv),
            **({"human_ratings_snapshot": sha256_file(human_ratings_path)} if human_ratings_path else {}),
        },
        "feature_params": {
            "sample_rate": 24000,
            "mono": True,
            "n_fft": 2048,
            "hop_length": 512,
            "chroma": "cqt_v1",
            "n_mfcc": 20,
            "tempogram_win_length": 384,
            "top_db_rhythm": None,
        },
        "metric_params": {
            "background_pairs": 2000,
            "background_seed": 424242,
            "dtw_metric": "euclidean",
            "transposition_shifts": 12,
            "timbre_standardization": "corpus_zscore_l2_v1",
        },
        "control_sizes": {"random_negatives": N_RANDOM_NEGATIVES, "hard_negatives": N_HARD_NEGATIVES},
        **(extra or {}),
    }
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(config, indent=2))
    return config


def _git_commit() -> str:
    try:
        import subprocess

        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()[:12]
    except Exception:
        return "unknown"
