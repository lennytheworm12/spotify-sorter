"""Frozen Stage 5B resolver benchmark over a held-out owner-library sample."""
from __future__ import annotations

import csv
import json
import os
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .stage5b1a2_config import YtDlpProviderConfig
from .stage5b1a2_ytdlp import (
    YtDlpDiscoveryAdapter,
    YtDlpPythonBackend,
    YtDlpSearchError,
)
from .stage5b1a_discovery import build_search_query
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_challenge import load_challenge_config, load_frozen_policies
from .stage5b1b_resolver import AUTO_MATCH, MATCH_UNCERTAIN
from .stage5b1c_normalization import parse_tier2_title
from .stage5b1h_source_semantics import derive_source_semantics
from .stage5b1i_live_fallback import EXACT_RECORDING
from .stage5b1j_representation_rediscovery import (
    REPRESENTATION_EQUIVALENT_MASTER_FALLBACK,
    REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK,
    _resolve_representation_pool,
    build_fallback_query,
    classify_fallback_target,
    derive_base_target,
    evaluate_candidate_pool,
    load_stage5b1j_config,
    q0_query_config,
)
from .stage5b_representative_library import verify_frozen_manifest


CONFIG_SCHEMA_VERSION = "stage5b-representative-library-execution-config-v1"
DISCOVERY_SCHEMA_VERSION = "stage5b-representative-library-discovery-v1"
FEATURE_SCHEMA_VERSION = "stage5b-representative-library-features-v1"
DECISION_SCHEMA_VERSION = "stage5b-representative-library-decisions-v1"
REVIEW_SCHEMA_VERSION = "stage5b-representative-library-review-v1"
ARTIFACT_SCHEMA_VERSION = "stage5b-representative-library-artifacts-v1"
STATUS_RUNNING = "STAGE5B_REPRESENTATIVE_LIBRARY_DISCOVERY_RUNNING"
STATUS_DISCOVERY_COMPLETE = "STAGE5B_REPRESENTATIVE_LIBRARY_DISCOVERY_COMPLETE"
STATUS_AWAITING_REVIEW = "STAGE5B_REPRESENTATIVE_LIBRARY_AWAITING_HUMAN_REVIEW"

REVIEW_LABELS = frozenset({"", "IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"})
REVIEW_COLUMNS = (
    "review_schema_version", "benchmark_id", "spotify_track_id",
    "expected_title", "expected_artists", "expected_album",
    "expected_duration_seconds", "expected_release_year",
    "candidate_video_id", "candidate_url", "candidate_title",
    "candidate_uploader", "candidate_channel", "candidate_duration_seconds",
    "candidate_view_count", "candidate_description", "match_mode",
    "fallback_reason", "candidate_review_label", "candidate_note", "track_note",
)


@dataclass(frozen=True)
class RepresentativeBenchmarkConfig:
    path: Path
    project_root: Path
    benchmark_id: str
    resolver_stack_id: str
    frozen_inputs: dict[str, dict[str, str]]
    provider: YtDlpProviderConfig
    artifacts: dict[str, Path]
    sha256: str


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_benchmark_config(path: str | Path) -> RepresentativeBenchmarkConfig:
    path = Path(path).resolve()
    value = _json(path)
    if value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected representative benchmark config schema")
    project_root = path.parent.parent
    provider = value.get("provider")
    if not isinstance(provider, dict):
        raise Stage5B1AValidationError("benchmark provider configuration is required")
    required_true = ("skip_download", "simulate", "ignore_user_config", "sequential_requests")
    if any(provider.get(key) is not True for key in required_true):
        raise Stage5B1AValidationError("benchmark discovery must remain sequential metadata-only")
    if (
        provider.get("candidate_limit") != 5
        or provider.get("search_prefix") != "ytsearch5:"
        or provider.get("extract_flat") != "in_playlist"
        or provider.get("cache_enabled") is not False
    ):
        raise Stage5B1AValidationError("benchmark discovery must use frozen ytsearch5 semantics")
    provider_config = YtDlpProviderConfig(
        candidate_limit=5,
        search_prefix="ytsearch5:",
        extract_flat="in_playlist",
        skip_download=True,
        simulate=True,
        ignore_user_config=True,
        cache_enabled=False,
        socket_timeout_seconds=int(provider["socket_timeout_seconds"]),
        max_attempts=int(provider["max_attempts"]),
        retry_backoff_seconds=float(provider["retry_backoff_seconds"]),
        sleep_between_tracks_seconds=float(provider["sleep_between_tracks_seconds"]),
    )
    return RepresentativeBenchmarkConfig(
        path=path,
        project_root=project_root,
        benchmark_id=str(value["benchmark_id"]),
        resolver_stack_id=str(value["resolver_stack_id"]),
        frozen_inputs=dict(value["frozen_inputs"]),
        provider=provider_config,
        artifacts={key: project_root / value for key, value in value["artifacts"].items()},
        sha256=file_sha256(path),
    )


