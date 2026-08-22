"""Run automatic evaluation metrics over a completed embedding store.

    python -m audio_similarity.cli.run_automatic_metrics \
        --embeddings artifacts/phase1_full/embeddings.parquet \
        --features data/fma/fma_metadata/features.csv \
        --manifest data/manifests/fma_small.parquet \
        --output reports/automatic_metrics.json

Produces genre overlap@{5,10,20}, same-artist@{5,10,20} (with and without
same-artist exclusion), cross-factor Jaccard@{5,10,20}, Pearson/Spearman
score-correlation matrices, and exact top-10 search latency percentiles.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from audio_similarity.conventional_features import load_conventional_features
from audio_similarity.manifest import load_manifest
from audio_similarity.metrics import (
    correlation_matrices,
    genre_overlap,
    jaccard_at_k,
    same_artist_rate,
)
from audio_similarity.retrieval import FACTOR_REPRESENTATIONS, RetrievalIndex


def evaluate_representation(
    index: RetrievalIndex,
    representation: str,
    query_ids: list[int],
    manifest: pd.DataFrame,
    ks: tuple[int, ...] = (5, 10, 20),
) -> dict:
    out: dict = {"n_queries": len(query_ids)}
    for k in ks:
        overlaps, artist_rates = [], []
        overlaps_excl, _ = [], []
        for qid in query_ids:
            neighbors = index.search(representation, qid, k=max(ks))
            go = genre_overlap(neighbors, qid, manifest, k)
            sa = same_artist_rate(neighbors, qid, manifest, k)
            if go is not None:
                overlaps.append(go)
            if sa is not None:
                artist_rates.append(sa)
            neighbors_excl = index.search(
                representation, qid, k=k, exclude_same_artist=True
            )
            go_excl = genre_overlap(neighbors_excl, qid, manifest, k)
            if go_excl is not None:
                overlaps_excl.append(go_excl)
        out[f"genre_overlap@{k}"] = float(np.mean(overlaps)) if overlaps else None
        out[f"genre_overlap_excl_artist@{k}"] = (
            float(np.mean(overlaps_excl)) if overlaps_excl else None
        )
        out[f"same_artist@{k}"] = float(np.mean(artist_rates)) if artist_rates else None
    return out


def search_latency_benchmark(index: RetrievalIndex, query_ids: list[int], k: int = 10) -> dict:
    latencies_ms = []
    build_start = time.perf_counter()
    _ = index.matrices["melody"].shape  # touch; index construction happens outside timing
    build_sec = time.perf_counter() - build_start
    for rep in ("melody", "rhythm", "timbre", "mert_general"):
        for qid in query_ids:
            t0 = time.perf_counter()
            index.search(rep, qid, k=k)
            latencies_ms.append((time.perf_counter() - t0) * 1000)
    arr = np.asarray(latencies_ms)
    return {
        "top10_search_p50_ms": float(np.percentile(arr, 50)),
        "top10_search_p95_ms": float(np.percentile(arr, 95)),
        "index_matrix_build_sec_approx": build_sec,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", required=True)
    parser.add_argument("--features", required=True)
    parser.add_argument("--manifest", default="data/manifests/fma_small.parquet")
    parser.add_argument("--queries", default=None, help="optional frozen query csv; else deterministic sample")
    parser.add_argument("--output", required=True)
    parser.add_argument("--sample-queries", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260822)
    args = parser.parse_args()

    with open("configs/phase1_fma_small.yaml") as fh:
        config = yaml.safe_load(fh)
    seed = args.seed or config.get("evaluation", {}).get("seed", 20260822)

    manifest = load_manifest(args.manifest)
    import pyarrow.parquet as pq

    encoded_track_ids = np.asarray(
        sorted(set(pq.read_table(args.embeddings, columns=["track_id"]).column("track_id").to_pylist())),
        dtype=np.int64,
    )
    conventional_matrix, _ = load_conventional_features(args.features, encoded_track_ids)
    index = RetrievalIndex(args.embeddings, manifest, conventional_matrix=conventional_matrix)

    if args.queries:
        query_ids = [int(t) for t in pd.read_csv(args.queries)["track_id"]]
    else:
        rng = np.random.default_rng(seed)
        query_ids = [int(t) for t in rng.choice(index.track_ids, size=args.sample_queries, replace=False)]

    report: dict = {"n_indexed": int(len(index.track_ids)), "representations": {}}
    representations = (*FACTOR_REPRESENTATIONS, "conventional_features")
    for rep in representations:
        print(f"evaluating {rep}...")
        report["representations"][rep] = evaluate_representation(index, rep, query_ids, manifest)

    jaccard_report: dict = {}
    for a, b in (("melody", "rhythm"), ("melody", "timbre"), ("rhythm", "timbre")):
        for k in (5, 10, 20):
            values = [
                jaccard_at_k(index.search(a, qid, k=20), index.search(b, qid, k=20), k)
                for qid in query_ids
            ]
            values = [v for v in values if v is not None]
            jaccard_report[f"{a}_vs_{b}@{k}"] = float(np.mean(values)) if values else None
    report["cross_factor_jaccard"] = jaccard_report

    corr_sample = [int(t) for t in np.random.default_rng(seed).choice(index.track_ids, size=min(100, len(index.track_ids)), replace=False)]
    corrs = correlation_matrices(index, corr_sample, FACTOR_REPRESENTATIONS, seed=seed)
    report["score_correlations"] = {
        method: frame.round(4).to_dict() for method, frame in corrs.items()
    }

    report["search_latency"] = search_latency_benchmark(index, query_ids[:50])
    report["query_ids"] = query_ids[:50] + ["...truncated"]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
