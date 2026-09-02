"""Stage 5B.1C-B source-neutral Tier-2 candidate resolution.

This stage runs only after frozen Balanced V1 and frozen Stage 5B.1C-A.  It
changes one eligibility interpretation: an unknown/OTHER source contributes no
recording-identity evidence instead of being an automatic rejection.  Every
stronger identity, version, and duration gate remains in force.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_challenge import load_challenge_config
from .stage5b1b_resolver import AUTO_MATCH, MATCH_UNCERTAIN
from .stage5b1c_tier2 import (
    FROZEN_BALANCED_AUTO_MATCH_COUNT,
    TIER2_POLICY_ID,
    _human_labels,
    _mapped_sol,
    _ordering_key,
    _tier2_gate,
    evaluate_frozen_challenge,
)


SOURCE_NEUTRAL_POLICY_ID = "POLICY_TIER2_SOURCE_NEUTRAL_V1"
SOURCE_NEUTRAL_FEATURE_SCHEMA_VERSION = "stage5b1c-source-neutral-candidate-features-v1"
SOURCE_NEUTRAL_DATASET_SCHEMA_VERSION = "stage5b1c-source-neutral-feature-dataset-v1"
SOURCE_NEUTRAL_DECISION_SCHEMA_VERSION = "stage5b1c-source-neutral-decisions-v1"
TIER2A_OTHER_SOURCE_REASON = "Tier 2A does not allow OTHER-source fallback"
TIER2A_TITLE_MISMATCH_REASON = "normalized structural core title does not match"
FROZEN_TIER2A_INPUT_HASHES = {
    "artifact_manifest.json": "c0b87d9a32d87dca1a6bc3bedbb32187c7cd962545433314f4dd08db330f6bb4",
    "tier2_candidate_features.json": "258accdc9a2db9b9c8a5c5f3dd3808539983f6aa6c2a03cee028315687b5cf68",
    "tier2_decisions.json": "6b7a987c38294717296f05086186047af6085c2a75a206d0b4595b6100c2304d",
}
FROZEN_TIER2A_SELECTED = {
    "s5b1c_015": "ZNEuWldWPD4",
    "s5b1c_016": "WXx5-HGERcg",
    "s5b1c_017": "62TrmUvQGjo",
    "s5b1c_026": "sKzoEwQaF7Y",
    "s5b1c_027": "aEi646akxko",
    "s5b1c_043": "zDOILKOOUCo",
}


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def verify_frozen_tier2a(
    config_path: Path, tier2a_dir: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """Verify both committed artifacts and a live deterministic 1C-A replay."""

    hashes = {
        name: file_sha256(tier2a_dir / name) for name in FROZEN_TIER2A_INPUT_HASHES
    }
    changed = {
        name: value
        for name, value in hashes.items()
        if value != FROZEN_TIER2A_INPUT_HASHES[name]
    }
    if changed:
        raise Stage5B1AValidationError(
            f"frozen Stage 5B.1C-A artifact changed: {sorted(changed)}"
        )

    committed_features = _json_object(tier2a_dir / "tier2_candidate_features.json")
    committed_decisions = _json_object(tier2a_dir / "tier2_decisions.json")
    replayed_features, replayed_decisions = evaluate_frozen_challenge(config_path)
    if replayed_features != committed_features:
        raise Stage5B1AValidationError("frozen Stage 5B.1C-A feature replay changed")
    comparable = dict(committed_decisions)
    comparable.pop("tier2_features_sha256", None)
    if replayed_decisions != comparable:
        raise Stage5B1AValidationError("frozen Stage 5B.1C-A decision replay changed")
    selected = {
        row["stable_track_id"]: row["selected_video_id"]
        for row in committed_decisions["selected"]
    }
    if selected != FROZEN_TIER2A_SELECTED:
        raise Stage5B1AValidationError("frozen Stage 5B.1C-A selected candidates changed")
    return committed_features, committed_decisions, hashes


def _provenance_state(feature: dict[str, Any]) -> dict[str, Any]:
    provenance = feature["source"]["provenance"]
    positive_signals = [
        name
        for name in (
            "topic_channel_signal",
            "provided_to_youtube_by_signal",
            "auto_generated_by_youtube_signal",
            "structured_release_metadata_signal",
        )
        if provenance.get(name)
    ]
    uploader_matches = [
        row
        for row in feature["performers"]["evidence"]
        if row["source"] in {"uploader", "channel"}
    ]
    if positive_signals or uploader_matches:
        return {
            "state": "POSITIVE_CORROBORATED",
            "contribution": "POSITIVE",
            "positive_signals": positive_signals,
            "uploader_or_channel_performer_matches": uploader_matches,
        }
    return {
        "state": "UNKNOWN_NEUTRAL",
        "contribution": "NEUTRAL",
        "positive_signals": [],
        "uploader_or_channel_performer_matches": [],
    }


def extract_source_neutral_evidence(item: dict[str, Any]) -> dict[str, Any]:
    """Apply only source-neutral composition over a frozen 1C-A candidate."""

    feature = item["features"]
    prior_reasons = _tier2_gate(feature)
    remaining_reasons = list(prior_reasons)
    waived_reasons: list[dict[str, str]] = []
    source_type = feature["source"]["source_type"]

    # 1C-A and frozen Tier 1 use different deterministic title parsers.  When
    # frozen Tier 1 already recorded exact normalized identity, it can
    # corroborate a 1C-A split failure (notably multi-artist prefixes).  This
    # does not accept fuzzy title evidence or alter either frozen stage.
    tier1_exact = feature["tier1_before"]["title_exact_normalized_match"]
    if (
        source_type == "OTHER"
        and tier1_exact
        and TIER2A_TITLE_MISMATCH_REASON in remaining_reasons
    ):
        remaining_reasons.remove(TIER2A_TITLE_MISMATCH_REASON)
        waived_reasons.append(
            {
                "reason": TIER2A_TITLE_MISMATCH_REASON,
                "basis": "frozen Tier-1 exact normalized title corroboration",
            }
        )

    if source_type == "OTHER" and TIER2A_OTHER_SOURCE_REASON in remaining_reasons:
        remaining_reasons.remove(TIER2A_OTHER_SOURCE_REASON)
        waived_reasons.append(
            {
                "reason": TIER2A_OTHER_SOURCE_REASON,
                "basis": "unknown/OTHER provenance is neutral, not negative",
            }
        )

    return {
        "schema_version": SOURCE_NEUTRAL_FEATURE_SCHEMA_VERSION,
        "track_id": feature["track_id"],
        "candidate_video_id": feature["candidate_video_id"],
        "source_type": source_type,
        "provenance_evidence": _provenance_state(feature),
        "frozen_tier1_exact_title_corroboration": bool(tier1_exact),
        "prior_tier2a_gate_reasons": prior_reasons,
        "source_neutral_waivers": waived_reasons,
        "remaining_gate_reasons": remaining_reasons,
        "eligible": not remaining_reasons,
        "identity_conflict_present": any(
            marker in reason
            for reason in remaining_reasons
            for marker in (
                "performer",
                "cover",
                "version conflict",
                "version evidence remains absent",
            )
        ),
    }


def extract_source_neutral_track(track_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "track": track_row["track"],
        "query": track_row.get("query"),
        "candidates": [
            {
                "candidate": item["candidate"],
                "tier2a_features": item["features"],
                "source_neutral": extract_source_neutral_evidence(item),
            }
            for item in track_row["candidates"]
        ],
    }


def _source_neutral_ordering_key(item: dict[str, Any]) -> tuple[Any, ...]:
    # Preserve the frozen 1C-A ordering so this experiment changes eligibility,
    # not the downstream ranking hierarchy.
    return _ordering_key(
        {"candidate": item["candidate"], "features": item["tier2a_features"]}
    )


def resolve_source_neutral_track(track_row: dict[str, Any]) -> dict[str, Any]:
    accepted = [
        item for item in track_row["candidates"] if item["source_neutral"]["eligible"]
    ]
    accepted.sort(key=_source_neutral_ordering_key)
    excluded = [
        {
            "video_id": item["candidate"]["youtube_video_id"],
            "candidate_rank": item["candidate"]["rank"],
            "title": item["candidate"].get("title"),
            "prior_tier2a_gate_reasons": item["source_neutral"]["prior_tier2a_gate_reasons"],
            "remaining_gate_reasons": item["source_neutral"]["remaining_gate_reasons"],
        }
        for item in track_row["candidates"]
        if not item["source_neutral"]["eligible"]
    ]
    if not accepted:
        strongest = min(
            track_row["candidates"],
            key=lambda item: (
                len(item["source_neutral"]["remaining_gate_reasons"]),
                _source_neutral_ordering_key(item),
            ),
        )
        return {
            "status": MATCH_UNCERTAIN,
            "policy_rule_id": SOURCE_NEUTRAL_POLICY_ID,
            "selected_video_id": None,
            "selected_candidate_rank": None,
            "uncertainty_reason": (
                "no candidate passes frozen identity/version/duration gates after "
                "treating unknown provenance as neutral"
            ),
            "strongest_rejected_candidate": {
                "video_id": strongest["candidate"]["youtube_video_id"],
                "candidate_rank": strongest["candidate"]["rank"],
                "title": strongest["candidate"].get("title"),
                "decisive_blocker": strongest["source_neutral"]["remaining_gate_reasons"][0],
                "all_blockers": strongest["source_neutral"]["remaining_gate_reasons"],
            },
            "excluded_candidates": excluded,
        }

    selected = accepted[0]
    evidence = selected["tier2a_features"]
    return {
        "status": AUTO_MATCH,
        "policy_rule_id": SOURCE_NEUTRAL_POLICY_ID,
        "selected_video_id": selected["candidate"]["youtube_video_id"],
        "selected_candidate_rank": selected["candidate"]["rank"],
        "selection_reason": (
            "strong recording identity, compatible target-relative version, and frozen "
            "duration gates pass; unknown/OTHER source provenance contributes neutrally"
        ),
        "evidence_summary": {
            "title": evidence["title"],
            "performers": evidence["performers"],
            "versions": evidence["versions"],
            "duration": evidence["duration"],
            "source": evidence["source"],
            "provenance_evidence": selected["source_neutral"]["provenance_evidence"],
            "source_neutral_waivers": selected["source_neutral"]["source_neutral_waivers"],
        },
        "ranked_plausible_candidates": [
            item["candidate"]["youtube_video_id"] for item in accepted
        ],
        "excluded_candidates": excluded,
    }


def evaluate_source_neutral_challenge(
    config_path: Path, *, tier2a_dir: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    tier2a_features, tier2a_decisions, tier2a_hashes = verify_frozen_tier2a(
        config_path, tier2a_dir
    )
    decision_by_id = {
        row["stable_track_id"]: row["decision"] for row in tier2a_decisions["tracks"]
    }
    attempted = [
        extract_source_neutral_track(row)
        for row in tier2a_features["tracks"]
        if decision_by_id[row["track"]["stable_track_id"]]["status"] == MATCH_UNCERTAIN
    ]
    features = {
        "schema_version": SOURCE_NEUTRAL_DATASET_SCHEMA_VERSION,
        "dataset_role": "FROZEN_FRESH_CHALLENGE_AFTER_TIER2A_UNRESOLVED_ONLY",
        "source_tier2a_sha256": tier2a_hashes["tier2_candidate_features.json"],
        "track_count": len(attempted),
        "candidate_pair_count": sum(len(row["candidates"]) for row in attempted),
        "tracks": attempted,
    }

    track_decisions = [
        {
            "stable_track_id": row["track"]["stable_track_id"],
            "decision": resolve_source_neutral_track(row),
        }
        for row in attempted
    ]
    report_dir = load_challenge_config(config_path).artifacts["features"].parent
    sol = _mapped_sol(report_dir)
    human = _human_labels(report_dir)
    selected = []
    for row in track_decisions:
        decision = row["decision"]
        if decision["status"] != AUTO_MATCH:
            continue
        identity = (row["stable_track_id"], decision["selected_video_id"])
        selected.append(
            {
                "stable_track_id": row["stable_track_id"],
                "selected_video_id": decision["selected_video_id"],
                "selected_candidate_rank": decision["selected_candidate_rank"],
                "sol_label": sol.get(identity, {}).get("label"),
                "sol_reason": sol.get(identity, {}).get("recording_identity_reason"),
                "human_label": human.get(identity, {}).get("label"),
                "human_note": human.get(identity, {}).get("note"),
                "evidence_summary": decision["evidence_summary"],
            }
        )

    unresolved = [
        {
            "stable_track_id": row["stable_track_id"],
            **row["decision"]["strongest_rejected_candidate"],
        }
        for row in track_decisions
        if row["decision"]["status"] == MATCH_UNCERTAIN
    ]
    recovered_count = len(selected)
    combined = FROZEN_BALANCED_AUTO_MATCH_COUNT + len(FROZEN_TIER2A_SELECTED) + recovered_count
    sol_counts = Counter(row["sol_label"] or "MISSING" for row in selected)
    human_counts = Counter(row["human_label"] or "MISSING" for row in selected)
    decisions = {
        "schema_version": SOURCE_NEUTRAL_DECISION_SCHEMA_VERSION,
        "policy_id": SOURCE_NEUTRAL_POLICY_ID,
        "production_auto_match_activated": False,
        "frozen_regressions": {
            "balanced_v1": tier2a_decisions["frozen_balanced_regression"],
            "tier2a": {
                "exact_decision_replay": True,
                "policy_id": TIER2_POLICY_ID,
                "auto_match_count": len(FROZEN_TIER2A_SELECTED),
                "match_uncertain_count": len(attempted),
                "selected_video_ids": FROZEN_TIER2A_SELECTED,
            },
        },
        "input_sha256": tier2a_hashes,
        "summary": {
            "source_neutral_attempted_tracks": len(track_decisions),
            "source_neutral_auto_match_count": recovered_count,
            "source_neutral_match_uncertain_count": len(track_decisions) - recovered_count,
            "combined_auto_match_count": combined,
            "combined_match_uncertain_count": 50 - combined,
            "combined_coverage": combined / 50,
            "percentage_point_gain_over_balanced_v1": (combined - 29) / 50 * 100,
            "percentage_point_gain_over_tier2a": recovered_count / 50 * 100,
            "selected_sol_label_counts": dict(sorted(sol_counts.items())),
            "selected_human_label_counts": dict(sorted(human_counts.items())),
            "human_validated_selection_count": sum(
                row["human_label"] is not None for row in selected
            ),
        },
        "selected": selected,
        "remaining_unresolved": unresolved,
        "tracks": track_decisions,
        "scope_guards": {
            "other_source_is_universally_admissible": False,
            "unknown_provenance_contribution": "NEUTRAL",
            "recognized_provenance_contribution": "POSITIVE",
            "duration_close_seconds": 7,
            "official_music_video_very_close_seconds": 2,
            "version_conflicts_are_hard_rejections": True,
            "audio_downloads": 0,
            "video_downloads": 0,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
    }
    return features, decisions


def write_source_neutral_evaluation(
    config_path: Path, *, tier2a_dir: Path, output_dir: Path
) -> tuple[Path, Path, dict[str, Any]]:
    features, decisions = evaluate_source_neutral_challenge(
        config_path, tier2a_dir=tier2a_dir
    )
    feature_path = output_dir / "source_neutral_candidate_features.json"
    decision_path = output_dir / "source_neutral_decisions.json"
    atomic_json(feature_path, features)
    decisions["source_neutral_features_sha256"] = file_sha256(feature_path)
    atomic_json(decision_path, decisions)
    return feature_path, decision_path, decisions
