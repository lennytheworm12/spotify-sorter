"""Stage 5B.1I representation-equivalent studio fallback for ordinary live targets.

The historical resolver remains the exact-recording authority. This downstream
policy is consulted only when that resolver returns ``MATCH_UNCERTAIN`` for a
target whose sole material version family is an ordinary live performance.
"""
from __future__ import annotations

import copy
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_identity import parse_target
from .stage5b1b_resolver import AUTO_MATCH, MATCH_UNCERTAIN
from .stage5b1h_source_semantics import (
    AUDIO_PRESENTATION,
    ART_TRACK_TOPIC,
    CANONICAL_STRONG,
    CANONICAL_SUPPORTED,
    CANONICAL_UNKNOWN,
    LYRIC_VIDEO,
    MUSIC_VIDEO,
    OFFICIAL_AUDIO,
    OFFICIAL_LYRIC_VIDEO,
    OFFICIAL_MUSIC_VIDEO,
    evaluate_stage5b1h,
    load_stage5b1h_config,
)


CONFIG_SCHEMA_VERSION = "stage5b1i-live-fallback-config-v1"
CLASSIFICATION_SCHEMA_VERSION = "stage5b1i-live-target-classification-v1"
FEATURE_SCHEMA_VERSION = "stage5b1i-live-fallback-candidate-features-v1"
DECISION_SCHEMA_VERSION = "stage5b1i-representation-equivalence-decisions-v1"
QUEUE_SCHEMA_VERSION = "stage5b1i-live-fallback-human-audit-queue-v1"
MANIFEST_SCHEMA_VERSION = "stage5b1i-live-fallback-artifact-manifest-v1"
POLICY_ID = "REPRESENTATION_EQUIVALENT_LIVE_FALLBACK_V1"
STATUS = "STAGE5B1I_LIVE_REPRESENTATION_FALLBACK_EVALUATED"

EXACT_RECORDING = "EXACT_RECORDING"
REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK = (
    "REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK"
)

NOT_LIVE_TARGET = "NOT_LIVE_TARGET"
ORDINARY_LIVE = "ORDINARY_LIVE"
ARRANGEMENT_CHANGING_LIVE = "ARRANGEMENT_CHANGING_LIVE"

REPRESENTATION_RISK_LOW = "LOW"
REPRESENTATION_RISK_ELEVATED = "ELEVATED"
REPRESENTATION_RISK_UNSUITABLE = "UNSUITABLE"

