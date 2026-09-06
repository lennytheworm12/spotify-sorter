"""Stage 5F.1 full-track energy and motion commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5f1_pipeline import (
    audit_gain,
    cache_rerun,
    compare_and_analyze,
    finalize,
    fit_scaler,
    golden,
    materialize,
    prepare,
    synthetic,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "prepare", "validate-synthetic", "materialize", "materialize-reference741",
        "validate-golden", "fit-scaler", "audit-gain", "analyze-rated-pairs", "cache-rerun", "finalize",
    ))
    parser.add_argument("--run-id", default="energy_motion_v1")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    commands = {
        "prepare": lambda: prepare(root, args.run_id),
        "validate-synthetic": lambda: synthetic(root, args.run_id),
        "materialize": lambda: materialize(root, args.run_id),
        "materialize-reference741": lambda: materialize(root, args.run_id, "reference741"),
        "validate-golden": lambda: golden(root, args.run_id),
        "fit-scaler": lambda: fit_scaler(root, args.run_id),
        "audit-gain": lambda: audit_gain(root, args.run_id),
        "analyze-rated-pairs": lambda: compare_and_analyze(root, args.run_id),
        "cache-rerun": lambda: cache_rerun(root, args.run_id),
        "finalize": lambda: finalize(root, args.run_id),
    }
    print(json.dumps(commands[args.command](), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
