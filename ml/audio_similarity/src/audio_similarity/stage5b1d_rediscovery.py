"""Stage 5B.1D targeted metadata-only rediscovery diagnostic.

The module keeps first-pass discovery and every frozen resolver layer intact.
It derives the diagnostic scope from the committed 1C-C artifact, issues at
most three deterministic ytsearch5 queries for each candidate-set failure,
and evaluates the resulting candidates with the unchanged resolver cascade.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .stage5b1a2_ytdlp import (
    YtDlpDiscoveryAdapter,
    YtDlpPythonBackend,
    YtDlpSearchError,
)
from .stage5b1a_config import QueryConfig
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_challenge import (
    load_challenge_config,
    load_challenge_manifest,
    load_frozen_policies,
)
from .stage5b1b_features import extract_track_features
from .stage5b1b_resolver import AUTO_MATCH, MATCH_UNCERTAIN, resolve_track
from .stage5b1c_normalization import parse_tier2_title
from .stage5b1c_source_neutral import (
    extract_source_neutral_track,
    resolve_source_neutral_track,
)
from .stage5b1c_strong_metadata import (
    evaluate_strong_metadata_challenge,
    extract_strong_metadata_track,
    resolve_strong_metadata_track,
)
from .stage5b1c_tier2 import extract_tier2_track_features, resolve_tier2_track
from .stage5b1d_queries import (
    Stage5B1DConfig,
    build_targeted_queries,
    load_stage5b1d_config,
    verify_stage5b1d_frozen_inputs,
)


QUERY_SCHEMA_VERSION = "stage5b1d-targeted-queries-v1"
DISCOVERY_SCHEMA_VERSION = "stage5b1d-targeted-discovery-v1"
FEATURE_SCHEMA_VERSION = "stage5b1d-rediscovery-candidate-features-v1"
DECISION_SCHEMA_VERSION = "stage5b1d-rediscovery-decisions-v1"
AUDIT_SCHEMA_VERSION = "stage5b1d-rediscovery-human-audit-queue-v1"
MANIFEST_SCHEMA_VERSION = "stage5b1d-artifact-manifest-v1"
STATUS_AWAITING_REVIEW = "STAGE5B1D_REDISCOVERY_COMPLETE_AWAITING_HUMAN_REVIEW"

CANDIDATE_SET_FAILURE = "CANDIDATE_SET_FAILURE"
REDISCOVERY_RECOVERED = "REDISCOVERY_RECOVERED"
BETTER_CANDIDATE_FOUND_BUT_RESOLVER_UNCERTAIN = (
    "BETTER_CANDIDATE_FOUND_BUT_RESOLVER_UNCERTAIN"
)
STILL_CANDIDATE_SET_FAILURE = "STILL_CANDIDATE_SET_FAILURE"
METADATA_INSUFFICIENT_AFTER_REDISCOVERY = "METADATA_INSUFFICIENT_AFTER_REDISCOVERY"

REVIEW_LABELS = {"", "IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"}
REVIEW_COLUMNS = [
    "review_schema_version",
    "stable_track_id",
    "expected_title",
    "expected_artists",
    "expected_album",
    "expected_duration_seconds",
    "expected_release_year",
    "target_version_evidence",
    "selected_candidate_video_id",
    "selected_candidate_url",
    "selected_candidate_title",
    "selected_candidate_uploader",
    "selected_candidate_channel",
    "selected_candidate_duration_seconds",
    "selected_candidate_description",
    "targeted_query_variants",
    "candidate_review_label",
    "candidate_note",
    "track_note",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def verify_frozen_resolver_stack(config: Stage5B1DConfig) -> dict[str, Any]:
    """Replay and compare the exact frozen 42/8 resolver state."""

    challenge = load_challenge_config(config.challenge_config_path)
    root = config.project_root / "reports"
    replayed_features, replayed_decisions = evaluate_strong_metadata_challenge(
        config.challenge_config_path,
        tier2a_dir=root / "stage5b1c_a",
        source_neutral_dir=root / "stage5b1c_b",
        diagnostic_path=root / "stage5b1c_c_diagnostic/remaining_tail_diagnostic.json",
    )
    committed_features = _json_object(
        root / "stage5b1c_c_strong_metadata/strong_metadata_candidate_features.json"
    )
    committed_decisions = _json_object(
        root / "stage5b1c_c_strong_metadata/strong_metadata_decisions.json"
    )
    if replayed_features != committed_features:
        raise Stage5B1AValidationError("frozen Stage 5B.1C-C feature replay changed")
    comparable = dict(committed_decisions)
    comparable.pop("strong_metadata_features_sha256", None)
    if replayed_decisions != comparable:
        raise Stage5B1AValidationError("frozen Stage 5B.1C-C decision replay changed")
    summary = committed_decisions.get("summary")
    expected = {
        "combined_auto_match_count": 42,
        "combined_match_uncertain_count": 8,
        "combined_coverage": 0.84,
    }
    if not isinstance(summary, dict) or any(summary.get(key) != value for key, value in expected.items()):
        raise Stage5B1AValidationError("frozen resolver is not the required 42/8 baseline")
    selected = {
        row["stable_track_id"]: row["selected_video_id"]
        for row in committed_decisions.get("selected", [])
    }
    if selected != {"s5b1c_012": "kxZYxojih3E", "s5b1c_023": "1UESu4eyalA"}:
        raise Stage5B1AValidationError("frozen Stage 5B.1C-C selected IDs changed")
    return {
        "exact_replay": True,
        "balanced_v1_auto_match_count": 29,
        "stage5b1c_a_incremental_count": 6,
        "stage5b1c_b_incremental_count": 5,
        "stage5b1c_c_incremental_count": 2,
        **expected,
        "strong_metadata_selected_video_ids": selected,
        "challenge_config_sha256": challenge.sha256,
    }


def _candidate_set_failures(config: Stage5B1DConfig) -> tuple[dict[str, Any], ...]:
    diagnostic = _json_object(
        config.project_root
        / config.frozen_inputs["remaining_tail_diagnostic"]["path"]
    )
    rows = tuple(
        row for row in diagnostic.get("tracks", [])
        if row.get("recoverability") == CANDIDATE_SET_FAILURE
    )
    ids = tuple(row.get("stable_track_id") for row in rows)
    if len(rows) != 4 or len(set(ids)) != 4:
        raise Stage5B1AValidationError(
            "frozen diagnostic must contain exactly four candidate-set failures"
        )
    confirmed = set(diagnostic.get("confirmed_unresolved_track_ids") or [])
    if any(stable_id not in confirmed for stable_id in ids):
        raise Stage5B1AValidationError("candidate-set failure is not in frozen unresolved tail")
    return rows


def build_targeted_query_artifact(config: Stage5B1DConfig) -> dict[str, Any]:
    verify_stage5b1d_frozen_inputs(config)
    regression = verify_frozen_resolver_stack(config)
    challenge = load_challenge_config(config.challenge_config_path)
    manifest = load_challenge_manifest(
        challenge.manifest_path, expected_sha256=challenge.manifest_sha256
    )
    manifest_by_id = {item.track.stable_track_id: item for item in manifest.tracks}
    rows = []
    for diagnostic in _candidate_set_failures(config):
        stable_id = diagnostic["stable_track_id"]
        item = manifest_by_id.get(stable_id)
        if item is None:
            raise Stage5B1AValidationError(f"rediscovery target missing from manifest: {stable_id}")
        query = build_targeted_queries(item.track, config.variants)
        rows.append(
            {
                **query,
                "case_tags": list(item.case_tags),
                "case_rationale": item.case_rationale,
                "frozen_diagnostic": {
                    "recoverability": diagnostic["recoverability"],
                    "primary_blocker": diagnostic["primary_blocker"],
                    "explanation": diagnostic["explanation"],
                    "recommended_route": diagnostic["recommended_route"],
                },
            }
        )
    return {
        "schema_version": QUERY_SCHEMA_VERSION,
        "experiment_id": config.path.stem,
        "config_sha256": config.sha256,
        "manifest_sha256": manifest.sha256,
        "frozen_regression": regression,
        "scope_source": "frozen Stage 5B.1C-C diagnostic CANDIDATE_SET_FAILURE rows",
        "track_count": len(rows),
        "query_count": sum(len(row["queries"]) for row in rows),
        "max_query_variants_per_track": 3,
        "tracks": rows,
        "scope_guards": {
            "all_50_tracks_researched": False,
            "resolver_changed": False,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
    }


def write_targeted_queries(config: Stage5B1DConfig) -> dict[str, Any]:
    artifact = build_targeted_query_artifact(config)
    atomic_json(config.artifacts["queries"], artifact)
    return artifact


def verify_targeted_query_artifact(
    config: Stage5B1DConfig, artifact: dict[str, Any]
) -> None:
    if artifact != build_targeted_query_artifact(config):
        raise Stage5B1AValidationError("frozen targeted query artifact changed")


def run_targeted_discovery(
    config: Stage5B1DConfig,
    query_artifact: dict[str, Any],
    adapter: YtDlpDiscoveryAdapter,
    *,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    """Execute the frozen query list sequentially; one failure never aborts later work."""

    verify_targeted_query_artifact(config, query_artifact)
    started = now()
    started_clock = time.monotonic()
    tracks: list[dict[str, Any]] = []
    provider_versions: set[str] = set()
    for track_index, row in enumerate(query_artifact["tracks"]):
        track = SpotifyTrack.from_dict(row["target"])
        outcomes = []
        for query_index, query_row in enumerate(row["queries"]):
            requested_at = now()
            try:
                outcome = adapter.discover_query(track, query_row["query"], limit=5).to_dict()
                provider_versions.add(str(outcome["provider"]["version"]))
                outcomes.append(
                    {
                        "variant_id": query_row["variant_id"],
                        "query": query_row["query"],
                        "requested_at_utc": requested_at,
                        "completed_at_utc": now(),
                        **outcome,
                    }
                )
            except YtDlpSearchError as exc:
                outcomes.append(
                    {
                        "variant_id": query_row["variant_id"],
                        "query": query_row["query"],
                        "requested_at_utc": requested_at,
                        "completed_at_utc": now(),
                        "track": track.to_dict(),
                        "candidates": [],
                        "candidate_video_ids": [],
                        "warnings": list(exc.warnings),
                        "error": exc.to_dict(),
                    }
                )
            if query_index + 1 < len(row["queries"]):
                sleep(config.sleep_between_queries_seconds)
        tracks.append(
            {
                "track": track.to_dict(),
                "case_tags": row["case_tags"],
                "case_rationale": row["case_rationale"],
                "structured_identity": row["structured_identity"],
                "queries": outcomes,
            }
        )
        if track_index + 1 < len(query_artifact["tracks"]):
            sleep(config.sleep_between_tracks_seconds)
    all_outcomes = [outcome for track in tracks for outcome in track["queries"]]
    candidate_ids = {
        candidate["youtube_video_id"]
        for outcome in all_outcomes
        for candidate in outcome.get("candidates", [])
    }
    return {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "experiment_id": query_artifact["experiment_id"],
        "status": "DISCOVERY_COMPLETE",
        "queries_sha256": file_sha256(config.artifacts["queries"]),
        "started_at_utc": started,
        "completed_at_utc": now(),
        "elapsed_wall_seconds": time.monotonic() - started_clock,
        "provider": {
            "name": "yt_dlp",
            "versions": sorted(provider_versions),
            "configuration": {
                "search_prefix": config.provider.search_prefix,
                "candidate_limit": config.provider.candidate_limit,
                "metadata_only_options": config.provider.metadata_only_options(),
                "sequential": True,
                "sleep_between_queries_seconds": config.sleep_between_queries_seconds,
                "sleep_between_tracks_seconds": config.sleep_between_tracks_seconds,
            },
        },
        "summary": {
            "tracks_attempted": len(tracks),
            "queries_attempted": len(all_outcomes),
            "query_failures": sum(outcome.get("error") is not None for outcome in all_outcomes),
            "queries_with_candidates": sum(bool(outcome.get("candidates")) for outcome in all_outcomes),
            "unique_candidate_video_ids": len(candidate_ids),
            "warning_count": sum(len(outcome.get("warnings") or []) for outcome in all_outcomes),
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


def _deduplicate_pool(
    original: list[dict[str, Any]], outcomes: Iterable[dict[str, Any]]
) -> tuple[list[dict[str, Any]], set[str]]:
    pool: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    original_ids = {row["youtube_video_id"] for row in original}
    for origin, candidate in [
        *(("original_top5", item) for item in original),
        *((outcome["variant_id"], item) for outcome in outcomes for item in outcome.get("candidates", [])),
    ]:
        video_id = candidate.get("youtube_video_id")
        if not video_id:
            continue
        occurrence = {
            "origin": origin,
            "query": candidate.get("query"),
            "provider_rank": candidate.get("provider_rank"),
        }
        if video_id in by_id:
            by_id[video_id]["rediscovery_occurrences"].append(occurrence)
            continue
        normalized = copy.deepcopy(candidate)
        normalized["rank"] = len(pool) + 1
        normalized["rediscovery_occurrences"] = [occurrence]
        normalized["introduced_by_rediscovery"] = video_id not in original_ids
        by_id[video_id] = normalized
        pool.append(normalized)
    return pool, {row["youtube_video_id"] for row in pool if row["introduced_by_rediscovery"]}


def _feature_row(track: SpotifyTrack, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    features = extract_track_features(track, candidates)
    return {
        "track": track.to_dict(),
        "case_tags": [],
        "case_rationale": "Stage 5B.1D targeted rediscovery",
        "query": "multiple frozen targeted query variants",
        "error": None,
        "warnings": [],
        "candidates": [
            {"candidate": candidate, "features": feature}
            for candidate, feature in zip(candidates, features)
        ],
    }


def _rerank(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = copy.deepcopy(list(candidates))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def evaluate_resolver_cascade(
    track: SpotifyTrack,
    candidates: list[dict[str, Any]],
    *,
    policy: Any,
    boundaries: Any,
) -> dict[str, Any]:
    """Run the unchanged Balanced -> 1C-A -> 1C-B -> 1C-C cascade."""

    base = _feature_row(track, candidates)
    tier1 = resolve_track(base, policy, boundaries)
    tier2_features = extract_tier2_track_features(base)
    tier2 = resolve_tier2_track(tier2_features)
    source_features = extract_source_neutral_track(tier2_features)
    source = resolve_source_neutral_track(source_features)
    strong_features = extract_strong_metadata_track(source_features)
    strong = resolve_strong_metadata_track(strong_features)
    ordered = (
        ("POLICY_BALANCED_V1", tier1),
        ("STAGE5B1C_A", tier2),
        ("STAGE5B1C_B", source),
        ("STAGE5B1C_C", strong),
    )
    selected_stage, final = next(
        ((stage, decision) for stage, decision in ordered if decision["status"] == AUTO_MATCH),
        ("MATCH_UNCERTAIN", strong),
    )
    return {
        "selected_stage": selected_stage,
        "final_decision": final,
        "layer_decisions": {stage: decision for stage, decision in ordered},
        "feature_layers": {
            "stage5b1b": base,
            # The composed 1C-C rows already retain their nested 1C-A and 1C-B
            # evidence, so persisting those layers again would duplicate a
            # large amount of raw candidate metadata.
            "stage5b1c_c_composed": strong_features,
        },
    }


def evaluate_rediscovery(
    config: Stage5B1DConfig, discovery: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    regression = verify_frozen_resolver_stack(config)
    if discovery.get("schema_version") != DISCOVERY_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected targeted discovery schema")
    if discovery.get("queries_sha256") != file_sha256(config.artifacts["queries"]):
        raise Stage5B1AValidationError("targeted discovery query identity changed")
    expected_ids = tuple(
        row["stable_track_id"] for row in _candidate_set_failures(config)
    )
    observed_ids = tuple(
        row.get("track", {}).get("stable_track_id")
        for row in discovery.get("tracks", [])
        if isinstance(row, dict)
    )
    if observed_ids != expected_ids:
        raise Stage5B1AValidationError("targeted discovery scope or order changed")
    expected_media = {
        "audio_downloads": 0,
        "video_downloads": 0,
        "stage5a_calls": 0,
        "clap_calls": 0,
        "muq_calls": 0,
    }
    if discovery.get("media_activity") != expected_media:
        raise Stage5B1AValidationError("targeted rediscovery media guard changed")
    challenge = load_challenge_config(config.challenge_config_path)
    manifest = load_challenge_manifest(
        challenge.manifest_path, expected_sha256=challenge.manifest_sha256
    )
    boundaries, policies = load_frozen_policies(challenge)
    first_pass = _json_object(challenge.artifacts["discovery"])
    original_by_id = {
        row["track"]["stable_track_id"]: row for row in first_pass["tracks"]
    }
    diagnostic_by_id = {
        row["stable_track_id"]: row for row in _candidate_set_failures(config)
    }
    track_by_id = {row.track.stable_track_id: row for row in manifest.tracks}
    feature_tracks = []
    decision_tracks = []
    for rediscovery in discovery["tracks"]:
        stable_id = rediscovery["track"]["stable_track_id"]
        if stable_id not in diagnostic_by_id or stable_id not in track_by_id:
            raise Stage5B1AValidationError(f"rediscovery scope changed: {stable_id}")
        original = original_by_id[stable_id]["candidates"]
        combined, new_ids = _deduplicate_pool(original, rediscovery["queries"])
        new_only = _rerank(
            row for row in combined if row["youtube_video_id"] in new_ids
        )
        combined_eval = evaluate_resolver_cascade(
            track_by_id[stable_id].track,
            combined,
            policy=policies["POLICY_BALANCED_V1"],
            boundaries=boundaries,
        )
        new_eval = evaluate_resolver_cascade(
            track_by_id[stable_id].track,
            new_only,
            policy=policies["POLICY_BALANCED_V1"],
            boundaries=boundaries,
        ) if new_only else None
        final = combined_eval["final_decision"]
        selected_id = final.get("selected_video_id")
        recovered = final["status"] == AUTO_MATCH and selected_id in new_ids
        base_by_id = {
            item["candidate"]["youtube_video_id"]: item["features"]
            for item in combined_eval["feature_layers"]["stage5b1b"]["candidates"]
        }
        composed_candidates = combined_eval["feature_layers"][
            "stage5b1c_c_composed"
        ]["candidates"]
        identity_plausible_new = any(
            item["candidate"]["youtube_video_id"] in new_ids
            and (
                item["tier2a_features"]["title"]["structural_core_title_match"]
                or base_by_id[item["candidate"]["youtube_video_id"]]["identity"][
                    "core_title_token_overlap"
                ] == 1.0
            )
            and item["tier2a_features"]["performers"]["primary_performer_match"]
            and not item["tier2a_features"]["performers"]["explicit_cover_signal"]
            and not item["tier2a_features"]["performers"]["explicit_performer_conflict"]
            and item["tier2a_features"]["versions"]["absent_count"] == 0
            and item["tier2a_features"]["versions"]["conflict_count"] == 0
            for item in composed_candidates
        )
        if recovered:
            classification = REDISCOVERY_RECOVERED
        elif new_eval and new_eval["final_decision"]["status"] == AUTO_MATCH:
            classification = BETTER_CANDIDATE_FOUND_BUT_RESOLVER_UNCERTAIN
        elif identity_plausible_new:
            classification = METADATA_INSUFFICIENT_AFTER_REDISCOVERY
        else:
            classification = STILL_CANDIDATE_SET_FAILURE
        feature_tracks.append(
            {
                "stable_track_id": stable_id,
                "target": rediscovery["track"],
                "original_candidates": original,
                "new_candidate_ids": sorted(new_ids),
                "combined_candidate_count": len(combined),
                "new_only": new_eval["feature_layers"] if new_eval else None,
                "combined": combined_eval["feature_layers"],
            }
        )
        decision_tracks.append(
            {
                "stable_track_id": stable_id,
                "classification": classification,
                "original_failure_explanation": diagnostic_by_id[stable_id]["explanation"],
                "new_candidate_ids": sorted(new_ids),
                "combined_pool": combined,
                "new_only_decision": new_eval["final_decision"] if new_eval else None,
                "new_only_selected_stage": new_eval["selected_stage"] if new_eval else None,
                "combined_decision": final,
                "combined_selected_stage": combined_eval["selected_stage"],
            }
        )
    recovered = [
        row for row in decision_tracks if row["classification"] == REDISCOVERY_RECOVERED
    ]
    features = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "dataset_role": "TARGETED_REDISCOVERY_DIAGNOSTIC_ONLY",
        "discovery_sha256": file_sha256(config.artifacts["discovery"]),
        "track_count": len(feature_tracks),
        "tracks": feature_tracks,
    }
    decisions = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "production_fallback_activated": False,
        "resolver_layers_unchanged": True,
        "frozen_regression": regression,
        "summary": {
            "tracks_attempted": len(decision_tracks),
            "tracks_with_new_candidates": sum(bool(row["new_candidate_ids"]) for row in decision_tracks),
            "rediscovery_auto_match_count": len(recovered),
            "remaining_candidate_set_failures": sum(
                row["classification"] == STILL_CANDIDATE_SET_FAILURE for row in decision_tracks
            ),
            "materially_better_candidate_pools": sum(
                row["classification"]
                in {
                    REDISCOVERY_RECOVERED,
                    BETTER_CANDIDATE_FOUND_BUT_RESOLVER_UNCERTAIN,
                    METADATA_INSUFFICIENT_AFTER_REDISCOVERY,
                }
                for row in decision_tracks
            ),
            "combined_auto_match_count": 42 + len(recovered),
            "combined_match_uncertain_count": 8 - len(recovered),
            "combined_coverage": (42 + len(recovered)) / 50,
            "diagnostic_90_percent_target_reached": 42 + len(recovered) >= 45,
            "classification_counts": dict(
                sorted(Counter(row["classification"] for row in decision_tracks).items())
            ),
        },
        "new_selections": [
            {
                "stable_track_id": row["stable_track_id"],
                "selected_video_id": row["combined_decision"]["selected_video_id"],
                "selected_candidate_rank": row["combined_decision"].get("selected_candidate_rank"),
                "selected_stage": row["combined_selected_stage"],
                "human_label": None,
                "sol_label": None,
            }
            for row in recovered
        ],
        "tracks": decision_tracks,
        "scope_guards": {
            "resolver_changed": False,
            "new_searches_outside_candidate_set_failures": 0,
            "audio_downloads": 0,
            "video_downloads": 0,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
            "sol_runs": 0,
        },
    }
    return features, decisions


def _review_rows(
    query_artifact: dict[str, Any], decisions: dict[str, Any]
) -> list[dict[str, Any]]:
    query_by_id = {row["stable_track_id"]: row for row in query_artifact["tracks"]}
    decision_by_id = {row["stable_track_id"]: row for row in decisions["tracks"]}
    rows = []
    for selection in decisions["new_selections"]:
        stable_id = selection["stable_track_id"]
        source = query_by_id[stable_id]
        decision = decision_by_id[stable_id]
        candidate = next(
            row for row in decision["combined_pool"]
            if row["youtube_video_id"] == selection["selected_video_id"]
        )
        target = source["target"]
        rows.append(
            {
                "review_schema_version": AUDIT_SCHEMA_VERSION,
                "stable_track_id": stable_id,
                "expected_title": target["title"],
                "expected_artists": " | ".join(target["artists"]),
                "expected_album": target.get("album") or "",
                "expected_duration_seconds": target["duration_ms"] / 1000.0,
                "expected_release_year": target.get("release_year") or "",
                "target_version_evidence": json.dumps(
                    source["structured_identity"]["version_descriptors"], ensure_ascii=False
                ),
                "selected_candidate_video_id": candidate["youtube_video_id"],
                "selected_candidate_url": candidate.get("canonical_url") or candidate.get("url") or "",
                "selected_candidate_title": candidate.get("title") or "",
                "selected_candidate_uploader": candidate.get("uploader") or "",
                "selected_candidate_channel": candidate.get("channel") or "",
                "selected_candidate_duration_seconds": candidate.get("duration_seconds")
                if candidate.get("duration_seconds") is not None else "",
                "selected_candidate_description": candidate.get("description") or "",
                "targeted_query_variants": " | ".join(
                    row["query"] for row in source["queries"]
                ),
                "candidate_review_label": "",
                "candidate_note": "",
                "track_note": "",
            }
        )
    return rows


def _write_review_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            existing = list(csv.DictReader(handle))
        immutable = set(REVIEW_COLUMNS) - {"candidate_review_label", "candidate_note", "track_note"}
        if len(existing) != len(rows) or any(
            any(old[name] != str(new[name]) for name in immutable)
            for old, new in zip(existing, rows)
        ):
            raise Stage5B1AValidationError("refusing to overwrite rediscovery human review")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_evaluation_artifacts(
    config: Stage5B1DConfig,
    query_artifact: dict[str, Any],
    discovery: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    features, decisions = evaluate_rediscovery(config, discovery)
    atomic_json(config.artifacts["features"], features)
    decisions["rediscovery_features_sha256"] = file_sha256(config.artifacts["features"])
    atomic_json(config.artifacts["decisions"], decisions)
    rows = _review_rows(query_artifact, decisions)
    queue = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "status": STATUS_AWAITING_REVIEW if rows else "NO_NEW_SELECTIONS_TO_REVIEW",
        "decisions_sha256": file_sha256(config.artifacts["decisions"]),
        "track_count": len(rows),
        "candidate_count": len(rows),
        "labels": sorted(REVIEW_LABELS - {""}),
        "cases": [
            {
                "stable_track_id": row["stable_track_id"],
                "candidate_video_ids": [row["selected_candidate_video_id"]],
            }
            for row in rows
        ],
    }
    atomic_json(config.artifacts["audit_queue"], queue)
    _write_review_csv(config.artifacts["human_review"], rows)
    return features, decisions


def write_artifact_manifest(config: Stage5B1DConfig) -> dict[str, Any]:
    names = ("queries", "discovery", "features", "decisions", "audit_queue", "human_review", "report")
    artifacts = {
        name: {
            "path": str(config.artifacts[name].relative_to(config.project_root)),
            "sha256": file_sha256(config.artifacts[name]),
            "size_bytes": config.artifacts[name].stat().st_size,
        }
        for name in names
        if config.artifacts[name].exists()
    }
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "config_sha256": config.sha256,
        "frozen_input_sha256": verify_stage5b1d_frozen_inputs(config),
        "artifacts": artifacts,
        "media_activity": {
            "audio_downloads": 0,
            "video_downloads": 0,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
    }
    atomic_json(config.artifacts["manifest"], manifest)
    return manifest


def _query_config() -> QueryConfig:
    return QueryConfig(
        variant_id="primary_artist_normalized_title_official_v1",
        template='"{primary_artist}" "{normalized_title}" official',
        normalize_featured_artist_noise=True,
    )


def _default_config() -> Path:
    return Path(__file__).parents[2] / "configs/stage5b1d_targeted_rediscovery.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "discover", "evaluate", "manifest"))
    parser.add_argument("--config", type=Path, default=_default_config())
    args = parser.parse_args(argv)
    config = load_stage5b1d_config(args.config)
    if args.command == "prepare":
        artifact = write_targeted_queries(config)
        print(json.dumps({"track_count": artifact["track_count"], "query_count": artifact["query_count"]}))
        return 0
    queries = _json_object(config.artifacts["queries"])
    if args.command == "discover":
        adapter = YtDlpDiscoveryAdapter(
            config.provider,
            _query_config(),
            YtDlpPythonBackend(config.provider),
        )
        discovery = run_targeted_discovery(config, queries, adapter)
        atomic_json(config.artifacts["discovery"], discovery)
        print(json.dumps(discovery["summary"], sort_keys=True))
        return 0
    discovery = _json_object(config.artifacts["discovery"])
    if args.command == "evaluate":
        _, decisions = write_evaluation_artifacts(config, queries, discovery)
        print(json.dumps(decisions["summary"], sort_keys=True))
        return 0
    manifest = write_artifact_manifest(config)
    print(json.dumps({"artifact_count": len(manifest["artifacts"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
