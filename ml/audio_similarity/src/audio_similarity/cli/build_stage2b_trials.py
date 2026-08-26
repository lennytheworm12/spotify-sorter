"""Build frozen balanced Stage 2B disagreement trials from validated artifacts."""

from __future__ import annotations

import argparse

from audio_similarity.stage2b_trials import build_balanced_trials


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/holistic_stage2b_fusion.yaml")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    balance = build_balanced_trials(args.config, args.root)
    print(f"selected {balance['selected_total']} trials: {balance['selected_pair_counts']}")
    print(f"balance ratio={balance['min_to_max_ratio']:.3f} gate={balance['gate_passed']}")


if __name__ == "__main__":
    main()
