"""Validate and freeze completed single-reviewer Stage 2B labels."""

from __future__ import annotations

import argparse

from audio_similarity.stage2b_ratings import validate_and_freeze_ratings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/holistic_stage2b_fusion_single_reviewer.yaml")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    summary = validate_and_freeze_ratings(args.config, args.root)
    print(
        f"froze {summary['canonical_trial_count']} canonical trials from "
        f"{summary['distinct_reviewers']} designated reviewer "
        f"({summary['self_correction_event_count']} self-corrections)"
    )


if __name__ == "__main__":
    main()
