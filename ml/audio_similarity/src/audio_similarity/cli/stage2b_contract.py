"""Validate and freeze the Stage 2B query split manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from audio_similarity.stage2b_contract import write_split_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/holistic_stage2b_fusion.yaml")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="reports/holistic_stage2b/query_split_manifest.json")
    args = parser.parse_args()
    manifest = write_split_manifest(Path(args.config), Path(args.root), Path(args.output))
    print(f"froze {len(manifest['queries'])} queries: {manifest['counts']}")


if __name__ == "__main__":
    main()
