"""Stage 5B.1B Part C fresh-challenge validation CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b1a2_ytdlp import YtDlpDiscoveryAdapter, YtDlpPythonBackend
from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256
from audio_similarity.stage5b1b_artifacts import atomic_json
from audio_similarity.stage5b1b_challenge import (
    load_challenge_config,
    load_challenge_manifest,
    load_frozen_policies,
    materialize_and_resolve,
    run_discovery,
    verify_non_overlap,
)
from audio_similarity.stage5b1b_challenge_audit import evaluate_review, write_audit_artifacts
from audio_similarity.stage5b1b_challenge_sol import (
    codex_backend,
    load_sol_runtime,
    prepare_sol_contract,
    run_challenge_sol,
)


def _inputs(path: str | Path):
    config = load_challenge_config(path)
    manifest = load_challenge_manifest(config.manifest_path, expected_sha256=config.manifest_sha256)
    return config, manifest


def verify(path: str | Path) -> dict:
    config, manifest = _inputs(path)
    boundaries, policies = load_frozen_policies(config)
    return {
        "status": "FRESH_CHALLENGE_READY_FOR_DISCOVERY",
        "starting_commit": config.starting_commit,
        "config_sha256": config.sha256,
        "manifest_sha256": manifest.sha256,
        "policy_bundle_sha256": config.policy_bundle_sha256,
        "policy_ids": sorted(policies),
        "duration_boundaries": boundaries.__dict__,
        "non_overlap": verify_non_overlap(config, manifest),
        "search_mode": config.discovery.provider.search_prefix,
        "metadata_only_options": config.discovery.provider.metadata_only_options(),
    }


def discover(path: str | Path) -> dict:
    config, manifest = _inputs(path)
    if config.artifacts["discovery"].exists():
        raise FileExistsError("fresh challenge discovery already exists")
    backend = YtDlpPythonBackend(config.discovery.provider)
    adapter = YtDlpDiscoveryAdapter(config.discovery.provider, config.discovery.query, backend)
    result = run_discovery(config, manifest, adapter)
    atomic_json(config.artifacts["discovery"], result)
    return {
        "status": result["status"], "yt_dlp_version": backend.version,
        "elapsed_wall_seconds": result["elapsed_wall_seconds"], **result["summary"],
        "artifact": str(config.artifacts["discovery"]),
        "sha256": file_sha256(config.artifacts["discovery"]),
    }


def prepare(path: str | Path) -> dict:
    config, manifest = _inputs(path)
    decisions = materialize_and_resolve(config, manifest)
    contract = prepare_sol_contract(config, manifest)
    return {
        "status": "FRESH_CHALLENGE_SOL_CONTRACT_READY",
        "features_sha256": file_sha256(config.artifacts["features"]),
        "policy_decisions_sha256": file_sha256(config.artifacts["policy_decisions"]),
        "sol_contract_sha256": file_sha256(config.artifacts["sol_contract"]),
        "candidate_count": contract["payload"]["candidate_count"],
        **decisions["comparison"],
    }


def run_sol(path: str | Path, *, max_batches: int | None = None, overwrite: bool = False) -> dict:
    config, _ = _inputs(path)
    runtime = load_sol_runtime(config)
    backend = codex_backend(runtime)
    result = run_challenge_sol(runtime, backend, max_batches=max_batches, overwrite=overwrite)
    return {
        "status": result["status"], "model": backend.model,
        "codex_cli_version": backend.version,
        "completed_track_count": result["completed_track_count"],
        "completed_candidate_count": result["completed_candidate_count"],
        "error_count": len(result["errors"]),
        "artifact_sha256": file_sha256(runtime.evaluations_path),
    }


def audit(path: str | Path) -> dict:
    config, manifest = _inputs(path)
    runtime = load_sol_runtime(config)
    result = write_audit_artifacts(config, manifest, runtime)
    status = {
        "schema_version": "stage5b1b-fresh-challenge-run-status-v1",
        **result,
        "manifest_sha256": manifest.sha256,
        "policy_bundle_sha256": config.policy_bundle_sha256,
        "discovery_sha256": file_sha256(config.artifacts["discovery"]),
        "features_sha256": file_sha256(config.artifacts["features"]),
        "policy_decisions_sha256": file_sha256(config.artifacts["policy_decisions"]),
        "sol_contract_sha256": file_sha256(config.artifacts["sol_contract"]),
        "sol_evaluations_sha256": file_sha256(config.artifacts["sol_evaluations"]),
        "audit_queue_sha256": file_sha256(config.artifacts["audit_queue"]),
        "human_review_sha256": file_sha256(config.artifacts["human_review"]),
        "review_path": str(config.artifacts["human_review"].relative_to(config.root)),
        "media_activity": {"audio_downloads": 0, "video_downloads": 0, "stage5a_calls": 0, "clap_calls": 0, "muq_calls": 0},
        "production_auto_match_activated": False,
    }
    atomic_json(config.artifacts["run_status"], status)
    return status


def review_status(path: str | Path) -> dict:
    config, _ = _inputs(path)
    return evaluate_review(config)


def parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[3]
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--config", default=str(root / "configs/stage5b1b_fresh_challenge.json"))
    sub = command.add_subparsers(dest="command", required=True)
    sub.add_parser("verify").set_defaults(function=lambda args: verify(args.config))
    sub.add_parser("discover").set_defaults(function=lambda args: discover(args.config))
    sub.add_parser("prepare").set_defaults(function=lambda args: prepare(args.config))
    sol = sub.add_parser("run-sol")
    sol.add_argument("--max-batches", type=int)
    sol.add_argument("--overwrite", action="store_true")
    sol.set_defaults(function=lambda args: run_sol(args.config, max_batches=args.max_batches, overwrite=args.overwrite))
    sub.add_parser("audit").set_defaults(function=lambda args: audit(args.config))
    sub.add_parser("review-status").set_defaults(function=lambda args: review_status(args.config))
    return command


def main() -> None:
    args = parser().parse_args()
    try:
        result = args.function(args)
    except (FileNotFoundError, FileExistsError, Stage5B1AValidationError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
