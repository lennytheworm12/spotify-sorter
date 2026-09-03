"""Freeze the Stage 5B.2 raw YouTube ranking benchmark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b2_youtube_prior import (
    build_blinded_sol_payload,
    freeze_youtube_prior_manifest,
    load_youtube_prior_config,
    run_top3_discovery,
)
from audio_similarity.stage5b2_youtube_prior_review import (
    write_closeout_artifacts,
    write_human_review_artifacts,
)


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "freeze-manifest", "discover", "build-sol-payload", "build-review", "closeout"
        ),
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=root / "reports/stage5b_representative_library_v1/library_snapshot.private.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "reports/stage5b_youtube_prior_v1",
    )
    args = parser.parse_args(argv)
    if args.action == "freeze-manifest":
        result = freeze_youtube_prior_manifest(root, args.snapshot, args.output_dir)
        output = {
            "status": "STAGE5B2_MANIFEST_FROZEN",
            "track_count": result["manifest"]["sampled_track_count"],
            "manifest_sha256": result["manifest_sha256"],
        }
    else:
        config = load_youtube_prior_config(args.output_dir / "benchmark_config.json")
        if args.action == "discover":
            result = run_top3_discovery(config)
            output = {"status": result["status"], **result["summary"]}
        elif args.action == "build-sol-payload":
            result = build_blinded_sol_payload(config)
            output = {
                "status": "STAGE5B2_SOL_PAYLOAD_FROZEN",
                "track_count": result["track_count"],
                "candidate_count": result["candidate_count"],
            }
        elif args.action == "build-review":
            queue, review_path = write_human_review_artifacts(config)
            output = {
                "status": "STAGE5B2_HUMAN_REVIEW_READY",
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
