"""Stage 5B.1A2 metadata-only yt-dlp discovery feasibility CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b1a2_comparison import (
    build_provider_comparison,
    write_provider_comparison,
)
from audio_similarity.stage5b1a2_config import Stage5B1A2Config, load_ytdlp_config
from audio_similarity.stage5b1a2_experiment import (
    load_ytdlp_results,
    run_ytdlp_experiment,
    write_ytdlp_results,
)
from audio_similarity.stage5b1a2_review import (
    METRICS_SCHEMA_VERSION,
    load_ytdlp_review_labels,
    write_review_csv,
)
from audio_similarity.stage5b1a2_ytdlp import YtDlpDiscoveryAdapter, YtDlpPythonBackend
from audio_similarity.stage5b1a_experiment import atomic_json
from audio_similarity.stage5b1a_models import (
    FrozenTrackManifest,
    Stage5B1AValidationError,
    file_sha256,
    load_frozen_manifest,
)
from audio_similarity.stage5b1a_review import compute_metrics


NOT_RUN = "IMPLEMENTED_BUT_REAL_DISCOVERY_NOT_RUN"


def _inputs(config_path: str | Path) -> tuple[Stage5B1A2Config, FrozenTrackManifest]:
    config = load_ytdlp_config(config_path)
    manifest = load_frozen_manifest(config.manifest_path, expected_sha256=config.manifest_sha256)
    return config, manifest


def _preflight(config: Stage5B1A2Config, *, overwrite: bool) -> None:
    results = config.artifacts["discovery_results"]
    review = config.artifacts["review"]
    if results.exists() and not overwrite:
        raise FileExistsError(f"yt-dlp discovery artifact already exists: {results}")
    if review.exists():
        labels = load_ytdlp_review_labels(review)
        if any(label.label for label in labels):
            raise Stage5B1AValidationError("refusing to overwrite yt-dlp human labels")
        if not overwrite:
            raise FileExistsError(f"yt-dlp review artifact already exists: {review}")


def prepare_review_template(config_path: str | Path, *, overwrite: bool = False) -> dict:
    config, manifest = _inputs(config_path)
    write_review_csv(config.artifacts["review_template"], manifest, overwrite=overwrite)
    return {"status": NOT_RUN, "track_count": len(manifest.tracks), "manifest_sha256": manifest.sha256}


def build_review(config_path: str | Path, *, overwrite: bool = False) -> dict:
    config, manifest = _inputs(config_path)
    results = load_ytdlp_results(config.artifacts["discovery_results"], manifest, config)
    review = config.artifacts["review"]
    if review.exists() and any(label.label for label in load_ytdlp_review_labels(review)):
        raise Stage5B1AValidationError("refusing to overwrite yt-dlp human labels")
    write_review_csv(review, manifest, results, overwrite=overwrite)
    return {"status": results["status"], "review": str(review), "track_count": len(results["tracks"])}


def compare_providers(config_path: str | Path) -> dict:
    config, manifest = _inputs(config_path)
    results = load_ytdlp_results(config.artifacts["discovery_results"], manifest, config)
    comparison = build_provider_comparison(
        config.comparison_sources["firecrawl_results"],
        results,
        firecrawl_metrics_path=config.comparison_sources["firecrawl_metrics"],
        ytdlp_metrics_path=config.artifacts["metrics"],
    )
    write_provider_comparison(config.artifacts["comparison"], comparison)
    return comparison


def run_real_discovery(config_path: str | Path, *, overwrite: bool = False) -> dict:
    config, manifest = _inputs(config_path)
    _preflight(config, overwrite=overwrite)
    backend = YtDlpPythonBackend(config.provider)
    adapter = YtDlpDiscoveryAdapter(config.provider, config.query, backend)
    results = run_ytdlp_experiment(manifest, config, adapter)
    write_ytdlp_results(config.artifacts["discovery_results"], results, overwrite=overwrite)
    review_status = build_review(config_path, overwrite=overwrite)
    comparison = compare_providers(config_path)
    run_status = {
        "schema_version": "stage5b1a2-run-status-v1",
        "experiment_id": results["experiment_id"],
        "status": results["status"],
        "manifest_sha256": manifest.sha256,
        "config_sha256": config.sha256,
        "yt_dlp_version": backend.version,
        "summary": results["summary"],
        "elapsed_wall_seconds": results["elapsed_wall_seconds"],
        "media_activity": results["media_activity"],
        "discovery_results": str(config.artifacts["discovery_results"].relative_to(config.project_root)),
        "discovery_results_sha256": file_sha256(config.artifacts["discovery_results"]),
        "review": str(config.artifacts["review"].relative_to(config.project_root)),
        "review_sha256": file_sha256(config.artifacts["review"]),
        "review_labels_completed": 0,
        "comparison": str(config.artifacts["comparison"].relative_to(config.project_root)),
        "comparison_sha256": file_sha256(config.artifacts["comparison"]),
        "feasibility_verdict": "PENDING_HUMAN_REVIEW",
    }
    atomic_json(config.artifacts["run_status"], run_status)
    return {
        "status": results["status"],
        "results": str(config.artifacts["discovery_results"]),
        "review": review_status["review"],
        "comparison_scope": comparison["comparison_scope"],
        "yt_dlp_version": backend.version,
        "summary": results["summary"],
        "elapsed_wall_seconds": results["elapsed_wall_seconds"],
    }


def calculate_metrics(config_path: str | Path) -> dict:
    config, manifest = _inputs(config_path)
    results = load_ytdlp_results(config.artifacts["discovery_results"], manifest, config)
    counts = {row["track"]["stable_track_id"]: len(row["candidates"]) for row in results["tracks"]}
    labels = load_ytdlp_review_labels(config.artifacts["review"], candidate_counts=counts)
    metrics = compute_metrics(
        results,
        labels,
        config.gate,
        metrics_schema_version=METRICS_SCHEMA_VERSION,
        request_failure_key="ytdlp_search_failure_count",
    )
    atomic_json(config.artifacts["metrics"], metrics)
    compare_providers(config_path)
    return metrics


def verify_inputs(config_path: str | Path) -> dict:
    config, manifest = _inputs(config_path)
    return {
        "status": "READY_FOR_REAL_DISCOVERY",
        "config_sha256": config.sha256,
        "manifest_sha256": manifest.sha256,
        "track_count": len(manifest.tracks),
        "query_variant_id": config.query.variant_id,
        "search_prefix": config.provider.search_prefix,
        "candidate_limit": config.provider.candidate_limit,
        "metadata_only_options": config.provider.metadata_only_options(),
        "pacing_seconds": config.provider.sleep_between_tracks_seconds,
        "gate": {
            "pass_min_recall_at_5": config.gate.pass_min_recall_at_5,
            "conditional_min_recall_at_5": config.gate.conditional_min_recall_at_5,
        },
    }


def parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[3]
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--config", default=str(root / "configs/stage5b1a2_ytdlp.json"))
    subcommands = command.add_subparsers(dest="command", required=True)
    for name, help_text, function in (
        ("prepare-review", "create an empty yt-dlp review template", prepare_review_template),
        ("run", "execute the real sequential metadata-only experiment", run_real_discovery),
        ("review", "regenerate review CSV from existing results", build_review),
    ):
        subcommand = subcommands.add_parser(name, help=help_text)
        subcommand.add_argument("--overwrite", action="store_true")
        subcommand.set_defaults(function=lambda args, fn=function: fn(args.config, overwrite=args.overwrite))
    metrics = subcommands.add_parser("metrics", help="score completed human labels")
    metrics.set_defaults(function=lambda args: calculate_metrics(args.config))
    compare = subcommands.add_parser("compare", help="compare provider coverage and available recall")
    compare.set_defaults(function=lambda args: compare_providers(args.config))
    verify = subcommands.add_parser("verify", help="validate frozen inputs without network access")
    verify.set_defaults(function=lambda args: verify_inputs(args.config))
    return command


def main() -> None:
    args = parser().parse_args()
    try:
        value = args.function(args)
    except (Stage5B1AValidationError, FileExistsError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
