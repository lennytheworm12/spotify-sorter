"""Freeze Phase 1B inputs: config + deterministic control manifests.

    python -m audio_similarity.cli.freeze_phase1b
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.phase1b_freeze import build_cases, freeze_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="data/manifests/fma_small.parquet")
    parser.add_argument("--embeddings", default="artifacts/phase1_full/embeddings.parquet")
    parser.add_argument("--key-factor", default="reports/human_eval/key_factor.csv")
    parser.add_argument("--conventional", default="data/fma/fma_metadata/features.csv")
    parser.add_argument("--queries", default="reports/phase1_queries.csv")
    parser.add_argument("--ratings", default="reports/human_eval/judgments_factor.csv")
    parser.add_argument("--output-dir", default="reports/phase1b")
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    cases = build_cases(
        args.manifest, args.embeddings, args.key_factor,
        args.conventional, args.queries,
    )
    payload = {"cases": [c.to_dict() for c in cases]}
    (out / "frozen_cases.json").write_text(json.dumps(payload, indent=1))

    config = freeze_config(
        out / "phase1b_config.json",
        manifest_path=args.manifest,
        embeddings_path=args.embeddings,
        key_factor_csv=args.key_factor,
        conventional_features_csv=args.conventional,
        queries_csv=args.queries,
        human_ratings_path=args.ratings,
        extra={"n_cases": len(cases)},
    )
    print(f"froze {len(cases)} cross-reference cases -> {out/'frozen_cases.json'}")
    print(f"config experiment_id={config['experiment_id']} commit={config['git_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
