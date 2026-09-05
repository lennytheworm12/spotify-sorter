"""Run the bounded Stage 5B.4B Playwright fallback evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from audio_similarity.stage5b4b_experiment import (
    OUTPUT_DIRECTORY,
    run_bounded_browser_diagnostic,
    run_live_evaluation,
    write_closeout,
    write_fallback_config,
    write_human_review,
)


def _verification(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    return {
        "focused": {
            "passed": bool(args.focused_passed and args.focused_passed > 0),
            "count": args.focused_passed,
        },
        "stage5b_regressions": {
            "passed": bool(args.regression_passed and args.regression_passed > 0),
            "count": args.regression_passed,
        },
        "full_non_heavy": {
            "passed": bool(args.full_passed and args.full_passed > 0),
            "count": args.full_passed,
            "deselected": args.full_deselected,
        },
    }


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("config", "live", "classify-browser-state", "build-review", "closeout"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / OUTPUT_DIRECTORY,
    )
    parser.add_argument("--focused-passed", type=int)
    parser.add_argument("--regression-passed", type=int)
    parser.add_argument("--full-passed", type=int)
    parser.add_argument("--full-deselected", type=int)
    args = parser.parse_args(argv)
    if args.action == "config":
        result = write_fallback_config(project_root, args.output_dir)
        output = {"experiment_id": result["experiment_id"], "query": result["query"]}
    elif args.action == "live":
        output = run_live_evaluation(project_root, args.output_dir)
    elif args.action == "classify-browser-state":
        output = run_bounded_browser_diagnostic(args.output_dir)
    elif args.action == "build-review":
        output = {"human_review": str(write_human_review(args.output_dir))}
    else:
        result = write_closeout(project_root, args.output_dir, _verification(args))
        output = {"verdict": result["verdict"]}
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
