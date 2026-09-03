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


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze-manifest", "discover", "build-sol-payload"))
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
        else:
            result = build_blinded_sol_payload(config)
            output = {
                "status": "STAGE5B2_SOL_PAYLOAD_FROZEN",
                "track_count": result["track_count"],
                "candidate_count": result["candidate_count"],
            }
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
