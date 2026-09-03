"""Run or evaluate the frozen Stage 5B representative library benchmark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b_representative_benchmark import (
    load_benchmark_config,
    run_discovery,
    verify_benchmark_inputs,
    write_evaluation_artifacts,
)


def _default_config() -> Path:
    return Path(__file__).parents[3] / "configs/stage5b_representative_library_v1.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "discover", "evaluate"))
    parser.add_argument("--config", type=Path, default=_default_config())
    args = parser.parse_args(argv)
    config = load_benchmark_config(args.config)
    if args.action == "verify":
        result = verify_benchmark_inputs(config)
        output = {
            "status": "STAGE5B_REPRESENTATIVE_LIBRARY_INPUTS_VERIFIED",
            "track_count": result["manifest"]["sampled_track_count"],
            "resolver_stack_id": result["stack"]["stack_id"],
        }
    elif args.action == "discover":
        result = run_discovery(config)
        output = {"status": result["status"], **result["summary"]}
    else:
        result = write_evaluation_artifacts(config)
        output = {
            "status": result["status"],
            "summary": result["summary"],
            "human_review": result["human_review"],
        }
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
