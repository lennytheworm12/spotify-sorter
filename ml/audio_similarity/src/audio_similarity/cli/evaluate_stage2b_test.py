"""Perform the one-time pushed-checkpoint-locked Stage 2B TEST reveal."""

from __future__ import annotations

import argparse

from audio_similarity.stage2b_test import run_locked_test
from audio_similarity.stage2b_verify import verify_existing_test


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/holistic_stage2b_fusion_single_reviewer.yaml")
    parser.add_argument("--root", default=".")
    parser.add_argument("--verify", action="store_true", help="hash-check existing outputs without rerunning TEST")
    args = parser.parse_args()
    if args.verify:
        verified = verify_existing_test(args.config, args.root)
        print(f"verified existing verdict: {verified['verdict']}")
        print(f"selected representation: {verified['selected_representation']}")
        return
    result = run_locked_test(args.config, args.root)
    comparison = result["headline_fusion_minus_individual"]
    print(f"verdict: {result['verdict']}")
    print(f"selected representation: {result['selected_representation']}")
    print(
        f"fusion-individual={comparison['estimate']:.4f}, "
        f"95% CI=[{comparison['ci_95'][0]:.4f}, {comparison['ci_95'][1]:.4f}]"
    )


if __name__ == "__main__":
    main()
