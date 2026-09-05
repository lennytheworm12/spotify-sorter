"""Prepare and run the Stage 5E.1 four-arm representation comparison."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5e1_analysis import analyze_retrieval
from audio_similarity.stage5e1_closeout import finalize_stage5e1
from audio_similarity.stage5e1_config import freeze_experiment
from audio_similarity.stage5e1_contract import prepare_stage5e1
from audio_similarity.stage5e1_materialize import (
    ARM_KEYS,
    cache_rerun,
    prime_historical_vectors,
    run_materialization,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "prepare", "freeze", "prime-cache", "run", "cache-rerun", "analyze",
            "finalize",
        ),
    )
    parser.add_argument(
        "--snapshot-active-retention",
        action="store_true",
        help="freeze the completed retained sources visible at command start while another retention batch continues",
    )
    parser.add_argument(
        "--arms",
        nargs="+",
        choices=ARM_KEYS,
        default=list(ARM_KEYS),
        help="representation passes to run; default executes all arms and fixed MuQ",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    if args.command == "prepare":
        print(
            json.dumps(
                prepare_stage5e1(
                    root,
                    snapshot_active_retention=args.snapshot_active_retention,
                ),
                indent=2,
            )
        )
    elif args.command == "freeze":
        print(json.dumps(freeze_experiment(root), indent=2))
    elif args.command == "prime-cache":
        print(json.dumps(prime_historical_vectors(root), indent=2))
    elif args.command == "run":
        print(json.dumps(run_materialization(root, arms=tuple(args.arms)), indent=2))
    elif args.command == "cache-rerun":
        print(json.dumps(cache_rerun(root), indent=2))
    elif args.command == "analyze":
        print(json.dumps(analyze_retrieval(root), indent=2))
    elif args.command == "finalize":
        print(json.dumps(finalize_stage5e1(root), indent=2))


if __name__ == "__main__":
    main()
