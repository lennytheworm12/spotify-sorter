"""Build the immutable Stage 2B fusion feature dataset."""

from __future__ import annotations

import argparse

from audio_similarity.stage2b_dataset import build_fusion_dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/holistic_stage2b_fusion_single_reviewer.yaml")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    summary = build_fusion_dataset(args.config, args.root)
    print(
        f"built {summary['row_count']} rows: {summary['binary_row_count']} binary, "
        f"{summary['excluded_row_count']} ambiguous"
    )


if __name__ == "__main__":
    main()
