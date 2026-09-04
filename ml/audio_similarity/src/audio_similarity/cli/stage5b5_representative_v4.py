"""Freeze, run, review, and close Representative Library V4."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b5_representative_v4 import (
    OUTPUT_DIRECTORY,
    freeze_v4_manifest,
    load_v4_config,
    run_frozen_selector,
    run_v4_discovery,
)
from audio_similarity.stage5b5_review import (
    write_closeout_artifacts,
    write_human_review_artifacts,
)


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("freeze-manifest", "discover", "run-selector", "build-review", "closeout"),
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=root / "reports/stage5b_representative_library_v1/library_snapshot.private.json",
    )
    parser.add_argument("--output-dir", type=Path, default=root / OUTPUT_DIRECTORY)
    parser.add_argument("--focused-passed", type=int, default=0)
    parser.add_argument("--stage5b-passed", type=int)
    parser.add_argument("--full-passed", type=int)
    parser.add_argument("--full-deselected", type=int)
    args = parser.parse_args(argv)
    if args.action == "freeze-manifest":
        result = freeze_v4_manifest(root, args.snapshot, args.output_dir)
        output = {
            "status": "STAGE5B5_MANIFEST_FROZEN",
            "track_count": result["manifest"]["sampled_track_count"],
            "eligible_track_count": result["manifest"]["eligible_heldout_track_count"],
            "manifest_sha256": result["manifest_sha256"],
        }
    else:
        config = load_v4_config(args.output_dir / "benchmark_config.json")
        if args.action == "discover":
            result = run_v4_discovery(config)
            output = {"status": result["status"], **result["summary"]}
        elif args.action == "run-selector":
            _decisions, metrics = run_frozen_selector(config)
            output = {
                "status": metrics["status"],
                "auto_select_count": metrics["auto_select_count"],
                "match_uncertain_count": metrics["match_uncertain_count"],
            }
        elif args.action == "build-review":
            queue, review = write_human_review_artifacts(config)
            output = {
                "status": queue["status"],
                "track_count": queue["track_count"],
                "candidate_count": queue["candidate_count"],
                "review_path": str(review),
            }
        else:
            output = write_closeout_artifacts(
                config,
                focused_passed=args.focused_passed,
                stage5b_passed=args.stage5b_passed,
                full_passed=args.full_passed,
                full_deselected=args.full_deselected,
            )
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