def verify_benchmark_inputs(config: RepresentativeBenchmarkConfig) -> dict[str, Any]:
    verified = {}
    for name, identity in config.frozen_inputs.items():
        path = (config.project_root / identity["path"]).resolve()
        actual = file_sha256(path)
        if actual != identity["sha256"]:
            raise Stage5B1AValidationError(f"frozen benchmark input changed: {name}")
        verified[name] = {"path": identity["path"], "sha256": actual}
    manifest_path = config.project_root / config.frozen_inputs["benchmark_manifest"]["path"]
    digest_path = manifest_path.with_suffix(".sha256")
    manifest = verify_frozen_manifest(manifest_path, digest_path)
    stack = _json(config.project_root / config.frozen_inputs["resolver_stack"]["path"])
    if stack.get("stack_id") != config.resolver_stack_id:
        raise Stage5B1AValidationError("frozen resolver stack identity changed")
    if manifest.get("sampled_track_count") != len(manifest.get("tracks", [])):
        raise Stage5B1AValidationError("benchmark manifest count mismatch")
    return {"verified": verified, "manifest": manifest, "stack": stack}


def _track(row: dict[str, Any]) -> SpotifyTrack:
    return SpotifyTrack.from_dict({
        "stable_track_id": row["benchmark_id"],
        "spotify_track_id": row["spotify_track_id"],
        "title": row["title"],
        "artists": row["artists"],
        "album": row.get("album"),
        "duration_ms": row.get("duration_ms"),
        "release_year": row.get("release_year"),
        "isrc": row.get("isrc"),
    })


def _outcome(
    adapter: YtDlpDiscoveryAdapter,
    track: SpotifyTrack,
    *,
    query: str | None = None,
) -> dict[str, Any]:
    requested = _utc_now()
    try:
        result = (
            adapter.discover_query(track, query, limit=5)
            if query is not None
            else adapter.discover(track, limit=5)
        ).to_dict()
        return {"requested_at_utc": requested, "completed_at_utc": _utc_now(), **result}
    except YtDlpSearchError as exc:
        frozen_query = query or build_search_query(track, q0_query_config())
        return {
            "requested_at_utc": requested,
            "completed_at_utc": _utc_now(),
            "track": track.to_dict(),
            "query": frozen_query,
            "candidates": [],
            "candidate_video_ids": [],
            "warnings": list(exc.warnings),
            "error": exc.to_dict(),
        }


def _policies(config: RepresentativeBenchmarkConfig) -> tuple[Any, Any]:
    stage1j = load_stage5b1j_config(
        config.project_root / config.frozen_inputs["stage5b1j_config"]["path"]
    )
    challenge = load_challenge_config(stage1j.challenge_config)
    boundaries, policies = load_frozen_policies(challenge)
    return boundaries, policies["POLICY_BALANCED_V1"]


def _exact_decision(
    track: SpotifyTrack,
    outcome: dict[str, Any],
    boundaries: Any,
    policy: Any,
) -> dict[str, Any]:
    return evaluate_candidate_pool(
        track,
        list(outcome.get("candidates") or []),
        policy=policy,
        boundaries=boundaries,
        neutralize_live_duration=False,
    )


