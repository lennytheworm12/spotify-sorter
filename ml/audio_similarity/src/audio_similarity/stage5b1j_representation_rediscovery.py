"""Stage 5B.1J fallback-specific rediscovery and offline resolution.

Historical Q0 pools and policies remain immutable. New metadata-only searches are
limited to unresolved ordinary-live and true-remaster targets. Each new pool is
first evaluated against the exact Spotify target, then—only if exact resolution
fails—against an explicit representation-equivalent base target.
"""
from __future__ import annotations

import copy
import json
import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .stage5b1a2_config import YtDlpProviderConfig
from .stage5b1a2_ytdlp import YtDlpDiscoveryAdapter, YtDlpSearchError
from .stage5b1a_config import QueryConfig
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_challenge import (
    load_challenge_config,
    load_challenge_manifest,
    load_frozen_policies,
)
from .stage5b1b_resolver import AUTO_MATCH, MATCH_UNCERTAIN
from .stage5b1c_normalization import parse_tier2_title
from .stage5b1d_rediscovery import evaluate_resolver_cascade
from .stage5b1f_diagnostic import candidate_snapshot
from .stage5b1g_global_preference import (
    build_global_candidate_evidence,
    resolve_global_candidates,
)
from .stage5b1h_source_semantics import (
    CANONICAL_STRONG,
    RECORDING_COMPATIBLE,
    derive_source_semantics,
)
from .stage5b1i_live_fallback import (
    ARRANGEMENT_CHANGING_LIVE,
    EXACT_RECORDING,
    NOT_LIVE_TARGET,
    ORDINARY_LIVE,
    REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK,
    classify_live_target,
    evaluate_stage5b1i,
    load_stage5b1i_config,
)


CONFIG_SCHEMA_VERSION = "stage5b1j-representation-rediscovery-config-v1"
QUERY_SCHEMA_VERSION = "stage5b1j-fallback-queries-v1"
DISCOVERY_SCHEMA_VERSION = "stage5b1j-fallback-discovery-v1"
FEATURE_SCHEMA_VERSION = "stage5b1j-fallback-candidate-features-v1"
DECISION_SCHEMA_VERSION = "stage5b1j-representation-equivalence-decisions-v1"
POLICY_ID = "REPRESENTATION_EQUIVALENT_REDISCOVERY_V1"
REPRESENTATION_EQUIVALENT_MASTER_FALLBACK = (
    "REPRESENTATION_EQUIVALENT_MASTER_FALLBACK"
)

FALLBACK_LIVE_TO_STUDIO = "LIVE_TO_STUDIO"
FALLBACK_REMASTER_TO_MASTER = "REMASTER_TO_MASTER"
NO_FALLBACK = "NO_FALLBACK"

STATUS_DISCOVERY_COMPLETE = "STAGE5B1J_FALLBACK_DISCOVERY_COMPLETE"
STATUS_AWAITING_REVIEW = "STAGE5B1J_PART_A_AWAITING_HUMAN_REVIEW"
STATUS_PART_A_PASSED = "STAGE5B1J_PART_A_PASSED"
STATUS_PART_A_FAILED = "STAGE5B1J_PART_A_FAILED"
STATUS_NO_SELECTIONS = "STAGE5B1J_PART_A_VALID_NO_NEW_SELECTIONS"

_UNSAFE_BASE_FAMILIES = frozenset({
    "acoustic",
    "content_rating",
    "duration_version",
    "edit",
    "extended",
    "instrumental",
    "karaoke",
    "live",
    "mix",
    "named_version",
    "nightcore",
    "radio_edit",
    "reverb",
    "remaster",
    "remix",
    "rerecording",
    "slowed",
    "sped_up",
})
_QUERY_SPACE = re.compile(r"\s+")
_EXPLICIT_ALTERNATE_MASTER_PRESENTATION = re.compile(
    r"\b(?:dolby\s+atmos|spatial\s+audio|surround\s+(?:sound|mix)|"
    r"\d+(?:\.\d+)+\s+(?:surround\s+)?mix)\b",
    re.I,
)


