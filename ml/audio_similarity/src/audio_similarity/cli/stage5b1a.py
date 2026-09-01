"""Stage 5B.1A Firecrawl discovery feasibility CLI."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Mapping

from audio_similarity.stage5b1a_config import Stage5B1AConfig, load_config
from audio_similarity.stage5b1a_discovery import (
    FirecrawlDiscoveryAdapter,
    FirecrawlHTTPTransport,
)
from audio_similarity.stage5b1a_experiment import (
    atomic_json,
    load_discovery_results,
    run_discovery_experiment,
    write_discovery_results,
)
from audio_similarity.stage5b1a_models import (
    FrozenTrackManifest,
    Stage5B1AValidationError,
    load_frozen_manifest,
)
from audio_similarity.stage5b1a_review import (
    compute_metrics,
    load_review_labels,
    write_review_csv,
)


NOT_RUN_STATUS = "IMPLEMENTED_BUT_REAL_DISCOVERY_NOT_RUN"


def _inputs(config_path: str | Path) -> tuple[Stage5B1AConfig, FrozenTrackManifest]:
    config = load_config(config_path)
    manifest = load_frozen_manifest(
        config.manifest_path,
        expected_sha256=config.manifest_sha256,
    )
    return config, manifest


def prepare_review_template(config_path: str | Path, *, overwrite: bool = False) -> dict:
    config, manifest = _inputs(config_path)
    output = config.artifacts["review_template"]
    write_review_csv(output, manifest, overwrite=overwrite)
    return {
        "status": NOT_RUN_STATUS,
        "manifest_sha256": manifest.sha256,
        "track_count": len(manifest.tracks),
        "review_template": str(output),
    }


def _preflight_run_artifacts(config: Stage5B1AConfig, *, overwrite: bool) -> None:
    results = config.artifacts["discovery_results"]
    review = config.artifacts["review"]
    if results.exists() and not overwrite:
        raise FileExistsError(f"discovery artifact already exists: {results}")
    if review.exists():
        existing = load_review_labels(review)
        if any(label.label for label in existing):
            raise Stage5B1AValidationError(
                "refusing to overwrite a review artifact containing human labels"
            )
        if not overwrite:
            raise FileExistsError(f"review artifact already exists: {review}")


def firecrawl_transport(
    config: Stage5B1AConfig,
    environment: Mapping[str, str] = os.environ,
) -> FirecrawlHTTPTransport:
    """Prefer an environment API key and otherwise use Firecrawl keyless REST."""
    variable = config.provider.api_key_environment_variable
    return FirecrawlHTTPTransport(config.provider, environment.get(variable))


def build_candidate_review(config_path: str | Path, *, overwrite: bool = False) -> dict:
    config, manifest = _inputs(config_path)
    results = load_discovery_results(
        config.artifacts["discovery_results"],
        manifest,
        config,
    )
    review = config.artifacts["review"]
    if review.exists():
        existing = load_review_labels(review)
        if any(label.label for label in existing):
            raise Stage5B1AValidationError(
                "refusing to overwrite a review artifact containing human labels"
            )
    write_review_csv(review, manifest, results, overwrite=overwrite)
    return {
        "status": results["status"],
        "review": str(review),
        "track_count": len(results["tracks"]),
    }


def run_real_discovery(
    config_path: str | Path,
    *,
    environment: Mapping[str, str] = os.environ,
    overwrite: bool = False,
) -> dict:
    config, manifest = _inputs(config_path)
    _preflight_run_artifacts(config, overwrite=overwrite)
    transport = firecrawl_transport(config, environment)
    adapter = FirecrawlDiscoveryAdapter(config.provider, config.query, transport)
    results = run_discovery_experiment(manifest, config, adapter)
    write_discovery_results(
        config.artifacts["discovery_results"],
        results,
        overwrite=overwrite,
    )
    review_status = build_candidate_review(config_path, overwrite=overwrite)
    return {
        "status": results["status"],
        "results": str(config.artifacts["discovery_results"]),
        "review": review_status["review"],
        "authentication_mode": transport.authentication_mode,
        "summary": results["summary"],
    }


def calculate_metrics(config_path: str | Path) -> dict:
    config, manifest = _inputs(config_path)
    results = load_discovery_results(
        config.artifacts["discovery_results"],
        manifest,
        config,
    )
    candidate_counts = {
        row["track"]["stable_track_id"]: len(row["candidates"])
        for row in results["tracks"]
    }
    labels = load_review_labels(
        config.artifacts["review"],
        candidate_counts=candidate_counts,
    )
    metrics = compute_metrics(results, labels, config.gate)
    atomic_json(config.artifacts["metrics"], metrics)
    return metrics


def verify_inputs(config_path: str | Path) -> dict:
    config, manifest = _inputs(config_path)
    return {
        "status": "READY_FOR_REAL_DISCOVERY",
        "config_sha256": config.sha256,
        "manifest_sha256": manifest.sha256,
        "track_count": len(manifest.tracks),
        "candidate_limit": config.provider.candidate_limit,
        "query_variant_id": config.query.variant_id,
        "gate": {
            "pass_min_recall_at_5": config.gate.pass_min_recall_at_5,
            "conditional_min_recall_at_5": config.gate.conditional_min_recall_at_5,
        },
    }


def parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[3]
    default_config = str(root / "configs/stage5b1a_firecrawl.json")
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--config", default=default_config)
    subcommands = command.add_subparsers(dest="command", required=True)
    prepare = subcommands.add_parser("prepare-review", help="create the committed no-result review template")
    prepare.add_argument("--overwrite", action="store_true")
    prepare.set_defaults(function=lambda args: prepare_review_template(args.config, overwrite=args.overwrite))
    run = subcommands.add_parser("run", help="execute the sequential real Firecrawl experiment")
    run.add_argument("--overwrite", action="store_true")
    run.set_defaults(function=lambda args: run_real_discovery(args.config, overwrite=args.overwrite))
    review = subcommands.add_parser("review", help="regenerate review CSV from existing discovery results")
    review.add_argument("--overwrite", action="store_true")
    review.set_defaults(function=lambda args: build_candidate_review(args.config, overwrite=args.overwrite))
    metrics = subcommands.add_parser("metrics", help="score completed human review labels")
    metrics.set_defaults(function=lambda args: calculate_metrics(args.config))
    verify = subcommands.add_parser("verify", help="validate the frozen inputs without network access")
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