def run_discovery(
    config: RepresentativeBenchmarkConfig,
    adapter: YtDlpDiscoveryAdapter | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    inputs = verify_benchmark_inputs(config)
    manifest = inputs["manifest"]
    path = config.artifacts["discovery"]
    existing = _json(path) if path.exists() else None
    if existing and existing.get("status") == STATUS_DISCOVERY_COMPLETE:
        raise Stage5B1AValidationError("benchmark discovery is already frozen")
    rows = list(existing.get("tracks", [])) if existing else []
    expected = [row["benchmark_id"] for row in manifest["tracks"]]
    if [row.get("benchmark_id") for row in rows] != expected[:len(rows)]:
        raise Stage5B1AValidationError("partial benchmark discovery is not a manifest prefix")
    adapter = adapter or YtDlpDiscoveryAdapter(
        config.provider,
        q0_query_config(),
        YtDlpPythonBackend(config.provider),
    )
    boundaries, policy = _policies(config)
    started = existing.get("started_at_utc") if existing else _utc_now()
    started_clock = time.monotonic()
    for index, manifest_row in enumerate(manifest["tracks"][len(rows):], start=len(rows)):
        track = _track(manifest_row)
        exact = _outcome(adapter, track)
        exact_pool = _exact_decision(track, exact, boundaries, policy)
        classification = classify_fallback_target(track)
        fallback = None
        base_target = None
        fallback_query = None
        if exact_pool["global_decision"]["status"] == MATCH_UNCERTAIN and classification["eligible"]:
            base_target = derive_base_target(track, classification)
            fallback_query = build_fallback_query(track, classification)
            fallback = _outcome(adapter, base_target, query=fallback_query)
        rows.append({
            "benchmark_id": track.stable_track_id,
            "spotify_target": track.to_dict(),
            "exact_query": exact.get("query") or build_search_query(track, q0_query_config()),
            "exact_outcome": exact,
            "fallback_classification": classification,
            "base_representation_target": base_target.to_dict() if base_target else None,
            "fallback_query": fallback_query,
            "fallback_outcome": fallback,
        })
        partial = _discovery_document(config, manifest, rows, started, STATUS_RUNNING, 0.0)
        atomic_json(path, partial)
        if index + 1 < len(manifest["tracks"]):
            sleep(config.provider.sleep_between_tracks_seconds)
    document = _discovery_document(
        config, manifest, rows, started, STATUS_DISCOVERY_COMPLETE,
        time.monotonic() - started_clock,
    )
    atomic_json(path, document)
    return document


def _discovery_document(
    config: RepresentativeBenchmarkConfig,
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    started: str,
    status: str,
    elapsed: float,
) -> dict[str, Any]:
    outcomes = [
        outcome
        for row in rows
        for outcome in (row["exact_outcome"], row.get("fallback_outcome"))
        if outcome is not None
    ]
    versions = sorted({
        str(outcome["provider"]["version"])
        for outcome in outcomes if outcome.get("provider", {}).get("version")
    })
    return {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "status": status,
        "config_sha256": config.sha256,
        "benchmark_manifest_sha256": config.frozen_inputs["benchmark_manifest"]["sha256"],
        "resolver_stack_sha256": config.frozen_inputs["resolver_stack"]["sha256"],
        "started_at_utc": started,
        "completed_at_utc": _utc_now() if status == STATUS_DISCOVERY_COMPLETE else None,
        "elapsed_current_process_seconds": elapsed,
        "provider": {
            "name": "yt_dlp", "versions": versions,
            "search_mode": "ytsearch5", "metadata_only": True,
            "sequential": True,
            "sleep_between_tracks_seconds": config.provider.sleep_between_tracks_seconds,
        },
        "summary": {
            "benchmark_tracks_total": manifest["sampled_track_count"],
            "benchmark_tracks_completed": len(rows),
            "searches_completed": len(outcomes),
            "fallback_searches_completed": sum(row.get("fallback_outcome") is not None for row in rows),
            "search_failures": sum(outcome.get("error") is not None for outcome in outcomes),
            "warning_count": sum(len(outcome.get("warnings", [])) for outcome in outcomes),
            "zero_candidate_searches": sum(not outcome.get("candidates") for outcome in outcomes),
            "deduplicated_candidates": sum(len(outcome.get("candidates", [])) for outcome in outcomes),
        },
        "tracks": rows,
        "media_activity": {
            "audio_downloads": 0, "video_downloads": 0, "stage5a_calls": 0,
            "clap_calls": 0, "muq_calls": 0,
        },
    }


def _selected_record(pool: dict[str, Any] | None, video_id: str | None) -> dict[str, Any] | None:
    if pool is None or video_id is None:
        return None
    return next((
        row for row in pool.get("candidate_records", [])
        if row["raw_candidate"].get("youtube_video_id") == video_id
    ), None)


def _candidate_from_outcome(outcome: dict[str, Any] | None, video_id: str | None) -> dict[str, Any] | None:
    if outcome is None or video_id is None:
        return None
    return next((
        row for row in outcome.get("candidates", [])
        if row.get("youtube_video_id") == video_id
    ), None)


def _failure_reason(
    exact_outcome: dict[str, Any],
    exact_pool: dict[str, Any],
    fallback_outcome: dict[str, Any] | None,
    fallback_pool: dict[str, Any] | None,
) -> str:
    outcomes = [item for item in (exact_outcome, fallback_outcome) if item is not None]
    records = [
        record for pool in (exact_pool, fallback_pool) if pool is not None
        for record in pool.get("candidate_records", [])
    ]
    if outcomes and all(item.get("error") is not None for item in outcomes):
        return "PROVIDER_FAILURE"
    if not any(item.get("candidates") for item in outcomes):
        return "DISCOVERY_FAILURE"
    if records and all(record["global_features"]["hard_conflicts"] for record in records):
        return "EXPLICIT_CONFLICT"
    if records and any(record["global_features"]["eligibility"]["eligible"] for record in records):
        return "RESOLVER_UNCERTAIN"
    return "METADATA_INSUFFICIENT"


def evaluate_benchmark(
    config: RepresentativeBenchmarkConfig,
    discovery: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    inputs = verify_benchmark_inputs(config)
    discovery = discovery or _json(config.artifacts["discovery"])
    if discovery.get("status") != STATUS_DISCOVERY_COMPLETE:
        raise Stage5B1AValidationError("benchmark discovery is not complete")
    expected_ids = [row["benchmark_id"] for row in inputs["manifest"]["tracks"]]
    if [row.get("benchmark_id") for row in discovery.get("tracks", [])] != expected_ids:
        raise Stage5B1AValidationError("benchmark discovery does not match frozen manifest")
    if discovery.get("media_activity") != {
        "audio_downloads": 0, "video_downloads": 0, "stage5a_calls": 0,
        "clap_calls": 0, "muq_calls": 0,
    }:
        raise Stage5B1AValidationError("benchmark media guard changed")
    boundaries, policy = _policies(config)
    feature_rows = []
    decision_rows = []
    for row in discovery["tracks"]:
        track = SpotifyTrack.from_dict(row["spotify_target"])
        exact_pool = _exact_decision(track, row["exact_outcome"], boundaries, policy)
        selected = exact_pool["global_decision"]
        match_mode = EXACT_RECORDING if selected["status"] == AUTO_MATCH else None
        selected_pool_name = "PRIMARY_Q0"
        selected_pool = exact_pool
        fallback_exact_pool = None
        representation_pool = None
        if selected["status"] == MATCH_UNCERTAIN and row.get("fallback_outcome") is not None:
            fallback_exact_pool = _exact_decision(
                track, row["fallback_outcome"], boundaries, policy
            )
            selected = fallback_exact_pool["global_decision"]
            selected_pool = fallback_exact_pool
            selected_pool_name = "FALLBACK_QUERY_EXACT_TARGET"
            if selected["status"] == AUTO_MATCH:
                match_mode = EXACT_RECORDING
            else:
                base = SpotifyTrack.from_dict(row["base_representation_target"])
                base_pool = evaluate_candidate_pool(
                    base,
                    list(row["fallback_outcome"].get("candidates") or []),
                    policy=policy,
                    boundaries=boundaries,
                    neutralize_live_duration=(
                        row["fallback_classification"]["fallback_family"] == "LIVE_TO_STUDIO"
                    ),
                )
                representation_pool = _resolve_representation_pool(base_pool)
                selected = representation_pool["global_decision"]
                selected_pool = representation_pool
                selected_pool_name = "FALLBACK_QUERY_BASE_REPRESENTATION"
                if selected["status"] == AUTO_MATCH:
                    match_mode = row["fallback_classification"]["match_mode"]
        video_id = selected.get("selected_video_id")
        selected_record = _selected_record(selected_pool, video_id)
        selected_semantics = (
            selected_record.get("source_semantics")
            if selected_record and selected_record.get("source_semantics")
            else derive_source_semantics(selected_record) if selected_record else None
        )
        selected_outcome = (
            row["exact_outcome"] if selected_pool_name == "PRIMARY_Q0"
            else row.get("fallback_outcome")
        )
        raw_selected = _candidate_from_outcome(selected_outcome, video_id)
        failure = None if selected["status"] == AUTO_MATCH else _failure_reason(
            row["exact_outcome"], exact_pool, row.get("fallback_outcome"),
            representation_pool or fallback_exact_pool,
        )
        parsed = parse_tier2_title(track.title, candidate=False)
        decision_rows.append({
            "benchmark_id": track.stable_track_id,
            "spotify_track_id": track.spotify_track_id,
            "spotify_target": track.to_dict(),
            "status": selected["status"],
            "selected_video_id": video_id,
            "selected_candidate_rank": selected.get("selected_candidate_rank"),
            "selected_pool": selected_pool_name if video_id else None,
            "match_mode": match_mode,
            "policy_rule_id": "STAGE5B_RESOLVER_CANDIDATE_V1",
            "selection_reason": (
                "frozen global resolver selected an exact recording candidate"
                if match_mode == EXACT_RECORDING
                else "exact resolution failed; frozen fallback selected a canonical representation-equivalent base recording"
                if match_mode else None
            ),
            "fallback_reason": (
                row["fallback_classification"]["reason"]
                if match_mode in {
                    REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK,
                    REPRESENTATION_EQUIVALENT_MASTER_FALLBACK,
                } else None
            ),
            "source_type": (
                selected_semantics.get("normalized_source_type")
                if selected_semantics else None
            ),
            "canonicality": (
                selected_semantics.get("canonicality", {}).get("level")
                if selected_semantics else None
            ),
            "failure_reason": failure,
            "target_version_families": sorted({item.family for item in parsed.versions}),
            "selected_candidate": raw_selected,
        })
        feature_rows.append({
            "benchmark_id": track.stable_track_id,
            "spotify_target": track.to_dict(),
            "fallback_classification": row["fallback_classification"],
            "primary_q0_evaluation": exact_pool,
            "fallback_exact_evaluation": fallback_exact_pool,
            "fallback_representation_evaluation": representation_pool,
        })
    auto_rows = [row for row in decision_rows if row["status"] == AUTO_MATCH]
    mode_counts = Counter(row["match_mode"] for row in auto_rows)
    source_counts = Counter(row["source_type"] or "UNKNOWN" for row in auto_rows)
    failure_counts = Counter(row["failure_reason"] for row in decision_rows if row["failure_reason"])
    version_counts: dict[str, Counter[str]] = {}
    for row in decision_rows:
        family = row["target_version_families"][0] if row["target_version_families"] else "ordinary_studio"
        version_counts.setdefault(family, Counter())[row["status"]] += 1
    total = len(decision_rows)
    summary = {
        "benchmark_track_count": total,
        "auto_match_count": len(auto_rows),
        "auto_match_coverage": len(auto_rows) / total if total else 0.0,
        "match_uncertain_count": total - len(auto_rows),
        "exact_recording_count": mode_counts[EXACT_RECORDING],
        "studio_fallback_count": mode_counts[REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK],
        "master_fallback_count": mode_counts[REPRESENTATION_EQUIVALENT_MASTER_FALLBACK],
        "product_coverage_target": 0.90,
        "product_coverage_gate_met": len(auto_rows) / total >= 0.90 if total else False,
        "source_composition": dict(sorted(source_counts.items())),
        "failure_reasons": dict(sorted(failure_counts.items())),
        "version_family_behavior": {
            key: dict(sorted(value.items())) for key, value in sorted(version_counts.items())
        },
    }
    features = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "benchmark_manifest_sha256": config.frozen_inputs["benchmark_manifest"]["sha256"],
        "discovery_sha256": file_sha256(config.artifacts["discovery"]),
        "track_count": total,
        "tracks": feature_rows,
    }
    decisions = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "status": STATUS_AWAITING_REVIEW,
        "resolver_stack_id": config.resolver_stack_id,
        "production_activated": False,
        "summary": summary,
        "tracks": decision_rows,
        "scope_guards": {
            "benchmark_tuning_permitted": False, "post_freeze_substitutions": 0,
            "audio_downloads": 0, "video_downloads": 0, "stage5a_calls": 0,
            "clap_calls": 0, "muq_calls": 0,
        },
    }
    coverage = {
        "schema_version": "stage5b-representative-library-coverage-v1",
        "status": STATUS_AWAITING_REVIEW,
        **summary,
        "human_review": {
            "required": len(auto_rows), "completed": 0,
            "safe_precision": None, "wrong_rate": None, "uncertain_rate": None,
        },
        "adversarial_challenge_comparison": {
            "challenge_auto_match": 43, "challenge_total": 50,
            "challenge_coverage": 0.86,
            "metrics_kept_separate": True,
        },
    }
    return features, decisions, coverage


