"""CLI for the bounded Stage 5B.4C artist-decomposition evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..stage5b4c_artist_decomposition_experiment import (
    OUTPUT_DIRECTORY,
    finalize,
    prepare,
    run_live,
    write_review,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "live", "build-review", "finalize"))
    parser.add_argument("--focused-passed", type=int, default=0)
    parser.add_argument("--regression-passed", type=int)
    parser.add_argument("--full-passed", type=int)
    parser.add_argument("--full-deselected", type=int)
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[3]
    output_dir = project_root / OUTPUT_DIRECTORY
    if args.action == "prepare":
        result = prepare(project_root, output_dir)
    elif args.action == "live":
        result = run_live(project_root, output_dir)
    elif args.action == "build-review":
        result = {"human_review": str(write_review(output_dir))}
    else:
        result = finalize(
            project_root,
            output_dir,
            focused_passed=args.focused_passed,
            regression_passed=args.regression_passed,
            full_passed=args.full_passed,
            full_deselected=args.full_deselected,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
