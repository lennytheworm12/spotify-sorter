"""Create the frozen 11-case Stage 5B.1C Tier-2 human-audit artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5b1c_review import write_tier2_review_artifacts


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "configs" / "stage5b1b_fresh_challenge.json",
    )
    parser.add_argument(
        "--tier2a-decisions",
        type=Path,
        default=root / "reports" / "stage5b1c_a" / "tier2_decisions.json",
    )
    parser.add_argument(
        "--source-neutral-decisions",
        type=Path,
        default=root / "reports" / "stage5b1c_b" / "source_neutral_decisions.json",
    )
    parser.add_argument(
        "--queue",
        type=Path,
        default=root / "reports" / "stage5b1c_b" / "tier2_human_audit_queue.json",
    )
    parser.add_argument(
        "--review",
        type=Path,
        default=root / "reports" / "stage5b1c_b" / "tier2_human_review.csv",
    )
    args = parser.parse_args()
    queue, rows = write_tier2_review_artifacts(
        config_path=args.config.resolve(),
        tier2a_decisions_path=args.tier2a_decisions.resolve(),
        source_neutral_decisions_path=args.source_neutral_decisions.resolve(),
        queue_path=args.queue.resolve(),
        review_path=args.review.resolve(),
    )
    print(
        json.dumps(
            {
                "status": queue["status"],
                "track_count": queue["track_count"],
                "candidate_count": len(rows),
                "queue": str(args.queue.resolve()),
                "queue_sha256": file_sha256(args.queue.resolve()),
                "review": str(args.review.resolve()),
                "review_sha256": file_sha256(args.review.resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
