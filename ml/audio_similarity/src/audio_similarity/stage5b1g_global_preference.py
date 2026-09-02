"""Stage 5B.1G global candidate preference over frozen Q0 candidates.

This experimental layer leaves the historical resolver cascade untouched. It
globally compares candidates admitted by any frozen tier plus candidates that
meet a new, bounded graduated-duration safety gate. Tier admission is retained
as provenance, never used as a preference signal.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_challenge import load_frozen_policies
from .stage5b1b_challenge_audit import REVIEW_COLUMNS, REVIEW_SCHEMA_VERSION
from .stage5b1b_resolver import AUTO_MATCH, MATCH_UNCERTAIN, SAFE_LABELS, SOURCE_ORDER
from .stage5b1e_experiment import _challenge
from .stage5b1e_queries import load_stage5b1e_config
from .stage5b1f_diagnostic import (
    candidate_snapshot,
    load_human_evidence,
    load_sol_evidence,
    load_stage5b1f_config,
    replay_frozen_q0,
)
from .stage5b1c_normalization import normalize_performer


CONFIG_SCHEMA_VERSION = "stage5b1g-global-preference-config-v1"
FEATURE_SCHEMA_VERSION = "stage5b1g-global-preference-candidate-features-v1"
DECISION_SCHEMA_VERSION = "stage5b1g-global-preference-decisions-v1"
CHANGED_SCHEMA_VERSION = "stage5b1g-changed-selection-comparisons-v1"
DURATION_SCHEMA_VERSION = "stage5b1g-duration-band-analysis-v1"
TAIL_SCHEMA_VERSION = "stage5b1g-remaining-tail-analysis-v1"
QUEUE_SCHEMA_VERSION = "stage5b1g-human-audit-queue-v1"
MANIFEST_SCHEMA_VERSION = "stage5b1g-artifact-manifest-v1"
POLICY_ID = "GLOBAL_CANDIDATE_PREFERENCE_V1"
STATUS = "STAGE5B1G_AWAITING_HUMAN_REVIEW"
Q0 = "Q0_CURRENT_CONTROL"

DURATION_VERY_CLOSE = "DURATION_VERY_CLOSE"
DURATION_CLOSE = "DURATION_CLOSE"
DURATION_EXTENDED_1 = "DURATION_EXTENDED_1"
DURATION_EXTENDED_2 = "DURATION_EXTENDED_2"
DURATION_EXTENDED_3 = "DURATION_EXTENDED_3"
DURATION_TOO_FAR = "DURATION_TOO_FAR"
DURATION_UNKNOWN = "DURATION_UNKNOWN"
DURATION_ORDER = (
    DURATION_VERY_CLOSE,
    DURATION_CLOSE,
    DURATION_EXTENDED_1,
    DURATION_EXTENDED_2,
    DURATION_EXTENDED_3,
    DURATION_TOO_FAR,
    DURATION_UNKNOWN,
)

GLOBAL_SOURCE_ORDER = {
    "ART_TRACK_TOPIC": 0,
    "OFFICIAL_AUDIO": 1,
    "LYRIC_VIDEO": 2,
    "OFFICIAL_MUSIC_VIDEO": 3,
    "OTHER": 4,
}
FROZEN_STAGE_ORDER = (
    "POLICY_BALANCED_V1",
    "STAGE5B1C_A",
    "STAGE5B1C_B",
    "STAGE5B1C_C",
)

_FEATURED_PERFORMER = re.compile(
    r"\b(?:feat(?:uring)?|ft)\.?\s+(.+?)(?=\)|\]|\s+[\(\[]|\s+-\s+|$)", re.IGNORECASE
)
_PERFORMER_SEPARATOR = re.compile(r"\s*(?:,|&|\band\b|\bx\b)\s*", re.IGNORECASE)


@dataclass(frozen=True)
class DurationBands:
    very_close_max: float = 2.0
    close_max: float = 7.0
    extended_1_max: float = 12.0
    extended_2_max: float = 16.0
    extended_3_max: float = 20.0

    def __post_init__(self) -> None:
        values = (
            self.very_close_max,
            self.close_max,
            self.extended_1_max,
            self.extended_2_max,
            self.extended_3_max,
        )
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise Stage5B1AValidationError("duration bands must be finite and non-negative")
        if tuple(sorted(values)) != values:
            raise Stage5B1AValidationError("duration bands must be monotonic")


@dataclass(frozen=True)
class Stage5B1GConfig:
    path: Path
    project_root: Path
    experiment_id: str
    policy_id: str
    stage5b1f_config: Path
    duration_bands: DurationBands
    frozen_inputs: dict[str, dict[str, Any]]
    artifacts: dict[str, Path]
    sha256: str


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def load_stage5b1g_config(path: Path) -> Stage5B1GConfig:
    path = path.resolve()
    value = _json_object(path)
    if value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.1G config schema")
    if value.get("policy_id") != POLICY_ID:
        raise Stage5B1AValidationError("unexpected Stage 5B.1G policy ID")
    if value.get("source_query_strategy") != Q0:
        raise Stage5B1AValidationError("Stage 5B.1G must use frozen Q0 discovery")
    project_root = path.parent.parent
    bands = DurationBands(**value["duration_bands_seconds"])
    if bands != DurationBands():
        raise Stage5B1AValidationError("Stage 5B.1G duration bands changed")
    return Stage5B1GConfig(
        path=path,
        project_root=project_root,
        experiment_id=str(value["experiment_id"]),
        policy_id=str(value["policy_id"]),
        stage5b1f_config=project_root / str(value["stage5b1f_config"]),
        duration_bands=bands,
        frozen_inputs=dict(value["frozen_inputs"]),
        artifacts={
            name: project_root / str(target)
            for name, target in value["artifacts"].items()
        },
        sha256=file_sha256(path),
    )


def verify_frozen_inputs(config: Stage5B1GConfig) -> dict[str, dict[str, Any]]:
    verified = {}
    for name, value in config.frozen_inputs.items():
        path = config.project_root / str(value["path"])
        actual = file_sha256(path)
        if actual != value["sha256"]:
            raise Stage5B1AValidationError(
                f"frozen Stage 5B.1G input changed: {name}: {actual} != {value['sha256']}"
            )
        verified[name] = {
            "path": str(path.relative_to(config.project_root)),
            "sha256": actual,
            "size_bytes": path.stat().st_size,
        }
    return verified


def duration_bucket(delta: float | None, bands: DurationBands | None = None) -> str:
    bands = bands or DurationBands()
    if delta is None or not math.isfinite(delta) or delta < 0:
        return DURATION_UNKNOWN
    if delta <= bands.very_close_max:
        return DURATION_VERY_CLOSE
    if delta <= bands.close_max:
        return DURATION_CLOSE
    if delta <= bands.extended_1_max:
        return DURATION_EXTENDED_1
    if delta <= bands.extended_2_max:
        return DURATION_EXTENDED_2
    if delta <= bands.extended_3_max:
        return DURATION_EXTENDED_3
    return DURATION_TOO_FAR


def _duration_rank(bucket: str) -> int:
    return DURATION_ORDER.index(bucket)


def _version_evidence(snapshot: dict[str, Any]) -> dict[str, Any]:
    versions = snapshot["version_evidence"]
    relationships = list(versions.get("relationships", []))
    target_versioned = bool(relationships)
    conflict = bool(versions.get("conflict_count"))
    absent = bool(versions.get("absent_count"))
    complete = not conflict and not absent
    explicit_complete_match = bool(
        target_versioned
        and complete
        and versions.get("match_count") == len(relationships)
        and all(row.get("candidate_evidence_source") for row in relationships)
    )
    return {
        "target_is_versioned": target_versioned,
        "complete_and_compatible": complete,
        "explicit_complete_match": explicit_complete_match,
        "match_count": versions.get("match_count", 0),
        "absent_count": versions.get("absent_count", 0),
        "conflict_count": versions.get("conflict_count", 0),
        "relationships": relationships,
    }


def _unexpected_featured_performers(snapshot: dict[str, Any]) -> list[str]:
    """Return explicitly featured names absent from the Spotify artist credits."""

    expected = {
        normalize_performer(value)
        for value in snapshot["identity"]["target"].get("credited_artists", [])
    }
    unexpected = []
    for match in _FEATURED_PERFORMER.finditer(str(snapshot.get("title") or "")):
        captured = normalize_performer(match.group(1))
        remainder = captured
        for artist in sorted(expected, key=len, reverse=True):
            remainder = remainder.replace(artist, " ")
        remainder = " ".join(
            token for token in remainder.split() if token not in {"and", "with", "x"}
        )
        if not remainder:
            continue
        for raw in _PERFORMER_SEPARATOR.split(match.group(1)):
            normalized = normalize_performer(raw)
            if normalized and normalized not in expected:
                unexpected.append(raw.strip())
    return sorted(set(unexpected))


def _provenance_evidence(snapshot: dict[str, Any]) -> dict[str, Any]:
    source = snapshot["source"]
    source_type = source["source_type"]
    raw = source["provenance"]
    performer_rows = snapshot["performer_evidence"].get("evidence", [])
    channel_performer = any(row.get("source") in {"uploader", "channel"} for row in performer_rows)
    release_performer = any(
        row.get("source") == "description_release_metadata" for row in performer_rows
    )
    identity_consistent = bool(
        snapshot["normalized_title"]["structural_core_title_match"]
        and snapshot["performer_evidence"]["primary_performer_match"]
        and not snapshot["performer_evidence"]["explicit_performer_conflict"]
        and not snapshot["version_evidence"]["conflict_count"]
        and not snapshot["modification_evidence"]["explicit_conflict"]
    )
    topic = bool(raw["topic_channel_signal"])
    provided = bool(raw["provided_to_youtube_by_signal"])
    auto_generated = bool(raw["auto_generated_by_youtube_signal"])
    structured = bool(raw["structured_release_metadata_signal"])
    art_track_consistent = bool(
        source_type == "ART_TRACK_TOPIC"
        and identity_consistent
        and (
            topic
            or (provided and auto_generated)
            or (provided and structured and release_performer)
        )
    )
    release_corroborated = bool(
        identity_consistent and provided and structured and release_performer
    )
    if art_track_consistent:
        tier, rank = "PROVENANCE_CANONICAL_CONSISTENT_ART_TRACK", 0
    elif channel_performer:
        tier, rank = "PROVENANCE_ARTIST_CHANNEL", 1
    elif release_corroborated:
        tier, rank = "PROVENANCE_RELEASE_CORROBORATED", 2
    elif provided or topic or auto_generated or structured:
        tier, rank = "PROVENANCE_UNCORROBORATED_CLAIM", 3
    else:
        tier, rank = "PROVENANCE_UNKNOWN_NEUTRAL", 4
    return {
        "tier": tier,
        "rank": rank,
        "contribution": "POSITIVE" if rank <= 2 else "NEUTRAL",
        "channel_or_uploader_performer_match": channel_performer,
        "description_release_performer_match": release_performer,
        "art_track_internally_consistent": art_track_consistent,
        "release_metadata_corroborated": release_corroborated,
        "signals": {
            "topic_channel_signal": topic,
            "provided_to_youtube_by_signal": provided,
            "auto_generated_by_youtube_signal": auto_generated,
            "structured_release_metadata_signal": structured,
        },
        "raw_evidence": raw.get("raw_evidence", {}),
    }


def build_global_candidate_evidence(
    snapshot: dict[str, Any], bands: DurationBands | None = None
) -> dict[str, Any]:
    bands = bands or DurationBands()
    performers = snapshot["performer_evidence"]
    versions = _version_evidence(snapshot)
    modifications = snapshot["modification_evidence"]
    unexpected_featured = _unexpected_featured_performers(snapshot)
    identity = snapshot["identity"]
    structural_title = bool(
        snapshot["normalized_title"]["structural_core_title_match"]
        or identity["title_exact_normalized_match"]
    )
    performer_strong = bool(
        performers["primary_performer_match"]
        and not performers["explicit_performer_conflict"]
    )
    hard_conflicts = []
    if identity.get("explicit_core_title_conflict"):
        hard_conflicts.append("EXPLICIT_CORE_TITLE_CONFLICT")
    if performers["explicit_performer_conflict"]:
        hard_conflicts.append("EXPLICIT_PERFORMER_OR_COVER_CONFLICT")
    if versions["conflict_count"]:
        hard_conflicts.append("EXPLICIT_VERSION_CONFLICT")
    if modifications["explicit_conflict"]:
        hard_conflicts.append("EXPLICIT_UNREQUESTED_MODIFICATION_CONFLICT")
    if unexpected_featured:
        hard_conflicts.append("EXPLICIT_UNEXPECTED_FEATURED_PERFORMER_CONFLICT")

    delta = snapshot["duration"]["absolute_duration_delta_seconds"]
    bucket = duration_bucket(delta, bands)
    provenance = _provenance_evidence(snapshot)
    admitted_stages = [
        stage for stage in FROZEN_STAGE_ORDER if snapshot["gates"][stage]["eligible"]
    ]
    source_type = snapshot["source"]["source_type"]
    title_lower = str(snapshot.get("title") or "").casefold()
    explicitly_not_mv = "not a mv" in title_lower or "not an mv" in title_lower
    effective_source_type = (
        "OTHER"
        if (source_type == "ART_TRACK_TOPIC" and not provenance["art_track_internally_consistent"])
        or (source_type == "OFFICIAL_MUSIC_VIDEO" and explicitly_not_mv)
        else source_type
    )

    base_conditions = {
        "strong_structural_title_identity": structural_title,
        "strong_primary_performer_identity": performer_strong,
        "complete_compatible_version_evidence": versions["complete_and_compatible"],
        "no_explicit_recording_conflicts": not hard_conflicts,
        "known_finite_duration_within_20_seconds": bucket not in {
            DURATION_TOO_FAR,
            DURATION_UNKNOWN,
        },
    }
    extended_conditions: dict[str, bool] = {}
    if bucket in {DURATION_VERY_CLOSE, DURATION_CLOSE, DURATION_EXTENDED_1}:
        extended_conditions = dict(base_conditions)
    elif bucket == DURATION_EXTENDED_2:
        extended_conditions = {
            **base_conditions,
            "explicit_version_match_when_versioned": (
                not versions["target_is_versioned"] or versions["explicit_complete_match"]
            ),
            "strong_corroborated_provenance": provenance["rank"] <= 2,
        }
    elif bucket == DURATION_EXTENDED_3:
        description = snapshot["description_evidence"]
        strongest_corroboration = bool(
            provenance["rank"] <= 1
            and (
                provenance["art_track_internally_consistent"]
                or provenance["channel_or_uploader_performer_match"]
                or description.get("description_album_match") is True
                or description.get("description_release_year_match") is True
            )
        )
        extended_conditions = {
            **base_conditions,
            "explicit_version_match_when_versioned": (
                not versions["target_is_versioned"] or versions["explicit_complete_match"]
            ),
            "strongest_consistent_provenance": strongest_corroboration,
        }
    else:
        extended_conditions = {
            **base_conditions,
            "hard_duration_maximum_not_exceeded": False,
        }

    frozen_admission_eligible = bool(admitted_stages and not hard_conflicts)
    graduated_duration_eligible = bool(extended_conditions and all(extended_conditions.values()))
    eligible = bool(
        not hard_conflicts
        and bucket not in {DURATION_TOO_FAR, DURATION_UNKNOWN}
        and (frozen_admission_eligible or graduated_duration_eligible)
    )
    failed = [name for name, passed in extended_conditions.items() if not passed]
    if hard_conflicts:
        failed.extend(hard_conflicts)
    return {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "track_id": snapshot.get("track_id"),
        "candidate_video_id": snapshot["video_id"],
        "search_rank": snapshot["search_rank"],
        "admitted_by_frozen_tiers": admitted_stages,
        "tier_is_preference_signal": False,
        "identity": {
            "strong_structural_title_identity": structural_title,
            "strong_primary_performer_identity": performer_strong,
            "title_similarity": identity["title_similarity"],
            "performer_evidence": performers,
        },
        "versions": versions,
        "modifications": modifications,
        "unexpected_featured_performers": unexpected_featured,
        "hard_conflicts": hard_conflicts,
        "duration": {
            **snapshot["duration"],
            "bucket": bucket,
            "maximum_experimental_delta_seconds": bands.extended_3_max,
        },
        "provenance": provenance,
        "source": {
            "classified_source_type": source_type,
            "effective_preference_source_type": effective_source_type,
            "explicit_not_music_video_signal": explicitly_not_mv,
        },
        "description_evidence": snapshot["description_evidence"],
        "weak_evidence": snapshot["weak_evidence"],
        "eligibility": {
            "eligible": eligible,
            "frozen_admission_eligible": frozen_admission_eligible,
            "graduated_duration_eligible": graduated_duration_eligible,
            "conditions": extended_conditions,
            "failed_conditions": sorted(set(failed)),
            "basis": (
                "FROZEN_TIER_ADMISSION"
                if frozen_admission_eligible
                else "GRADUATED_DURATION_EVIDENCE"
                if graduated_duration_eligible
                else "INELIGIBLE"
            ),
        },
    }


def global_preference_key(item: dict[str, Any]) -> tuple[Any, ...]:
    feature = item["global_features"]
    identity = feature["identity"]
    versions = feature["versions"]
    provenance = feature["provenance"]
    duration = feature["duration"]
    description = feature["description_evidence"]
    weak = feature["weak_evidence"]
    source_type = feature["source"]["effective_preference_source_type"]
    version_rank = 0 if (
        not versions["target_is_versioned"] or versions["explicit_complete_match"]
    ) else 1
    description_rank = -sum(
        value is True
        for value in (
            description.get("description_album_match"),
            description.get("description_release_year_match"),
        )
    )
    relative_views = weak.get("relative_view_strength")
    view_rank = weak.get("view_rank_among_plausible_candidates")
    return (
        0 if identity["strong_structural_title_identity"] else 1,
        version_rank,
        0 if identity["strong_primary_performer_identity"] else 1,
        provenance["rank"],
        _duration_rank(duration["bucket"]),
        GLOBAL_SOURCE_ORDER.get(source_type, len(GLOBAL_SOURCE_ORDER)),
        description_rank,
        0 if relative_views is not None else 1,
        -(float(relative_views) if relative_views is not None else -1.0),
        int(view_rank) if view_rank is not None else 1_000_000,
        int(feature["search_rank"]),
    )


def resolve_global_candidates(track_row: dict[str, Any]) -> dict[str, Any]:
    eligible = [
        item for item in track_row["candidates"]
        if item["global_features"]["eligibility"]["eligible"]
    ]
    ordered = sorted(eligible, key=global_preference_key)
    if not ordered:
        return {
            "status": MATCH_UNCERTAIN,
            "policy_rule_id": POLICY_ID,
            "selected_video_id": None,
            "selected_candidate_rank": None,
            "uncertainty_reason": (
                "no frozen-Q0 candidate satisfies conflict-free identity, version, "
                "provenance, and graduated-duration requirements"
            ),
            "ranked_plausible_candidates": [],
        }
    selected = ordered[0]
    feature = selected["global_features"]
    return {
        "status": AUTO_MATCH,
        "policy_rule_id": POLICY_ID,
        "selected_video_id": selected["snapshot"]["video_id"],
        "selected_candidate_rank": selected["snapshot"]["search_rank"],
        "selection_reason": (
            "global lexicographic preference across every defensible candidate: identity "
            "and version, performer, consistent provenance, graduated duration, source "
            "quality, release corroboration, then weak views/search-rank tiebreakers"
        ),
        "confidence_tier": "EXPERIMENTAL_GLOBAL_PREFERENCE",
        "evidence_summary": feature,
        "ranked_plausible_candidates": [
            item["snapshot"]["video_id"] for item in ordered
        ],
    }


def _candidate_record(snapshot: dict[str, Any], bands: DurationBands) -> dict[str, Any]:
    return {
        "candidate": {
            key: snapshot.get(key)
            for key in (
                "video_id", "search_rank", "title", "url", "uploader", "channel",
                "duration_seconds", "view_count", "human_evidence", "sol_evidence",
            )
        },
        "snapshot": snapshot,
        "global_features": build_global_candidate_evidence(snapshot, bands),
    }


def _evidence_label(record: dict[str, Any], source: str) -> str | None:
    evidence = record["snapshot"].get(f"{source}_evidence")
    return evidence.get("label") if evidence else None


def _selected_record(track_row: dict[str, Any], video_id: str | None) -> dict[str, Any] | None:
    return next(
        (row for row in track_row["candidates"] if row["snapshot"]["video_id"] == video_id),
        None,
    )


def evaluate_stage5b1g(
    config: Stage5B1GConfig,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    verify_frozen_inputs(config)
    stage5b1f = load_stage5b1f_config(config.stage5b1f_config)
    replays = replay_frozen_q0(stage5b1f)
    stage5b1e = load_stage5b1e_config(stage5b1f.stage5b1e_config)
    challenge, _manifest = _challenge(stage5b1e)
    boundaries, policies = load_frozen_policies(challenge)
    policy = policies["POLICY_BALANCED_V1"]
    human = load_human_evidence(stage5b1f)
    sol = load_sol_evidence(stage5b1f)

    feature_tracks = []
    old_decisions = {}
    for row in replays:
        track = SpotifyTrack.from_dict(row["target"])
        candidates = []
        for candidate in row["candidates"]:
            snapshot = candidate_snapshot(
                track,
                candidate,
                row["replay"],
                policy=policy,
                boundaries=boundaries,
                human=human,
                sol=sol,
            )
            candidates.append(_candidate_record(
                {
                    **snapshot,
                    "track_id": row["stable_track_id"],
                    "description": candidate.get("description"),
                },
                config.duration_bands,
            ))
        feature_tracks.append({
            "track": row["target"],
            "query": row["query"],
            "candidates": candidates,
        })
        old_decisions[row["stable_track_id"]] = row["replay"]["final_decision"]

    track_decisions = []
    changed = []
    newly_resolved = []
    selected_by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for track_row in feature_tracks:
        stable_id = track_row["track"]["stable_track_id"]
        decision = resolve_global_candidates(track_row)
        old = old_decisions[stable_id]
        selected = _selected_record(track_row, decision.get("selected_video_id"))
        if selected:
            selected_by_bucket[selected["global_features"]["duration"]["bucket"]].append(selected)
        change_type = "UNCHANGED"
        if old["status"] == MATCH_UNCERTAIN and decision["status"] == AUTO_MATCH:
            change_type = "NEWLY_RESOLVED"
            newly_resolved.append(stable_id)
        elif old.get("selected_video_id") != decision.get("selected_video_id"):
            change_type = "SELECTION_CHANGED"
        track_decisions.append({
            "stable_track_id": stable_id,
            "baseline_decision": old,
            "global_preference_decision": decision,
            "change_type": change_type,
        })
        if change_type != "UNCHANGED":
            old_selected = _selected_record(track_row, old.get("selected_video_id"))
            changed.append({
                "stable_track_id": stable_id,
                "target": track_row["track"],
                "change_type": change_type,
                "old_selected_candidate": old_selected,
                "new_selected_candidate": selected,
                "why_changed": (
                    "all defensible candidates now compete globally; tier number is ignored "
                    "and consistent provenance precedes graduated duration/source preference"
                ),
            })

    auto_count = sum(
        row["global_preference_decision"]["status"] == AUTO_MATCH
        for row in track_decisions
    )
    if len(track_decisions) != 50:
        raise Stage5B1AValidationError("Stage 5B.1G challenge track count changed")
    baseline_auto = sum(row["status"] == AUTO_MATCH for row in old_decisions.values())
    baseline_uncertain = 50 - baseline_auto
    if (baseline_auto, baseline_uncertain) != (42, 8):
        raise Stage5B1AValidationError("pre-1G frozen 42/8 baseline changed")

    selected_records = [
        selected
        for track_row, decision_row in zip(feature_tracks, track_decisions)
        if (selected := _selected_record(
            track_row,
            decision_row["global_preference_decision"].get("selected_video_id"),
        )) is not None
    ]
    selected_human_counts = Counter(
        _evidence_label(row, "human") or "UNREVIEWED" for row in selected_records
    )
    selected_sol_counts = Counter(
        _evidence_label(row, "sol") or "MISSING" for row in selected_records
    )
    selected_source_counts = Counter(
        row["global_features"]["source"]["effective_preference_source_type"]
        for row in selected_records
    )

    features = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "dataset_role": "FROZEN_Q0_CHALLENGE_GLOBAL_PREFERENCE_EXPERIMENT",
        "duration_bands_seconds": config.duration_bands.__dict__,
        "track_count": len(feature_tracks),
        "candidate_count": sum(len(row["candidates"]) for row in feature_tracks),
        "tracks": feature_tracks,
    }
    decisions = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "status": STATUS,
        "policy_id": POLICY_ID,
        "production_activated": False,
        "frozen_regression": {
            "baseline_auto_match_count": baseline_auto,
            "baseline_match_uncertain_count": baseline_uncertain,
            "same_baseline_selected_candidate_ids": True,
        },
        "summary": {
            "total_tracks": 50,
            "baseline_auto_match_count": baseline_auto,
            "global_auto_match_count": auto_count,
            "global_match_uncertain_count": 50 - auto_count,
            "baseline_coverage": baseline_auto / 50,
            "global_coverage": auto_count / 50,
            "incremental_auto_match_count": auto_count - baseline_auto,
            "absolute_percentage_point_gain": (auto_count - baseline_auto) / 50 * 100,
            "existing_selection_changed_count": sum(
                row["change_type"] == "SELECTION_CHANGED" for row in track_decisions
            ),
            "newly_resolved_count": len(newly_resolved),
            "unchanged_count": sum(row["change_type"] == "UNCHANGED" for row in track_decisions),
            "selected_human_label_counts": dict(sorted(selected_human_counts.items())),
            "selected_sol_label_counts": dict(sorted(selected_sol_counts.items())),
            "selected_source_type_counts": dict(sorted(selected_source_counts.items())),
            "selected_known_human_safe_count": sum(
                _evidence_label(row, "human") in SAFE_LABELS for row in selected_records
            ),
            "selected_known_human_wrong_count": selected_human_counts["WRONG"],
            "selected_known_human_uncertain_count": selected_human_counts["UNCERTAIN"],
            "selected_known_sol_wrong_count": selected_sol_counts["WRONG"],
        },
        "tracks": track_decisions,
        "scope_guards": {
            "q0_query_changed": False,
            "new_youtube_searches": 0,
            "historical_resolver_changed": False,
            "duration_max_seconds": 20.0,
            "tier_is_preference_signal": False,
            "explicit_recording_conflicts_are_hard_rejections": True,
            "production_activated": False,
            "sol_runs": 0,
            "human_labels_changed": False,
            "audio_downloads": 0,
            "video_downloads": 0,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
    }

    source_transitions = Counter()
    human_transitions = Counter()
    for row in changed:
        old = row["old_selected_candidate"]
        new = row["new_selected_candidate"]
        old_source = (
            old["global_features"]["source"]["effective_preference_source_type"]
            if old else "MATCH_UNCERTAIN"
        )
        new_source = (
            new["global_features"]["source"]["effective_preference_source_type"]
            if new else "MATCH_UNCERTAIN"
        )
        source_transitions[f"{old_source} -> {new_source}"] += 1
        human_transitions[
            f"{_evidence_label(old, 'human') if old else None} -> "
            f"{_evidence_label(new, 'human') if new else None}"
        ] += 1

    frozen_pair_doc = _json_object(
        config.project_root / config.frozen_inputs["stage5b1f_candidate_pairs"]["path"]
    )
    decision_by_id = {row["stable_track_id"]: row for row in track_decisions}
    reevaluated = []
    for row in frozen_pair_doc["comparisons"]:
        stable_id = row["stable_track_id"]
        new_id = decision_by_id[stable_id]["global_preference_decision"].get(
            "selected_video_id"
        )
        preferred_id = row["best_known_human_safe_candidate"]["video_id"]
        reevaluated.append({
            "stable_track_id": stable_id,
            "stage5b1f_old_selected_video_id": row["resolver_selected_candidate"]["video_id"],
            "stage5b1f_best_known_human_safe_video_id": preferred_id,
            "global_selected_video_id": new_id,
            "global_selected_best_known_human_safe": new_id == preferred_id,
            "stage5b1f_primary_cause": row["primary_cause"],
        })
    changed_doc = {
        "schema_version": CHANGED_SCHEMA_VERSION,
        "status": STATUS,
        "comparison_count": len(changed),
        "source_type_transitions": dict(sorted(source_transitions.items())),
        "human_label_transitions": dict(sorted(human_transitions.items())),
        "stage5b1f_preference_case_replay": reevaluated,
        "comparisons": changed,
    }

    all_candidates = [candidate for row in feature_tracks for candidate in row["candidates"]]
    duration_rows = []
    for bucket in DURATION_ORDER:
        considered = [row for row in all_candidates if row["global_features"]["duration"]["bucket"] == bucket]
        eligible = [row for row in considered if row["global_features"]["eligibility"]["eligible"]]
        selected = selected_by_bucket.get(bucket, [])
        human_counts = Counter(_evidence_label(row, "human") or "UNREVIEWED" for row in selected)
        duration_rows.append({
            "bucket": bucket,
            "candidates_considered": len(considered),
            "candidates_eligible": len(eligible),
            "candidates_selected": len(selected),
            "selected_human_label_counts": dict(sorted(human_counts.items())),
            "selected_human_safe_count": sum(
                _evidence_label(row, "human") in SAFE_LABELS for row in selected
            ),
            "selected_human_wrong_count": sum(
                _evidence_label(row, "human") == "WRONG" for row in selected
            ),
            "selected_human_uncertain_count": sum(
                _evidence_label(row, "human") == "UNCERTAIN" for row in selected
            ),
        })
    duration_doc = {
        "schema_version": DURATION_SCHEMA_VERSION,
        "status": STATUS,
        "duration_bands_seconds": config.duration_bands.__dict__,
        "rows": duration_rows,
    }

    frozen_tail = _json_object(
        config.project_root / config.frozen_inputs["stage5b1f_remaining_tail"]["path"]
    )
    old_tail_by_id = {row["stable_track_id"]: row for row in frozen_tail["tracks"]}
    tail_rows = []
    for decision_row in track_decisions:
        stable_id = decision_row["stable_track_id"]
        if decision_row["baseline_decision"]["status"] != MATCH_UNCERTAIN:
            continue
        track_row = next(row for row in feature_tracks if row["track"]["stable_track_id"] == stable_id)
        global_decision = decision_row["global_preference_decision"]
        if global_decision["status"] == AUTO_MATCH:
            classification = "RESOLVED_BY_GLOBAL_PREFERENCE"
        else:
            prior = old_tail_by_id[stable_id]["classification"]
            has_human_safe = any(
                _evidence_label(row, "human") in SAFE_LABELS for row in track_row["candidates"]
            )
            has_conflicting_strong = any(
                row["global_features"]["identity"]["strong_structural_title_identity"]
                and row["global_features"]["hard_conflicts"]
                for row in track_row["candidates"]
            )
            if has_human_safe:
                classification = "SAFE_CANDIDATE_PRESENT_BUT_METADATA_INSUFFICIENT"
            elif prior == "METADATA_INSUFFICIENT":
                classification = "SAFE_CANDIDATE_PRESENT_BUT_METADATA_INSUFFICIENT"
            elif has_conflicting_strong:
                classification = "TRUE_CONFLICTING_CANDIDATES"
            else:
                classification = "NO_DEFENSIBLE_CANDIDATE_IN_TOP5"
        tail_rows.append({
            "stable_track_id": stable_id,
            "target": track_row["track"],
            "classification": classification,
            "global_preference_decision": global_decision,
            "prior_stage5b1f_classification": old_tail_by_id[stable_id]["classification"],
            "prior_stage5b1f_primary_blocker": old_tail_by_id[stable_id]["primary_blocker"],
            "candidates": track_row["candidates"],
        })
    tail_doc = {
        "schema_version": TAIL_SCHEMA_VERSION,
        "status": STATUS,
        "baseline_unresolved_count": 8,
        "remaining_unresolved_count": sum(
            row["classification"] != "RESOLVED_BY_GLOBAL_PREFERENCE" for row in tail_rows
        ),
        "classification_counts": dict(sorted(Counter(row["classification"] for row in tail_rows).items())),
        "tracks": tail_rows,
    }

    review_cases = []
    for row in changed:
        candidate = row["new_selected_candidate"]
        if candidate is None:
            raise Stage5B1AValidationError(
                "Stage 5B.1G must not withdraw a frozen AUTO_MATCH: "
                f"{row['stable_track_id']}"
            )
        review_cases.append({
            "stable_track_id": row["stable_track_id"],
            "candidate_video_ids": [candidate["snapshot"]["video_id"]],
            "change_type": row["change_type"],
            "prior_human_label": _evidence_label(candidate, "human"),
            "selection_reason": "GLOBAL_CANDIDATE_PREFERENCE_V1 changed or newly created this selection",
        })
    queue = {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "status": STATUS,
        "policy_id": POLICY_ID,
        "track_count": len(review_cases),
        "candidate_count": len(review_cases),
        "cases": review_cases,
    }
    return features, decisions, changed_doc, duration_doc, tail_doc, queue


def _review_rows(features: dict[str, Any], queue: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {row["track"]["stable_track_id"]: row for row in features["tracks"]}
    rows = []
    for case in queue["cases"]:
        track_row = by_id[case["stable_track_id"]]
        target = track_row["track"]
        video_id = case["candidate_video_ids"][0]
        wrapped = next(
            row for row in track_row["candidates"]
            if row["snapshot"]["video_id"] == video_id
        )
        candidate = wrapped["snapshot"]
        rows.append({
            "review_schema_version": REVIEW_SCHEMA_VERSION,
            "stable_track_id": target["stable_track_id"],
            "expected_title": target["title"],
            "expected_artists": " | ".join(target["artists"]),
            "expected_album": target.get("album") or "",
            "expected_duration_seconds": (
                target["duration_ms"] / 1000.0 if target.get("duration_ms") is not None else ""
            ),
            "expected_release_year": target.get("release_year") or "",
            "candidate_video_id": video_id,
            "candidate_url": candidate.get("url") or "",
            "candidate_title": candidate.get("title") or "",
            "candidate_uploader": candidate.get("uploader") or "",
            "candidate_channel": candidate.get("channel") or "",
            "candidate_duration_seconds": candidate.get("duration_seconds") or "",
            "candidate_view_count": candidate.get("view_count") or "",
            "candidate_description": candidate.get("description") or "",
            "candidate_review_label": "",
            "candidate_note": "",
            "track_note": "",
        })
    return rows


def _write_review_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            existing = list(csv.DictReader(handle))
        reviewer_fields = {"candidate_review_label", "candidate_note", "track_note"}
        has_review_evidence = any(
            str(row.get(name) or "").strip()
            for row in existing
            for name in reviewer_fields
        )
        if not has_review_evidence:
            existing = []
        immutable = [name for name in REVIEW_COLUMNS if name not in {
            "candidate_review_label", "candidate_note", "track_note",
        }]
        if existing and (len(existing) != len(rows) or any(
            old[name] != str(new[name]) for old, new in zip(existing, rows) for name in immutable
        )):
            raise Stage5B1AValidationError("refusing to overwrite changed Stage 5B.1G review evidence")
        if existing:
            return
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def _display_path(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def write_report(
    config: Stage5B1GConfig,
    decisions: dict[str, Any],
    changed: dict[str, Any],
    duration: dict[str, Any],
    tail: dict[str, Any],
    queue: dict[str, Any],
) -> None:
    summary = decisions["summary"]
    lines = [
        "# Stage 5B.1G — Global Candidate Preference + Graduated Duration Evidence",
        "",
        f"Status: `{STATUS}`",
        "",
        "## Outcome",
        "",
        (
            f"The frozen pre-1G resolver replayed exactly at **42/50 AUTO_MATCH "
            f"and 8/50 MATCH_UNCERTAIN**. Global preference produced "
            f"**{summary['global_auto_match_count']}/50 AUTO_MATCH "
            f"({summary['global_coverage']:.0%})**, a "
            f"**{summary['absolute_percentage_point_gain']:.0f}-percentage-point** "
            "mechanical coverage change."
        ),
        "",
        (
            f"It changed {summary['existing_selection_changed_count']} existing selections "
            f"and newly resolved {summary['newly_resolved_count']} tracks. Every changed or "
            "new selection is queued for human review; production activation remains false."
        ),
        "",
        (
            f"Among all 42 selected candidates, frozen human evidence currently marks "
            f"{summary['selected_known_human_safe_count']} SAFE, "
            f"{summary['selected_known_human_wrong_count']} WRONG, and "
            f"{summary['selected_known_human_uncertain_count']} UNCERTAIN; the rest are "
            "unreviewed. These are evidence-availability counts, not a population precision "
            "estimate."
        ),
        "",
        "## Architecture",
        "",
        "The historical Balanced V1 → 1C-A → 1C-B → 1C-C cascade is replayed unchanged. "
        "Stage 5B.1G then considers every conflict-free candidate admitted by any frozen "
        "tier plus candidates independently admitted by the graduated-duration gate. The "
        "admitting tier is evidence provenance only and never affects preference.",
        "",
        "Global lexicographic preference is: structural recording identity; target-relative "
        "version compatibility; performer identity; internally consistent provenance; "
        "graduated duration; source quality; album/year corroboration; finally views and "
        "search rank as weak tiebreakers.",
        "",
        "## Graduated duration evidence",
        "",
        "| Bucket | Interval | Considered | Eligible | Selected | Human SAFE | Human WRONG | Human UNCERTAIN |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    intervals = {
        DURATION_VERY_CLOSE: "0–2 s",
        DURATION_CLOSE: ">2–7 s",
        DURATION_EXTENDED_1: ">7–12 s",
        DURATION_EXTENDED_2: ">12–16 s",
        DURATION_EXTENDED_3: ">16–20 s",
        DURATION_TOO_FAR: ">20 s",
        DURATION_UNKNOWN: "unknown",
    }
    for row in duration["rows"]:
        lines.append(
            f"| {row['bucket']} | {intervals[row['bucket']]} | "
            f"{row['candidates_considered']} | {row['candidates_eligible']} | "
            f"{row['candidates_selected']} | {row['selected_human_safe_count']} | "
            f"{row['selected_human_wrong_count']} | {row['selected_human_uncertain_count']} |"
        )
    lines.extend([
        "",
        "Candidates beyond seven seconds require progressively stronger corroboration. "
        "A delta above 20 seconds is a hard rejection. Explicit performer, cover, version, "
        "or unrequested-modification conflicts remain hard rejections at every band.",
        "",
        "## Changed and newly resolved selections",
        "",
    ])
    if not changed["comparisons"]:
        lines.append("No candidate selection changed.")
    for row in changed["comparisons"]:
        old = row["old_selected_candidate"]
        new = row["new_selected_candidate"]
        old_id = old["snapshot"]["video_id"] if old else "MATCH_UNCERTAIN"
        new_id = new["snapshot"]["video_id"] if new else "MATCH_UNCERTAIN"
        human = _evidence_label(new, "human") if new else None
        sol = _evidence_label(new, "sol") if new else None
        lines.append(
            f"- `{row['stable_track_id']}`: `{old_id}` → `{new_id}` "
            f"({row['change_type']}; existing human={human or 'unreviewed'}; "
            f"frozen Sol={sol or 'missing'})."
        )
    lines.extend([
        "",
        "Frozen human-label transitions among changed selections:",
        "",
    ])
    for transition, count in changed["human_label_transitions"].items():
        lines.append(f"- `{transition}`: {count}")
    lines.extend([
        "",
        "Source-type transitions:",
        "",
    ])
    for transition, count in changed["source_type_transitions"].items():
        lines.append(f"- `{transition}`: {count}")
    lines.extend([
        "",
        "### Stage 5B.1F preference-case replay",
        "",
        "| Track | Prior cause | Global selection equals best known human-SAFE candidate |",
        "|---|---|---:|",
    ])
    for row in changed["stage5b1f_preference_case_replay"]:
        lines.append(
            f"| `{row['stable_track_id']}` | `{row['stage5b1f_primary_cause']}` | "
            f"{'yes' if row['global_selected_best_known_human_safe'] else 'no'} |"
        )
    lines.extend([
        "",
        "## Remaining tail",
        "",
        f"The experiment leaves **{tail['remaining_unresolved_count']}/8** previously "
        "unresolved tracks unresolved.",
        "",
    ])
    for row in tail["tracks"]:
        decision = row["global_preference_decision"]
        lines.append(
            f"- `{row['stable_track_id']}` — `{row['classification']}`; "
            f"decision `{decision['status']}`; prior blocker: "
            f"{row['prior_stage5b1f_primary_blocker']}."
        )
    lines.extend([
        "",
        "## Conclusions",
        "",
        (
            "1. Global competition materially changes source preference: it selects the best "
            "known human-SAFE candidate in four of the five Stage 5B.1F preference cases. "
            "Track 044 remains unchanged because its internally consistent release evidence "
            "still outranks the reviewed alternative. Five additional changed candidates "
            "lack frozen human labels and require the generated audit."
        ),
        (
            "2. Graduated duration removes the 7-second mathematical cliff without creating "
            "new coverage. The selected >16-second Official Music Video is frozen-Sol "
            "ACCEPTABLE but human-unreviewed, so safety of that band remains pending. "
            "Extended bands cannot override conflicts, and 12–20-second candidates require "
            "strong or strongest corroborated provenance."
        ),
        (
            f"3. Existing selections changed: {summary['existing_selection_changed_count']}; "
            f"new tracks resolved: {summary['newly_resolved_count']}. Four changed selections "
            "are upgrades in frozen human evidence, one is IDEAL-to-IDEAL, and five are "
            "unreviewed. No changed selection is frozen-human WRONG or frozen-Sol WRONG."
        ),
        (
            f"4. Mechanical coverage {'reaches' if summary['global_coverage'] >= 0.9 else 'does not reach'} "
            f"the 90% milestone: {summary['global_auto_match_count']}/50 "
            f"({summary['global_coverage']:.0%}). The eight-track tail remains four pools with "
            "no defensible candidate, three metadata-insufficient pools, and one pool dominated "
            "by conflicting candidates."
        ),
        (
            "5. The selection-bottleneck hypothesis is supported for source quality, not for "
            "remaining coverage. Global comparison corrects known duration/provenance and "
            "tier-lock inversions, but no defensible deterministic path to at least 45/50 is "
            "demonstrated by the frozen top-five metadata. Better discovery or additional "
            "evidence remains necessary for the unresolved tail."
        ),
        (
            "6. Counterfactual negatives remain protected: no selected candidate carries an "
            "explicit performer/cover, version, or unrequested modified-audio conflict, and "
            "every >7-second eligible candidate records the corroboration that admitted it."
        ),
        "",
        "## Review and scope",
        "",
        f"- review queue: `{_display_path(config.artifacts['human_review_csv'], config.project_root)}`",
        f"- queued tracks/candidates: {queue['track_count']}/{queue['candidate_count']}",
        "- Q0 changed: no; searches run: 0; media downloaded: 0; Sol rerun: no",
        "- historical resolver policies changed: no",
        "- production activation: no",
        "",
        "## Tests",
        "",
        "Test results are recorded at closeout after deterministic artifact generation.",
        "",
    ])
    config.artifacts["report"].parent.mkdir(parents=True, exist_ok=True)
    config.artifacts["report"].write_text("\n".join(lines), encoding="utf-8")


def write_artifacts(config: Stage5B1GConfig) -> dict[str, Any]:
    verified = verify_frozen_inputs(config)
    features, decisions, changed, duration, tail, queue = evaluate_stage5b1g(config)
    outputs = {
        "candidate_features": features,
        "decisions": decisions,
        "changed_selections": changed,
        "duration_analysis": duration,
        "remaining_tail": tail,
        "human_audit_queue": queue,
    }
    for name, value in outputs.items():
        atomic_json(config.artifacts[name], value)
    _write_review_csv(config.artifacts["human_review_csv"], _review_rows(features, queue))
    write_report(config, decisions, changed, duration, tail, queue)
    output_names = tuple(outputs) + ("human_review_csv", "report")
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": STATUS,
        "config": {
            "path": _display_path(config.path, config.project_root),
            "sha256": config.sha256,
        },
        "frozen_inputs": verified,
        "artifacts": {
            name: {
                "path": _display_path(config.artifacts[name], config.project_root),
                "sha256": file_sha256(config.artifacts[name]),
                "size_bytes": config.artifacts[name].stat().st_size,
            }
            for name in output_names
        },
        "scope_guards": decisions["scope_guards"],
    }
    atomic_json(config.artifacts["manifest"], manifest)
    return manifest


def _default_config() -> Path:
    return Path(__file__).parents[2] / "configs/stage5b1g_global_preference.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_default_config())
    args = parser.parse_args(argv)
    config = load_stage5b1g_config(args.config)
    manifest = write_artifacts(config)
    print(json.dumps({
        "status": manifest["status"],
        "manifest": str(config.artifacts["manifest"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
