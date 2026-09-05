"""Compare blinded Sol judgments with an explicitly uncalibrated resolver proposal."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_sol import load_blind_inputs, load_sol_evaluations
from .stage5b1b_sol_config import SolAuditConfig


COMPARISON_SCHEMA_VERSION = "stage5b1b-sol-resolver-comparison-v1"
AUDIT_SCHEMA_VERSION = "stage5b1b-sol-manual-audit-v1"
QUEUE_SCHEMA_VERSION = "stage5b1b-sol-manual-audit-queue-v1"


def _load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _truth_rank(value: bool | None) -> int:
    return 0 if value is True else 1 if value is False else 2


def _proposal_key(feature: dict[str, Any]) -> tuple[Any, ...]:
    duration = feature["duration"]["absolute_duration_delta_seconds"]
    weak = feature["weak_evidence"]
    view_rank = weak["view_rank_among_plausible_candidates"]
    return (
        duration is None,
        float(duration) if duration is not None else float("inf"),
        -int(feature["source"]["source_preference_tier"]),
        _truth_rank(feature["description_evidence"]["album_evidence_match"]),
        _truth_rank(feature["description_evidence"]["release_year_evidence_match"]),
        -float(feature["identity"]["title_similarity"]),
        -float(feature["identity"]["artist_similarity"]),
        view_rank is None,
        int(view_rank) if view_rank is not None else 1_000_000,
        int(weak["search_rank"]),
    )


def propose_track_resolution(
    track_row: dict[str, Any], *, resolver_version: str
) -> dict[str, Any]:
    """Make a conservative DEV proposal; this is not an AUTO_MATCH policy."""
    strong: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for wrapped in track_row["candidates"]:
        candidate = wrapped["candidate"]
        feature = wrapped["features"]
        reasons: list[str] = []
        if not feature["recording_eligible"]:
            reasons.extend(feature["ineligible_auto_match_reasons"])
        if not feature["identity"]["title_exact_normalized_match"]:
            reasons.append("normalized core title is not exact")
        if not feature["identity"]["primary_artist_match"]:
            reasons.append("primary performer is not explicitly matched")
        if feature["versions"]["version_absent_count"]:
            reasons.append("target version evidence is absent")
        if feature["versions"]["version_conflict_count"]:
            reasons.append("target-relative version conflict")
        summary = {
            "video_id": candidate["youtube_video_id"],
            "rank": candidate["rank"],
            "title": candidate.get("title"),
            "source_type": feature["source"]["source_type"],
            "duration_delta_seconds": feature["duration"][
                "absolute_duration_delta_seconds"
            ],
            "reasons": reasons,
        }
        if reasons:
            rejected.append(summary)
        else:
            strong.append({**summary, "key": _proposal_key(feature), "feature": feature})
    if not strong:
        return {
            "resolver_version": resolver_version,
            "status": "MATCH_UNCERTAIN",
            "selected_video_id": None,
            "reason": "no candidate has exact title + explicit performer + resolved version evidence",
            "production_auto_match_enabled": False,
            "eligible_candidate_count": 0,
            "rejected_candidates": rejected,
        }
    ordered = sorted(strong, key=lambda item: item["key"])
    selected = ordered[0]
    return {
        "resolver_version": resolver_version,
        "status": "PROVISIONAL_SELECTED",
        "selected_video_id": selected["video_id"],
        "reason": (
            "strong identity/version gate passed; lexicographic hierarchy used duration, "
            "source tier, release evidence, then weak views/rank"
        ),
        "production_auto_match_enabled": False,
        "eligible_candidate_count": len(strong),
        "selected_evidence": {
            "rank": selected["rank"],
            "title": selected["title"],
            "source_type": selected["source_type"],
            "duration_delta_seconds": selected["duration_delta_seconds"],
            "ordering_key": list(selected["key"]),
        },
        "alternative_video_ids": [item["video_id"] for item in ordered[1:]],
        "rejected_candidates": rejected,
    }


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _random_key(seed: str, stable_id: str) -> str:
    return hashlib.sha256(f"{seed}|{stable_id}".encode()).hexdigest()


def compare_sol_and_resolver(config: SolAuditConfig) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if file_sha256(config.resolver_features_path) != config.resolver_features_sha256:
        raise Stage5B1AValidationError("resolver feature artifact hash changed")
    manifest, blind_rows = load_blind_inputs(config)
    sol = load_sol_evaluations(config.artifacts["sol_evaluations"], config)
    feature_dataset = _load_json(config.resolver_features_path)
    if feature_dataset.get("manifest_sha256") != manifest.sha256:
        raise Stage5B1AValidationError("resolver features do not match held-out manifest")
    feature_rows = feature_dataset.get("tracks")
    if not isinstance(feature_rows, list) or [
        row.get("track", {}).get("stable_track_id") for row in feature_rows
    ] != list(manifest.stable_track_ids):
        raise Stage5B1AValidationError("resolver feature track coverage mismatch")

    sol_by_id = {row["stable_track_id"]: row for row in sol["tracks"]}
    proposal_by_id = {
        row["track"]["stable_track_id"]: propose_track_resolution(
            row, resolver_version=config.resolver_version
        )
        for row in feature_rows
    }
    cases: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    sol_uncertain: list[dict[str, Any]] = []
    resolver_uncertain: list[dict[str, Any]] = []
    clean_agreement_ids: list[str] = []
    safe = wrong = exact = exact_denominator = 0

    for stable_id in manifest.stable_track_ids:
        sol_row = sol_by_id[stable_id]
        proposal = proposal_by_id[stable_id]
        sol_labels = {
            candidate["video_id"]: candidate["label"]
            for candidate in sol_row["candidates"]
        }
        uncertain_ids = sorted(
            video_id for video_id, label in sol_labels.items() if label == "UNCERTAIN"
        )
        case = {
            "stable_track_id": stable_id,
            "resolver": proposal,
            "sol_selection_status": sol_row["selection_status"],
            "sol_selected_video_id": sol_row["selected_video_id"],
            "sol_uncertain_candidate_ids": uncertain_ids,
            "comparison_class": None,
        }
        selected = proposal["selected_video_id"]
        if selected is None:
            case["comparison_class"] = "RESOLVER_UNCERTAIN"
            resolver_uncertain.append(case)
        else:
            selected_label = sol_labels[selected]
            case["sol_label_for_resolver_selection"] = selected_label
            if selected_label in {"IDEAL", "ACCEPTABLE"}:
                safe += 1
                if sol_row["selection_status"] == "SELECTED":
                    exact_denominator += 1
                    if sol_row["selected_video_id"] == selected:
                        exact += 1
                        case["comparison_class"] = "SAFE_EXACT_SOURCE_AGREEMENT"
                        if not uncertain_ids:
                            clean_agreement_ids.append(stable_id)
                    else:
                        case["comparison_class"] = "SAFE_SOURCE_PREFERENCE_DISAGREEMENT"
                        disagreements.append(case)
                else:
                    case["comparison_class"] = "SAFE_SOL_SELECTION_UNCERTAIN"
            elif selected_label == "WRONG":
                wrong += 1
                case["comparison_class"] = "UNSAFE_SELECTION_DISAGREEMENT"
                disagreements.append(case)
            else:
                case["comparison_class"] = "SOL_UNCERTAIN_ON_RESOLVER_SELECTION"
        if sol_row["selection_status"] == "UNCERTAIN" or uncertain_ids:
            sol_uncertain.append(case)
        cases.append(case)

    random_ids = sorted(
        clean_agreement_ids, key=lambda stable_id: _random_key(config.random_seed, stable_id)
    )[: config.random_agreement_track_count]
    reason_by_id: dict[str, set[str]] = {}
    for case in disagreements:
        reason_by_id.setdefault(case["stable_track_id"], set()).add("DISAGREEMENT")
    for case in sol_uncertain:
        reason_by_id.setdefault(case["stable_track_id"], set()).add("SOL_UNCERTAIN")
    for case in resolver_uncertain:
        reason_by_id.setdefault(case["stable_track_id"], set()).add("RESOLVER_UNCERTAIN")
    for stable_id in random_ids:
        reason_by_id.setdefault(stable_id, set()).add("RANDOM_AGREEMENT_AUDIT")
    audit_ids = [stable_id for stable_id in manifest.stable_track_ids if stable_id in reason_by_id]
    audit_candidate_ids: dict[str, list[str]] = {}
    blind_by_id = {row["stable_track_id"]: row for row in blind_rows}
    case_by_id = {row["stable_track_id"]: row for row in cases}
    for stable_id in audit_ids:
        case = case_by_id[stable_id]
        ordered_ids = [
            candidate["video_id"] for candidate in blind_by_id[stable_id]["candidates"]
        ]
        requested: set[str] = set(case["sol_uncertain_candidate_ids"])
        if case["resolver"]["selected_video_id"]:
            requested.add(case["resolver"]["selected_video_id"])
        if case["sol_selected_video_id"]:
            requested.add(case["sol_selected_video_id"])
        if "RESOLVER_UNCERTAIN" in reason_by_id[stable_id]:
            requested.update(ordered_ids)
        audit_candidate_ids[stable_id] = [
            video_id for video_id in ordered_ids if video_id in requested
        ]

    comparison = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "status": "SOL_ASSISTED_AUDIT_READY",
        "manifest_sha256": manifest.sha256,
        "discovery_sha256": config.discovery_sha256,
        "resolver_features_sha256": config.resolver_features_sha256,
        "sol_evaluations_sha256": file_sha256(config.artifacts["sol_evaluations"]),
        "resolver_version": config.resolver_version,
        "production_auto_match_enabled": False,
        "agreement_definition": (
            "Sol independently labels the resolver-selected source IDEAL or ACCEPTABLE; "
            "WRONG is a safety disagreement. Sol and resolver uncertainty are excluded."
        ),
        "summary": {
            "track_count": len(cases),
            "resolver_selected_count": len(cases) - len(resolver_uncertain),
            "resolver_uncertain_count": len(resolver_uncertain),
            "sol_uncertain_track_count": len(sol_uncertain),
            "safe_selection_agreement_count": safe,
            "unsafe_selection_disagreement_count": wrong,
            "safe_selection_evaluable_count": safe + wrong,
            "safe_selection_agreement_rate": _rate(safe, safe + wrong),
            "exact_source_agreement_count": exact,
            "exact_source_evaluable_count": exact_denominator,
            "exact_source_agreement_rate": _rate(exact, exact_denominator),
            "disagreement_case_count": len(disagreements),
            "random_audit_track_count": len(random_ids),
            "manual_audit_track_count": len(audit_ids),
            "manual_audit_candidate_count": sum(
                len(video_ids) for video_ids in audit_candidate_ids.values()
            ),
        },
        "disagreement_cases": disagreements,
        "sol_uncertain_cases": sol_uncertain,
        "resolver_uncertain_cases": resolver_uncertain,
        "random_audit_track_ids": random_ids,
        "cases": cases,
        "limitations": [
            "Sol judgments are independent semantic triage, not human ground truth.",
            "The resolver proposal is deliberately uncalibrated and cannot activate AUTO_MATCH.",
            "Agreement can share systematic metadata-only errors; random human audits are required.",
        ],
    }

    audit = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "status": "AWAITING_TARGETED_HUMAN_AUDIT",
        "manifest_sha256": manifest.sha256,
        "selection_reasons": {
            stable_id: sorted(reason_by_id[stable_id]) for stable_id in audit_ids
        },
        "track_count": len(audit_ids),
        "candidate_count": sum(
            len(video_ids) for video_ids in audit_candidate_ids.values()
        ),
        "tracks": [
            {
                "blind_input": {
                    **blind_by_id[stable_id],
                    "candidates": [
                        candidate
                        for candidate in blind_by_id[stable_id]["candidates"]
                        if candidate["video_id"] in audit_candidate_ids[stable_id]
                    ],
                },
                "comparison": case_by_id[stable_id],
                "sol": sol_by_id[stable_id],
                "audit_reasons": sorted(reason_by_id[stable_id]),
            }
            for stable_id in audit_ids
        ],
        "human_labels_source": "reports/stage5b1b/heldout_review.csv",
    }
    queue = {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "manifest_sha256": manifest.sha256,
        "source_comparison_sha256": None,
        "track_ids": audit_ids,
        "cases": [
            {
                "stable_track_id": stable_id,
                "candidate_video_ids": audit_candidate_ids[stable_id],
                "reasons": sorted(reason_by_id[stable_id]),
            }
            for stable_id in audit_ids
        ],
        "selection_reasons": {
            stable_id: sorted(reason_by_id[stable_id]) for stable_id in audit_ids
        },
    }
    return comparison, audit, queue


def write_comparison_artifacts(config: SolAuditConfig) -> dict[str, Any]:
    comparison, audit, queue = compare_sol_and_resolver(config)
    atomic_json(config.artifacts["comparison"], comparison)
    atomic_json(config.artifacts["manual_audit"], audit)
    queue["source_comparison_sha256"] = file_sha256(config.artifacts["comparison"])
    atomic_json(config.artifacts["manual_audit_queue"], queue)
    return {
        "status": comparison["status"],
        **comparison["summary"],
        "comparison": str(config.artifacts["comparison"]),
        "manual_audit": str(config.artifacts["manual_audit"]),
        "manual_audit_queue": str(config.artifacts["manual_audit_queue"]),
    }


def load_audit_queue(
    path: str | Path, manifest_sha256: str
) -> dict[str, tuple[str, ...]]:
    value = _load_json(path)
    if value.get("schema_version") != QUEUE_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected manual audit queue schema")
    if value.get("manifest_sha256") != manifest_sha256:
        raise Stage5B1AValidationError("manual audit queue manifest hash mismatch")
    track_ids = value.get("track_ids")
    if not isinstance(track_ids, list) or any(
        not isinstance(stable_id, str) or not stable_id for stable_id in track_ids
    ):
        raise Stage5B1AValidationError("manual audit queue track_ids are invalid")
    if len(track_ids) != len(set(track_ids)):
        raise Stage5B1AValidationError("manual audit queue contains duplicate tracks")
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != len(track_ids):
        raise Stage5B1AValidationError("manual audit queue cases are invalid")
    result: dict[str, tuple[str, ...]] = {}
    for expected_id, case in zip(track_ids, cases):
        if not isinstance(case, dict) or case.get("stable_track_id") != expected_id:
            raise Stage5B1AValidationError("manual audit queue case order is invalid")
        video_ids = case.get("candidate_video_ids")
        if not isinstance(video_ids, list) or not video_ids or any(
            not isinstance(video_id, str) or not video_id for video_id in video_ids
        ) or len(video_ids) != len(set(video_ids)):
            raise Stage5B1AValidationError("manual audit candidate identities are invalid")
        result[expected_id] = tuple(video_ids)
    return result
