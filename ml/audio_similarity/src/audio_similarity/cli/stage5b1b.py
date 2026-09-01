"""Stage 5B.1B Part A feature and held-out discovery CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b1a2_experiment import load_ytdlp_results
from audio_similarity.stage5b1a2_ytdlp import YtDlpDiscoveryAdapter, YtDlpPythonBackend
from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256, load_frozen_manifest
from audio_similarity.stage5b1b_artifacts import (
    atomic_json,
    dev_diagnostics,
    load_dev_review,
    load_heldout_review,
    materialize_features,
    write_heldout_review,
)
from audio_similarity.stage5b1b_config import Stage5B1BConfig, load_stage5b1b_config
from audio_similarity.stage5b1b_experiment import (
    READY_FOR_REVIEW,
    load_heldout_results,
    run_heldout_discovery,
    write_heldout_results,
)
from audio_similarity.stage5b1b_manifest import HeldoutManifest, load_heldout_manifest


def _inputs(path: str | Path) -> tuple[Stage5B1BConfig, HeldoutManifest]:
    config = load_stage5b1b_config(path)
    heldout = load_heldout_manifest(
        config.heldout_manifest_path, expected_sha256=config.heldout_manifest_sha256
    )
    return config, heldout


def generate_dev(path: str | Path) -> dict:
    config, _ = _inputs(path)
    manifest = load_frozen_manifest(
        config.dev_manifest_path, expected_sha256=config.dev_manifest_sha256
    )
    results = load_ytdlp_results(config.dev_discovery_path, manifest, config.discovery)
    dataset = materialize_features(
        results, manifest_sha256=manifest.sha256, dataset_role="DEV_ONLY_NOT_HELD_OUT"
    )
    if dataset["track_count"] != 25 or dataset["candidate_pair_count"] != 125:
        raise Stage5B1AValidationError("DEV feature materialization must contain 25 tracks / 125 pairs")
    diagnostics = dev_diagnostics(dataset, load_dev_review(config.dev_review_path))
    atomic_json(config.artifacts["dev_features"], dataset)
    atomic_json(config.artifacts["dev_diagnostics"], diagnostics)
    return {
        "status": "DEV_FEATURE_ANALYSIS_COMPLETE",
        "track_count": dataset["track_count"],
        "candidate_pair_count": dataset["candidate_pair_count"],
        "features": str(config.artifacts["dev_features"]),
        "diagnostics": str(config.artifacts["dev_diagnostics"]),
    }


def generate_heldout_artifacts(path: str | Path, *, overwrite: bool = False) -> dict:
    config, manifest = _inputs(path)
    results = load_heldout_results(config.artifacts["heldout_discovery"], manifest, config)
    dataset = materialize_features(
        results, manifest_sha256=manifest.sha256, dataset_role="HELD_OUT_UNLABELED"
    )
    review_path = config.artifacts["heldout_review"]
    if review_path.exists():
        rows = load_heldout_review(review_path)
        if any(row["candidate_review_label"].strip() for row in rows):
            raise Stage5B1AValidationError("refusing to overwrite held-out human labels")
    atomic_json(config.artifacts["heldout_features"], dataset)
    write_heldout_review(review_path, dataset, overwrite=overwrite)
    version = results.get("configuration", {}).get("provider", {}).get("version")
    status = {
        "schema_version": "stage5b1b-run-status-v1",
        "status": READY_FOR_REVIEW,
        "stage5b1a2_evidence_checkpoint": config.checkpoint_commit,
        "config_sha256": config.sha256,
        "heldout_manifest_sha256": manifest.sha256,
        "yt_dlp_version": version,
        "summary": results["summary"],
        "elapsed_wall_seconds": results["elapsed_wall_seconds"],
        "media_activity": results["media_activity"],
        "artifacts": {
            key: {
                "path": str(config.artifacts[key].relative_to(config.project_root)),
                "sha256": file_sha256(config.artifacts[key]),
            }
            for key in ("heldout_discovery", "heldout_features", "heldout_review")
        },
        "review_labels_completed": 0,
        "final_auto_match_threshold": None,
        "heldout_labels_required_before_calibration": True,
    }
    atomic_json(config.artifacts["run_status"], status)
    return {
        "status": READY_FOR_REVIEW,
        "track_count": dataset["track_count"],
        "candidate_pair_count": dataset["candidate_pair_count"],
        "review": str(review_path),
    }


def run_real_heldout(path: str | Path, *, overwrite: bool = False) -> dict:
    config, manifest = _inputs(path)
    if config.artifacts["heldout_discovery"].exists() and not overwrite:
        raise FileExistsError("held-out discovery artifact already exists")
    backend = YtDlpPythonBackend(config.discovery.provider)
    adapter = YtDlpDiscoveryAdapter(config.discovery.provider, config.discovery.query, backend)
    results = run_heldout_discovery(manifest, config, adapter)
    write_heldout_results(config.artifacts["heldout_discovery"], results, overwrite=overwrite)
    artifacts = generate_heldout_artifacts(path, overwrite=overwrite)
    return {**artifacts, "yt_dlp_version": backend.version, "summary": results["summary"], "elapsed_wall_seconds": results["elapsed_wall_seconds"]}


def verify(path: str | Path) -> dict:
    config, manifest = _inputs(path)
    original = load_frozen_manifest(
        config.dev_manifest_path, expected_sha256=config.dev_manifest_sha256
    )
    return {
        "status": "READY_FOR_HELDOUT_DISCOVERY",
        "stage5b1a2_evidence_checkpoint": config.checkpoint_commit,
        "dev_manifest_sha256": original.sha256,
        "heldout_manifest_sha256": manifest.sha256,
        "heldout_track_count": len(manifest.tracks),
        "search_prefix": config.discovery.provider.search_prefix,
        "query_template": config.discovery.query.template,
        "metadata_only_options": config.discovery.provider.metadata_only_options(),
        "final_auto_match_threshold": None,
    }


def parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[3]
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--config", default=str(root / "configs" / "stage5b1b.json"))
    subcommands = command.add_subparsers(dest="command", required=True)
    dev = subcommands.add_parser("dev", help="materialize 25-track DEV features and diagnostics")
    dev.set_defaults(function=lambda args: generate_dev(args.config))
    verify_parser = subcommands.add_parser("verify", help="verify frozen inputs without network")
    verify_parser.set_defaults(function=lambda args: verify(args.config))
    run = subcommands.add_parser("run-heldout", help="run sequential metadata-only held-out discovery")
    run.add_argument("--overwrite", action="store_true")
    run.set_defaults(function=lambda args: run_real_heldout(args.config, overwrite=args.overwrite))
    artifacts = subcommands.add_parser("artifacts", help="regenerate unlabeled artifacts from discovery")
    artifacts.add_argument("--overwrite", action="store_true")
    artifacts.set_defaults(function=lambda args: generate_heldout_artifacts(args.config, overwrite=args.overwrite))
    return command


def main() -> None:
    args = parser().parse_args()
    try:
        value = args.function(args)
    except (FileNotFoundError, FileExistsError, Stage5B1AValidationError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