@dataclass(frozen=True)
class Stage5B1JConfig:
    path: Path
    project_root: Path
    experiment_id: str
    policy_id: str
    stage5b1i_config: Path
    challenge_config: Path
    frozen_inputs: dict[str, dict[str, str]]
    provider: YtDlpProviderConfig
    sleep_between_tracks_seconds: float
    artifacts: dict[str, Path]
    sha256: str


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _bounded_number(value: Any, name: str, low: float, high: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not low <= float(value) <= high
    ):
        raise Stage5B1AValidationError(f"{name} must be between {low} and {high}")
    return float(value)


def load_stage5b1j_config(path: str | Path) -> Stage5B1JConfig:
    path = Path(path).resolve()
    value = _json_object(path)
    if value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.1J config schema")
    if value.get("policy_id") != POLICY_ID:
        raise Stage5B1AValidationError("unexpected Stage 5B.1J policy ID")
    project_root = path.parent.parent
    frozen = value.get("frozen_inputs")
    artifacts = value.get("artifacts")
    if not isinstance(frozen, dict) or not frozen:
        raise Stage5B1AValidationError("Stage 5B.1J frozen inputs are required")
    if not isinstance(artifacts, dict) or not artifacts:
        raise Stage5B1AValidationError("Stage 5B.1J artifacts are required")
    provider_raw = value.get("provider")
    if not isinstance(provider_raw, dict):
        raise Stage5B1AValidationError("Stage 5B.1J provider config is required")
    required_true = ("skip_download", "simulate", "ignore_user_config", "sequential_requests")
    if any(provider_raw.get(name) is not True for name in required_true):
        raise Stage5B1AValidationError("fallback discovery must remain sequential metadata-only")
    if (
        provider_raw.get("candidate_limit") != 5
        or provider_raw.get("search_prefix") != "ytsearch5:"
        or provider_raw.get("extract_flat") != "in_playlist"
        or provider_raw.get("cache_enabled") is not False
    ):
        raise Stage5B1AValidationError("fallback discovery must use frozen ytsearch5 semantics")
    attempts = provider_raw.get("max_attempts")
    timeout = provider_raw.get("socket_timeout_seconds")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 3:
        raise Stage5B1AValidationError("provider.max_attempts must be between 1 and 3")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 5 <= timeout <= 120:
        raise Stage5B1AValidationError("provider.socket_timeout_seconds is out of bounds")
    provider = YtDlpProviderConfig(
        candidate_limit=5,
        search_prefix="ytsearch5:",
        extract_flat="in_playlist",
        skip_download=True,
        simulate=True,
        ignore_user_config=True,
        cache_enabled=False,
        socket_timeout_seconds=timeout,
        max_attempts=attempts,
        retry_backoff_seconds=_bounded_number(
            provider_raw.get("retry_backoff_seconds"),
            "provider.retry_backoff_seconds",
            0,
            30,
        ),
        sleep_between_tracks_seconds=_bounded_number(
            provider_raw.get("sleep_between_tracks_seconds"),
            "provider.sleep_between_tracks_seconds",
            0,
            30,
        ),
    )
    return Stage5B1JConfig(
        path=path,
        project_root=project_root,
        experiment_id=str(value["experiment_id"]),
        policy_id=str(value["policy_id"]),
        stage5b1i_config=project_root / str(value["stage5b1i_config"]),
        challenge_config=project_root / str(value["challenge_config"]),
        frozen_inputs=dict(frozen),
        provider=provider,
        sleep_between_tracks_seconds=provider.sleep_between_tracks_seconds,
        artifacts={
            name: project_root / str(target) for name, target in artifacts.items()
        },
        sha256=file_sha256(path),
    )


