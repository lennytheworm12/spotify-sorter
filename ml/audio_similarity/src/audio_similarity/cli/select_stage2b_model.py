"""Run locked TRAIN/VALIDATION-only Stage 2B model selection."""

from __future__ import annotations

import argparse

from audio_similarity.stage2b_selection import run_model_selection


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/holistic_stage2b_fusion_single_reviewer.yaml")
    parser.add_argument("--root", default=".")
    parser.add_argument("--ratings", default=None, help="must be the frozen TRAIN/VALIDATION canonical export")
    args = parser.parse_args()
    result = run_model_selection(args.config, args.root, args.ratings)
    print(f"selected individual: {result['selected_individual']}")
    print(f"selected fusion: {result['selected_fusion']} (C={result['selected_fusion_C']})")
    print("TEST labels accessed: false")


if __name__ == "__main__":
    main()
