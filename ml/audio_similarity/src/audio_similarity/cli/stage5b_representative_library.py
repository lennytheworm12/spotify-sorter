"""Freeze the gated Stage 5B stack or a held-out owner-library manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b_representative_artifacts import (
    freeze_benchmark_manifest,
    freeze_resolver_stack,
    load_part_a_config,
)


def _config() -> Path:
    return Path(__file__).parents[3] / "configs/stage5b1j_representation_fallback.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze-stack", "freeze-manifest"))
    parser.add_argument("--config", type=Path, default=_config())
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    config = load_part_a_config(args.config)
    if args.action == "freeze-stack":
        result = freeze_resolver_stack(config)
        output = {"status": result["status"], "stack_id": result["stack_id"]}
    else:
        if args.snapshot is None:
            parser.error("freeze-manifest requires --snapshot")
        result = freeze_benchmark_manifest(config, args.snapshot, args.output_dir)
        output = {
            "status": "STAGE5B_REPRESENTATIVE_LIBRARY_MANIFEST_FROZEN",
            "track_count": result["benchmark_manifest"]["sampled_track_count"],
            "manifest_sha256": result["benchmark_manifest_sha256"],
        }
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
