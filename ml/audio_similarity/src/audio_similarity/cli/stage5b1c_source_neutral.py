"""Offline Stage 5B.1C-B frozen source-neutral evaluation CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5b1c_source_neutral import write_source_neutral_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate source-neutral fallback after frozen Balanced V1 and 1C-A"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/stage5b1b_fresh_challenge.json"),
    )
    parser.add_argument(
        "--tier2a-dir",
        type=Path,
        default=Path("reports/stage5b1c_a"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/stage5b1c_b"),
    )
    args = parser.parse_args()
    feature_path, decision_path, decisions = write_source_neutral_evaluation(
        args.config.resolve(),
        tier2a_dir=args.tier2a_dir.resolve(),
        output_dir=args.output_dir.resolve(),
    )
    print(
        json.dumps(
            {
                "status": "STAGE5B1C_B_SOURCE_NEUTRAL_EVALUATED",
                **decisions["summary"],
                "features": str(feature_path),
                "features_sha256": file_sha256(feature_path),
                "decisions": str(decision_path),
                "decisions_sha256": file_sha256(decision_path),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