def verify_frozen_inputs(config: Stage5B1JConfig) -> dict[str, dict[str, Any]]:
    verified = {}
    for name, value in config.frozen_inputs.items():
        path = (config.project_root / str(value["path"])).resolve()
        if not path.is_relative_to(config.project_root):
            raise Stage5B1AValidationError(f"frozen input escapes project: {name}")
        actual = file_sha256(path)
        expected = str(value["sha256"])
        if actual != expected:
            raise Stage5B1AValidationError(
                f"frozen Stage 5B.1J input changed: {name}: {actual} != {expected}"
            )
        verified[name] = {
            "path": str(path.relative_to(config.project_root)),
            "sha256": actual,
            "size_bytes": path.stat().st_size,
        }
    return verified


def verify_frozen_baseline(config: Stage5B1JConfig) -> dict[str, Any]:
    verify_frozen_inputs(config)
    stage5b1i = load_stage5b1i_config(config.stage5b1i_config)
    classifications, _features, decisions, _queue = evaluate_stage5b1i(stage5b1i)
    summary = decisions["summary"]
    if (
        summary["stage5b1i_auto_match_count"],
        summary["stage5b1i_match_uncertain_count"],
        summary["representation_equivalent_fallback_count"],
    ) != (42, 8, 0):
        raise Stage5B1AValidationError("frozen pre-1J Stage 5B.1I baseline changed")
    committed = _json_object(
        config.project_root
        / config.frozen_inputs["stage5b1i_decisions"]["path"]
    )
    if decisions != committed:
        raise Stage5B1AValidationError("Stage 5B.1I decision replay is not byte-equivalent")
    return {
        "exact_replay": True,
        "auto_match_count": 42,
        "match_uncertain_count": 8,
        "coverage": 0.84,
        "existing_selected_candidate_ids_unchanged": True,
        "live_target_count": classifications["summary"]["live_target_count"],
    }


def classify_fallback_target(track: SpotifyTrack) -> dict[str, Any]:
    """Classify only ordinary-live and true-remaster representation fallbacks."""

    parsed = parse_tier2_title(track.title, candidate=False)
    families = sorted({item.family for item in parsed.versions})
    live = classify_live_target(track.to_dict())
    if live["classification"] == ORDINARY_LIVE:
        fallback_family = FALLBACK_LIVE_TO_STUDIO
        match_mode = REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK
        eligible = True
        reason = "live is the target's only material version family"
    elif live["classification"] == ARRANGEMENT_CHANGING_LIVE:
        fallback_family = NO_FALLBACK
        match_mode = None
        eligible = False
        reason = live["reason"]
    elif set(families) == {"remaster"}:
        fallback_family = FALLBACK_REMASTER_TO_MASTER
        match_mode = REPRESENTATION_EQUIVALENT_MASTER_FALLBACK
        eligible = True
        reason = "remaster is the target's only material version family"
    else:
        fallback_family = NO_FALLBACK
        match_mode = None
        eligible = False
        reason = "target is not an ordinary-live or true-remaster fallback family"
    return {
        "stable_track_id": track.stable_track_id,
        "eligible": eligible,
        "fallback_family": fallback_family,
        "match_mode": match_mode,
        "base_title": parsed.core_title,
        "version_families": families,
        "version_descriptors": [item.to_dict() for item in parsed.versions],
        "reason": reason,
        "live_classification": live["classification"]
        if live["classification"] != NOT_LIVE_TARGET
        else None,
    }


def derive_base_target(track: SpotifyTrack, classification: dict[str, Any]) -> SpotifyTrack:
    if not classification["eligible"]:
        raise Stage5B1AValidationError("cannot derive base target for an ineligible family")
    is_live = classification["fallback_family"] == FALLBACK_LIVE_TO_STUDIO
    return SpotifyTrack(
        stable_track_id=track.stable_track_id,
        spotify_track_id=None,
        title=str(classification["base_title"]),
        artists=track.artists,
        album=None if is_live else track.album,
        duration_ms=None if is_live else track.duration_ms,
        release_year=None,
        isrc=None,
    )


