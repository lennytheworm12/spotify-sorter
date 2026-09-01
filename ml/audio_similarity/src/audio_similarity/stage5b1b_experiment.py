"""Sequential metadata-only held-out discovery for Stage 5B.1B."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from .stage5b1a2_ytdlp import YtDlpDiscoveryAdapter, YtDlpSearchError
from .stage5b1a_discovery import build_search_query
from .stage5b1a_experiment import utc_now
from .stage5b1a_models import Stage5B1AValidationError
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_config import EXPERIMENT_ID, Stage5B1BConfig
from .stage5b1b_manifest import HeldoutManifest


RESULT_SCHEMA_VERSION = "stage5b1b-heldout-ytdlp-discovery-v1"
READY_FOR_REVIEW = "STAGE5B1B_HELDOUT_READY_FOR_HUMAN_REVIEW"


def run_heldout_discovery(
    manifest: HeldoutManifest,
    config: Stage5B1BConfig,
    adapter: YtDlpDiscoveryAdapter,
    *,
    clock: Callable[[], str] = utc_now,
    timer: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    started_at, started = clock(), timer()
    rows = []
    provider = config.discovery.provider
    for index, item in enumerate(manifest.tracks):
        requested_at = clock()
        try:
            row = adapter.discover(item.track, limit=provider.candidate_limit).to_dict()
        except YtDlpSearchError as exc:
            query = build_search_query(item.track, config.discovery.query)
            row = {
                "track": item.track.to_dict(),
                "query": query,
                "request": {
                    "search_expression": provider.search_expression(query),
                    "options": provider.metadata_only_options(),
                    "download": False,
                },
                "provider": {"name": "yt_dlp", "version": adapter.backend.version, "attempts": exc.attempts},
                "normalized_results": [],
                "candidates": [],
                "candidate_video_ids": [],
                "warnings": list(exc.warnings),
                "error": exc.to_dict(),
            }
        row.update(
            {
                "case_tags": list(item.case_tags),
                "case_rationale": item.case_rationale,
                "requested_at_utc": requested_at,
                "completed_at_utc": clock(),
            }
        )
        rows.append(row)
        if index + 1 < len(manifest.tracks):
            sleep(provider.sleep_between_tracks_seconds)
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "status": READY_FOR_REVIEW,
        "manifest": {"path": str(manifest.path.relative_to(config.project_root)), "sha256": manifest.sha256, "track_count": len(manifest.tracks)},
        "configuration": {
            "path": str(config.path.relative_to(config.project_root)),
            "sha256": config.sha256,
            "query_variant_id": config.discovery.query.variant_id,
            "query_template": config.discovery.query.template,
            "provider": {
                "name": "yt_dlp",
                "version": adapter.backend.version,
                "search_prefix": provider.search_prefix,
                "candidate_limit": provider.candidate_limit,
                "metadata_only_options": provider.metadata_only_options(),
                "sequential_requests": True,
                "sleep_between_tracks_seconds": provider.sleep_between_tracks_seconds,
                "max_attempts": provider.max_attempts,
                "retry_backoff_seconds": provider.retry_backoff_seconds,
            },
        },
        "started_at_utc": started_at,
        "completed_at_utc": clock(),
        "elapsed_wall_seconds": max(0.0, timer() - started),
        "media_activity": {"audio_downloads": 0, "video_downloads": 0, "clap_calls": 0, "muq_calls": 0, "stage5a_materializations": 0},
        "summary": {
            "tracks": len(rows),
            "ytdlp_search_failures": sum(row["error"] is not None for row in rows),
            "tracks_with_zero_youtube_candidates": sum(not row["candidates"] for row in rows),
            "deduplicated_candidate_video_ids": sum(len(row["candidates"]) for row in rows),
            "tracks_with_warnings": sum(bool(row["warnings"]) for row in rows),
            "warning_count": sum(len(row["warnings"]) for row in rows),
        },
        "tracks": rows,
    }


def write_heldout_results(path: str | Path, value: dict, *, overwrite: bool = False) -> None:
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"held-out discovery artifact already exists: {output}")
    atomic_json(output, value)


def load_heldout_results(path: str | Path, manifest: HeldoutManifest, config: Stage5B1BConfig) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema_version") != RESULT_SCHEMA_VERSION or value.get("experiment_id") != EXPERIMENT_ID:
        raise Stage5B1AValidationError("unexpected held-out discovery identity")
    if value.get("manifest", {}).get("sha256") != manifest.sha256:
        raise Stage5B1AValidationError("held-out discovery uses a different manifest")
    rows = value.get("tracks")
    if not isinstance(rows, list) or tuple(row.get("track", {}).get("stable_track_id") for row in rows) != manifest.stable_track_ids:
        raise Stage5B1AValidationError("held-out discovery track order does not match manifest")
    for row in rows:
        candidates = row.get("candidates")
        if not isinstance(candidates, list) or len(candidates) > 5:
            raise Stage5B1AValidationError("invalid held-out candidates")
        ids = [candidate.get("youtube_video_id") for candidate in candidates]
        ranks = [candidate.get("rank") for candidate in candidates]
        if len(ids) != len(set(ids)) or ranks != list(range(1, len(candidates) + 1)):
            raise Stage5B1AValidationError("held-out candidates are duplicated or misordered")
    if any(value != 0 for value in value.get("media_activity", {}).values()):
        raise Stage5B1AValidationError("held-out discovery performed forbidden media or model work")
    return value