_ARRANGEMENT_CHANGING_FAMILIES = frozenset({
    "acoustic",
    "content_rating",
    "duration_version",
    "edit",
    "extended",
    "instrumental",
    "karaoke",
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
_EXTRA_ARRANGEMENT_PATTERNS = {
    "orchestral": re.compile(r"\b(?:orchestral|orchestra|symphonic)\b", re.I),
    "bass_boosted": re.compile(r"\bbass[ -]?boost(?:ed)?\b", re.I),
    "mashup": re.compile(r"\bmash[ -]?up\b", re.I),
    "unplugged": re.compile(r"\bunplugged\b", re.I),
    "alternate_arrangement": re.compile(
        r"\b(?:alternate|alternative)\s+(?:arrangement|version)\b", re.I
    ),
}
_LIVE_PRESENTATION = re.compile(
    r"\blive\b|\b(?:concert|tour|festival|auditorium|theatre|theater|arena)\b|"
    r"(?:^|\s)@\s*[\w]",
    re.I,
)

_SOURCE_ORDER = {
    ART_TRACK_TOPIC: 0,
    OFFICIAL_AUDIO: 1,
    OFFICIAL_LYRIC_VIDEO: 2,
    OFFICIAL_MUSIC_VIDEO: 3,
}


@dataclass(frozen=True)
class Stage5B1IConfig:
    path: Path
    project_root: Path
    experiment_id: str
    policy_id: str
    stage5b1h_config: Path
    frozen_inputs: dict[str, dict[str, Any]]
    artifacts: dict[str, Path]
    sha256: str


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def load_stage5b1i_config(path: Path) -> Stage5B1IConfig:
    path = path.resolve()
    value = _json_object(path)
    if value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.1I config schema")
    if value.get("policy_id") != POLICY_ID:
        raise Stage5B1AValidationError("unexpected Stage 5B.1I policy ID")
    project_root = path.parent.parent
    frozen = value.get("frozen_inputs")
    artifacts = value.get("artifacts")
    if not isinstance(frozen, dict) or not frozen:
        raise Stage5B1AValidationError("Stage 5B.1I frozen inputs are required")
    if not isinstance(artifacts, dict) or not artifacts:
        raise Stage5B1AValidationError("Stage 5B.1I artifacts are required")
    return Stage5B1IConfig(
        path=path,
        project_root=project_root,
        experiment_id=str(value["experiment_id"]),
        policy_id=str(value["policy_id"]),
        stage5b1h_config=project_root / str(value["stage5b1h_config"]),
        frozen_inputs=dict(frozen),
        artifacts={
            name: project_root / str(target) for name, target in artifacts.items()
        },
        sha256=file_sha256(path),
    )


def verify_frozen_inputs(config: Stage5B1IConfig) -> dict[str, dict[str, Any]]:
    verified = {}
    for name, value in config.frozen_inputs.items():
        path = config.project_root / str(value["path"])
        actual = file_sha256(path)
        expected = str(value["sha256"])
        if actual != expected:
            raise Stage5B1AValidationError(
                f"frozen Stage 5B.1I input changed: {name}: {actual} != {expected}"
            )
        verified[name] = {
            "path": str(path.relative_to(config.project_root)),
            "sha256": actual,
            "size_bytes": path.stat().st_size,
        }
    return verified


def classify_live_target(track_dict: dict[str, Any]) -> dict[str, Any]:
    """Classify whether the target permits an ordinary-live studio fallback."""

    track = SpotifyTrack.from_dict(track_dict)
    identity = parse_target(track)
    families = {descriptor.family for descriptor in identity.versions}
    searchable_text = " ".join((track.title, track.album or ""))
    explicit_arrangements = sorted(
        name
        for name, pattern in _EXTRA_ARRANGEMENT_PATTERNS.items()
        if pattern.search(searchable_text)
    )
    material_families = sorted(
        (families - {"live"}) & _ARRANGEMENT_CHANGING_FAMILIES
    )
    live_descriptor = next(
        (descriptor for descriptor in identity.versions if descriptor.family == "live"),
        None,
    )
    if "live" not in families:
        classification = NOT_LIVE_TARGET
        fallback_allowed = False
        risk = None
        reason = "target does not request a live performance"
    elif material_families or explicit_arrangements:
        classification = ARRANGEMENT_CHANGING_LIVE
        fallback_allowed = False
        risk = REPRESENTATION_RISK_UNSUITABLE
        reason = (
            "live target also contains arrangement/production-changing identity: "
            + ", ".join(material_families + explicit_arrangements)
        )
    else:
        classification = ORDINARY_LIVE
        fallback_allowed = True
        risk = (
            REPRESENTATION_RISK_ELEVATED
            if live_descriptor and live_descriptor.qualifier
            else REPRESENTATION_RISK_LOW
        )
        reason = (
            "live is the target's only material version family; a canonical studio "
            "recording may represent the song if exact-live resolution fails"
        )
    return {
        "stable_track_id": track.stable_track_id,
        "classification": classification,
        "studio_fallback_allowed": fallback_allowed,
        "representation_risk": risk,
        "reason": reason,
        "target_identity": identity.to_dict(),
        "material_arrangement_families": material_families,
        "extra_arrangement_markers": explicit_arrangements,
    }


def _fallback_canonicality(
    global_features: dict[str, Any], source_semantics: dict[str, Any]
) -> dict[str, Any]:
    provenance = global_features["provenance"]
    artist = bool(provenance["channel_or_uploader_performer_match"])
    release = bool(
        provenance["art_track_internally_consistent"]
        or provenance["release_metadata_corroborated"]
    )
    official_phrase = bool(
        source_semantics["source_presentation"][
            "explicit_official_source_signal"
        ]
    )
    if artist or release:
        level = CANONICAL_STRONG
        reason = (
            "artist/channel provenance"
            if artist and not release
            else "internally consistent release/distributor provenance"
        )
    elif official_phrase:
        level = CANONICAL_SUPPORTED
        reason = "explicit official wording without independent provenance"
    else:
        level = CANONICAL_UNKNOWN
        reason = "no artist, label/distributor, or release-backed provenance"
    return {
        "level": level,
        "reason": reason,
        "artist_channel_or_uploader_signal": artist,
        "release_or_distributor_signal": release,
        "explicit_official_source_phrase_signal": official_phrase,
    }


def build_fallback_candidate_evidence(
    candidate_record: dict[str, Any],
    source_semantics: dict[str, Any],
    target_classification: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate a candidate under live→studio representation-equivalence semantics."""

    snapshot = candidate_record["snapshot"]
    global_features = candidate_record["global_features"]
    identity = global_features["identity"]
    performer = identity["performer_evidence"]
    versions = global_features["versions"]
    modifications = global_features["modifications"]
    candidate_families = set(modifications["candidate_families"])
    non_live_version_conflicts = [
        row
        for row in versions["relationships"]
        if row["family"] != "live" and row["relationship"] == "CONFLICT"
    ]
    title_and_description = " ".join(
        (str(snapshot.get("title") or ""), str(snapshot.get("description") or ""))
    )
    explicit_live_presentation = bool(_LIVE_PRESENTATION.search(title_and_description))
    canonicality = _fallback_canonicality(global_features, source_semantics)
    source_presentation = copy.deepcopy(source_semantics["source_presentation"])
    presentation = source_presentation.get(
        "normalized_presentation_signal",
        source_presentation["normalized_source_type"],
    )
    fallback_source_type = source_presentation["normalized_source_type"]
    if canonicality["level"] == CANONICAL_STRONG:
        fallback_source_type = {
            AUDIO_PRESENTATION: OFFICIAL_AUDIO,
            LYRIC_VIDEO: OFFICIAL_LYRIC_VIDEO,
            MUSIC_VIDEO: OFFICIAL_MUSIC_VIDEO,
        }.get(presentation, fallback_source_type)
    hard_conflicts = list(global_features["hard_conflicts"])
    conditions = {
        "ordinary_live_target": target_classification["classification"]
        == ORDINARY_LIVE,
        "strong_core_title_identity": identity[
            "strong_structural_title_identity"
        ],
        "strong_primary_performer_identity": identity[
            "strong_primary_performer_identity"
        ],
        "no_explicit_performer_or_cover_conflict": not (
            performer["explicit_cover_signal"]
            or performer["explicit_performer_conflict"]
            or performer["explicit_title_performer_conflict"]
        ),
        "no_explicit_recording_conflicts": not hard_conflicts,
        "candidate_has_no_production_changing_version": not candidate_families,
        "candidate_is_not_another_live_performance": not explicit_live_presentation,
        "no_non_live_version_conflict": not non_live_version_conflicts,
        "canonical_studio_provenance": canonicality["level"] == CANONICAL_STRONG,
    }
    failed = [name for name, passed in conditions.items() if not passed]
    return {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "stable_track_id": global_features["track_id"],
        "candidate_video_id": global_features["candidate_video_id"],
        "candidate": {
            key: snapshot.get(key)
            for key in (
                "video_id",
                "search_rank",
                "title",
                "url",
                "uploader",
                "channel",
                "duration_seconds",
                "view_count",
            )
        },
        "identity": {
            "strong_core_title_identity": identity[
                "strong_structural_title_identity"
            ],
            "strong_primary_performer_identity": identity[
                "strong_primary_performer_identity"
            ],
            "performer_evidence": copy.deepcopy(performer),
        },
        "versions": {
            "target_families": list(modifications["target_families"]),
            "candidate_families": list(modifications["candidate_families"]),
            "relationships": copy.deepcopy(versions["relationships"]),
            "live_absence_is_expected_for_studio_fallback": True,
            "non_live_conflicts": non_live_version_conflicts,
        },
        "canonicality": canonicality,
        "source": {
            **source_presentation,
            "fallback_normalized_source_type": fallback_source_type,
        },
        "duration": {
            "target_live_seconds": global_features["duration"]["target_seconds"],
            "candidate_studio_seconds": global_features["duration"][
                "candidate_seconds"
            ],
            "live_to_studio_delta_seconds": global_features["duration"][
                "absolute_duration_delta_seconds"
            ],
            "used_for_fallback_eligibility": False,
            "reason": "live and studio performances need not have similar durations",
        },
        "hard_conflicts": hard_conflicts,
        "explicit_live_presentation_evidence": explicit_live_presentation,
        "eligibility": {
            "eligible": not failed,
            "conditions": conditions,
            "failed_conditions": failed,
            "basis": (
                "ORDINARY_LIVE_CANONICAL_STUDIO_EQUIVALENCE"
                if not failed
                else "INELIGIBLE"
            ),
        },
        "human_evidence": copy.deepcopy(snapshot.get("human_evidence")),
        "sol_evidence": copy.deepcopy(snapshot.get("sol_evidence")),
    }


def _fallback_preference_key(row: dict[str, Any]) -> tuple[Any, ...]:
    canonicality = row["canonicality"]
    source_type = row["source"]["fallback_normalized_source_type"]
    candidate = row["candidate"]
    return (
        0 if canonicality["release_or_distributor_signal"] else 1,
        0 if canonicality["artist_channel_or_uploader_signal"] else 1,
        _SOURCE_ORDER.get(source_type, len(_SOURCE_ORDER)),
        0 if candidate.get("view_count") is not None else 1,
        -(int(candidate["view_count"]) if candidate.get("view_count") is not None else -1),
        int(candidate["search_rank"]),
    )


def _decision_identity(decision: dict[str, Any]) -> dict[str, Any]:
    """Keep the new decision artifact compact; Stage 5B.1H remains hash-bound."""

    return {
        key: copy.deepcopy(decision.get(key))
        for key in (
            "status",
            "policy_rule_id",
            "selected_video_id",
            "selected_candidate_rank",
        )
    }


def resolve_representation_equivalence(
    baseline_decision: dict[str, Any],
    target_classification: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply exact-first, ordinary-live-only representation equivalence."""

    if baseline_decision["status"] == AUTO_MATCH:
        return {
            **_decision_identity(baseline_decision),
            "match_mode": EXACT_RECORDING,
            "decision_origin": "STAGE5B1H_EXACT_RESOLVER",
            "selection_reason": baseline_decision.get("selection_reason"),
            "representation_risk": None,
        }
    eligible = sorted(
        (row for row in candidates if row["eligibility"]["eligible"]),
        key=_fallback_preference_key,
    )
    if target_classification["classification"] != ORDINARY_LIVE or not eligible:
        return {
            **_decision_identity(baseline_decision),
            "policy_rule_id": POLICY_ID,
            "match_mode": None,
            "decision_origin": "STAGE5B1I_LIVE_FALLBACK",
            "representation_risk": target_classification["representation_risk"],
            "uncertainty_reason": (
                target_classification["reason"]
                if target_classification["classification"] != ORDINARY_LIVE
                else "no canonical conflict-free studio candidate exists in frozen Q0 top five"
            ),
        }
    selected = eligible[0]
    return {
        "status": AUTO_MATCH,
        "policy_rule_id": POLICY_ID,
        "selected_video_id": selected["candidate_video_id"],
        "selected_candidate_rank": selected["candidate"]["search_rank"],
        "match_mode": REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK,
        "decision_origin": "STAGE5B1I_LIVE_FALLBACK",
        "selection_reason": (
            "exact-live resolution failed; selected a conflict-free canonical studio "
            "recording for representation equivalence"
        ),
        "representation_risk": target_classification["representation_risk"],
        "evidence_summary": copy.deepcopy(selected),
        "ranked_plausible_candidates": [
            row["candidate_video_id"] for row in eligible
        ],
    }


def evaluate_stage5b1i(
    config: Stage5B1IConfig,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Replay Stage 5B.1H and evaluate the new downstream fallback."""

    verify_frozen_inputs(config)
    stage5b1h = load_stage5b1h_config(config.stage5b1h_config)
    semantics_doc, baseline_doc, *_ = evaluate_stage5b1h(stage5b1h)
    summary = baseline_doc["summary"]
    if (
        summary["stage5b1h_auto_match_count"],
        summary["stage5b1h_match_uncertain_count"],
        summary["selection_ids_changed"],
    ) != (42, 8, 0):
        raise Stage5B1AValidationError("frozen Stage 5B.1H 42/8 baseline changed")

    full_features = _json_object(
        config.project_root
        / str(config.frozen_inputs["stage5b1g_features"]["path"])
    )
    baseline_by_id = {
        row["stable_track_id"]: row["stage5b1h_decision"]
        for row in baseline_doc["tracks"]
    }
    semantics_by_key = {
        (track["track"]["stable_track_id"], candidate["video_id"]): candidate[
            "source_semantics"
        ]
        for track in semantics_doc["tracks"]
        for candidate in track["candidates"]
    }

    classifications = []
    feature_tracks = []
    decisions = []
    live_rows = []
    for track_row in full_features["tracks"]:
        track = track_row["track"]
        stable_id = track["stable_track_id"]
        classification = classify_live_target(track)
        baseline = baseline_by_id[stable_id]
        candidate_features = [
            build_fallback_candidate_evidence(
                candidate,
                semantics_by_key[(stable_id, candidate["snapshot"]["video_id"])],
                classification,
            )
            for candidate in track_row["candidates"]
        ]
        final = resolve_representation_equivalence(
            baseline, classification, candidate_features
        )
        if baseline["status"] == AUTO_MATCH and (
            final.get("selected_video_id") != baseline.get("selected_video_id")
            or final["match_mode"] != EXACT_RECORDING
        ):
            raise Stage5B1AValidationError(
                f"Stage 5B.1I displaced an exact decision: {stable_id}"
            )
        decisions.append({
            "stable_track_id": stable_id,
            "stage5b1h_decision": _decision_identity(baseline),
            "stage5b1i_decision": final,
            "coverage_changed": baseline["status"] != final["status"],
        })
        if classification["classification"] != NOT_LIVE_TARGET:
            exact_candidates = [
                candidate["snapshot"]["video_id"]
                for candidate in track_row["candidates"]
                if candidate["global_features"]["eligibility"]["eligible"]
                and any(
                    relationship["family"] == "live"
                    and relationship["relationship"] == "MATCH"
                    for relationship in candidate["global_features"]["versions"][
                        "relationships"
                    ]
                )
            ]
            classification = {
                **classification,
                "target": copy.deepcopy(track),
                "exact_live_candidate_ids": exact_candidates,
                "exact_live_candidate_available": bool(exact_candidates),
                "stage5b1h_exact_outcome": baseline["status"],
                "stage5b1h_selected_video_id": baseline.get("selected_video_id"),
                "studio_fallback_candidate_ids": [
                    row["candidate_video_id"]
                    for row in candidate_features
                    if row["eligibility"]["eligible"]
                ],
                "stage5b1i_match_mode": final.get("match_mode"),
                "stage5b1i_selected_video_id": final.get("selected_video_id"),
            }
            classifications.append(classification)
            live_rows.append((track, classification, baseline, final))
        if (
            baseline["status"] == MATCH_UNCERTAIN
            and classification["classification"] == ORDINARY_LIVE
        ):
            feature_tracks.append({
                "track": copy.deepcopy(track),
                "target_classification": classification,
                "candidates": candidate_features,
            })

    auto_count = sum(
        row["stage5b1i_decision"]["status"] == AUTO_MATCH for row in decisions
    )
    fallback_rows = [
        row
        for row in decisions
        if row["stage5b1i_decision"].get("match_mode")
        == REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK
    ]
    classification_counts = Counter(
        row["classification"] for row in classifications
    )
    classification_doc = {
        "schema_version": CLASSIFICATION_SCHEMA_VERSION,
        "status": STATUS,
        "summary": {
            "live_target_count": len(classifications),
            "ordinary_live_target_count": classification_counts[ORDINARY_LIVE],
            "arrangement_changing_live_target_count": classification_counts[
                ARRANGEMENT_CHANGING_LIVE
            ],
            "exact_live_auto_match_count": sum(
                row["stage5b1h_exact_outcome"] == AUTO_MATCH
                for row in classifications
            ),
            "ordinary_live_exact_failures": sum(
                row["classification"] == ORDINARY_LIVE
                and row["stage5b1h_exact_outcome"] == MATCH_UNCERTAIN
                for row in classifications
            ),
            "studio_fallback_opportunity_count": sum(
                bool(row["studio_fallback_candidate_ids"])
                for row in classifications
            ),
        },
        "tracks": classifications,
    }
    features_doc = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "status": STATUS,
        "policy_id": POLICY_ID,
        "scope": "ordinary-live targets unresolved by frozen Stage 5B.1H",
        "attempted_track_count": len(feature_tracks),
        "candidate_count": sum(len(row["candidates"]) for row in feature_tracks),
        "tracks": feature_tracks,
    }
    decisions_doc = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "status": STATUS,
        "policy_id": POLICY_ID,
        "production_activated": False,
        "summary": {
            "total_tracks": len(decisions),
            "stage5b1h_auto_match_count": 42,
            "stage5b1h_match_uncertain_count": 8,
            "stage5b1i_auto_match_count": auto_count,
            "stage5b1i_match_uncertain_count": len(decisions) - auto_count,
            "exact_recording_count": sum(
                row["stage5b1i_decision"].get("match_mode") == EXACT_RECORDING
                for row in decisions
            ),
            "representation_equivalent_fallback_count": len(fallback_rows),
            "incremental_auto_match_count": auto_count - 42,
            "coverage_before": 42 / 50,
            "coverage_after": auto_count / 50,
            "absolute_percentage_point_gain": (auto_count - 42) / 50 * 100,
        },
        "scope_guards": {
            "q0_discovery_changed": False,
            "youtube_searches": 0,
            "historical_resolver_policies_changed": False,
            "remaster_semantics_changed": False,
            "non_live_version_semantics_changed": False,
            "live_to_studio_duration_used_for_eligibility": False,
            "media_downloads": 0,
            "sol_runs": 0,
            "human_labels_changed": False,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
        "tracks": decisions,
    }
    queue_cases = []
    full_by_id = {row["stable_track_id"]: row for row in decisions}
    feature_by_id = {
        row["track"]["stable_track_id"]: row for row in feature_tracks
    }
    for row in fallback_rows:
        stable_id = row["stable_track_id"]
        decision = full_by_id[stable_id]["stage5b1i_decision"]
        feature = next(
            item
            for item in feature_by_id[stable_id]["candidates"]
            if item["candidate_video_id"] == decision["selected_video_id"]
        )
        queue_cases.append({
            "stable_track_id": stable_id,
            "target": feature_by_id[stable_id]["track"],
            "candidate": feature["candidate"],
            "match_mode": REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK,
            "representation_risk": decision["representation_risk"],
            "review_label": "",
            "review_note": "",
            "allowed_labels": ["IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"],
        })
    queue_doc = {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "status": (
            "AWAITING_HUMAN_REVIEW" if queue_cases else "NO_REVIEW_REQUIRED"
        ),
        "policy_id": POLICY_ID,
        "track_count": len(queue_cases),
        "candidate_count": len(queue_cases),
        "cases": queue_cases,
    }
    return classification_doc, features_doc, decisions_doc, queue_doc
    LYRIC_VIDEO,
    MUSIC_VIDEO,
