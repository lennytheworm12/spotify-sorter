"""Freeze, discover, evaluate, and close Stage 5B.4 Representative V3."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b4_representative_v3 import (
    freeze_v3_manifest,
    load_v3_config,
    run_frozen_selector,
    run_v3_discovery,
)
from audio_similarity.stage5b4_review import (
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
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "reports/stage5b4_representative_v3",
    )
    args = parser.parse_args(argv)
    if args.action == "freeze-manifest":
        result = freeze_v3_manifest(root, args.snapshot, args.output_dir)
        output = {
            "status": "STAGE5B4_MANIFEST_FROZEN",
            "track_count": result["manifest"]["sampled_track_count"],
            "eligible_track_count": result["manifest"]["eligible_heldout_track_count"],
            "manifest_sha256": result["manifest_sha256"],
        }
    else:
        config = load_v3_config(args.output_dir / "benchmark_config.json")
        if args.action == "discover":
            result = run_v3_discovery(config)
            output = {"status": result["status"], **result["summary"]}
        elif args.action == "run-selector":
            _decisions, result = run_frozen_selector(config)
            output = {
                "status": result["status"],
                "auto_select_count": result["auto_select_count"],
                "match_uncertain_count": result["match_uncertain_count"],
                "selected_rank_distribution": result["selected_rank_distribution"],
            }
        elif args.action == "build-review":
            queue, review_path = write_human_review_artifacts(config)
            output = {
                "status": queue["status"],
                "track_count": queue["track_count"],
                "candidate_count": queue["candidate_count"],
                "review_path": str(review_path),
            }
        else:
            output = write_closeout_artifacts(config)
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
