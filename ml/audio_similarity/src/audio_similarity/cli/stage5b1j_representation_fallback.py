"""Freeze, discover, evaluate, or finalize Stage 5B.1J Part A."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b1j_artifacts import (
    discover,
    evaluate_and_write,
    freeze_queries,
    load_config,
)


def _default_config() -> Path:
    return Path(__file__).parents[3] / "configs/stage5b1j_representation_fallback.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("freeze-queries", "discover", "evaluate"),
    )
    parser.add_argument("--config", type=Path, default=_default_config())
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.action == "freeze-queries":
        result = freeze_queries(config)
        output = {
            "status": "STAGE5B1J_FALLBACK_QUERIES_FROZEN",
            "track_count": result["track_count"],
            "artifact": str(config.artifacts["queries"]),
        }
    elif args.action == "discover":
        result = discover(config)
        output = {
            "status": result["status"],
            "summary": result["summary"],
            "artifact": str(config.artifacts["discovery"]),
        }
    else:
        result = evaluate_and_write(config)
        output = {
            "status": result["status"],
            "summary": result["summary"],
            "part_b_authorized": result["part_b_authorized"],
            "artifact": str(config.artifacts["manifest"]),
        }
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
