"""Frozen-Q0 human-oracle audit for the unresolved Stage 5B.1H tail.

This module is diagnostic only.  It replays Stage 5B.1H, derives the audit
universe from the replay, preserves reviewer-owned labels, and compares SAFE
human judgments with the unchanged Stage 5B.1G/1H evidence model.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_identity import parse_target
from .stage5b1b_resolver import MATCH_UNCERTAIN
from .stage5b1g_global_preference import global_preference_key
from .stage5b1h_source_semantics import evaluate_stage5b1h, load_stage5b1h_config


CONFIG_SCHEMA_VERSION = "stage5b1i-human-oracle-config-v1"
QUEUE_SCHEMA_VERSION = "stage5b1i-human-review-queue-v1"
RESULTS_SCHEMA_VERSION = "stage5b1i-human-oracle-results-v1"
COMPARISON_SCHEMA_VERSION = "stage5b1i-safe-candidate-comparisons-v1"
GAP_SCHEMA_VERSION = "stage5b1i-resolver-human-gap-analysis-v1"
TAXONOMY_SCHEMA_VERSION = "stage5b1i-error-taxonomy-v1"
RULE_SCHEMA_VERSION = "stage5b1i-rule-hypotheses-v1"
MANIFEST_SCHEMA_VERSION = "stage5b1i-artifact-manifest-v1"
AWAITING_REVIEW = "STAGE5B1I_AWAITING_HUMAN_REVIEW"
COMPLETE = "STAGE5B1I_HUMAN_ORACLE_AUDIT_COMPLETE"
SAFE_LABELS = frozenset({"IDEAL", "ACCEPTABLE"})


@dataclass(frozen=True)
class Stage5B1IConfig:
    path: Path
    project_root: Path
    experiment_id: str
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
        stage5b1h_config=project_root / str(value["stage5b1h_config"]),
        frozen_inputs=dict(frozen),
        artifacts={name: project_root / str(target) for name, target in artifacts.items()},
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


def _target_version_descriptors(track_row: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = track_row["candidates"]
    if candidates:
        return list(
            candidates[0]["snapshot"]["identity"]["target"]["version_descriptors"]
        )
    return [
        value.to_dict()
        for value in parse_target(SpotifyTrack.from_dict(track_row["track"])).versions
    ]


def replay_human_oracle_universe(config: Stage5B1IConfig) -> dict[str, Any]:
    """Derive the eight-track audit solely from the frozen Stage 5B.1H replay."""

    verify_frozen_inputs(config)
    stage5b1h = load_stage5b1h_config(config.stage5b1h_config)
    semantics, decisions, *_ = evaluate_stage5b1h(stage5b1h)
    summary = decisions["summary"]
    if summary["stage5b1h_auto_match_count"] != 42 or summary[
        "stage5b1h_match_uncertain_count"
    ] != 8:
        raise Stage5B1AValidationError("frozen Stage 5B.1H 42/8 baseline changed")
    if summary["selection_ids_changed"] != 0:
        raise Stage5B1AValidationError("Stage 5B.1H unexpectedly changed selections")

    unresolved = [
        row["stable_track_id"]
        for row in decisions["tracks"]
        if row["stage5b1h_decision"]["status"] == MATCH_UNCERTAIN
    ]
    if len(unresolved) != 8 or len(unresolved) != len(set(unresolved)):
        raise Stage5B1AValidationError("frozen Stage 5B.1H unresolved universe changed")

    full_features = _json_object(
        config.project_root
        / str(config.frozen_inputs["stage5b1g_candidate_features"]["path"])
    )
    semantics_by_id = {
        row["track"]["stable_track_id"]: row for row in semantics["tracks"]
    }
    feature_by_id = {
        row["track"]["stable_track_id"]: row for row in full_features["tracks"]
    }
    tracks = []
    identities: set[tuple[str, str]] = set()
    for stable_id in unresolved:
        if stable_id not in feature_by_id or stable_id not in semantics_by_id:
            raise Stage5B1AValidationError(f"missing frozen Q0 track: {stable_id}")
        source = feature_by_id[stable_id]
        semantic = semantics_by_id[stable_id]
        semantic_by_video = {row["video_id"]: row for row in semantic["candidates"]}
        candidates = []
        for wrapped in source["candidates"]:
            snapshot = wrapped["snapshot"]
            video_id = snapshot["video_id"]
            identity = (stable_id, video_id)
            if identity in identities:
                raise Stage5B1AValidationError(f"duplicate frozen Q0 candidate: {identity}")
            identities.add(identity)
            semantic_row = semantic_by_video.get(video_id)
            if semantic_row is None:
                raise Stage5B1AValidationError(f"missing Stage 5B.1H semantics: {identity}")
            candidates.append({
                "candidate": {
                    "rank": snapshot["search_rank"],
                    "video_id": video_id,
                    "url": snapshot.get("url") or f"https://www.youtube.com/watch?v={video_id}",
                    "title": snapshot.get("title"),
                    "uploader": snapshot.get("uploader"),
                    "channel": snapshot.get("channel"),
                    "duration_seconds": snapshot.get("duration_seconds"),
                    "view_count": snapshot.get("view_count"),
                    "description": snapshot.get("description"),
                },
                "resolver_evidence": {
                    "identity": wrapped["global_features"]["identity"],
                    "version": wrapped["global_features"]["versions"],
                    "modifications": wrapped["global_features"]["modifications"],
                    "hard_conflicts": wrapped["global_features"]["hard_conflicts"],
                    "duration": wrapped["global_features"]["duration"],
                    "source": wrapped["global_features"]["source"],
                    "provenance": wrapped["global_features"]["provenance"],
                    "description_evidence": wrapped["global_features"]["description_evidence"],
                    "eligibility": wrapped["global_features"]["eligibility"],
                    "frozen_tier_gates": snapshot["gates"],
                    "source_semantics": semantic_row["source_semantics"],
                },
                "global_features": wrapped["global_features"],
                "frozen_sol_evidence": snapshot.get("sol_evidence"),
            })
        ranks = [row["candidate"]["rank"] for row in candidates]
        if ranks != list(range(1, len(candidates) + 1)) or len(candidates) > 5:
            raise Stage5B1AValidationError(f"invalid frozen Q0 ranks: {stable_id}")
        tracks.append({
            "track": source["track"],
            "target_version_descriptors": _target_version_descriptors(source),
            "query": source["query"],
            "candidate_availability": "AVAILABLE" if candidates else "NO_Q0_CANDIDATES",
            "candidates": candidates,
        })
    candidate_count = sum(len(row["candidates"]) for row in tracks)
    return {
        "schema_version": "stage5b1i-frozen-audit-universe-v1",
        "status": AWAITING_REVIEW,
        "dataset_role": "FROZEN_Q0_UNRESOLVED_HUMAN_ORACLE_TAIL",
        "baseline": {
            "stage5b1h_auto_match_count": 42,
            "stage5b1h_match_uncertain_count": 8,
            "coverage": 42 / 50,
            "resolver_outputs_mutated": False,
        },
        "track_count": len(tracks),
        "candidate_count": candidate_count,
        "tracks_with_candidates": sum(bool(row["candidates"]) for row in tracks),
        "tracks_without_candidates": sum(not row["candidates"] for row in tracks),
        "tracks": tracks,
    }


def build_review_queue(universe: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for row in universe["tracks"]:
        track = row["track"]
        cases.append({
            "stable_track_id": track["stable_track_id"],
            "track": track,
            "target_version_descriptors": row["target_version_descriptors"],
            "candidate_availability": row["candidate_availability"],
            "candidate_video_ids": [item["candidate"]["video_id"] for item in row["candidates"]],
            "candidate_count": len(row["candidates"]),
        })
    return {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "status": AWAITING_REVIEW,
        "dataset_role": universe["dataset_role"],
        "baseline": universe["baseline"],
        "track_count": len(cases),
        "candidate_count": universe["candidate_count"],
        "tracks_with_candidates": universe["tracks_with_candidates"],
        "tracks_without_candidates": universe["tracks_without_candidates"],
        "cases": cases,
        "review_instructions": {
            "question": "Would this candidate suitably represent the requested Spotify recording?",
            "labels": ["IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"],
            "independence": "label before revealing frozen resolver evidence",
            "zero_candidate_tracks": "explicitly documented; no fabricated judgment row",
        },
    }


def _combined_failed_gates(wrapped: dict[str, Any]) -> dict[str, Any]:
    evidence = wrapped["resolver_evidence"]
    frozen = evidence["frozen_tier_gates"]
    categories = list(frozen.get("all_failed_gate_categories", []))
    conditions = list(evidence["eligibility"].get("failed_conditions", []))
    reasons = []
    for policy_id in (
        "POLICY_BALANCED_V1", "STAGE5B1C_A", "STAGE5B1C_B", "STAGE5B1C_C"
    ):
        gate = frozen.get(policy_id) or {}
        reasons.extend(gate.get("reasons", []))
    return {
        "categories": sorted(set(categories)),
        "stage5b1g_failed_conditions": sorted(set(conditions)),
        "frozen_tier_reasons": list(dict.fromkeys(reasons)),
    }


def _gap_category(wrapped: dict[str, Any]) -> tuple[str, str]:
    evidence = wrapped["resolver_evidence"]
    eligibility = evidence["eligibility"]
    if eligibility["eligible"]:
        return (
            "PREFERENCE_RANKING_FAILURE",
            "candidate is eligible but loses global preference",
        )
    conflicts = set(evidence["hard_conflicts"])
    identity = evidence["identity"]
    version = evidence["version"]
    duration = evidence["duration"]
    if conflicts:
        return (
            "EVIDENCE_EXTRACTION_FAILURE",
            "human SAFE judgment contradicts an extracted hard recording conflict",
        )
    if not identity["strong_structural_title_identity"] or not identity[
        "strong_primary_performer_identity"
    ]:
        return (
            "EVIDENCE_EXTRACTION_FAILURE",
            "human recognizes identity that the structural title/performer features do not",
        )
    if version["target_is_versioned"] and not version["explicit_complete_match"]:
        return (
            "EVIDENCE_INTERPRETATION_FAILURE",
            "candidate is human SAFE but target-version evidence remains incomplete",
        )
    if duration["bucket"] == "DURATION_TOO_FAR":
        return (
            "EVIDENCE_INTERPRETATION_FAILURE",
            "human SAFE judgment survives the frozen twenty-second duration ceiling",
        )
    return (
        "HUMAN_SEMANTIC_INFERENCE_NOT_ENCODED",
        "human SAFE judgment relies on context not represented by a decisive resolver feature",
    )


def _pending_documents(universe: dict[str, Any], completed: int) -> tuple[dict[str, Any], ...]:
    common = {
        "status": AWAITING_REVIEW,
        "required_candidate_judgments": universe["candidate_count"],
        "completed_candidate_judgments": completed,
        "tracks_without_candidates": universe["tracks_without_candidates"],
        "analysis_deferred": "all available frozen Q0 candidates must be human-labeled",
    }
    return tuple({"schema_version": schema, **common} for schema in (
        RESULTS_SCHEMA_VERSION,
        COMPARISON_SCHEMA_VERSION,
        GAP_SCHEMA_VERSION,
        TAXONOMY_SCHEMA_VERSION,
        RULE_SCHEMA_VERSION,
    ))


def evaluate_human_oracle(
    universe: dict[str, Any], review_rows: list[dict[str, str]]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    expected = [
        (track["track"]["stable_track_id"], row["candidate"]["video_id"])
        for track in universe["tracks"] for row in track["candidates"]
    ]
    actual = [(row["stable_track_id"], row["candidate_video_id"]) for row in review_rows]
    if actual != expected:
        raise Stage5B1AValidationError("Stage 5B.1I review rows changed frozen Q0 order")
    completed = sum(bool(row["candidate_review_label"]) for row in review_rows)
    if completed != len(review_rows):
        return _pending_documents(universe, completed)  # type: ignore[return-value]

    review = {
        (row["stable_track_id"], row["candidate_video_id"]): row
        for row in review_rows
    }
    result_tracks = []
    comparisons = []
    taxonomy = Counter()
    recall = {1: 0, 3: 0, 5: 0}
    label_counts = Counter(row["candidate_review_label"] for row in review_rows)

    for track_row in universe["tracks"]:
        track = track_row["track"]
        stable_id = track["stable_track_id"]
        labeled = []
        for wrapped in track_row["candidates"]:
            candidate = wrapped["candidate"]
            human = review[(stable_id, candidate["video_id"])]
            labeled.append((wrapped, human))
        safe = [(wrapped, human) for wrapped, human in labeled if human["candidate_review_label"] in SAFE_LABELS]
        best_safe = min(
            safe,
            key=lambda item: (
                0 if item[1]["candidate_review_label"] == "IDEAL" else 1,
                item[0]["candidate"]["rank"],
            ),
            default=None,
        )
        best_features = min(
            track_row["candidates"], key=global_preference_key, default=None
        )
        safe_ranks = [wrapped["candidate"]["rank"] for wrapped, _ in safe]
        for k in recall:
            recall[k] += bool(safe_ranks and min(safe_ranks) <= k)

        if safe:
            track_category = _gap_category(best_safe[0])[0]  # type: ignore[index]
        elif not labeled or all(
            human["candidate_review_label"] == "WRONG" for _, human in labeled
        ):
            track_category = "TRUE_CANDIDATE_SET_FAILURE"
        elif any(human["candidate_review_label"] == "UNCERTAIN" for _, human in labeled):
            track_category = "METADATA_INSUFFICIENT"
        else:
            track_category = "GENUINE_CONFLICTING_EVIDENCE"
        taxonomy[track_category] += 1

        candidate_counts = Counter(human["candidate_review_label"] for _, human in labeled)
        result_tracks.append({
            "stable_track_id": stable_id,
            "target": track,
            "candidate_availability": track_row["candidate_availability"],
            "human_label_counts": dict(sorted(candidate_counts.items())),
            "has_safe_candidate": bool(safe),
            "best_human_safe_candidate": (
                {
                    "video_id": best_safe[0]["candidate"]["video_id"],
                    "rank": best_safe[0]["candidate"]["rank"],
                    "label": best_safe[1]["candidate_review_label"],
                    "rationale_verbatim": best_safe[1]["candidate_note"],
                } if best_safe else None
            ),
            "best_candidate_by_current_features": (
                {
                    "video_id": best_features["candidate"]["video_id"],
                    "rank": best_features["candidate"]["rank"],
                    "eligible": best_features["resolver_evidence"]["eligibility"]["eligible"],
                    "failed_gates": _combined_failed_gates(best_features),
                } if best_features else None
            ),
            "primary_error_family": track_category,
            "track_note_verbatim": labeled[0][1]["track_note"] if labeled else "",
        })

        for wrapped, human in safe:
            category, reason = _gap_category(wrapped)
            comparisons.append({
                "stable_track_id": stable_id,
                "candidate": wrapped["candidate"],
                "human_label": human["candidate_review_label"],
                "human_rationale_verbatim": human["candidate_note"],
                "frozen_sol_evidence": wrapped["frozen_sol_evidence"],
                "resolver_evidence": wrapped["resolver_evidence"],
                "failed_gates": _combined_failed_gates(wrapped),
                "gap_category": category,
                "gap_explanation": reason,
                "currently_selected": False,
            })

    safe_pool_count = sum(row["has_safe_candidate"] for row in result_tracks)
    results = {
        "schema_version": RESULTS_SCHEMA_VERSION,
        "status": COMPLETE,
        "dataset_role": universe["dataset_role"],
        "baseline": universe["baseline"],
        "review": {
            "candidate_judgments": len(review_rows),
            "track_count": len(result_tracks),
            "label_counts": dict(sorted(label_counts.items())),
            "safe_definition": "IDEAL_OR_ACCEPTABLE",
        },
        "tail_metrics": {
            "denominator_tracks": len(result_tracks),
            "safe_recall_at_1": recall[1] / len(result_tracks),
            "safe_recall_at_3": recall[3] / len(result_tracks),
            "safe_recall_at_5": recall[5] / len(result_tracks),
            "tracks_with_at_least_one_safe_candidate": safe_pool_count,
            "tracks_without_safe_candidate": len(result_tracks) - safe_pool_count,
        },
        "human_oracle_top5_ceiling": {
            "current_resolved_tracks": 42,
            "additional_safe_unresolved_pools": safe_pool_count,
            "ceiling_tracks": 42 + safe_pool_count,
            "challenge_track_count": 50,
            "ceiling": (42 + safe_pool_count) / 50,
            "achieved_coverage_claimed": False,
        },
        "tracks": result_tracks,
    }
    comparison_doc = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "status": COMPLETE,
        "safe_candidate_count": len(comparisons),
        "comparisons": comparisons,
    }
    gap_doc = {
        "schema_version": GAP_SCHEMA_VERSION,
        "status": COMPLETE,
        "safe_but_unselected_count": len(comparisons),
        "gap_category_counts": dict(sorted(Counter(
            row["gap_category"] for row in comparisons
        ).items())),
        "tracks": [
            {
                "stable_track_id": row["stable_track_id"],
                "primary_error_family": row["primary_error_family"],
                "best_human_safe_candidate": row["best_human_safe_candidate"],
                "best_candidate_by_current_features": row["best_candidate_by_current_features"],
            }
            for row in result_tracks
        ],
    }
    taxonomy_doc = {
        "schema_version": TAXONOMY_SCHEMA_VERSION,
        "status": COMPLETE,
        "track_count": len(result_tracks),
        "category_counts": dict(sorted(taxonomy.items())),
        "definitions": {
            "EVIDENCE_EXTRACTION_FAILURE": "human-safe identity conflicts with extracted title, performer, or hard-conflict evidence",
            "EVIDENCE_INTERPRETATION_FAILURE": "evidence is present but frozen version/duration semantics remain too rigid",
            "PREFERENCE_RANKING_FAILURE": "human-safe candidate is eligible but loses global ordering",
            "HUMAN_SEMANTIC_INFERENCE_NOT_ENCODED": "human context is not represented by decisive deterministic metadata",
            "METADATA_INSUFFICIENT": "review does not establish a safe candidate from frozen metadata/listening",
            "TRUE_CANDIDATE_SET_FAILURE": "no human-safe candidate exists in the frozen Q0 pool",
            "GENUINE_CONFLICTING_EVIDENCE": "plausible candidates remain mutually contradictory",
        },
        "tracks": [
            {"stable_track_id": row["stable_track_id"], "category": row["primary_error_family"]}
            for row in result_tracks
        ],
    }
    rule_doc = _build_rule_hypotheses(comparisons, result_tracks)
    return results, comparison_doc, gap_doc, taxonomy_doc, rule_doc


def _build_rule_hypotheses(
    comparisons: list[dict[str, Any]], result_tracks: list[dict[str, Any]]
) -> dict[str, Any]:
    categories = Counter(row["gap_category"] for row in comparisons)
    hypotheses = []
    templates = {
        "EVIDENCE_EXTRACTION_FAILURE": {
            "rule_cluster": "STRUCTURED_IDENTITY_AND_RELEASE_EVIDENCE_EXTRACTION",
            "abstract_rule": "Extract target-relative performer/version evidence from title, description, album, year, and structured release provenance before declaring a conflict.",
            "generalization_value": "HIGH_GENERALIZATION_VALUE",
            "risk": "false equivalence between canonical but different releases",
        },
        "EVIDENCE_INTERPRETATION_FAILURE": {
            "rule_cluster": "CONDITIONAL_VERSION_AND_DURATION_INTERPRETATION",
            "abstract_rule": "Evaluate version completeness and duration only after consistent identity and release evidence, without allowing absence to become a match.",
            "generalization_value": "PROMISING_BUT_NEEDS_VALIDATION",
            "risk": "wrong remaster, live performance, remix, or modified-audio variant",
        },
        "PREFERENCE_RANKING_FAILURE": {
            "rule_cluster": "GLOBAL_SAFE_CANDIDATE_PREFERENCE",
            "abstract_rule": "Among independently eligible candidates, prefer internally consistent canonical release evidence before weak views/rank and small duration differences.",
            "generalization_value": "HIGH_GENERALIZATION_VALUE",
            "risk": "canonical provenance attached to a different recording version",
        },
        "HUMAN_SEMANTIC_INFERENCE_NOT_ENCODED": {
            "rule_cluster": "CONTEXTUAL_EQUIVALENCE_EVIDENCE",
            "abstract_rule": "Acquire an additional deterministic evidence source before encoding human contextual equivalence as a runtime rule.",
            "generalization_value": "REQUIRES_NEW_EVIDENCE",
            "risk": "turning human familiarity or guessing into an unsafe heuristic",
        },
    }
    safety_controls = [
        "wrong named remix", "wrong remaster", "wrong live performance", "cover",
        "mashup", "slowed/reverb mismatch", "sped-up", "nightcore",
        "bass boosted", "karaoke", "instrumental mismatch", "wrong performer",
    ]
    for category, template in templates.items():
        affected = sorted({
            row["stable_track_id"] for row in comparisons if row["gap_category"] == category
        })
        if not affected:
            continue
        hypotheses.append({
            **template,
            "affected_track_count": len(affected),
            "affected_tracks": affected,
            "deterministic_expression_possible": category != "HUMAN_SEMANTIC_INFERENCE_NOT_ENCODED",
            "counterfactual_negative_controls": safety_controls,
            "production_rule_implemented": False,
        })
    no_safe = [row["stable_track_id"] for row in result_tracks if not row["has_safe_candidate"]]
    if no_safe:
        hypotheses.append({
            "rule_cluster": "NO_SAFE_Q0_CANDIDATE",
            "abstract_rule": "Do not loosen the resolver when the frozen top five contains no human-safe candidate; use better discovery or audio evidence.",
            "generalization_value": "REQUIRES_NEW_EVIDENCE",
            "affected_track_count": len(no_safe),
            "affected_tracks": sorted(no_safe),
            "deterministic_expression_possible": False,
            "risk": "accepting a wrong candidate to manufacture coverage",
            "counterfactual_negative_controls": safety_controls,
            "production_rule_implemented": False,
        })
    priority = {
        "HIGH_GENERALIZATION_VALUE": 0,
        "PROMISING_BUT_NEEDS_VALIDATION": 1,
        "REQUIRES_NEW_EVIDENCE": 2,
        "CASE_SPECIFIC / DO_NOT_IMPLEMENT": 3,
    }
    hypotheses.sort(key=lambda row: (priority[row["generalization_value"]], row["rule_cluster"]))
    return {
        "schema_version": RULE_SCHEMA_VERSION,
        "status": COMPLETE,
        "selection_principle": "generalized semantic categories only; no track-specific rule",
        "safe_gap_category_counts": dict(sorted(categories.items())),
        "hypotheses": hypotheses,
    }