def _existing_review(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    output = {}
    for row in rows:
        if row.get("candidate_review_label") not in REVIEW_LABELS:
            raise Stage5B1AValidationError("invalid representative review label")
        output[(row["benchmark_id"], row["candidate_video_id"])] = row
    return output


def write_review_csv(config: RepresentativeBenchmarkConfig, decisions: dict[str, Any]) -> None:
    existing = _existing_review(config.artifacts["human_review"])
    rows = []
    for decision in decisions["tracks"]:
        if decision["status"] != AUTO_MATCH:
            continue
        track = decision["spotify_target"]
        candidate = decision["selected_candidate"]
        identity = (decision["benchmark_id"], decision["selected_video_id"])
        prior = existing.get(identity, {})
        rows.append({
            "review_schema_version": REVIEW_SCHEMA_VERSION,
            "benchmark_id": decision["benchmark_id"],
            "spotify_track_id": decision["spotify_track_id"],
            "expected_title": track["title"],
            "expected_artists": " | ".join(track["artists"]),
            "expected_album": track.get("album") or "",
            "expected_duration_seconds": (
                track["duration_ms"] / 1000 if track.get("duration_ms") is not None else ""
            ),
            "expected_release_year": track.get("release_year") or "",
            "candidate_video_id": decision["selected_video_id"],
            "candidate_url": candidate.get("canonical_url") or candidate.get("url") or "",
            "candidate_title": candidate.get("title") or "",
            "candidate_uploader": candidate.get("uploader") or "",
            "candidate_channel": candidate.get("channel") or "",
            "candidate_duration_seconds": candidate.get("duration_seconds")
            if candidate.get("duration_seconds") is not None else "",
            "candidate_view_count": candidate.get("view_count")
            if candidate.get("view_count") is not None else "",
            "candidate_description": candidate.get("description") or "",
            "match_mode": decision["match_mode"],
            "fallback_reason": decision.get("fallback_reason") or "",
            "candidate_review_label": prior.get("candidate_review_label", ""),
            "candidate_note": prior.get("candidate_note", ""),
            "track_note": prior.get("track_note", ""),
        })
    if existing and set(existing) != {
        (row["benchmark_id"], row["candidate_video_id"]) for row in rows
    }:
        raise Stage5B1AValidationError("benchmark selections changed after review began")
    path = config.artifacts["human_review"]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _human_summary(path: Path) -> dict[str, Any]:
    rows = list(_existing_review(path).values())
    labels = Counter(row["candidate_review_label"] for row in rows if row["candidate_review_label"])
    reviewed = sum(labels.values())
    safe = labels["IDEAL"] + labels["ACCEPTABLE"]
    return {
        "required": len(rows),
        "completed": reviewed,
        "label_counts": dict(sorted(labels.items())),
        "safe_precision": safe / reviewed if reviewed else None,
        "wrong_rate": labels["WRONG"] / reviewed if reviewed else None,
        "uncertain_rate": labels["UNCERTAIN"] / reviewed if reviewed else None,
        "complete": reviewed == len(rows),
    }


def _render_report(
    config: RepresentativeBenchmarkConfig,
    discovery: dict[str, Any],
    decisions: dict[str, Any],
    coverage: dict[str, Any],
    human: dict[str, Any],
) -> str:
    summary = decisions["summary"]
    return "\n".join([
        "# Stage 5B — Representative Owner-Library Benchmark v1",
        "",
        f"Status: `{STATUS_AWAITING_REVIEW if not human['complete'] else 'STAGE5B_REPRESENTATIVE_LIBRARY_HUMAN_REVIEW_COMPLETE'}`",
        "",
        "## Frozen evaluation contract",
        "",
        f"- resolver stack: `{config.resolver_stack_id}`",
        f"- benchmark manifest SHA-256: `{config.frozen_inputs['benchmark_manifest']['sha256']}`",
        "- deterministic 100-track sample from liked songs plus owner-owned playlists",
        "- all historical DEV/calibration/challenge identities excluded before sampling",
        "- Q0 discovery: `\"{primary_artist}\" \"{normalized_title}\" official` via metadata-only `ytsearch5`",
        "- no benchmark-driven query, parser, threshold, or resolver mutation permitted",
        "",
        "## Discovery",
        "",
        f"- benchmark tracks: **{summary['benchmark_track_count']}**",
        f"- searches: **{discovery['summary']['searches_completed']}**",
        f"- fallback searches: **{discovery['summary']['fallback_searches_completed']}**",
        f"- provider failures: **{discovery['summary']['search_failures']}**",
        f"- warnings: **{discovery['summary']['warning_count']}**",
        f"- yt-dlp: `{', '.join(discovery['provider']['versions'])}`",
        "",
        "## Automated resolution",
        "",
        f"- AUTO_MATCH: **{summary['auto_match_count']}/{summary['benchmark_track_count']} ({summary['auto_match_coverage']:.1%})**",
        f"- EXACT_RECORDING: **{summary['exact_recording_count']}**",
        f"- REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK: **{summary['studio_fallback_count']}**",
        f"- REPRESENTATION_EQUIVALENT_MASTER_FALLBACK: **{summary['master_fallback_count']}**",
        f"- MATCH_UNCERTAIN: **{summary['match_uncertain_count']}**",
        f"- ≥90% product coverage gate: **{'PASS' if summary['product_coverage_gate_met'] else 'MISS'}**",
        f"- source composition: `{json.dumps(summary['source_composition'], sort_keys=True)}`",
        f"- unresolved reasons: `{json.dumps(summary['failure_reasons'], sort_keys=True)}`",
        "",
        "## Human precision gate",
        "",
        f"- selected candidates requiring review: **{human['required']}**",
        f"- completed: **{human['completed']}**",
        f"- labels: `{json.dumps(human['label_counts'], sort_keys=True)}`",
        f"- SAFE precision: **{human['safe_precision']:.1%}**" if human["safe_precision"] is not None else "- SAFE precision: **pending**",
        "- product safety target: **≥95% SAFE**",
        "",
        "Human precision remains pending until every automatically selected candidate is reviewed. "
        "The benchmark is frozen evaluation evidence and must not be used to tune this stack.",
        "",
        "## Adversarial comparison",
        "",
        "The separately reported adversarial challenge is **43/50 (86%)** after the human-safe "
        "representation fallback. Its metric is not merged with this representative sample.",
        "",
        "## Scope guards",
        "",
        "Audio downloads 0; video downloads 0; Stage 5A calls 0; CLAP calls 0; MuQ calls 0. "
        "The frozen resolver remains a candidate stack, not production activated.",
        "",
    ])


def write_evaluation_artifacts(config: RepresentativeBenchmarkConfig) -> dict[str, Any]:
    discovery = _json(config.artifacts["discovery"])
    features, decisions, coverage = evaluate_benchmark(config, discovery)
    atomic_json(config.artifacts["features"], features)
    atomic_json(config.artifacts["decisions"], decisions)
    write_review_csv(config, decisions)
    human = _human_summary(config.artifacts["human_review"])
    coverage["human_review"] = human
    atomic_json(config.artifacts["coverage"], coverage)
    config.artifacts["report"].write_text(
        _render_report(config, discovery, decisions, coverage, human), encoding="utf-8"
    )
    artifact_names = (
        "discovery", "features", "decisions", "coverage", "human_review", "report"
    )
    manifest = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "status": STATUS_AWAITING_REVIEW if not human["complete"] else "STAGE5B_REPRESENTATIVE_LIBRARY_HUMAN_REVIEW_COMPLETE",
        "benchmark_id": config.benchmark_id,
        "resolver_stack_id": config.resolver_stack_id,
        "config_sha256": config.sha256,
        "input_artifacts": verify_benchmark_inputs(config)["verified"],
        "output_artifacts": {
            name: {
                "path": str(config.artifacts[name].relative_to(config.project_root)),
                "sha256": file_sha256(config.artifacts[name]),
                "size_bytes": config.artifacts[name].stat().st_size,
            }
            for name in artifact_names
        },
        "summary": decisions["summary"],
        "human_review": human,
        "production_activated": False,
    }
    atomic_json(config.artifacts["manifest"], manifest)
    return manifest


def discover_and_evaluate(config: RepresentativeBenchmarkConfig) -> dict[str, Any]:
    run_discovery(config)
    return write_evaluation_artifacts(config)
