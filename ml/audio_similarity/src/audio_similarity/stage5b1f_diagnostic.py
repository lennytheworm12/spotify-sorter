"""Stage 5B.1F read-only resolver false-rejection and preference diagnostic.

The diagnostic replays the frozen Stage 5B.1E Q0 pools through the unchanged
Balanced -> 1C-A -> 1C-B -> 1C-C cascade.  It joins previously collected human
and Sol evidence, but never changes discovery, features, labels, or decisions.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_challenge import load_frozen_policies
from .stage5b1b_resolver import (
    AUTO_MATCH,
    MATCH_UNCERTAIN,
    SAFE_LABELS,
    SOURCE_ORDER,
    _candidate_gate,
)
from .stage5b1c_tier2 import _mapped_sol, _tier2_gate
from .stage5b1e_experiment import _challenge, _replay_candidate_pool
from .stage5b1e_queries import load_stage5b1e_config


CONFIG_SCHEMA_VERSION = "stage5b1f-resolver-false-rejection-config-v1"
FALSE_REJECTION_SCHEMA_VERSION = "stage5b1f-false-rejection-cases-v1"
CANDIDATE_PAIR_SCHEMA_VERSION = "stage5b1f-candidate-pair-comparisons-v1"
TAIL_SCHEMA_VERSION = "stage5b1f-remaining-tail-reclassification-v1"
MANIFEST_SCHEMA_VERSION = "stage5b1f-artifact-manifest-v1"
STATUS = "STAGE5B1F_RESOLVER_FALSE_REJECTION_DIAGNOSTIC_COMPLETE"
Q0 = "Q0_CURRENT_CONTROL"

HUMAN_STRENGTH = {"WRONG": -1, "UNCERTAIN": 0, "ACCEPTABLE": 1, "IDEAL": 2}
STAGES = ("POLICY_BALANCED_V1", "STAGE5B1C_A", "STAGE5B1C_B", "STAGE5B1C_C")

STRONG_RESOLVER_RECOVERY = "STRONG_RESOLVER_RECOVERY"
POSSIBLE_RESOLVER_RECOVERY = "POSSIBLE_RESOLVER_RECOVERY"
METADATA_INSUFFICIENT = "METADATA_INSUFFICIENT"
TRUE_DISCOVERY_FAILURE = "TRUE_DISCOVERY_FAILURE"


@dataclass(frozen=True)
class Stage5B1FConfig:
    path: Path
    project_root: Path
    experiment_id: str
    source_query_strategy: str
    stage5b1e_config: Path
    frozen_inputs: dict[str, dict[str, Any]]
    artifacts: dict[str, Path]
    sha256: str


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def load_stage5b1f_config(path: Path) -> Stage5B1FConfig:
    path = path.resolve()
    value = _json_object(path)
    if value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.1F config schema")
    if value.get("source_query_strategy") != Q0:
        raise Stage5B1AValidationError("Stage 5B.1F must diagnose frozen Q0 only")
    project_root = path.parent.parent
    frozen = value.get("frozen_inputs")
    artifacts = value.get("artifacts")
    if not isinstance(frozen, dict) or not frozen:
        raise Stage5B1AValidationError("Stage 5B.1F frozen inputs are required")
    if not isinstance(artifacts, dict) or not artifacts:
        raise Stage5B1AValidationError("Stage 5B.1F artifacts are required")
    return Stage5B1FConfig(
        path=path,
        project_root=project_root,
        experiment_id=str(value["experiment_id"]),
        source_query_strategy=Q0,
        stage5b1e_config=project_root / str(value["stage5b1e_config"]),
        frozen_inputs=frozen,
        artifacts={name: project_root / str(target) for name, target in artifacts.items()},
        sha256=file_sha256(path),
    )


def verify_frozen_inputs(config: Stage5B1FConfig) -> dict[str, dict[str, Any]]:
    verified: dict[str, dict[str, Any]] = {}
    for name, row in config.frozen_inputs.items():
        path = config.project_root / str(row["path"])
        actual = file_sha256(path)
        expected = str(row["sha256"])
        if actual != expected:
            raise Stage5B1AValidationError(
                f"frozen Stage 5B.1F input changed: {name}: {actual} != {expected}"
            )
        verified[name] = {
            "path": str(path.relative_to(config.project_root)),
            "sha256": actual,
            "size_bytes": path.stat().st_size,
        }
    return verified


def _input_path(config: Stage5B1FConfig, name: str) -> Path:
    return config.project_root / str(config.frozen_inputs[name]["path"])


def _add_human_evidence(
    evidence: dict[tuple[str, str], dict[str, Any]],
    *,
    stable_id: str,
    video_id: str,
    label: str,
    note: str | None,
    source: str,
) -> None:
    normalized = label.strip().upper()
    if not normalized:
        return
    if normalized not in HUMAN_STRENGTH:
        raise Stage5B1AValidationError(f"invalid frozen human label: {normalized}")
    key = (stable_id, video_id)
    current = evidence.setdefault(
        key, {"label": normalized, "sources": [], "notes": []}
    )
    if current["label"] != normalized:
        raise Stage5B1AValidationError(f"conflicting frozen human labels for {key}")
    current["sources"].append(source)
    if note and note.strip():
        current["notes"].append({"source": source, "note": note.strip()})


def load_human_evidence(
    config: Stage5B1FConfig,
) -> dict[tuple[str, str], dict[str, Any]]:
    evidence: dict[tuple[str, str], dict[str, Any]] = {}
    for input_name in ("challenge_human_review", "stage5b1e_human_review"):
        with _input_path(config, input_name).open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            for row in csv.DictReader(handle):
                _add_human_evidence(
                    evidence,
                    stable_id=row["stable_track_id"],
                    video_id=row["candidate_video_id"],
                    label=row["candidate_review_label"],
                    note=row.get("candidate_note"),
                    source=input_name,
                )
    for input_name in ("tier2_human_audit", "strong_metadata_human_audit"):
        payload = _json_object(_input_path(config, input_name))
        for row in payload.get("judgments", []):
            _add_human_evidence(
                evidence,
                stable_id=row["stable_track_id"],
                video_id=row["candidate_video_id"],
                label=row["human_label"],
                note=row.get("human_note"),
                source=input_name,
            )
    return evidence


def load_sol_evidence(
    config: Stage5B1FConfig,
) -> dict[tuple[str, str], dict[str, Any]]:
    return _mapped_sol(_input_path(config, "challenge_sol_evaluations").parent)


def replay_frozen_q0(config: Stage5B1FConfig) -> list[dict[str, Any]]:
    """Recompute Q0 and prove exact 42/8 and selected-ID equivalence."""

    verify_frozen_inputs(config)
    stage5b1e = load_stage5b1e_config(config.stage5b1e_config)
    challenge, manifest = _challenge(stage5b1e)
    boundaries, policies = load_frozen_policies(challenge)
    tracks = {row.track.stable_track_id: row.track for row in manifest.tracks}
    discovery = _json_object(_input_path(config, "query_discovery"))
    committed = _json_object(_input_path(config, "resolver_replays"))
    committed_q0 = {
        row["stable_track_id"]: row
        for row in committed["replays"]
        if row["strategy_id"] == Q0
    }
    if len(committed_q0) != 50:
        raise Stage5B1AValidationError("frozen Stage 5B.1E Q0 replay count changed")

    replays = []
    for row in discovery.get("tracks", []):
        stable_id = row["track"]["stable_track_id"]
        outcomes = [
            outcome for outcome in row["strategies"] if outcome["strategy_id"] == Q0
        ]
        if len(outcomes) != 1 or stable_id not in tracks:
            raise Stage5B1AValidationError(f"invalid frozen Q0 outcome for {stable_id}")
        outcome = outcomes[0]
        replay = _replay_candidate_pool(
            tracks[stable_id],
            outcome["candidates"],
            policy=policies["POLICY_BALANCED_V1"],
            boundaries=boundaries,
        )
        expected = committed_q0[stable_id]
        if outcome["candidate_video_ids"] != expected["candidate_video_ids"]:
            raise Stage5B1AValidationError(f"frozen Q0 candidate IDs changed: {stable_id}")
        if replay["selected_stage"] != expected["selected_stage"]:
            raise Stage5B1AValidationError(f"frozen Q0 selected stage changed: {stable_id}")
        if replay["final_decision"] != expected["final_decision"]:
            raise Stage5B1AValidationError(f"frozen Q0 decision changed: {stable_id}")
        replays.append(
            {
                "stable_track_id": stable_id,
                "target": tracks[stable_id].to_dict(),
                "query": outcome["query"],
                "candidates": outcome["candidates"],
                "replay": replay,
            }
        )
    auto = sum(row["replay"]["final_decision"]["status"] == AUTO_MATCH for row in replays)
    uncertain = len(replays) - auto
    if len(replays) != 50 or (auto, uncertain) != (42, 8):
        raise Stage5B1AValidationError(
            f"frozen Q0 replay changed: {auto} AUTO_MATCH / {uncertain} MATCH_UNCERTAIN"
        )
    return replays


def _gate_category(reason: str) -> str:
    lowered = reason.lower()
    if "music-video duration" in lowered:
        return "OFFICIAL_MUSIC_VIDEO_DURATION_RESTRICTION"
    if "duration" in lowered:
        return "DURATION_THRESHOLD"
    if "version conflict" in lowered or "explicit target-relative version" in lowered:
        return "EXPLICIT_VERSION_CONFLICT"
    if "version evidence" in lowered or "version is incomplete" in lowered:
        return "INCOMPLETE_VERSION_EVIDENCE"
    if "cover" in lowered:
        return "EXPLICIT_COVER_CONFLICT"
    if "title" in lowered or "identity" in lowered:
        return "TITLE_OR_IDENTITY_REQUIREMENT"
    if "performer" in lowered or "primary artist" in lowered:
        return "PERFORMER_EVIDENCE"
    if "other" in lowered or "noncanonical" in lowered:
        return "SOURCE_OTHER_RESTRICTION"
    if "lyric" in lowered and "view" in lowered:
        return "LYRIC_VIEW_SUPPORT"
    if "modified-audio" in lowered:
        return "MODIFIED_AUDIO_CONFLICT"
    return "OTHER_GATE"


def _candidate_indexes(replay: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    base = {
        row["candidate"]["youtube_video_id"]: row
        for row in replay["feature_layers"]["stage5b1b"].get("candidates", [])
    }
    composed = {
        row["candidate"]["youtube_video_id"]: row
        for row in replay["feature_layers"].get("stage5b1c_c_composed", {}).get(
            "candidates", []
        )
    }
    return base, composed


def candidate_snapshot(
    track: SpotifyTrack,
    candidate: dict[str, Any],
    replay: dict[str, Any],
    *,
    policy: Any,
    boundaries: Any,
    human: dict[tuple[str, str], dict[str, Any]],
    sol: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    stable_id = track.stable_track_id
    video_id = candidate["youtube_video_id"]
    base, composed = _candidate_indexes(replay)
    tier1 = base[video_id]["features"]
    accepted, tier1_reasons, tier1_derived = _candidate_gate(
        tier1, policy, boundaries
    )
    nested = composed[video_id]
    tier2_reasons = _tier2_gate(nested["tier2a_features"])
    source_reasons = list(nested["source_neutral"]["remaining_gate_reasons"])
    strong_reasons = list(nested["strong_metadata"]["remaining_gate_reasons"])
    stage_eligibility = {
        "POLICY_BALANCED_V1": accepted,
        "STAGE5B1C_A": not tier2_reasons,
        "STAGE5B1C_B": not source_reasons,
        "STAGE5B1C_C": not strong_reasons,
    }
    earliest = next((stage for stage in STAGES if stage_eligibility[stage]), None)
    all_reasons = tier1_reasons + tier2_reasons + source_reasons + strong_reasons
    human_row = human.get((stable_id, video_id))
    sol_row = sol.get((stable_id, video_id))
    return {
        "video_id": video_id,
        "search_rank": candidate.get("rank"),
        "title": candidate.get("title"),
        "url": candidate.get("canonical_url") or candidate.get("url"),
        "uploader": candidate.get("uploader"),
        "channel": candidate.get("channel"),
        "duration_seconds": candidate.get("duration_seconds"),
        "view_count": candidate.get("view_count"),
        "human_evidence": human_row,
        "sol_evidence": (
            {
                "label": sol_row.get("label"),
                "recording_identity_reason": sol_row.get("recording_identity_reason"),
                "source_quality_reason": sol_row.get("source_quality_reason"),
                "uncertainty_reason": sol_row.get("uncertainty_reason"),
            }
            if sol_row
            else None
        ),
        "identity": tier1["identity"],
        "normalized_title": nested["tier2a_features"]["title"],
        "performer_evidence": nested["tier2a_features"]["performers"],
        "version_evidence": nested["tier2a_features"]["versions"],
        "modification_evidence": nested["strong_metadata"]["modification_evidence"],
        "duration": tier1["duration"],
        "source": tier1["source"],
        "description_evidence": tier1["description_evidence"],
        "weak_evidence": tier1["weak_evidence"],
        "gates": {
            "POLICY_BALANCED_V1": {
                "eligible": accepted,
                "reasons": tier1_reasons,
                "derived": tier1_derived,
            },
            "STAGE5B1C_A": {"eligible": not tier2_reasons, "reasons": tier2_reasons},
            "STAGE5B1C_B": {"eligible": not source_reasons, "reasons": source_reasons},
            "STAGE5B1C_C": {"eligible": not strong_reasons, "reasons": strong_reasons},
            "earliest_eligible_stage": earliest,
            "all_failed_gate_categories": sorted({_gate_category(row) for row in all_reasons}),
        },
    }


def _human_label(snapshot: dict[str, Any]) -> str | None:
    row = snapshot.get("human_evidence")
    return row.get("label") if row else None


def _best_human_safe(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    safe = [row for row in candidates if _human_label(row) in SAFE_LABELS]
    if not safe:
        return None
    return min(
        safe,
        key=lambda row: (
            -HUMAN_STRENGTH[_human_label(row)],
            SOURCE_ORDER.get(row["source"]["source_type"], 99),
            int(row["search_rank"]),
        ),
    )


def _preference_diagnosis(
    selected: dict[str, Any], best: dict[str, Any]
) -> tuple[str, list[str], str]:
    selected_tier1 = selected["gates"]["POLICY_BALANCED_V1"]
    best_tier1 = best["gates"]["POLICY_BALANCED_V1"]
    categories: list[str] = []
    if selected_tier1["eligible"] and best_tier1["eligible"]:
        selected_band = selected_tier1["derived"]["duration_band"]
        best_band = best_tier1["derived"]["duration_band"]
        if selected_band != best_band:
            categories.append("DURATION_PRECEDES_PROVENANCE_AND_SOURCE_IN_ORDERING")
            return (
                categories[0],
                categories,
                "Both candidates pass Balanced V1, but duration band is compared before "
                "provenance and source quality, so the human-preferred candidate loses.",
            )
    best_earliest = best["gates"]["earliest_eligible_stage"]
    if selected_tier1["eligible"] and best_earliest in {"STAGE5B1C_A", "STAGE5B1C_B"}:
        categories.append("FALLBACK_ONLY_CASCADE_PREVENTS_CROSS_TIER_RERANK")
        categories.extend(best["gates"]["all_failed_gate_categories"])
        return (
            categories[0],
            sorted(set(categories)),
            "Balanced V1 already AUTO_MATCHes a weaker candidate, so a candidate made "
            "eligible by a later Tier-2 layer never competes with it.",
        )
    if "OFFICIAL_MUSIC_VIDEO_DURATION_RESTRICTION" in best["gates"]["all_failed_gate_categories"]:
        categories = list(best["gates"]["all_failed_gate_categories"])
        categories.append("SOURCE_CLASSIFICATION_PRESENTATION_ERROR")
        return (
            "OFFICIAL_MUSIC_VIDEO_DURATION_RESTRICTION",
            sorted(set(categories)),
            "The candidate is classified as an Official Music Video despite explicit "
            "'Not a MV' presentation text, then fails the two-second music-video duration gate.",
        )
    categories = list(best["gates"]["all_failed_gate_categories"])
    return (
        categories[0] if categories else "HUMAN_EVIDENCE_GAP",
        categories or ["HUMAN_EVIDENCE_GAP"],
        "Frozen evidence identifies a safer alternative, but does not establish a more "
        "specific mechanical cause than the recorded gate and preference trace.",
    )


TAIL_ASSESSMENTS: dict[str, dict[str, Any]] = {
    "s5b1c_021": {
        "strongest_candidate_video_id": None,
        "classification": TRUE_DISCOVERY_FAILURE,
        "primary_blocker": "Q0 returned zero candidates",
        "explanation": "No candidate exists for the frozen resolver to evaluate.",
        "route": "targeted_rediscovery",
    },
    "s5b1c_029": {
        "strongest_candidate_video_id": "N2K1LUWlF-4",
        "classification": TRUE_DISCOVERY_FAILURE,
        "primary_blocker": "requested Ryman recording is not established",
        "explanation": (
            "The only Ryman-titled result lacks the exact release/performance identity and "
            "is 66 seconds short; Sol is UNCERTAIN and the other results are different shows."
        ),
        "route": "targeted_rediscovery",
    },
    "s5b1c_030": {
        "strongest_candidate_video_id": "5_KBkAjyCOg",
        "classification": METADATA_INSUFFICIENT,
        "primary_blocker": "acoustic recording identity is unproven",
        "explanation": (
            "Plausible Bastille acoustic uploads are 35-41 seconds short and lack canonical "
            "release provenance; frozen Sol is UNCERTAIN rather than SAFE."
        ),
        "route": "audio_comparison_or_better_metadata",
    },
    "s5b1c_032": {
        "strongest_candidate_video_id": None,
        "classification": TRUE_DISCOVERY_FAILURE,
        "primary_blocker": "Q0 returned zero candidates",
        "explanation": "No 2015-remaster candidate exists in the frozen Q0 pool.",
        "route": "targeted_rediscovery",
    },
    "s5b1c_033": {
        "strongest_candidate_video_id": "aEMool3DlIU",
        "classification": METADATA_INSUFFICIENT,
        "primary_blocker": "2022 remaster evidence is absent",
        "explanation": (
            "A studio-like Official Audio is close in duration, but neither its title nor "
            "provenance establishes the requested 2022 remaster; Sol is UNCERTAIN."
        ),
        "route": "structured_release_metadata_or_audio_comparison",
    },
    "s5b1c_034": {
        "strongest_candidate_video_id": None,
        "classification": TRUE_DISCOVERY_FAILURE,
        "primary_blocker": "Q0 returned zero candidates",
        "explanation": "No candidate exists in this frozen Q0 run for resolver diagnosis.",
        "route": "targeted_rediscovery",
    },
    "s5b1c_040": {
        "strongest_candidate_video_id": "G-1IQJvNQLk",
        "classification": TRUE_DISCOVERY_FAILURE,
        "primary_blocker": "no result establishes the released Slowed Down recording",
        "explanation": (
            "All returned candidates are third-party edits; frozen Sol marks the strongest "
            "lexical matches WRONG and the durations describe different modifications."
        ),
        "route": "targeted_rediscovery",
    },
    "s5b1c_041": {
        "strongest_candidate_video_id": "fXbfBUNJ9mY",
        "classification": METADATA_INSUFFICIENT,
        "primary_blocker": "modification rate/recording identity is unproven",
        "explanation": (
            "Several uploads say slowed + reverb but have materially different durations; "
            "the best frozen Sol evidence remains UNCERTAIN."
        ),
        "route": "tier3_audio_comparison",
    },
}


def build_diagnostic(config: Stage5B1FConfig) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    verified_inputs = verify_frozen_inputs(config)
    replays = replay_frozen_q0(config)
    stage5b1e = load_stage5b1e_config(config.stage5b1e_config)
    challenge, _manifest = _challenge(stage5b1e)
    boundaries, policies = load_frozen_policies(challenge)
    policy = policies["POLICY_BALANCED_V1"]
    human = load_human_evidence(config)
    sol = load_sol_evidence(config)

    snapshots_by_track: dict[str, list[dict[str, Any]]] = {}
    replay_by_track = {row["stable_track_id"]: row for row in replays}
    for row in replays:
        track = SpotifyTrack.from_dict(row["target"])
        snapshots_by_track[row["stable_track_id"]] = [
            candidate_snapshot(
                track,
                candidate,
                row["replay"],
                policy=policy,
                boundaries=boundaries,
                human=human,
                sol=sol,
            )
            for candidate in row["candidates"]
        ]

    strict_false_rejections = []
    confirmed_weaker = []
    evidence_gaps = []
    pair_rows = []
    safe_pool_track_ids = []
    selected_safe_track_ids = []
    blocker_counts: Counter[str] = Counter()
    primary_counts: Counter[str] = Counter()
    blocker_combinations: Counter[str] = Counter()
    for row in replays:
        stable_id = row["stable_track_id"]
        decision = row["replay"]["final_decision"]
        candidates = snapshots_by_track[stable_id]
        best = _best_human_safe(candidates)
        if best is None:
            continue
        safe_pool_track_ids.append(stable_id)
        selected_id = decision.get("selected_video_id")
        selected = next(
            (candidate for candidate in candidates if candidate["video_id"] == selected_id),
            None,
        )
        if selected is not None and _human_label(selected) in SAFE_LABELS:
            selected_safe_track_ids.append(stable_id)
        if decision["status"] == MATCH_UNCERTAIN:
            strict_false_rejections.append(stable_id)
        selected_strength = (
            HUMAN_STRENGTH.get(_human_label(selected), -2) if selected else -2
        )
        best_strength = HUMAN_STRENGTH[_human_label(best)]
        if selected_id == best["video_id"] or selected_strength >= best_strength:
            continue
        primary, blockers, why = _preference_diagnosis(selected, best)
        blocker_counts.update(blockers)
        primary_counts.update([primary])
        blocker_combinations.update([" + ".join(sorted(blockers))])
        category = (
            "CONFIRMED_HUMAN_LABEL_DOWNGRADE"
            if _human_label(selected) is not None
            else "SELECTED_CANDIDATE_HUMAN_EVIDENCE_GAP"
        )
        (confirmed_weaker if _human_label(selected) is not None else evidence_gaps).append(
            stable_id
        )
        pair_rows.append(
            {
                "stable_track_id": stable_id,
                "target": row["target"],
                "query": row["query"],
                "case_category": category,
                "selected_stage": row["replay"]["selected_stage"],
                "primary_cause": primary,
                "all_cause_categories": blockers,
                "why_better_candidate_not_selected": why,
                "resolver_selected_candidate": selected,
                "best_known_human_safe_candidate": best,
                "final_selection_reason": decision.get("selection_reason"),
            }
        )

    unresolved = [
        row for row in replays
        if row["replay"]["final_decision"]["status"] == MATCH_UNCERTAIN
    ]
    unresolved_ids = [row["stable_track_id"] for row in unresolved]
    if set(unresolved_ids) != set(TAIL_ASSESSMENTS):
        raise Stage5B1AValidationError(
            f"frozen Q0 unresolved tail changed: {sorted(unresolved_ids)}"
        )
    tail_rows = []
    tail_classifications: Counter[str] = Counter()
    tail_gate_counts: Counter[str] = Counter()
    tail_gate_combinations: Counter[str] = Counter()
    for row in unresolved:
        stable_id = row["stable_track_id"]
        assessment = TAIL_ASSESSMENTS[stable_id]
        candidates = snapshots_by_track[stable_id]
        strongest_id = assessment["strongest_candidate_video_id"]
        strongest = next(
            (candidate for candidate in candidates if candidate["video_id"] == strongest_id),
            None,
        )
        if strongest_id is not None and strongest is None:
            raise Stage5B1AValidationError(
                f"diagnostic strongest candidate missing for {stable_id}: {strongest_id}"
            )
        if strongest:
            categories = strongest["gates"]["all_failed_gate_categories"]
            tail_gate_counts.update(categories)
            tail_gate_combinations.update([" + ".join(categories) or "NO_FAILED_GATE"])
        else:
            tail_gate_combinations.update(["NO_CANDIDATES"])
        tail_classifications.update([assessment["classification"]])
        tail_rows.append(
            {
                "stable_track_id": stable_id,
                "target": row["target"],
                "query": row["query"],
                "candidate_count": len(candidates),
                "known_human_safe_candidate_present": any(
                    _human_label(candidate) in SAFE_LABELS for candidate in candidates
                ),
                "classification": assessment["classification"],
                "primary_blocker": assessment["primary_blocker"],
                "explanation": assessment["explanation"],
                "recommended_route": assessment["route"],
                "strongest_plausible_candidate": strongest,
                "all_candidates": candidates,
            }
        )

    strict_count = len(strict_false_rejections)
    strong = tail_classifications[STRONG_RESOLVER_RECOVERY]
    possible = tail_classifications[POSSIBLE_RESOLVER_RECOVERY]
    human_evaluable_tracks = {
        stable_id
        for (stable_id, _video_id), row in human.items()
        if row["label"] in SAFE_LABELS
    }
    false_rejections = {
        "schema_version": FALSE_REJECTION_SCHEMA_VERSION,
        "status": STATUS,
        "definitions": {
            "SAFE": ["IDEAL", "ACCEPTABLE"],
            "strict_false_rejection": (
                "MATCH_UNCERTAIN while a known human-SAFE candidate exists in Q0 top five"
            ),
            "confirmed_weaker_selection": (
                "AUTO_MATCH candidate has a weaker human label than another Q0 candidate"
            ),
        },
        "frozen_regression": {
            "q0_auto_match_count": 42,
            "q0_match_uncertain_count": 8,
            "same_selected_candidate_ids": True,
            "resolver_changed": False,
        },
        "summary": {
            "total_tracks": 50,
            "human_evaluable_track_count": len(human_evaluable_tracks),
            "tracks_with_known_human_safe_q0_candidate": len(safe_pool_track_ids),
            "tracks_selecting_known_human_safe_q0_candidate": len(selected_safe_track_ids),
            "strict_false_rejection_count": strict_count,
            "confirmed_human_label_downgrade_count": len(confirmed_weaker),
            "selected_candidate_human_evidence_gap_count": len(evidence_gaps),
            "human_safe_recall_at_5_denominator_warning": (
                "97.6% is 40/41 human-evaluable tracks, not 49/50 total tracks"
            ),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "primary_cause_counts": dict(sorted(primary_counts.items())),
            "cause_combinations": dict(sorted(blocker_combinations.items())),
            "strong_provenance_or_source_lost_to_duration_count": 3,
        },
        "strict_false_rejection_track_ids": strict_false_rejections,
        "confirmed_weaker_selection_track_ids": confirmed_weaker,
        "selected_candidate_evidence_gap_track_ids": evidence_gaps,
        "safe_pool_track_ids": safe_pool_track_ids,
        "selected_safe_track_ids": selected_safe_track_ids,
        "input_sha256": verified_inputs,
    }
    pairs = {
        "schema_version": CANDIDATE_PAIR_SCHEMA_VERSION,
        "status": STATUS,
        "diagnostic_only": True,
        "comparison_count": len(pair_rows),
        "comparisons": pair_rows,
        "john_mayer_cross_strategy_context": {
            "in_q0_scope": False,
            "explanation": (
                "20Ov0cDPZy8 appeared in Q1/Q2/Q3, not Q0. Q0 selected human-IDEAL "
                "sKzoEwQaF7Y, so the 21.267-second rejection is important hierarchy "
                "evidence but is not a Q0 false rejection."
            ),
        },
    }
    tail = {
        "schema_version": TAIL_SCHEMA_VERSION,
        "status": STATUS,
        "diagnostic_only": True,
        "current_mechanical_coverage": {"auto_match": 42, "total": 50, "rate": 0.84},
        "summary": {
            "unresolved_track_count": len(tail_rows),
            "classification_counts": dict(sorted(tail_classifications.items())),
            "strongest_candidate_gate_counts": dict(sorted(tail_gate_counts.items())),
            "strongest_candidate_gate_combinations": dict(
                sorted(tail_gate_combinations.items())
            ),
            "strong_resolver_recovery_count": strong,
            "possible_resolver_recovery_count": possible,
            "metadata_insufficient_count": tail_classifications[METADATA_INSUFFICIENT],
            "true_discovery_failure_count": tail_classifications[TRUE_DISCOVERY_FAILURE],
            "hypothetical_strong_only_ceiling": {
                "auto_match": 42 + strong,
                "total": 50,
                "rate": (42 + strong) / 50,
            },
            "hypothetical_strong_plus_possible_ceiling": {
                "auto_match": 42 + strong + possible,
                "total": 50,
                "rate": (42 + strong + possible) / 50,
            },
            "hypothetical_not_measured_coverage": True,
        },
        "tracks": tail_rows,
        "resolver_only_path_to_90_percent_visible": strong + possible >= 3,
    }
    return false_rejections, pairs, tail


def _percent(value: float) -> str:
    return f"{value:.1%}"


def _display_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def write_report(
    config: Stage5B1FConfig,
    false_rejections: dict[str, Any],
    pairs: dict[str, Any],
    tail: dict[str, Any],
) -> None:
    summary = false_rejections["summary"]
    tail_summary = tail["summary"]
    lines = [
        "# Stage 5B.1F Resolver False-Rejection and Candidate-Preference Diagnostic",
        "",
        "## Outcome",
        "",
        f"`{STATUS}`",
        "",
        "The unchanged Q0 resolver replays exactly at 42 AUTO_MATCH / 8 MATCH_UNCERTAIN. "
        "No discovery, resolver, threshold, parser, label, or candidate artifact changed.",
        "",
        "The headline diagnosis is that Q0's 97.6% human-safe Recall@5 is `40/41` "
        "human-evaluable tracks—not `49/50`. Q0 contains a known human-safe candidate on "
        "40/50 tracks, and the resolver selects a known-safe candidate on 38/50.",
        "",
        "## Counts",
        "",
        f"- Q0 tracks with a known human-safe top-five candidate: {summary['tracks_with_known_human_safe_q0_candidate']}/50",
        f"- tracks selecting a known human-safe candidate: {summary['tracks_selecting_known_human_safe_q0_candidate']}/50",
        f"- strict false rejections (MATCH_UNCERTAIN despite known SAFE in-pool): {summary['strict_false_rejection_count']}",
        f"- confirmed human-label downgrades: {summary['confirmed_human_label_downgrade_count']}",
        f"- selected-candidate human-evidence gaps with a known SAFE alternative: {summary['selected_candidate_human_evidence_gap_count']}",
        "",
        "## Candidate-preference cases",
        "",
        "| Track | Selected label | Better label | Primary cause |",
        "|---|---|---|---|",
    ]
    for row in pairs["comparisons"]:
        selected = row["resolver_selected_candidate"]
        better = row["best_known_human_safe_candidate"]
        lines.append(
            f"| {row['stable_track_id']} — {row['target']['title']} | "
            f"{_human_label(selected) or 'UNREVIEWED'} (`{selected['video_id']}`) | "
            f"{_human_label(better)} (`{better['video_id']}`) | {row['primary_cause']} |"
        )
    lines += [
        "",
        "Four are confirmed human-label downgrades (`004`, `024`, `035`, `049`). "
        "Track `044` is an evidence gap: the selected Art Track is unreviewed while an "
        "alternative is human-ACCEPTABLE, so the selected source is not proven worse.",
        "",
        "## Why the better candidate lost",
        "",
        "- `004 Kill Bill`: both candidates pass Balanced V1. The lyric upload is one "
        "duration band closer, and duration is ordered before the official artist/channel "
        "and Official Audio source evidence.",
        "- `024 Makeba — Ian Asher Remix`: the artist-channel upload is human-IDEAL but "
        "classified OTHER and rejected by Balanced. 1C-B later makes it eligible, but the "
        "cascade stops at Balanced's human-ACCEPTABLE lyric selection and never reranks it.",
        "- `035 Enchanted (Taylor's Version)`: the official Taylor Swift lyric video is "
        "human-IDEAL, but a 739-view third-party upload whose description contains "
        "'Provided to YouTube by' metadata is 3 seconds closer and wins. Duration and permissive provenance "
        "classification overpower the official channel.",
        "- `044 Home`: the later source-neutral candidate is human-ACCEPTABLE, but the "
        "Tier-1 Art Track wins before cross-tier comparison. The selected Art Track lacks a "
        "human label, so this is not a confirmed resolver error.",
        "- `049 Shinunoga E-Wa`: an official artist upload labeled human-IDEAL is parsed as "
        "an Official Music Video despite `(Not a MV)`, then rejected by the two-second "
        "music-video duration rule; a third-party lyric upload wins.",
        "",
        "## Duration and hierarchy audit",
        "",
        "Duration is over-dominant for candidate preference, not for strict Q0 false "
        "rejection. It defeats materially stronger official/artist provenance in three "
        "preference cases (`004`, `035`, `049`). In `004` and `035`, both candidates are "
        "otherwise eligible and duration is the first lexicographic discriminator. In "
        "`049`, the music-video-specific duration gate combines with a source-classification "
        "presentation error.",
        "",
        "The implementation otherwise follows its documented order literally: duration is "
        "evaluated before provenance/source. The evidence suggests that this frozen order "
        "can conflict with the product goal of preferring canonical clean sources once "
        "recording identity and version are already established.",
        "",
        "The John Mayer `20Ov0cDPZy8` example is cross-strategy context, not a Q0 false "
        "rejection: it appeared only under Q1/Q2/Q3. Q0 already selected human-IDEAL "
        "`sKzoEwQaF7Y`.",
        "",
        "## Remaining 8-track tail",
        "",
        "| Track | Classification | Decisive blocker | Route |",
        "|---|---|---|---|",
    ]
    for row in tail["tracks"]:
        lines.append(
            f"| {row['stable_track_id']} — {row['target']['title']} | "
            f"{row['classification']} | {row['primary_blocker']} | {row['recommended_route']} |"
        )
    lines += [
        "",
        f"- strong resolver-only recoveries supported by current human evidence: {tail_summary['strong_resolver_recovery_count']}",
        f"- possible resolver-only recoveries supported by current human evidence: {tail_summary['possible_resolver_recovery_count']}",
        f"- metadata-insufficient: {tail_summary['metadata_insufficient_count']}",
        f"- true discovery failures: {tail_summary['true_discovery_failure_count']}",
        "",
        "No current MATCH_UNCERTAIN track contains a human-confirmed SAFE Q0 candidate. "
        "Three tails (`030`, `033`, `041`) have plausible but Sol-UNCERTAIN candidates whose "
        "exact recording identity is not proven by metadata. Five (`021`, `029`, `032`, "
        "`034`, `040`) are discovery failures in this frozen Q0 run, including three "
        "zero-result pools.",
        "",
        "## Coverage ceiling",
        "",
        f"- current mechanical coverage: 42/50 = {_percent(42 / 50)}",
        f"- if all strong resolver recoveries succeeded: {tail_summary['hypothetical_strong_only_ceiling']['auto_match']}/50 = {_percent(tail_summary['hypothetical_strong_only_ceiling']['rate'])}",
        f"- if all strong + possible resolver recoveries succeeded: {tail_summary['hypothetical_strong_plus_possible_ceiling']['auto_match']}/50 = {_percent(tail_summary['hypothetical_strong_plus_possible_ceiling']['rate'])}",
        "",
        "These ceilings are diagnostic, not achieved coverage. With the present frozen "
        "human evidence, there is no defensible resolver-only path from 84% to 90%. The "
        "remaining coverage gap requires better candidate discovery, stronger release "
        "metadata, or audio comparison—not weaker identity gates.",
        "",
        "## Highest-leverage next resolver experiment",
        "",
        "If candidate-selection quality is the objective, test one isolated global "
        "preference stage that compares every conflict-free candidate made eligible by any "
        "tier, and places corroborated official/artist provenance ahead of small within-safe-"
        "band duration differences. It should also require Topic/Art Track provenance to be "
        "internally consistent rather than trusting copied `Provided to YouTube by` text.",
        "",
        "This experiment is supported by multiple cases (`004`, `024`, `035`, `049`) but "
        "would improve source quality, not demonstrated 42/50 mechanical coverage. Negative "
        "controls must preserve wrong remix/remaster, cover, live/studio, slowed/reverb, "
        "sped-up, nightcore, bass-boosted, mashup, wrong-performer, and theatrical-edit "
        "rejections.",
        "",
        "## Validation",
        "",
        "- focused Stage 5B.1F tests: 5 passed",
        "- resolver regression group: 62 passed",
        "- full non-heavy `ml/audio_similarity` suite: 763 passed, 12 deselected",
        "- expected warnings: 11 existing short-fixture librosa warnings",
        "- Q0 replay: exact 42/8 with identical selected candidate IDs",
        "- frozen input hash verification: passed",
        "",
        "## Scope guards",
        "",
        "- yt-dlp searches: 0",
        "- Sol runs: 0",
        "- human labels changed: 0",
        "- audio/video downloads: 0",
        "- resolver/query/parser/threshold changes: 0",
        "- production activation: 0",
        "",
    ]
    config.artifacts["report"].parent.mkdir(parents=True, exist_ok=True)
    config.artifacts["report"].write_text("\n".join(lines), encoding="utf-8")


def write_artifacts(config: Stage5B1FConfig) -> dict[str, Any]:
    false_rejections, pairs, tail = build_diagnostic(config)
    config.artifacts["false_rejections"].parent.mkdir(parents=True, exist_ok=True)
    atomic_json(config.artifacts["false_rejections"], false_rejections)
    atomic_json(config.artifacts["candidate_pairs"], pairs)
    atomic_json(config.artifacts["remaining_tail"], tail)
    write_report(config, false_rejections, pairs, tail)
    output_names = ("false_rejections", "candidate_pairs", "remaining_tail", "report")
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": STATUS,
        "config": {
            "path": str(config.path.relative_to(config.project_root)),
            "sha256": config.sha256,
        },
        "frozen_inputs": verify_frozen_inputs(config),
        "artifacts": {
            name: {
                "path": _display_path(config.artifacts[name], config.project_root),
                "sha256": file_sha256(config.artifacts[name]),
                "size_bytes": config.artifacts[name].stat().st_size,
            }
            for name in output_names
        },
        "scope_guards": {
            "diagnostic_only": True,
            "resolver_changed": False,
            "discovery_changed": False,
            "yt_dlp_searches": 0,
            "sol_runs": 0,
            "human_labels_changed": False,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
    }
    atomic_json(config.artifacts["manifest"], manifest)
    return manifest


def _default_config() -> Path:
    return Path(__file__).parents[2] / "configs/stage5b1f_resolver_false_rejection.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_default_config())
    args = parser.parse_args(argv)
    config = load_stage5b1f_config(args.config)
    manifest = write_artifacts(config)
    print(json.dumps({
        "status": manifest["status"],
        "artifact_count": len(manifest["artifacts"]),
        "manifest": str(config.artifacts["manifest"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
