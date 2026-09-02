"""Frozen Stage 5B.1C-C diagnostic for the final unresolved challenge tail.

This module does not resolve candidates.  It replays and verifies the frozen
Balanced V1 -> 1C-A -> 1C-B cascade, then joins its existing evidence to a
versioned set of qualitative diagnostic annotations.  The annotations explain
what a future experiment might test; they are deliberately not policy rules.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_challenge import load_challenge_config
from .stage5b1b_resolver import MATCH_UNCERTAIN
from .stage5b1c_source_neutral import (
    FROZEN_TIER2A_SELECTED,
    _json_object,
    evaluate_source_neutral_challenge,
)
from .stage5b1c_tier2 import _human_labels, _mapped_sol


DIAGNOSTIC_SCHEMA_VERSION = "stage5b1c-c-remaining-tail-diagnostic-v1"
DIAGNOSTIC_STATUS = "STAGE5B1C_C_DIAGNOSTIC_COMPLETE"

FROZEN_SOURCE_NEUTRAL_HASHES = {
    "source_neutral_candidate_features.json": (
        "f319e4d5288405ba6abdd3c2bde65d56ab429410d2f2a41d185c4d0457a97596"
    ),
    "source_neutral_decisions.json": (
        "67caf7cd35574bb75271e7950f4b5a105c22425804692073f0c630caf68c5eb3"
    ),
}
FROZEN_TIER2_AUDIT_HASHES = {
    "tier2_human_review.csv": (
        "2d98a42513d30fb3ce49f89e481698913fb4ff09b047a6341cbf952cdd7cf2f0"
    ),
    "tier2_human_audit_results.json": (
        "26fbfc59fc7617fd54377fde099cabf9170f2c55946bd3046839ea4e7e8edcb5"
    ),
}
FROZEN_SOURCE_NEUTRAL_SELECTED = {
    "s5b1c_020": "OUkkaqSNduU",
    "s5b1c_022": "oS6wfWu0JvA",
    "s5b1c_025": "9gnyYxEWgi4",
    "s5b1c_028": "k4HWjQNN1K8",
    "s5b1c_044": "DQJpFVzeNp8",
}
FROZEN_UNRESOLVED_IDS = (
    "s5b1c_012",
    "s5b1c_021",
    "s5b1c_023",
    "s5b1c_029",
    "s5b1c_030",
    "s5b1c_032",
    "s5b1c_033",
    "s5b1c_034",
    "s5b1c_040",
    "s5b1c_041",
)

STRONG_METADATA_RECOVERY = "STRONG_METADATA_RECOVERY"
POSSIBLE_METADATA_RECOVERY = "POSSIBLE_METADATA_RECOVERY"
METADATA_INSUFFICIENT = "METADATA_INSUFFICIENT"
CANDIDATE_SET_FAILURE = "CANDIDATE_SET_FAILURE"

_REASON_CATEGORIES = {
    "normalized structural core title does not match": (
        "EXACT_TITLE_REQUIREMENT_OR_PARSER_NORMALIZATION"
    ),
    "primary performer lacks deterministic title/provenance evidence": (
        "PRIMARY_PERFORMER_EVIDENCE"
    ),
    "explicit cover/different-performer evidence": "EXPLICIT_PERFORMER_OR_COVER_CONFLICT",
    "important target version evidence remains absent": (
        "INCOMPLETE_OR_MISSING_VERSION_EVIDENCE"
    ),
    "explicit target-relative version conflict": "EXPLICIT_VERSION_CONFLICT",
    "duration exceeds frozen Balanced DURATION_CLOSE boundary": "DURATION_THRESHOLD",
    "music-video duration exceeds frozen Balanced DURATION_VERY_CLOSE boundary": (
        "OFFICIAL_MUSIC_VIDEO_DURATION_RESTRICTION"
    ),
    "Tier 2A does not allow OTHER-source fallback": "SOURCE_CLASSIFICATION_OTHER_REJECTION",
    "lyric fallback lacks frozen Balanced relative-view support": (
        "LYRIC_FALLBACK_PROVENANCE_OR_VIEW_SUPPORT"
    ),
    "duration evidence is unavailable": "MISSING_DURATION_EVIDENCE",
}


# These are frozen research annotations over already-frozen evidence.  They are
# intentionally track-specific because this is a retrospective case analysis,
# not runtime resolver code.  A future policy must be designed and validated in
# a separate goal.
FROZEN_DIAGNOSTIC_ASSESSMENTS: dict[str, dict[str, Any]] = {
    "s5b1c_012": {
        "strongest_candidate_video_id": "kxZYxojih3E",
        "primary_failed_gate": "EXACT_TITLE_REQUIREMENT_OR_PARSER_NORMALIZATION",
        "primary_blocker": "resolver/parsing limitation",
        "additional_blocker_categories": [],
        "recoverability": STRONG_METADATA_RECOVERY,
        "explanation": (
            "The candidate contains the correct song and complete credited lineup, has no "
            "version conflict, and differs by 0.5 seconds. The parser leaves artist/feature "
            "text inside the structural title; source neutrality cannot repair that split."
        ),
        "sol_comparison": (
            "Sol marked the candidate ACCEPTABLE by interpreting the artist prefix and "
            "Spanish lyric-video wording contextually. The same reasoning is likely "
            "encodable deterministically."
        ),
        "sol_gap_category": "RESOLVER_COULD_ENCODE_SAME_REASONING_DETERMINISTICALLY",
        "recommended_route": "metadata_parser_experiment",
    },
    "s5b1c_021": {
        "strongest_candidate_video_id": "rqVg1PpPSj8",
        "primary_failed_gate": "EXPLICIT_VERSION_CONFLICT",
        "primary_blocker": "bad search candidates",
        "additional_blocker_categories": ["CANDIDATE_SET_QUALITY", "DURATION_THRESHOLD"],
        "recoverability": CANDIDATE_SET_FAILURE,
        "explanation": (
            "Every result is a different named remix or a mashup. No candidate identifies "
            "the requested FISHER remix, so relaxing resolution would select a known wrong "
            "recording."
        ),
        "sol_comparison": "Sol independently marked all five candidates WRONG.",
        "sol_gap_category": "CANDIDATE_SET_ITSELF_INADEQUATE",
        "recommended_route": "targeted_second_search",
    },
    "s5b1c_023": {
        "strongest_candidate_video_id": "1UESu4eyalA",
        "primary_failed_gate": "DURATION_THRESHOLD",
        "primary_blocker": "policy threshold limitation",
        "additional_blocker_categories": [],
        "recoverability": STRONG_METADATA_RECOVERY,
        "explanation": (
            "Rank 1 is an Official Audio from Tiesto's channel with exact title, performer, "
            "and named-remix MATCH evidence and no conflicts. Its only failed gate is a "
            "14.764-second duration delta. The mechanically closest rejected candidate is "
            "the wrong original mix, demonstrating why identity must outrank duration."
        ),
        "sol_comparison": (
            "Sol marked rank 1 IDEAL. Its judgment weights exact named-version and official "
            "source evidence above the isolated duration delta; that hierarchy is likely "
            "encodable as a narrow deterministic experiment."
        ),
        "sol_gap_category": "RESOLVER_COULD_ENCODE_SAME_REASONING_DETERMINISTICALLY",
        "recommended_route": "evidence_conditioned_duration_experiment",
    },
    "s5b1c_029": {
        "strongest_candidate_video_id": "N2K1LUWlF-4",
        "primary_failed_gate": "INCOMPLETE_OR_MISSING_VERSION_EVIDENCE",
        "primary_blocker": "bad search candidates",
        "additional_blocker_categories": [
            "VENUE_OR_PERFORMANCE_IDENTITY",
            "DURATION_THRESHOLD",
            "CANDIDATE_SET_QUALITY",
        ],
        "recoverability": CANDIDATE_SET_FAILURE,
        "explanation": (
            "Only rank 1 names the Ryman, but it is 66 seconds shorter and supplies no date "
            "or release identity. The remaining results identify other venues/dates or a "
            "generic live performance. None safely establishes the 2023 Live at the Ryman "
            "album recording."
        ),
        "sol_comparison": (
            "Sol was UNCERTAIN on the Ryman result and generic live result and WRONG on the "
            "three explicitly different performances; contextual reasoning cannot recover "
            "missing performance identity."
        ),
        "sol_gap_category": "CANDIDATE_SET_ITSELF_INADEQUATE",
        "recommended_route": "targeted_second_search",
    },
    "s5b1c_030": {
        "strongest_candidate_video_id": "5_KBkAjyCOg",
        "primary_failed_gate": "DURATION_THRESHOLD",
        "primary_blocker": "missing metadata",
        "additional_blocker_categories": [
            "EXACT_TITLE_REQUIREMENT_OR_PARSER_NORMALIZATION",
            "GENUINE_MULTI_VERSION_OR_RECORDING_AMBIGUITY",
        ],
        "recoverability": METADATA_INSUFFICIENT,
        "explanation": (
            "Several titles claim Bastille's acoustic version, but the plausible uploads are "
            "35-41 seconds shorter than the target and lack canonical release provenance. "
            "The sole Art Track is explicitly by another performer. Parsing the title would "
            "not establish which acoustic recording is present."
        ),
        "sol_comparison": (
            "Sol marked the live and wrong-performer candidates WRONG and the three plausible "
            "Bastille uploads UNCERTAIN. The missing recording identity affects both systems."
        ),
        "sol_gap_category": "METADATA_INSUFFICIENT_EVEN_FOR_SOL",
        "recommended_route": "targeted_search_then_audio_comparison",
    },
    "s5b1c_032": {
        "strongest_candidate_video_id": "k4M53xndqiU",
        "primary_failed_gate": "INCOMPLETE_OR_MISSING_VERSION_EVIDENCE",
        "primary_blocker": "bad search candidates",
        "additional_blocker_categories": [
            "REMASTER_OR_REISSUE_AMBIGUITY",
            "CANDIDATE_SET_QUALITY",
        ],
        "recoverability": CANDIDATE_SET_FAILURE,
        "explanation": (
            "The closest Art Track explicitly describes the 1975 album release, not the "
            "requested 2015 remaster. Every other result is a live/performance recording or "
            "otherwise wrong. The requested version is not established anywhere in top 5."
        ),
        "sol_comparison": "Sol independently marked all five candidates WRONG.",
        "sol_gap_category": "CANDIDATE_SET_ITSELF_INADEQUATE",
        "recommended_route": "targeted_second_search",
    },
    "s5b1c_033": {
        "strongest_candidate_video_id": "D2gWc5Sw75w",
        "primary_failed_gate": "INCOMPLETE_OR_MISSING_VERSION_EVIDENCE",
        "primary_blocker": "missing metadata",
        "additional_blocker_categories": ["REMASTER_OR_REISSUE_AMBIGUITY"],
        "recoverability": METADATA_INSUFFICIENT,
        "explanation": (
            "The duration-matched generic upload and near-duration Official Audio do not "
            "identify the 2022 remaster. Other results are an alternate version, edited music "
            "video, or live performance. Metadata cannot establish the master of the two "
            "otherwise plausible studio uploads."
        ),
        "sol_comparison": (
            "Sol marked the two studio-like uploads UNCERTAIN and all explicit alternatives "
            "WRONG, matching the deterministic information limit."
        ),
        "sol_gap_category": "METADATA_INSUFFICIENT_EVEN_FOR_SOL",
        "recommended_route": "targeted_search_or_audio_comparison",
    },
    "s5b1c_034": {
        "strongest_candidate_video_id": "2dzf4T3RbEc",
        "primary_failed_gate": "INCOMPLETE_OR_MISSING_VERSION_EVIDENCE",
        "primary_blocker": "missing metadata",
        "additional_blocker_categories": [
            "EXACT_TITLE_REQUIREMENT_OR_PARSER_NORMALIZATION",
            "REMASTER_OR_REISSUE_AMBIGUITY",
        ],
        "recoverability": POSSIBLE_METADATA_RECOVERY,
        "explanation": (
            "The official Art Track 'Single Version' is 1.4 seconds from the target and Sol "
            "finds it compatible with the Greatest Hits presentation, but frozen metadata "
            "does not explicitly equate Single Version with 2000 Remaster. The closer Dolby "
            "Atmos Art Track is explicitly a different mix. A deterministic equivalence "
            "would require independently grounded release metadata, not title inference."
        ),
        "sol_comparison": (
            "Sol marked the Single Version ACCEPTABLE through contextual album/duration "
            "reasoning. This is a semantic advantage, but the equivalence is not proven by "
            "the supplied fields."
        ),
        "sol_gap_category": "SOL_CONTEXTUAL_EVIDENCE_WEIGHTING_ADVANTAGE",
        "recommended_route": "structured_release_equivalence_experiment",
    },
    "s5b1c_040": {
        "strongest_candidate_video_id": "G-1IQJvNQLk",
        "primary_failed_gate": "DURATION_THRESHOLD",
        "primary_blocker": "bad search candidates",
        "additional_blocker_categories": [
            "MODIFIED_AUDIO_INDICATORS",
            "CANDIDATE_SET_QUALITY",
        ],
        "recoverability": CANDIDATE_SET_FAILURE,
        "explanation": (
            "All five results are third-party slowed edits. The nominally matching uploads "
            "are 14-19 seconds shorter than the specific 2022 release; the close-duration "
            "alternatives add reverb or clean edits. No result establishes the released "
            "Slowed Down recording."
        ),
        "sol_comparison": "Sol independently marked all five candidates WRONG.",
        "sol_gap_category": "CANDIDATE_SET_ITSELF_INADEQUATE",
        "recommended_route": "targeted_second_search",
    },
    "s5b1c_041": {
        "strongest_candidate_video_id": "fXbfBUNJ9mY",
        "primary_failed_gate": "DURATION_THRESHOLD",
        "primary_blocker": "genuine recording ambiguity",
        "additional_blocker_categories": ["MODIFIED_AUDIO_INDICATORS"],
        "recoverability": POSSIBLE_METADATA_RECOVERY,
        "explanation": (
            "Rank 1 exactly names the song, performer, slowed, and reverb descriptors, but is "
            "15 seconds longer than the target and is an unofficial lyric upload. Multiple "
            "other slowed/reverb edits have materially different durations, so matching "
            "tokens alone cannot identify the exact modification rate."
        ),
        "sol_comparison": (
            "Sol was UNCERTAIN on ranks 1 and 4 and WRONG on the more divergent edits. A "
            "version-aware duration experiment is conceivable, but metadata alone does not "
            "currently establish recording equivalence."
        ),
        "sol_gap_category": "METADATA_INSUFFICIENT_EVEN_FOR_SOL",
        "recommended_route": "tier3_audio_comparison",
    },
}


def _candidate_by_video_id(track: dict[str, Any], video_id: str) -> dict[str, Any]:
    matches = [
        row for row in track["candidates"]
        if row["candidate"]["youtube_video_id"] == video_id
    ]
    if len(matches) != 1:
        raise Stage5B1AValidationError(
            f"expected one candidate {video_id!r} for {track['track']['stable_track_id']}"
        )
    return matches[0]


def _reason_category(reason: str) -> str:
    try:
        return _REASON_CATEGORIES[reason]
    except KeyError as exc:
        raise Stage5B1AValidationError(f"unmapped frozen gate reason: {reason}") from exc


def _gate_categories(candidate: dict[str, Any]) -> list[str]:
    return [
        _reason_category(reason)
        for reason in candidate["source_neutral"]["remaining_gate_reasons"]
    ]


def verify_frozen_source_neutral(
    config_path: Path, tier2a_dir: Path, source_neutral_dir: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """Verify committed 1C-B bytes and deterministic cascade replay."""

    hashes = {
        name: file_sha256(source_neutral_dir / name)
        for name in FROZEN_SOURCE_NEUTRAL_HASHES
    }
    if hashes != FROZEN_SOURCE_NEUTRAL_HASHES:
        raise Stage5B1AValidationError("frozen Stage 5B.1C-B artifacts changed")

    committed_features = _json_object(
        source_neutral_dir / "source_neutral_candidate_features.json"
    )
    committed_decisions = _json_object(
        source_neutral_dir / "source_neutral_decisions.json"
    )
    replayed_features, replayed_decisions = evaluate_source_neutral_challenge(
        config_path, tier2a_dir=tier2a_dir
    )
    if replayed_features != committed_features:
        raise Stage5B1AValidationError("frozen Stage 5B.1C-B feature replay changed")
    comparable = dict(committed_decisions)
    comparable.pop("source_neutral_features_sha256", None)
    if replayed_decisions != comparable:
        raise Stage5B1AValidationError("frozen Stage 5B.1C-B decision replay changed")
    selected = {
        row["stable_track_id"]: row["selected_video_id"]
        for row in committed_decisions["selected"]
    }
    if selected != FROZEN_SOURCE_NEUTRAL_SELECTED:
        raise Stage5B1AValidationError("frozen Stage 5B.1C-B selected candidates changed")
    return committed_features, committed_decisions, hashes


def verify_frozen_tier2_human_audit(source_neutral_dir: Path) -> dict[str, Any]:
    hashes = {
        name: file_sha256(source_neutral_dir / name)
        for name in FROZEN_TIER2_AUDIT_HASHES
    }
    if hashes != FROZEN_TIER2_AUDIT_HASHES:
        raise Stage5B1AValidationError("frozen Tier-2 human-audit evidence changed")
    results = _json_object(source_neutral_dir / "tier2_human_audit_results.json")
    expected = {
        "reviewed_judgments": 11,
        "ideal_count": 5,
        "acceptable_count": 6,
        "wrong_count": 0,
        "uncertain_count": 0,
        "safe_count": 11,
    }
    if any(results["summary"].get(key) != value for key, value in expected.items()):
        raise Stage5B1AValidationError("frozen Tier-2 human-audit summary changed")
    return {"sha256": hashes, "summary": expected, "status": results["status"]}


def _candidate_record(
    stable_id: str,
    candidate: dict[str, Any],
    sol: dict[tuple[str, str], dict[str, Any]],
    human: dict[tuple[str, str], dict[str, str]],
) -> dict[str, Any]:
    raw = candidate["candidate"]
    identity = (stable_id, raw["youtube_video_id"])
    sol_row = sol.get(identity)
    human_row = human.get(identity)
    return {
        "candidate": raw,
        "tier2a_features": candidate["tier2a_features"],
        "source_neutral_features": candidate["source_neutral"],
        "failed_gate_categories": _gate_categories(candidate),
        "frozen_sol_evidence": (
            {
                "label": sol_row.get("label"),
                "recording_identity_reason": sol_row.get("recording_identity_reason"),
                "source_quality_reason": sol_row.get("source_quality_reason"),
                "uncertainty_reason": sol_row.get("uncertainty_reason"),
            }
            if sol_row else None
        ),
        "frozen_human_evidence": human_row,
    }


def build_remaining_tail_diagnostic(
    config_path: Path, *, tier2a_dir: Path, source_neutral_dir: Path
) -> dict[str, Any]:
    features, decisions, source_hashes = verify_frozen_source_neutral(
        config_path, tier2a_dir, source_neutral_dir
    )
    audit = verify_frozen_tier2_human_audit(source_neutral_dir)

    unresolved = tuple(
        row["stable_track_id"]
        for row in decisions["tracks"]
        if row["decision"]["status"] == MATCH_UNCERTAIN
    )
    if unresolved != FROZEN_UNRESOLVED_IDS:
        raise Stage5B1AValidationError(
            f"frozen unresolved tail changed: expected {FROZEN_UNRESOLVED_IDS}, got {unresolved}"
        )
    if set(FROZEN_DIAGNOSTIC_ASSESSMENTS) != set(unresolved):
        raise Stage5B1AValidationError("diagnostic annotations do not cover frozen tail")

    report_dir = load_challenge_config(config_path).artifacts["features"].parent
    sol = _mapped_sol(report_dir)
    human = _human_labels(report_dir)
    tracks_by_id = {row["track"]["stable_track_id"]: row for row in features["tracks"]}
    incomplete_candidate_sets = {
        stable_id: len(tracks_by_id[stable_id]["candidates"])
        for stable_id in unresolved
        if len(tracks_by_id[stable_id]["candidates"]) != 5
    }
    if incomplete_candidate_sets:
        raise Stage5B1AValidationError(
            f"frozen unresolved candidate counts changed: {incomplete_candidate_sets}"
        )
    frozen_mechanical = {
        row["stable_track_id"]: row for row in decisions["remaining_unresolved"]
    }

    tracks = []
    strongest_gate_counts: Counter[str] = Counter()
    primary_gate_counts: Counter[str] = Counter()
    blocker_combo_counts: Counter[str] = Counter()
    any_candidate_track_counts: Counter[str] = Counter()
    recoverability_counts: Counter[str] = Counter()
    sol_gap_counts: Counter[str] = Counter()
    primary_blocker_counts: Counter[str] = Counter()
    additional_blocker_counts: Counter[str] = Counter()
    for stable_id in unresolved:
        source_track = tracks_by_id[stable_id]
        assessment = FROZEN_DIAGNOSTIC_ASSESSMENTS[stable_id]
        strongest = _candidate_by_video_id(
            source_track, assessment["strongest_candidate_video_id"]
        )
        strongest_categories = _gate_categories(strongest)
        if assessment["primary_failed_gate"] not in strongest_categories:
            raise Stage5B1AValidationError(
                f"primary failed gate is not present for {stable_id} strongest candidate"
            )
        strongest_gate_counts.update(strongest_categories)
        primary_gate_counts.update([assessment["primary_failed_gate"]])
        blocker_combo_counts.update([" + ".join(sorted(strongest_categories))])
        any_categories = {
            category
            for candidate in source_track["candidates"]
            for category in _gate_categories(candidate)
        }
        any_candidate_track_counts.update(any_categories)
        recoverability_counts.update([assessment["recoverability"]])
        sol_gap_counts.update([assessment["sol_gap_category"]])
        primary_blocker_counts.update([assessment["primary_blocker"]])
        additional_blocker_counts.update(assessment["additional_blocker_categories"])
        candidate_records = [
            _candidate_record(stable_id, candidate, sol, human)
            for candidate in source_track["candidates"]
        ]
        strongest_record = next(
            row for row in candidate_records
            if row["candidate"]["youtube_video_id"]
            == assessment["strongest_candidate_video_id"]
        )
        tracks.append(
            {
                "stable_track_id": stable_id,
                "target": source_track["track"],
                "query": source_track.get("query"),
                "frozen_mechanical_strongest_rejected": frozen_mechanical[stable_id],
                "diagnostic_strongest_candidate": strongest_record,
                "all_failed_gates_for_strongest": strongest_categories,
                "primary_failed_gate": assessment["primary_failed_gate"],
                "primary_blocker": assessment["primary_blocker"],
                "additional_blocker_categories": assessment[
                    "additional_blocker_categories"
                ],
                "recoverability": assessment["recoverability"],
                "explanation": assessment["explanation"],
                "sol_comparison": assessment["sol_comparison"],
                "sol_gap_category": assessment["sol_gap_category"],
                "recommended_route": assessment["recommended_route"],
                "all_five_candidates": candidate_records,
            }
        )

    strong = recoverability_counts[STRONG_METADATA_RECOVERY]
    possible = recoverability_counts[POSSIBLE_METADATA_RECOVERY]
    current_auto = decisions["summary"]["combined_auto_match_count"]
    return {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "status": DIAGNOSTIC_STATUS,
        "diagnostic_only": True,
        "resolver_policy_changed": False,
        "input_sha256": {
            "stage5b1c_b": source_hashes,
            "tier2_human_audit": audit["sha256"],
        },
        "frozen_regression": {
            "balanced_v1": {
                "auto_match_count": 29,
                "match_uncertain_count": 21,
                "exact_selected_candidate_replay": True,
            },
            "stage5b1c_a": {
                "incremental_auto_match_count": len(FROZEN_TIER2A_SELECTED),
                "selected_video_ids": FROZEN_TIER2A_SELECTED,
                "exact_selected_candidate_replay": True,
            },
            "stage5b1c_b": {
                "incremental_auto_match_count": len(FROZEN_SOURCE_NEUTRAL_SELECTED),
                "selected_video_ids": FROZEN_SOURCE_NEUTRAL_SELECTED,
                "exact_selected_candidate_replay": True,
            },
            "combined": {
                "auto_match_count": current_auto,
                "match_uncertain_count": len(unresolved),
                "coverage": current_auto / 50,
            },
            "tier2_human_audit": audit,
        },
        "confirmed_unresolved_track_ids": list(unresolved),
        "summary": {
            "unresolved_track_count": len(unresolved),
            "candidate_pair_count": sum(
                len(track["all_five_candidates"]) for track in tracks
            ),
            "recoverability_counts": dict(sorted(recoverability_counts.items())),
            "strongest_candidate_failed_gate_track_counts": dict(
                sorted(strongest_gate_counts.items())
            ),
            "primary_failed_gate_track_counts": dict(sorted(primary_gate_counts.items())),
            "common_strongest_candidate_blocker_combinations": dict(
                sorted(blocker_combo_counts.items())
            ),
            "tracks_with_gate_on_any_candidate": dict(
                sorted(any_candidate_track_counts.items())
            ),
            "sol_gap_counts": dict(sorted(sol_gap_counts.items())),
            "primary_blocker_counts": dict(sorted(primary_blocker_counts.items())),
            "additional_blocker_counts": dict(sorted(additional_blocker_counts.items())),
            "current_coverage": {"auto_match": current_auto, "total": 50, "rate": 0.80},
            "hypothetical_strong_only_ceiling": {
                "auto_match": current_auto + strong,
                "total": 50,
                "rate": (current_auto + strong) / 50,
            },
            "hypothetical_strong_plus_possible_ceiling": {
                "auto_match": current_auto + strong + possible,
                "total": 50,
                "rate": (current_auto + strong + possible) / 50,
            },
            "ceiling_is_diagnostic_not_validated_coverage": True,
        },
        "tracks": tracks,
        "recommended_next_experiment": {
            "scope": (
                "A separately specified metadata experiment for structural title parsing "
                "and evidence-conditioned duration only; do not treat the possible cases "
                "as validated recoveries."
            ),
            "strong_targets": ["s5b1c_012", "s5b1c_023"],
            "possible_but_risky_targets": ["s5b1c_034", "s5b1c_041"],
            "targeted_second_search": [
                "s5b1c_021", "s5b1c_029", "s5b1c_032", "s5b1c_040"
            ],
            "audio_comparison_or_better_discovery": [
                "s5b1c_030", "s5b1c_033", "s5b1c_041"
            ],
            "remain_unresolved_without_new_evidence": [
                "s5b1c_030", "s5b1c_033", "s5b1c_034", "s5b1c_041"
            ],
        },
        "scope_guards": {
            "new_policy_implemented": False,
            "duration_threshold_changed": False,
            "version_equivalence_added": False,
            "resolver_features_changed": False,
            "yt_dlp_searches": 0,
            "sol_runs": 0,
            "human_labels_changed": False,
            "audio_downloads": 0,
            "video_downloads": 0,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
    }


def write_remaining_tail_diagnostic(
    config_path: Path,
    *,
    tier2a_dir: Path,
    source_neutral_dir: Path,
    output_path: Path,
) -> dict[str, Any]:
    diagnostic = build_remaining_tail_diagnostic(
        config_path,
        tier2a_dir=tier2a_dir,
        source_neutral_dir=source_neutral_dir,
    )
    atomic_json(output_path, diagnostic)
    return diagnostic
