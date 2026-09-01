"""Objective provider comparison for Firecrawl and yt-dlp discovery runs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .stage5b1a_experiment import atomic_json
from .stage5b1a_models import Stage5B1AValidationError


SCHEMA_VERSION = "stage5b1a-provider-comparison-v1"


def _coverage(results: dict, provider: str) -> dict[str, Any]:
    rows = results.get("tracks")
    if not isinstance(rows, list):
        raise Stage5B1AValidationError(f"{provider} comparison input lacks tracks")
    counts = [len(row.get("candidates", [])) for row in rows]
    failures = sum(row.get("error") is not None for row in rows)
    return {
        "tracks": len(rows),
        "tracks_with_candidates": sum(count > 0 for count in counts),
        "tracks_with_zero_candidates": sum(count == 0 for count in counts),
        "request_failures": failures,
        "total_deduplicated_candidates": sum(counts),
        "mean_candidates_per_track": sum(counts) / len(counts) if counts else None,
        "candidate_count_histogram": {
            str(count): sum(value == count for value in counts) for count in range(6)
        },
    }


def _metadata(results: dict, fields: tuple[str, ...]) -> dict[str, Any]:
    candidates = [candidate for row in results["tracks"] for candidate in row.get("candidates", [])]
    return {
        "candidate_count": len(candidates),
        "populated_candidate_fields": {
            field: sum(candidate.get(field) not in (None, "") for candidate in candidates)
            for field in fields
        },
    }


def _correctness(metrics_path: Path) -> dict[str, Any] | None:
    if not metrics_path.exists():
        return None
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    verdict = metrics.get("feasibility_verdict")
    recalls = [metrics.get(f"recall_at_{k}") for k in (1, 3, 5)]
    if verdict in {"PENDING_HUMAN_REVIEW", "NO_EVALUABLE_TRACKS"} or any(
        not isinstance(recall, dict) or recall.get("value") is None for recall in recalls
    ):
        return None
    return {
        "recall_at_1": recalls[0],
        "recall_at_3": recalls[1],
        "recall_at_5": recalls[2],
        "feasibility_verdict": verdict,
    }


def build_provider_comparison(
    firecrawl_results_path: str | Path,
    ytdlp_results: dict,
    *,
    firecrawl_metrics_path: str | Path,
    ytdlp_metrics_path: str | Path,
) -> dict:
    firecrawl = json.loads(Path(firecrawl_results_path).read_text(encoding="utf-8"))
    firecrawl_manifest = firecrawl.get("manifest", {}).get("sha256")
    ytdlp_manifest = ytdlp_results.get("manifest", {}).get("sha256")
    if not isinstance(firecrawl_manifest, str) or firecrawl_manifest != ytdlp_manifest:
        raise Stage5B1AValidationError("provider comparison requires the same frozen manifest")
    firecrawl_correctness = _correctness(Path(firecrawl_metrics_path))
    ytdlp_correctness = _correctness(Path(ytdlp_metrics_path))
    correctness_ready = firecrawl_correctness is not None and ytdlp_correctness is not None
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_sha256": ytdlp_manifest,
        "comparison_scope": (
            "coverage_and_metadata_only" if not correctness_ready else "coverage_metadata_and_human_recall"
        ),
        "providers": {
            "firecrawl": {
                "role": "preserved_historical_provider_experiment",
                "coverage": _coverage(firecrawl, "firecrawl"),
                "metadata_richness": _metadata(firecrawl, ("description", "uploader", "channel", "duration_seconds")),
                "correctness": firecrawl_correctness,
            },
            "yt_dlp": {
                "role": "candidate_active_discovery_provider",
                "coverage": _coverage(ytdlp_results, "yt_dlp"),
                "metadata_richness": _metadata(
                    ytdlp_results,
                    ("description", "uploader", "channel", "duration_seconds", "availability", "live_status"),
                ),
                "correctness": ytdlp_correctness,
            },
        },
        "correctness_comparison_status": (
            "AVAILABLE" if correctness_ready else "PENDING_HUMAN_REVIEW_FOR_BOTH_PROVIDERS"
        ),
    }


def write_provider_comparison(path: str | Path, comparison: dict) -> None:
    atomic_json(path, comparison)
