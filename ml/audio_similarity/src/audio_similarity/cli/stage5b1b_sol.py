"""Blinded Sol evaluator and targeted-audit artifact CLI for Stage 5B.1B."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256
from audio_similarity.stage5b1b_sol import (
    CodexCliSolBackend,
    load_blind_inputs,
    run_sol_evaluation,
)
from audio_similarity.stage5b1b_sol_comparison import write_comparison_artifacts
from audio_similarity.stage5b1b_sol_config import load_sol_audit_config


def verify(path: str | Path) -> dict:
    config = load_sol_audit_config(path)
    manifest, rows = load_blind_inputs(config)
    return {
        "status": "BLINDED_SOL_EVALUATOR_READY",
        "model": config.evaluator.model,
        "reasoning_effort": config.evaluator.reasoning_effort,
        "prompt_version": config.evaluator.prompt_version,
        "track_count": len(rows),
        "candidate_count": sum(len(row["candidates"]) for row in rows),
        "manifest_sha256": manifest.sha256,
        "discovery_sha256": config.discovery_sha256,
        "resolver_features_supplied_to_model": False,
        "human_labels_supplied_to_model": False,
        "tools_allowed": config.evaluator.tools_allowed,
        "production_auto_match_enabled": config.production_auto_match_enabled,
    }


def run(path: str | Path, *, overwrite: bool = False) -> dict:
    config = load_sol_audit_config(path)
    backend = CodexCliSolBackend(config)
    result = run_sol_evaluation(config, backend, overwrite=overwrite)
    summary = {
        "status": result["status"],
        "model": backend.model,
        "codex_cli_version": backend.version,
        "completed_track_count": result["completed_track_count"],
        "completed_candidate_count": result["completed_candidate_count"],
        "error_count": len(result["errors"]),
        "artifact": str(config.artifacts["sol_evaluations"]),
        "artifact_sha256": file_sha256(config.artifacts["sol_evaluations"]),
    }
    if result["status"] == "COMPLETE":
        summary["comparison"] = write_comparison_artifacts(config)
    return summary


def compare(path: str | Path) -> dict:
    return write_comparison_artifacts(load_sol_audit_config(path))


def parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[3]
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument(
        "--config", default=str(root / "configs" / "stage5b1b_sol.json")
    )
    subcommands = command.add_subparsers(dest="command", required=True)
    verify_parser = subcommands.add_parser(
        "verify", help="verify frozen blind inputs without invoking Sol"
    )
    verify_parser.set_defaults(function=lambda args: verify(args.config))
    run_parser = subcommands.add_parser(
        "run", help="run/resume blinded Sol evaluation and emit targeted-audit artifacts"
    )
    run_parser.add_argument("--overwrite", action="store_true")
    run_parser.set_defaults(
        function=lambda args: run(args.config, overwrite=args.overwrite)
    )
    compare_parser = subcommands.add_parser(
        "compare", help="regenerate comparison/audit artifacts from frozen Sol output"
    )
    compare_parser.set_defaults(function=lambda args: compare(args.config))
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
