"""Offline Stage 5B.1B resolver calibration and blinded Sol review CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256
from audio_similarity.stage5b1b_calibration_sol import (
    CalibrationCodexBackend,
    load_calibration_sol_config,
    run_calibration_sol,
)
from audio_similarity.stage5b1b_calibration import run_calibration_analysis


def verify_sol(path: str | Path) -> dict:
    config = load_calibration_sol_config(path)
    payload = json.loads(config.payload_path.read_text(encoding="utf-8"))
    tracks = payload["tracks"]
    serialized = json.dumps(payload)
    forbidden = [
        name
        for name in (
            "candidate_review_label",
            "title_similarity",
            "version_relationships",
            "recording_eligible",
            "source_type",
            "case_tags",
            "case_rationale",
            "original_search_rank",
            "youtube_video_id",
            '"rank"',
            '"query"',
        )
        if name in serialized
    ]
    if forbidden:
        raise Stage5B1AValidationError(f"blinded payload leaks forbidden fields: {forbidden}")
    return {
        "status": "CALIBRATION_SOL_BLIND_INPUT_FROZEN",
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "track_count": len(tracks),
        "candidate_count": sum(len(row["candidates"]) for row in tracks),
        "payload_sha256": config.payload_sha256,
        "private_mapping_sha256": config.mapping_sha256,
        "prompt_sha256": config.prompt_sha256,
        "output_schema_sha256": config.output_schema_sha256,
        "candidate_order_is_search_rank": payload["candidate_order_is_search_rank"],
        "forbidden_field_leaks": forbidden,
        "production_auto_match_activated": False,
    }


def run_sol(path: str | Path, *, overwrite: bool, max_batches: int | None) -> dict:
    config = load_calibration_sol_config(path)
    backend = CalibrationCodexBackend(config)
    state = run_calibration_sol(
        config, backend, overwrite=overwrite, max_batches=max_batches
    )
    return {
        "status": state["status"],
        "model": backend.model,
        "codex_cli_version": backend.version,
        "completed_track_count": state["completed_track_count"],
        "completed_candidate_count": state["completed_candidate_count"],
        "error_count": len(state["errors"]),
        "artifact": str(config.evaluations_path),
        "artifact_sha256": file_sha256(config.evaluations_path),
    }


def analyze(path: str | Path, feature_v2: str | Path, output_dir: str | Path) -> dict:
    return run_calibration_analysis(
        load_calibration_sol_config(path),
        feature_v2_path=feature_v2,
        output_dir=output_dir,
    )


def parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[3]
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument(
        "--config", default=str(root / "configs/stage5b1b_calibration_sol.json")
    )
    subcommands = command.add_subparsers(dest="command", required=True)
    verify = subcommands.add_parser("verify-sol")
    verify.set_defaults(function=lambda args: verify_sol(args.config))
    run = subcommands.add_parser("run-sol")
    run.add_argument("--overwrite", action="store_true")
    run.add_argument("--max-batches", type=int)
    run.set_defaults(
        function=lambda args: run_sol(
            args.config, overwrite=args.overwrite, max_batches=args.max_batches
        )
    )
    analyze_parser = subcommands.add_parser("analyze")
    analyze_parser.add_argument(
        "--feature-v2",
        default=str(root / "reports/stage5b1b_calibration/candidate_features_v2.json"),
    )
    analyze_parser.add_argument(
        "--output-dir",
        default=str(root / "reports/stage5b1b_calibration"),
    )
    analyze_parser.set_defaults(
        function=lambda args: analyze(args.config, args.feature_v2, args.output_dir)
    )
    return command


def main() -> None:
    args = parser().parse_args()
    try:
        result = args.function(args)
    except (FileNotFoundError, Stage5B1AValidationError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
