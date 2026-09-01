"""Sequential, auditable Stage 5B.1A discovery experiment orchestration."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .stage5b1a_config import Stage5B1AConfig
from .stage5b1a_discovery import (
    FirecrawlDiscoveryAdapter,
    FirecrawlRequestError,
    build_search_query,
)
from .stage5b1a_models import EXPERIMENT_ID, FrozenTrackManifest
from .stage5b1a_models import Stage5B1AValidationError


RESULT_SCHEMA_VERSION = "stage5b1a-firecrawl-discovery-results-v1"
AWAITING_REVIEW = "DISCOVERY_COMPLETE_AWAITING_HUMAN_REVIEW"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: str | Path, value: dict) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)


def run_discovery_experiment(
    manifest: FrozenTrackManifest,
    config: Stage5B1AConfig,
    adapter: FirecrawlDiscoveryAdapter,
    *,
    clock: Callable[[], str] = utc_now,
) -> dict:
    """Execute exactly one sequential request per frozen manifest row."""
    started_at = clock()
    rows = []
    for item in manifest.tracks:
        requested_at = clock()
        try:
            outcome = adapter.discover(item.track, limit=config.provider.candidate_limit)
            row = outcome.to_dict()
        except FirecrawlRequestError as exc:
            query = build_search_query(item.track, config.query)
            row = {
                "track": item.track.to_dict(),
                "query": query,
                "request": {
                    "endpoint": config.provider.endpoint,
                    "payload": config.provider.request_payload(query),
                    "api_key_environment_variable": config.provider.api_key_environment_variable,
                },
                "provider": {
                    "name": "firecrawl",
                    "discovery_version": config.provider.discovery_version,
                    "attempts": exc.attempts,
                    "job_id": None,
                    "credits_used": None,
                    "warning": None,
                },
                "normalized_results": [],
                "candidates": [],
                "candidate_video_ids": [],
                "error": exc.to_dict(),
            }
        row["case_tags"] = list(item.case_tags)
        row["case_rationale"] = item.case_rationale
        row["requested_at_utc"] = requested_at
        row["completed_at_utc"] = clock()
        rows.append(row)
    request_failures = sum(row["error"] is not None for row in rows)
    zero_candidates = sum(not row["candidates"] for row in rows)
    invalid_results = sum(
        result["youtube_video_id"] is None
        for row in rows
        for result in row["normalized_results"]
    )
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
                "name": "firecrawl",
                "discovery_version": config.provider.discovery_version,
                "endpoint": config.provider.endpoint,
                "sources": [dict(source) for source in config.provider.sources],
                "include_domains": list(config.provider.include_domains),
                "provider_result_limit": config.provider.provider_result_limit,
                "candidate_limit": config.provider.candidate_limit,
                "country": config.provider.country,
                "highlights": config.provider.highlights,
                "sequential_requests": True,
                "max_attempts": config.provider.max_attempts,
                "request_timeout_ms": config.provider.request_timeout_ms,
            },
        },
        "started_at_utc": started_at,
        "completed_at_utc": clock(),
        "summary": {
            "tracks": len(rows),
            "firecrawl_request_failures": request_failures,
            "tracks_with_zero_youtube_candidates": zero_candidates,
            "invalid_or_non_video_results": invalid_results,
        },
        "tracks": rows,
    }


def write_discovery_results(path: str | Path, results: dict, *, overwrite: bool = False) -> None:
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"discovery artifact already exists: {output}")
    atomic_json(output, results)


def load_discovery_results(
    path: str | Path,
    manifest: FrozenTrackManifest,
    config: Stage5B1AConfig,
) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != RESULT_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected discovery result schema")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise Stage5B1AValidationError("unexpected discovery result experiment ID")
    if payload.get("manifest", {}).get("sha256") != manifest.sha256:
        raise Stage5B1AValidationError("discovery results use a different frozen manifest")
    if payload.get("configuration", {}).get("sha256") != config.sha256:
        raise Stage5B1AValidationError("discovery results use a different frozen configuration")
    rows = payload.get("tracks")
    if not isinstance(rows, list):
        raise Stage5B1AValidationError("discovery results tracks must be an array")
    identities = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("track"), dict):
            raise Stage5B1AValidationError("invalid discovery result track row")
        stable_id = row["track"].get("stable_track_id")
        candidates = row.get("candidates")
        if not isinstance(stable_id, str) or not isinstance(candidates, list):
            raise Stage5B1AValidationError("invalid discovery result track identity or candidates")
        if len(candidates) > config.provider.candidate_limit:
            raise Stage5B1AValidationError("discovery result exceeds the frozen candidate limit")
        ranks = [candidate.get("rank") for candidate in candidates if isinstance(candidate, dict)]
        video_ids = [
            candidate.get("youtube_video_id")
            for candidate in candidates
            if isinstance(candidate, dict)
        ]
        if ranks != list(range(1, len(candidates) + 1)):
            raise Stage5B1AValidationError("discovery candidate ranks are not contiguous")
        if any(not isinstance(video_id, str) for video_id in video_ids) or len(video_ids) != len(set(video_ids)):
            raise Stage5B1AValidationError("discovery candidates contain invalid or duplicate video IDs")
        identities.append(stable_id)
    if tuple(identities) != manifest.stable_track_ids:
        raise Stage5B1AValidationError("discovery result identities do not match manifest order")
    return payload
