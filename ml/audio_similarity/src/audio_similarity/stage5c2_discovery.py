"""Frozen Stage 5B discovery and selection for the Stage 5C.2 manifest."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .stage5b1a2_config import YtDlpProviderConfig
from .stage5b1a2_ytdlp import YtDlpDiscoveryAdapter, YtDlpPythonBackend
from .stage5b1a_config import QueryConfig
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b3_minimal_selector import (
    AUTO_SELECT,
    DURATION_ANOMALY_SECONDS,
    EXPERIMENT_ID as SELECTOR_ID,
    select_native_rank,
)
from .stage5b4c_artist_decomposition import (
    ALL_QUERY_VARIANTS_EMPTY,
    FALLBACK_SUCCESS,
    PRIMARY_SUCCESS,
    PROVIDER_ERROR,
    QUERY_CONTRACT_ID,
    build_artist_decomposition_plan,
    discover_with_artist_decomposition,
)
from .stage5c2_manifest import (
    EXPERIMENT_ID,
    REPORT_DIRECTORY,
    SAMPLE_SIZE,
    verify_frozen_manifest,
)


DISCOVERY_SCHEMA_VERSION = "stage5c2-discovery-results-v1"
DECISIONS_SCHEMA_VERSION = "stage5c2-automated-selector-decisions-v1"
SELECTED_SCHEMA_VERSION = "stage5c2-selected-sources-v1"
STATUS_RUNNING = "STAGE5C2_DISCOVERY_RUNNING"
STATUS_COMPLETE = "STAGE5C2_DISCOVERY_COMPLETE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _track(row: dict[str, Any]) -> SpotifyTrack:
    return SpotifyTrack.from_dict(
        {
            "stable_track_id": row["stage5c2_track_id"],
            "spotify_track_id": row["spotify_track_id"],
            "title": row["title"],
            "artists": row["artists"],
            "album": row.get("album"),
            "duration_ms": row.get("duration_ms"),
            "release_year": row.get("release_year"),
            "isrc": row.get("isrc"),
        }
    )


def default_provider() -> YtDlpDiscoveryAdapter:
    config = YtDlpProviderConfig(
        candidate_limit=3,
        search_prefix="ytsearch3:",
        extract_flat="in_playlist",
        skip_download=True,
        simulate=True,
        ignore_user_config=True,
        cache_enabled=False,
        socket_timeout_seconds=30,
        max_attempts=2,
        retry_backoff_seconds=2.0,
        sleep_between_tracks_seconds=1.0,
    )
    inert_query = QueryConfig(
        variant_id="stage5c2-explicit-frozen-query",
        template="{normalized_title} {primary_artist}",
        normalize_featured_artist_noise=False,
    )
    return YtDlpDiscoveryAdapter(config, inert_query, YtDlpPythonBackend(config))


def _document(
    manifest_sha: str,
    rows: list[dict[str, Any]],
    *,
    status: str,
    started_at: str,
    elapsed_seconds: float,
) -> dict[str, Any]:
    outcomes = [row["discovery"] for row in rows]
    attempts = [attempt for outcome in outcomes for attempt in outcome["attempts"]]
    return {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "status": status,
        "representative_manifest_sha256": manifest_sha,
        "started_at_utc": started_at,
        "completed_at_utc": _now() if status == STATUS_COMPLETE else None,
        "elapsed_seconds": elapsed_seconds,
        "summary": {
            "tracks_total": SAMPLE_SIZE,
            "tracks_completed": len(rows),
            "primary_success_count": sum(
                outcome["outcome"] == PRIMARY_SUCCESS for outcome in outcomes
            ),
            "fallback_trigger_count": sum(
                len(outcome["attempts"]) > 1 for outcome in outcomes
            ),
            "fallback_success_count": sum(
                outcome["outcome"] == FALLBACK_SUCCESS for outcome in outcomes
            ),
            "all_query_variants_empty_count": sum(
                outcome["outcome"] == ALL_QUERY_VARIANTS_EMPTY for outcome in outcomes
            ),
            "provider_error_count": sum(
                outcome["outcome"] == PROVIDER_ERROR for outcome in outcomes
            ),
            "tracks_with_candidates": sum(bool(outcome["candidates"]) for outcome in outcomes),
            "zero_candidate_tracks": sum(not outcome["candidates"] for outcome in outcomes),
            "candidate_count": sum(len(outcome["candidates"]) for outcome in outcomes),
            "provider_request_count": len(attempts),
            "provider_warning_count": sum(len(attempt["warnings"]) for attempt in attempts),
            "provider_elapsed_seconds": sum(attempt["elapsed_seconds"] for attempt in attempts),
        },
        "tracks": rows,
        "scope_guards": {
            "query_contract_id": QUERY_CONTRACT_ID,
            "maximum_queries_per_track": 4,
            "fallback_only_after_valid_zero": True,
            "candidate_pool_merges": 0,
            "candidate_reranking": False,
            "audio_downloads": 0,
            "video_downloads": 0,
            "production_activation": False,
        },
    }


def run_discovery(
    project_root: str | Path,
    provider: Any | None = None,
    *,
    report_dir: str | Path | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    report = Path(report_dir).resolve() if report_dir else root / REPORT_DIRECTORY
    manifest, manifest_sha = verify_frozen_manifest(report / "representative_manifest.json")
    output = report / "discovery_results.json"
    existing = _json(output) if output.exists() else None
    if existing and existing.get("status") == STATUS_COMPLETE:
        return existing
    rows = list(existing.get("tracks", [])) if existing else []
    expected_ids = [row["stage5c2_track_id"] for row in manifest["tracks"]]
    if [row.get("stage5c2_track_id") for row in rows] != expected_ids[: len(rows)]:
        raise Stage5B1AValidationError("partial Stage 5C.2 discovery is not a manifest prefix")
    active_provider = provider or default_provider()
    started_at = existing.get("started_at_utc") if existing else _now()
    started = time.monotonic()
    for index, manifest_row in enumerate(manifest["tracks"][len(rows) :], start=len(rows)):
        spotify_track = _track(manifest_row)
        expected_plan = build_artist_decomposition_plan(spotify_track).to_dict()
        requested_at = _now()
        outcome = discover_with_artist_decomposition(spotify_track, active_provider)
        if outcome["query_plan"] != expected_plan:
            raise Stage5B1AValidationError("Stage 5C.2 query plan changed during discovery")
        candidates = outcome["candidates"]
        if len(candidates) > 3 or [row.get("rank") for row in candidates] != list(
            range(1, len(candidates) + 1)
        ):
            raise Stage5B1AValidationError("native YouTube candidate order changed")
        rows.append(
            {
                "stage5c2_track_id": manifest_row["stage5c2_track_id"],
                "spotify_track_id": manifest_row["spotify_track_id"],
                "requested_at_utc": requested_at,
                "completed_at_utc": _now(),
                "discovery": outcome,
            }
        )
        atomic_json(
            output,
            _document(
                manifest_sha,
                rows,
                status=STATUS_RUNNING,
                started_at=started_at,
                elapsed_seconds=time.monotonic() - started,
            ),
        )
        if index + 1 < SAMPLE_SIZE:
            sleep(1.0)
    result = _document(
        manifest_sha,
        rows,
        status=STATUS_COMPLETE,
        started_at=started_at,
        elapsed_seconds=time.monotonic() - started,
    )
    atomic_json(output, result)
    return result


def freeze_selected_sources(
    project_root: str | Path,
    *,
    report_dir: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    root = Path(project_root).resolve()
    report = Path(report_dir).resolve() if report_dir else root / REPORT_DIRECTORY
    manifest, manifest_sha = verify_frozen_manifest(report / "representative_manifest.json")
    discovery_path = report / "discovery_results.json"
    discovery = _json(discovery_path)
    if (
        discovery.get("status") != STATUS_COMPLETE
        or discovery.get("representative_manifest_sha256") != manifest_sha
    ):
        raise Stage5B1AValidationError("complete Stage 5C.2 discovery is required")
    targets = {row["stage5c2_track_id"]: row for row in manifest["tracks"]}
    decisions: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for row in discovery["tracks"]:
        track_id = row["stage5c2_track_id"]
        target = targets[track_id]
        outcome = row["discovery"]
        decision = {
            "stage5c2_track_id": track_id,
            "spotify_track_id": target["spotify_track_id"],
            "spotify_target": target,
            "discovery_mode": outcome["discovery_mode"],
            "query_variant_index": outcome["query_variant_index"],
            "successful_query": outcome["successful_query"],
            **select_native_rank(target, outcome["candidates"]),
        }
        decisions.append(decision)
        candidate = decision.get("selected_candidate")
        if decision["decision"] == AUTO_SELECT and isinstance(candidate, dict):
            video_id = decision["selected_video_id"]
            selected.append(
                {
                    "stage5c2_track_id": track_id,
                    "manifest_index": target["manifest_index"],
                    "spotify_track_id": target["spotify_track_id"],
                    "title": target["title"],
                    "artists": target["artists"],
                    "album": target.get("album"),
                    "spotify_duration_ms": target.get("duration_ms"),
                    "release_year": target.get("release_year"),
                    "selected_youtube_video_id": video_id,
                    "selected_youtube_url": f"https://www.youtube.com/watch?v={video_id}",
                    "selected_candidate_rank": decision["selected_rank"],
                    "discovery_mode": decision["discovery_mode"],
                    "query_variant_index": decision["query_variant_index"],
                    "successful_query": decision["successful_query"],
                    "selector_decision": decision["decision"],
                    "selector_reason": decision["selection_reason"],
                    "candidate_metadata": candidate,
                }
            )
    decisions_document = {
        "schema_version": DECISIONS_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "status": "STAGE5C2_SELECTOR_FROZEN",
        "representative_manifest_sha256": manifest_sha,
        "discovery_sha256": file_sha256(discovery_path),
        "selector": {
            "selector_id": SELECTOR_ID,
            "implementation_sha256": manifest["frozen_contracts"]["selector_source"]["sha256"],
            "duration_veto_seconds": DURATION_ANOMALY_SECONDS,
            "modified_for_stage5c2": False,
        },
        "human_labels_read": 0,
        "tracks": decisions,
    }
    decisions_path = report / "automated_selector_decisions.json"
    if decisions_path.exists() and _json(decisions_path) != decisions_document:
        raise Stage5B1AValidationError("refusing to replace frozen Stage 5C.2 selector decisions")
    if not decisions_path.exists():
        atomic_json(decisions_path, decisions_document)
    selected_document = {
        "schema_version": SELECTED_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "frozen_at_utc": _now(),
        "representative_manifest_sha256": manifest_sha,
        "discovery_sha256": file_sha256(discovery_path),
        "selector_decisions_sha256": file_sha256(decisions_path),
        "manifest_track_count": SAMPLE_SIZE,
        "automated_selection_count": len(selected),
        "manual_tail_count": SAMPLE_SIZE - len(selected),
        "post_freeze_substitutions": 0,
        "exact_id_acquisition_only": True,
        "tracks": selected,
    }
    selected_path = report / "selected_sources.json"
    if selected_path.exists():
        prior = _json(selected_path)
        comparable = dict(selected_document)
        comparable["frozen_at_utc"] = prior.get("frozen_at_utc")
        if prior != comparable:
            raise Stage5B1AValidationError("refusing to replace frozen selected sources")
        selected_document = prior
    else:
        atomic_json(selected_path, selected_document)
    digest = file_sha256(selected_path)
    digest_path = report / "selected_sources.sha256"
    if digest_path.exists() and digest_path.read_text(encoding="utf-8").strip() != digest:
        raise Stage5B1AValidationError("Stage 5C.2 selected-source digest changed")
    if not digest_path.exists():
        digest_path.write_text(digest + "\n", encoding="utf-8")
    return selected_document, digest


def verify_selected_sources(path: str | Path) -> tuple[dict[str, Any], str]:
    selected_path = Path(path).resolve()
    expected = selected_path.with_suffix(".sha256").read_text(encoding="utf-8").strip()
    actual = file_sha256(selected_path)
    if actual != expected:
        raise Stage5B1AValidationError("Stage 5C.2 selected sources changed")
    value = _json(selected_path)
    tracks = value.get("tracks")
    if (
        value.get("schema_version") != SELECTED_SCHEMA_VERSION
        or value.get("post_freeze_substitutions") != 0
        or value.get("exact_id_acquisition_only") is not True
        or not isinstance(tracks, list)
        or value.get("automated_selection_count") != len(tracks)
    ):
        raise Stage5B1AValidationError("invalid frozen Stage 5C.2 selected sources")
    if len({row["spotify_track_id"] for row in tracks}) != len(tracks):
        raise Stage5B1AValidationError("duplicate Spotify IDs in selected sources")
    return value, actual
