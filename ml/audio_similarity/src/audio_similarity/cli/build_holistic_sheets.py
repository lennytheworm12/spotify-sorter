"""Stage 13-16 CLI: exact retrieval per encoder, candidate unions, blinded sheets.

    python -m audio_similarity.cli.build_holistic_sheets
"""

from __future__ import annotations

import argparse
from pathlib import Path

from audio_similarity.holistic_eval import (
    ENCODER_REPRS,
    build_trials,
    load_embeddings,
    build_unions,
    write_blinded_sheets,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", default="artifacts/holistic_stage1a")
    parser.add_argument("--queries", default="reports/holistic_stage1a/frozen_queries.csv")
    parser.add_argument("--manifest", default="data/manifests/fma_small.parquet")
    parser.add_argument("--output-dir", default="reports/holistic_stage1a")
    parser.add_argument("--trials-per-query", type=int, default=8)
    args = parser.parse_args()

    import pandas as pd

    embeddings = {}
    for enc in ENCODER_REPRS:
        path = Path(args.artifacts) / f"{enc}.parquet"
        vecs, key = load_embeddings(path)
        print(f"{enc}: {len(vecs)} embeddings (key {key[:8]})")
        if len(vecs) < 100:
            print(f"  WARNING: {enc} has too few embeddings — excluded from unions")
            continue
        embeddings[enc] = (vecs, key)

    queries = pd.read_csv(args.queries)["query_id"].astype(int).tolist()
    print(f"frozen queries: {len(queries)}")

    manifest = pd.read_parquet(args.manifest)
    unions = build_unions(embeddings, queries)

    # audio-level near-duplicate suppression uses MuQ as the reference geometry
    muq_vectors = embeddings["muq_mulan_large"][0]
    trials, provenance = build_trials(
        unions, manifest, n_trials_per_query=args.trials_per_query,
        reference_vectors=muq_vectors,
    )
    write_blinded_sheets(trials, provenance, args.output_dir)

    n = len(trials)
    print(f"generated {n} blinded A/B trials ({len(queries)} queries x ~{n // max(len(queries), 1)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