def _quoted(value: str) -> str:
    return _QUERY_SPACE.sub(" ", value.replace('"', " ")).strip()


def build_fallback_query(track: SpotifyTrack, classification: dict[str, Any]) -> str:
    if not classification["eligible"]:
        raise Stage5B1AValidationError("fallback query requires an eligible target")
    artist = _quoted(track.artists[0])
    base_title = _quoted(str(classification["base_title"]))
    if not artist or not base_title:
        raise Stage5B1AValidationError("fallback query identity is incomplete")
    return f'"{artist}" "{base_title}" official'


def build_fallback_queries(config: Stage5B1JConfig) -> dict[str, Any]:
    baseline = verify_frozen_baseline(config)
    challenge = load_challenge_config(config.challenge_config)
    manifest = load_challenge_manifest(
        challenge.manifest_path, expected_sha256=challenge.manifest_sha256
    )
    committed = _json_object(
        config.project_root / config.frozen_inputs["stage5b1i_decisions"]["path"]
    )
    decision_by_id = {
        row["stable_track_id"]: row["stage5b1i_decision"]
        for row in committed["tracks"]
    }
    q0_discovery = _json_object(
        config.project_root / config.frozen_inputs["challenge_discovery"]["path"]
    )
    q0_candidates_by_id = {
        row["track"]["stable_track_id"]: list(row["candidate_video_ids"])
        for row in q0_discovery["tracks"]
    }
    rows = []
    for item in manifest.tracks:
        track = item.track
        baseline_decision = decision_by_id[track.stable_track_id]
        classification = classify_fallback_target(track)
        if baseline_decision["status"] != MATCH_UNCERTAIN or not classification["eligible"]:
            continue
        base = derive_base_target(track, classification)
        rows.append({
            "stable_track_id": track.stable_track_id,
            "spotify_target": track.to_dict(),
            "fallback_classification": classification,
            "base_representation_target": base.to_dict(),
            "query": build_fallback_query(track, classification),
            "query_strategy": "Q0_BASE_REPRESENTATION_V1",
            "original_q0_selected_video_id": baseline_decision.get("selected_video_id"),
            "original_q0_candidate_video_ids": q0_candidates_by_id[
                track.stable_track_id
            ],
        })
    return {
        "schema_version": QUERY_SCHEMA_VERSION,
        "experiment_id": config.experiment_id,
        "config_sha256": config.sha256,
        "challenge_manifest_sha256": manifest.sha256,
        "frozen_baseline": baseline,
        "track_count": len(rows),
        "query_count": len(rows),
        "tracks": rows,
        "scope_guards": {
            "only_unresolved_fallback_eligible_tracks": True,
            "query_style": '"{primary_artist}" "{base_title}" official',
            "candidate_limit": 5,
            "original_q0_pools_mutated": False,
        },
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_fallback_discovery(
    config: Stage5B1JConfig,
    queries: dict[str, Any],
    adapter: YtDlpDiscoveryAdapter,
    *,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    if queries != build_fallback_queries(config):
        raise Stage5B1AValidationError("frozen fallback query artifact changed")
    started = now()
    started_clock = time.monotonic()
    tracks = []
    versions: set[str] = set()
    for index, row in enumerate(queries["tracks"]):
        base = SpotifyTrack.from_dict(row["base_representation_target"])
        requested = now()
        try:
            outcome = adapter.discover_query(base, row["query"], limit=5).to_dict()
            versions.add(str(outcome["provider"]["version"]))
            result = {
                "requested_at_utc": requested,
                "completed_at_utc": now(),
                **outcome,
            }
        except YtDlpSearchError as exc:
            result = {
                "requested_at_utc": requested,
                "completed_at_utc": now(),
                "track": base.to_dict(),
                "query": row["query"],
                "candidates": [],
                "candidate_video_ids": [],
                "warnings": list(exc.warnings),
                "error": exc.to_dict(),
            }
        tracks.append({
            "stable_track_id": row["stable_track_id"],
            "spotify_target": row["spotify_target"],
            "fallback_classification": row["fallback_classification"],
            "base_representation_target": row["base_representation_target"],
            "original_q0_selected_video_id": row["original_q0_selected_video_id"],
            "original_q0_candidate_video_ids": row[
                "original_q0_candidate_video_ids"
            ],
            "fallback_query": row["query"],
            "outcome": result,
        })
        if index + 1 < len(queries["tracks"]):
            sleep(config.sleep_between_tracks_seconds)
    return {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "status": STATUS_DISCOVERY_COMPLETE,
        "queries_sha256": file_sha256(config.artifacts["queries"]),
        "started_at_utc": started,
        "completed_at_utc": now(),
        "elapsed_wall_seconds": time.monotonic() - started_clock,
        "provider": {
            "name": "yt_dlp",
            "versions": sorted(versions),
            "configuration": {
                "search_prefix": config.provider.search_prefix,
                "candidate_limit": config.provider.candidate_limit,
                "metadata_only_options": config.provider.metadata_only_options(),
                "sequential": True,
                "sleep_between_tracks_seconds": config.sleep_between_tracks_seconds,
            },
        },
        "summary": {
            "tracks_attempted": len(tracks),
            "search_failures": sum(row["outcome"].get("error") is not None for row in tracks),
            "tracks_with_candidates": sum(bool(row["outcome"].get("candidates")) for row in tracks),
            "zero_candidate_tracks": sum(not row["outcome"].get("candidates") for row in tracks),
            "total_deduplicated_candidates": sum(len(row["outcome"].get("candidates", [])) for row in tracks),
            "warning_count": sum(len(row["outcome"].get("warnings", [])) for row in tracks),
        },
        "tracks": tracks,
        "media_activity": {
            "audio_downloads": 0,
            "video_downloads": 0,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
    }


def _neutralize_live_duration(snapshot: dict[str, Any]) -> None:
    candidate_seconds = snapshot["duration"].get("candidate_seconds")
    snapshot["representation_equivalence_duration"] = {
        "original_live_target_seconds": snapshot["duration"].get("target_seconds"),
        "candidate_studio_seconds": candidate_seconds,
        "live_to_studio_duration_used_for_eligibility": False,
    }
    if candidate_seconds is None or not math.isfinite(float(candidate_seconds)):
        return
    snapshot["duration"] = {
        "target_seconds": float(candidate_seconds),
        "candidate_seconds": float(candidate_seconds),
        "absolute_duration_delta_seconds": 0.0,
        "relative_duration_delta": 0.0,
    }


def evaluate_candidate_pool(
    track: SpotifyTrack,
    candidates: list[dict[str, Any]],
    *,
    policy: Any,
    boundaries: Any,
    neutralize_live_duration: bool,
) -> dict[str, Any]:
    replay = evaluate_resolver_cascade(
        track, candidates, policy=policy, boundaries=boundaries
    )
    records = []
    for candidate in candidates:
        snapshot = candidate_snapshot(
            track,
            candidate,
            replay,
            policy=policy,
            boundaries=boundaries,
            human={},
            sol={},
        )
        if neutralize_live_duration:
            _neutralize_live_duration(snapshot)
        record = {
            "raw_candidate": copy.deepcopy(candidate),
            "snapshot": snapshot,
            "global_features": build_global_candidate_evidence(snapshot),
        }
        record["source_semantics"] = derive_source_semantics(record)
        records.append(record)
    track_row = {"track": track.to_dict(), "candidates": records}
    return {
        "target": track.to_dict(),
        "candidate_records": records,
        "global_decision": resolve_global_candidates(track_row),
    }


def _representation_candidates(pool: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for record in pool["candidate_records"]:
        global_features = record["global_features"]
        source = record["source_semantics"]
        candidate_families = set(global_features["modifications"]["candidate_families"])
        raw_candidate = record["raw_candidate"]
        release_text = " ".join(
            str(raw_candidate.get(field) or "")
            for field in ("title", "description")
        )
        alternate_master_matches = sorted({
            match.group(0) for match in _EXPLICIT_ALTERNATE_MASTER_PRESENTATION.finditer(
                release_text
            )
        })
        conditions = {
            "global_candidate_eligible": global_features["eligibility"]["eligible"],
            "recording_identity_compatible": source["recording_identity"]["state"]
            == RECORDING_COMPATIBLE,
            "canonicality_strong": source["canonicality"]["level"] == CANONICAL_STRONG,
            "no_explicit_conflicts": not global_features["hard_conflicts"],
            "no_exact_required_version_family": not (
                candidate_families & _UNSAFE_BASE_FAMILIES
            ),
            "no_explicit_alternate_master_presentation": not alternate_master_matches,
        }
        enriched = copy.deepcopy(record)
        enriched["representation_equivalence_eligibility"] = {
            "eligible": all(conditions.values()),
            "conditions": conditions,
            "failed_conditions": [name for name, value in conditions.items() if not value],
            "explicit_alternate_master_evidence": alternate_master_matches,
        }
        output.append(enriched)
    return output


def _resolve_representation_pool(pool: dict[str, Any]) -> dict[str, Any]:
    candidates = _representation_candidates(pool)
    eligible = [
        row for row in candidates
        if row["representation_equivalence_eligibility"]["eligible"]
    ]
    decision = resolve_global_candidates({"candidates": eligible})
    return {"candidate_records": candidates, "global_decision": decision}


def evaluate_fallback_discovery(
    config: Stage5B1JConfig, discovery: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline = verify_frozen_baseline(config)
    if discovery.get("schema_version") != DISCOVERY_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.1J discovery schema")
    if discovery.get("queries_sha256") != file_sha256(config.artifacts["queries"]):
        raise Stage5B1AValidationError("fallback discovery query identity changed")
    if discovery.get("media_activity") != {
        "audio_downloads": 0,
        "video_downloads": 0,
        "stage5a_calls": 0,
        "clap_calls": 0,
        "muq_calls": 0,
    }:
        raise Stage5B1AValidationError("fallback discovery media guard changed")
    queries = _json_object(config.artifacts["queries"])
    expected_ids = [row["stable_track_id"] for row in queries["tracks"]]
    observed_ids = [row.get("stable_track_id") for row in discovery.get("tracks", [])]
    if observed_ids != expected_ids:
        raise Stage5B1AValidationError("fallback discovery scope or order changed")

    challenge = load_challenge_config(config.challenge_config)
    boundaries, policies = load_frozen_policies(challenge)
    policy = policies["POLICY_BALANCED_V1"]
    features = []
    decisions = []
    for row in discovery["tracks"]:
        target = SpotifyTrack.from_dict(row["spotify_target"])
        base = SpotifyTrack.from_dict(row["base_representation_target"])
        classification = row["fallback_classification"]
        candidates = list(row["outcome"].get("candidates") or [])
        exact_pool = evaluate_candidate_pool(
            target,
            candidates,
            policy=policy,
            boundaries=boundaries,
            neutralize_live_duration=False,
        )
        exact_decision = exact_pool["global_decision"]
        if exact_decision["status"] == AUTO_MATCH:
            selected = exact_decision
            match_mode = EXACT_RECORDING
            selected_pool = "FALLBACK_DISCOVERY_EXACT_TARGET_REPLAY"
            representation_pool = None
        else:
            base_pool = evaluate_candidate_pool(
                base,
                candidates,
                policy=policy,
                boundaries=boundaries,
                neutralize_live_duration=(
                    classification["fallback_family"] == FALLBACK_LIVE_TO_STUDIO
                ),
            )
            representation_pool = _resolve_representation_pool(base_pool)
            selected = representation_pool["global_decision"]
            match_mode = classification["match_mode"] if selected["status"] == AUTO_MATCH else None
            selected_pool = "BASE_REPRESENTATION_TARGET" if match_mode else None
        selected_video_id = selected.get("selected_video_id")
        decision = {
            "stable_track_id": target.stable_track_id,
            "fallback_family": classification["fallback_family"],
            "exact_pool_decision": exact_decision,
            "representation_pool_decision": (
                representation_pool["global_decision"] if representation_pool else None
            ),
            "final_decision": {
                "status": selected["status"],
                "selected_video_id": selected_video_id,
                "selected_candidate_rank": selected.get("selected_candidate_rank"),
                "policy_rule_id": POLICY_ID,
                "match_mode": match_mode,
                "selected_pool": selected_pool,
                "selection_reason": (
                    "fallback discovery surfaced an exact requested recording"
                    if match_mode == EXACT_RECORDING
                    else "exact resolution remained uncertain; selected a canonical base recording as an explicit representation approximation"
                    if match_mode
                    else "neither exact nor canonical representation-equivalent resolution succeeded"
                ),
            },
        }
        features.append({
            "stable_track_id": target.stable_track_id,
            "spotify_target": target.to_dict(),
            "base_representation_target": base.to_dict(),
            "fallback_classification": classification,
            "fallback_query": row["fallback_query"],
            "original_q0_candidate_pool_reference": {
                "artifact": config.frozen_inputs["challenge_discovery"]["path"],
                "candidate_video_ids": row["original_q0_candidate_video_ids"],
                "mutated": False,
            },
            "fallback_candidates": candidates,
            "exact_target_evaluation": exact_pool,
            "base_target_evaluation": representation_pool,
        })
        decisions.append(decision)

    new_selections = [row for row in decisions if row["final_decision"]["status"] == AUTO_MATCH]
    mode_counts = Counter(row["final_decision"]["match_mode"] for row in new_selections)
    auto = 42 + len(new_selections)
    features_doc = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "discovery_sha256": file_sha256(config.artifacts["discovery"]),
        "track_count": len(features),
        "tracks": features,
    }
    decisions_doc = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "status": STATUS_AWAITING_REVIEW if new_selections else STATUS_NO_SELECTIONS,
        "policy_id": POLICY_ID,
        "production_activated": False,
        "frozen_baseline": baseline,
        "summary": {
            "fallback_tracks_attempted": len(decisions),
            "new_selection_count": len(new_selections),
            "new_exact_recording_count": mode_counts[EXACT_RECORDING],
            "new_studio_fallback_count": mode_counts[
                REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK
            ],
            "new_master_fallback_count": mode_counts[
                REPRESENTATION_EQUIVALENT_MASTER_FALLBACK
            ],
            "combined_auto_match_count": auto,
            "combined_match_uncertain_count": 50 - auto,
            "coverage_before": 0.84,
            "coverage_after": auto / 50,
            "absolute_percentage_point_gain": (auto - 42) / 50 * 100,
        },
        "new_selections": [
            {
                "stable_track_id": row["stable_track_id"],
                **row["final_decision"],
                "human_label": None,
            }
            for row in new_selections
        ],
        "tracks": decisions,
        "scope_guards": {
            "original_q0_pools_mutated": False,
            "historical_resolver_changed": False,
            "exact_precedes_fallback": True,
            "new_searches_outside_fallback_eligible_unresolved_tracks": 0,
            "audio_downloads": 0,
            "video_downloads": 0,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
            "sol_runs": 0,
        },
    }
    return features_doc, decisions_doc


def q0_query_config() -> QueryConfig:
    return QueryConfig(
        variant_id="primary_artist_base_title_official_v1",
        template='"{primary_artist}" "{normalized_title}" official',
        normalize_featured_artist_noise=True,
    )
