"""CLI for the bounded Stage 5B.4C official Data API fallback evaluation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ..stage5b4c_experiment import (
    OUTPUT_DIRECTORY,
    finalize,
    run_live,
    write_config,
    write_review,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("config", "live", "build-review", "finalize"))
    parser.add_argument("--focused-passed", type=int, default=0)
    parser.add_argument("--regression-passed", type=int)
    parser.add_argument("--full-passed", type=int)
    parser.add_argument("--full-deselected", type=int)
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[3]
    output_dir = project_root / OUTPUT_DIRECTORY
    if args.action == "config":
        result = write_config(project_root, output_dir)
    elif args.action == "live":
        result = run_live(
            project_root,
            output_dir,
            os.environ.get("YOUTUBE_DATA_API_KEY", ""),
        )
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
