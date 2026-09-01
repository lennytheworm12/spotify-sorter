"""Sequential orchestration and validation for Stage 5B.1A2."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from .stage5b1a2_config import EXPERIMENT_ID, Stage5B1A2Config
from .stage5b1a2_ytdlp import YtDlpDiscoveryAdapter, YtDlpSearchError
from .stage5b1a_discovery import build_search_query
from .stage5b1a_experiment import atomic_json, utc_now
from .stage5b1a_models import FrozenTrackManifest, Stage5B1AValidationError


RESULT_SCHEMA_VERSION = "stage5b1a2-ytdlp-discovery-results-v1"
AWAITING_REVIEW = "DISCOVERY_COMPLETE_AWAITING_HUMAN_REVIEW"


def run_ytdlp_experiment(
    manifest: FrozenTrackManifest,
    config: Stage5B1A2Config,
    adapter: YtDlpDiscoveryAdapter,
    *,
    clock: Callable[[], str] = utc_now,
    timer: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Run one bounded search per track, sequentially, with inter-track pacing."""
    started_at = clock()
    started = timer()
    rows = []
    for index, item in enumerate(manifest.tracks):
        requested_at = clock()
        try:
            row = adapter.discover(item.track, limit=config.provider.candidate_limit).to_dict()
        except YtDlpSearchError as exc:
            query = build_search_query(item.track, config.query)
            row = {
                "track": item.track.to_dict(),
                "query": query,
                "request": {
                    "search_expression": config.provider.search_expression(query),
                    "options": config.provider.metadata_only_options(),
                    "download": False,
                },
                "provider": {
                    "name": "yt_dlp",
                    "version": adapter.backend.version,
                    "attempts": exc.attempts,
                },
                "normalized_results": [],
                "candidates": [],
                "candidate_video_ids": [],
                "warnings": list(exc.warnings),
                "error": exc.to_dict(),
            }
        row["case_tags"] = list(item.case_tags)
        row["case_rationale"] = item.case_rationale
        row["requested_at_utc"] = requested_at
        row["completed_at_utc"] = clock()
        rows.append(row)
        if index + 1 < len(manifest.tracks):
            sleep(config.provider.sleep_between_tracks_seconds)
    elapsed = max(0.0, timer() - started)
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "status": AWAITING_REVIEW,
        "manifest": {
            "path": str(config.manifest_path.relative_to(config.project_root)),
            "sha256": manifest.sha256,
            "track_count": len(manifest.tracks),
        },
        "configuration": {
            "path": str(config.path.relative_to(config.project_root)),
            "sha256": config.sha256,
            "query_variant_id": config.query.variant_id,
            "query_template": config.query.template,
            "provider": {
                "name": "yt_dlp",
                "version": adapter.backend.version,
                "search_prefix": config.provider.search_prefix,
                "candidate_limit": config.provider.candidate_limit,
                "metadata_only_options": config.provider.metadata_only_options(),
                "sequential_requests": True,
                "sleep_between_tracks_seconds": config.provider.sleep_between_tracks_seconds,
                "max_attempts": config.provider.max_attempts,
                "retry_backoff_seconds": config.provider.retry_backoff_seconds,
            },
        },
        "started_at_utc": started_at,
        "completed_at_utc": clock(),
        "elapsed_wall_seconds": elapsed,
        "media_activity": {
            "audio_downloads": 0,
            "video_downloads": 0,
            "clap_calls": 0,
            "muq_calls": 0,
            "stage5a_materializations": 0,
        },
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


def write_ytdlp_results(path: str | Path, results: dict, *, overwrite: bool = False) -> None:
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"yt-dlp discovery artifact already exists: {output}")
    atomic_json(output, results)


def load_ytdlp_results(
    path: str | Path,
    manifest: FrozenTrackManifest,
    config: Stage5B1A2Config,
) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != RESULT_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected yt-dlp result schema")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise Stage5B1AValidationError("unexpected yt-dlp experiment ID")
    if payload.get("manifest", {}).get("sha256") != manifest.sha256:
        raise Stage5B1AValidationError("yt-dlp results use a different frozen manifest")
    if payload.get("configuration", {}).get("sha256") != config.sha256:
        raise Stage5B1AValidationError("yt-dlp results use a different frozen configuration")
    rows = payload.get("tracks")
    if not isinstance(rows, list):
        raise Stage5B1AValidationError("yt-dlp result tracks must be an array")
    identities = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("track"), dict):
            raise Stage5B1AValidationError("invalid yt-dlp result track row")
        stable_id = row["track"].get("stable_track_id")
        candidates = row.get("candidates")
        if not isinstance(stable_id, str) or not isinstance(candidates, list):
            raise Stage5B1AValidationError("invalid yt-dlp result identity or candidates")
        if len(candidates) > config.provider.candidate_limit:
            raise Stage5B1AValidationError("yt-dlp result exceeds candidate limit")
        ranks = [candidate.get("rank") for candidate in candidates if isinstance(candidate, dict)]
        ids = [candidate.get("youtube_video_id") for candidate in candidates if isinstance(candidate, dict)]
        providers = [candidate.get("provider") for candidate in candidates if isinstance(candidate, dict)]
        if ranks != list(range(1, len(candidates) + 1)):
            raise Stage5B1AValidationError("yt-dlp candidate ranks are not contiguous")
        if len(ids) != len(candidates) or any(not isinstance(value, str) for value in ids):
            raise Stage5B1AValidationError("yt-dlp candidates contain invalid video IDs")
        if len(ids) != len(set(ids)) or any(value != "yt_dlp" for value in providers):
            raise Stage5B1AValidationError("yt-dlp candidates are duplicated or misattributed")
        identities.append(stable_id)
    if tuple(identities) != manifest.stable_track_ids:
        raise Stage5B1AValidationError("yt-dlp result identities do not match manifest order")
    media = payload.get("media_activity")
    if not isinstance(media, dict) or any(value != 0 for value in media.values()):
        raise Stage5B1AValidationError("Stage 5B.1A2 must not perform media or encoder work")
    return payload
