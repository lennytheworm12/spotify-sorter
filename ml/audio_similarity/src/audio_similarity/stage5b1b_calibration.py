"""Offline Stage 5B.1B human/Sol/resolver calibration analysis."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_calibration_sol import CalibrationSolConfig, mapped_sol_judgments
from .stage5b1b_resolver import (
    AUTO_MATCH,
    SAFE_LABELS,
    derive_duration_boundaries,
    duration_band,
    human_label_state,
    policy_variants,
    resolve_dataset,
)


CALIBRATION_STATUS = "STAGE5B1B_POLICY_READY_FOR_FRESH_CHALLENGE_VALIDATION"
POLICY_STATUS = "CANDIDATE_POLICY_ONLY"


def _json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _human_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 248:
        raise Stage5B1AValidationError("calibration human-review universe must contain 248 rows")
    return rows


def _feature_index(dataset: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result = {}
    for track in dataset["tracks"]:
        stable_id = track["track"]["stable_track_id"]
        for wrapped in track["candidates"]:
            key = (stable_id, wrapped["candidate"]["youtube_video_id"])
            if key in result:
                raise Stage5B1AValidationError("duplicate calibration candidate identity")
            result[key] = wrapped
    if len(result) != 248:
        raise Stage5B1AValidationError("calibration feature universe must contain 248 candidates")
    return result


def _sol_index(sol: dict[str, Any]) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    candidates = {}
    tracks = {}
    for track in sol["tracks"]:
        stable_id = track["stable_track_id"]
        tracks[stable_id] = track
        for candidate in track["candidates"]:
            candidates[(stable_id, candidate["youtube_video_id"])] = candidate
    if len(candidates) != 248 or len(tracks) != 50:
        raise Stage5B1AValidationError("mapped Sol universe must contain 50 tracks / 248 candidates")
    return candidates, tracks


def _human_index(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    return {
        (row["stable_track_id"], row["candidate_video_id"]): row
        for row in rows
        if row["candidate_review_label"]
    }


def _safety(label: str) -> str:
    return human_label_state(label)


def sol_human_agreement(
    human: dict[tuple[str, str], dict[str, str]],
    sol: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    exact_matrix: Counter[str] = Counter()
    safety_matrix: Counter[str] = Counter()
    disagreements = []
    for key, human_row in human.items():
        human_label = human_row["candidate_review_label"]
        sol_row = sol[key]
        sol_label = sol_row["label"]
        exact_matrix[f"{human_label}->{sol_label}"] += 1
        human_safety, sol_safety = _safety(human_label), _safety(sol_label)
        safety_matrix[f"{human_safety}->{sol_safety}"] += 1
        if human_label != sol_label or human_safety != sol_safety:
            disagreements.append(
                {
                    "stable_track_id": key[0],
                    "video_id": key[1],
                    "human_label": human_label,
                    "human_safety": human_safety,
                    "human_note_verbatim": human_row["candidate_note"],
                    "sol_label": sol_label,
                    "sol_safety": sol_safety,
                    "sol_recording_identity_reason": sol_row["recording_identity_reason"],
                    "sol_source_quality_reason": sol_row["source_quality_reason"],
                    "sol_uncertainty_reason": sol_row["uncertainty_reason"],
                }
            )
    exact_count = sum(
        count for transition, count in exact_matrix.items() if len(set(transition.split("->"))) == 1
    )
    safety_count = sum(
        count for transition, count in safety_matrix.items() if len(set(transition.split("->"))) == 1
    )
    human_resolved = sum(_safety(row["candidate_review_label"]) != "UNRESOLVED" for row in human.values())
    both_resolved = sum(
        _safety(row["candidate_review_label"]) != "UNRESOLVED"
        and _safety(sol[key]["label"]) != "UNRESOLVED"
        for key, row in human.items()
    )
    both_resolved_agree = sum(
        _safety(row["candidate_review_label"]) == _safety(sol[key]["label"])
        and _safety(row["candidate_review_label"]) != "UNRESOLVED"
        and _safety(sol[key]["label"]) != "UNRESOLVED"
        for key, row in human.items()
    )
    return {
        "schema_version": "stage5b1b-sol-human-agreement-v1",
        "targeted_human_candidate_count": len(human),
        "exact_label_agreement_count": exact_count,
        "exact_label_agreement_rate": exact_count / len(human),
        "all_state_safety_agreement_count": safety_count,
        "all_state_safety_agreement_rate": safety_count / len(human),
        "human_resolved_candidate_count": human_resolved,
        "both_resolved_candidate_count": both_resolved,
        "both_resolved_safety_agreement_count": both_resolved_agree,
        "both_resolved_safety_agreement_rate": both_resolved_agree / both_resolved,
        "exact_label_matrix": dict(sorted(exact_matrix.items())),
        "safety_matrix": dict(sorted(safety_matrix.items())),
        "disagreements": disagreements,
        "bias_warning": (
            "The 80 human rows are a targeted audit, not a representative random sample. "
            "Sol labels on the remaining 168 rows are diagnostic evidence, not human ground truth."
        ),
    }


def _label_summary(keys: list[tuple[str, str]], human: dict[tuple[str, str], dict[str, str]]) -> dict[str, Any]:
    labels = Counter(human[key]["candidate_review_label"] for key in keys if key in human)
    resolved = labels["IDEAL"] + labels["ACCEPTABLE"] + labels["WRONG"]
    safe = labels["IDEAL"] + labels["ACCEPTABLE"]
    return {
        "human_audited_count": sum(labels.values()),
        "IDEAL": labels["IDEAL"],
        "ACCEPTABLE": labels["ACCEPTABLE"],
        "WRONG": labels["WRONG"],
        "UNCERTAIN": labels["UNCERTAIN"],
        "resolved_human_count": resolved,
        "safe_rate_among_resolved_human_labels": safe / resolved if resolved else None,
    }


def feature_label_analysis(
    features: dict[tuple[str, str], dict[str, Any]],
    human: dict[tuple[str, str], dict[str, str]],
    boundaries: Any,
) -> dict[str, Any]:
    patterns: dict[str, list[tuple[str, str]]] = defaultdict(list)
    numeric: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for key in human:
        feature = features[key]["features"]
        source = feature["source"]
        provenance = source["provenance"]
        identity = feature["identity"]
        versions = feature["versions"]
        description = feature["description_evidence"]
        weak = feature["weak_evidence"]
        band = duration_band(feature["duration"]["absolute_duration_delta_seconds"], boundaries)
        label = human[key]["candidate_review_label"]
        safety = _safety(label)
        numeric_values = {
            "absolute_duration_delta_seconds": feature["duration"][
                "absolute_duration_delta_seconds"
            ],
            "relative_duration_delta": feature["duration"]["relative_duration_delta"],
            "title_similarity": identity["title_similarity"],
            "artist_similarity": identity["artist_similarity"],
            "relative_view_strength": weak["relative_view_strength"],
            "log_relative_view_strength": weak["log_relative_view_strength"],
            "search_rank": weak["search_rank"],
        }
        for name, value in numeric_values.items():
            if value is not None:
                numeric[name][label].append(float(value))
                numeric[name][safety].append(float(value))
        attributes = {
            f"source:{source['source_type']}",
            f"duration:{band}",
            f"search_rank:{weak['search_rank']}",
            f"title_exact:{identity['title_exact_normalized_match']}",
            f"primary_artist_match:{identity['primary_artist_match']}",
            f"version_conflict:{bool(versions['version_conflict_count'])}",
            f"version_absent:{bool(versions['version_absent_count'])}",
            "version_state:" + (
                "CONFLICT" if versions["version_conflict_count"]
                else "ABSENT" if versions["version_absent_count"]
                else "MATCH"
            ),
            f"topic_channel:{provenance['topic_channel_signal']}",
            f"provided_to_youtube_by:{provenance['provided_to_youtube_by_signal']}",
            f"auto_generated_by_youtube:{provenance['auto_generated_by_youtube_signal']}",
            f"structured_release_metadata:{provenance['structured_release_metadata_signal']}",
            f"description_album_match:{description['description_album_match']}",
            f"description_release_year_match:{description['description_release_year_match']}",
        }
        for attribute in attributes:
            patterns[attribute].append(key)
        strong = (
            feature["recording_eligible"]
            and identity["title_exact_normalized_match"]
            and identity["primary_artist_match"]
            and not versions["version_conflict_count"]
        )
        if strong and provenance["topic_channel_signal"]:
            patterns["canonical_pattern:strong_identity+topic_channel"].append(key)
        if (
            strong
            and provenance["provided_to_youtube_by_signal"]
            and band in {"DURATION_VERY_CLOSE", "DURATION_CLOSE"}
        ):
            patterns["canonical_pattern:strong_identity+provided_to_youtube+close_duration"].append(key)
        if strong and source["source_type"] == "OFFICIAL_AUDIO" and band in {
            "DURATION_VERY_CLOSE", "DURATION_CLOSE"
        }:
            patterns["canonical_pattern:strong_identity+official_audio+close_duration"].append(key)
        relative = weak["relative_view_strength"]
        if (
            strong
            and source["source_type"] == "LYRIC_VIDEO"
            and band in {"DURATION_VERY_CLOSE", "DURATION_CLOSE"}
            and relative is not None
        ):
            bucket = "at_least_0.001" if relative >= 0.001 else "below_0.001"
            patterns[f"lyric_pattern:strong_identity+close_duration+relative_views_{bucket}"].append(key)
    rows = {
        name: {"pattern": name, **_label_summary(keys, human)}
        for name, keys in sorted(patterns.items())
    }

    def numeric_summary(values: list[float]) -> dict[str, Any]:
        ordered = sorted(values)

        def quantile(q: float) -> float:
            position = (len(ordered) - 1) * q
            lower = int(position)
            upper = min(lower + 1, len(ordered) - 1)
            fraction = position - lower
            return ordered[lower] + fraction * (ordered[upper] - ordered[lower])

        return {
            "count": len(ordered),
            "minimum": ordered[0],
            "q25": quantile(0.25),
            "median": quantile(0.5),
            "q75": quantile(0.75),
            "maximum": ordered[-1],
        }

    numeric_rows = {
        name: {
            group: numeric_summary(values)
            for group, values in sorted(groups.items())
        }
        for name, groups in sorted(numeric.items())
    }
    return {
        "schema_version": "stage5b1b-feature-label-analysis-v1",
        "targeted_human_candidate_count": len(human),
        "patterns": rows,
        "numeric_distributions_by_human_label_and_safety": numeric_rows,
        "small_cell_warning": "Patterns with few audited rows are descriptive only.",
        "duration_raw_values_retained": True,
        "relative_views_are_late_weak_evidence": True,
    }


def _policy_metrics(
    decisions: dict[str, Any],
    human: dict[tuple[str, str], dict[str, str]],
    sol_candidates: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    human_labels: Counter[str] = Counter()
    human_safety: Counter[str] = Counter()
    sol_labels: Counter[str] = Counter()
    sol_safety: Counter[str] = Counter()
    audited = unaudited = 0
    selected = []
    for row in decisions["tracks"]:
        decision = row["decision"]
        if decision["status"] != AUTO_MATCH:
            continue
        key = (row["stable_track_id"], decision["selected_video_id"])
        human_row = human.get(key)
        human_label = human_row["candidate_review_label"] if human_row else None
        sol_row = sol_candidates[key]
        human_labels[human_label or "UNAUDITED"] += 1
        sol_labels[sol_row["label"]] += 1
        human_safety[_safety(human_label) if human_label else "UNAUDITED"] += 1
        sol_safety[_safety(sol_row["label"])] += 1
        audited += human_row is not None
        unaudited += human_row is None
        selected.append(
            {
                "stable_track_id": key[0],
                "video_id": key[1],
                "candidate_rank": decision["selected_candidate_rank"],
                "human_label": human_label,
                "human_note_verbatim": human_row["candidate_note"] if human_row else None,
                "sol_label": sol_row["label"],
                "sol_reason": sol_row["recording_identity_reason"],
            }
        )
    total = decisions["summary"]["track_count"]
    auto = decisions["summary"]["auto_match_count"]
    return {
        "policy_id": decisions["policy"]["policy_id"],
        "track_count": total,
        "auto_match_count": auto,
        "automatic_track_coverage": auto / total,
        "match_uncertain_count": decisions["summary"]["match_uncertain_count"],
        "match_uncertain_rate": decisions["summary"]["match_uncertain_count"] / total,
        "human_audited_selected_count": audited,
        "selected_without_human_audit_count": unaudited,
        "human_selected_label_counts": dict(sorted(human_labels.items())),
        "human_selected_safety_counts": dict(sorted(human_safety.items())),
        "known_human_wrong_auto_match_count": human_labels["WRONG"],
        "known_human_uncertain_auto_match_count": human_labels["UNCERTAIN"],
        "known_human_safe_auto_match_count": human_labels["IDEAL"] + human_labels["ACCEPTABLE"],
        "sol_selected_label_counts": dict(sorted(sol_labels.items())),
        "sol_selected_safety_counts": dict(sorted(sol_safety.items())),
        "sol_wrong_auto_match_count": sol_labels["WRONG"],
        "sol_uncertain_auto_match_count": sol_labels["UNCERTAIN"],
        "selected_tracks": selected,
        "targeted_audit_bias_warning": (
            "Selected-candidate human counts apply only where the targeted queue happened "
            "to include that candidate; they are not full-universe precision."
        ),
    }


def _select_policy(metrics: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any]]:
    if not metrics:
        return None, {"reason": "no policy variants evaluated"}
    candidates = list(metrics)
    stages = []
    for field in (
        "known_human_wrong_auto_match_count",
        "known_human_uncertain_auto_match_count",
        "sol_wrong_auto_match_count",
        "sol_uncertain_auto_match_count",
    ):
        best = min(row[field] for row in candidates)
        candidates = [row for row in candidates if row[field] == best]
        stages.append({"criterion": field, "minimum": best, "remaining": [row["policy_id"] for row in candidates]})
    selected = max(candidates, key=lambda row: row["auto_match_count"])
    return selected["policy_id"], {
        "selection_priority": "lexicographic safety-first, then maximum track coverage",
        "stages": stages,
        "coverage_tiebreak": selected["auto_match_count"],
        "selected_policy_id": selected["policy_id"],
    }


def _three_way(
    dataset: dict[str, Any],
    decisions: dict[str, Any],
    sol_candidates: dict[tuple[str, str], dict[str, Any]],
    sol_tracks: dict[str, dict[str, Any]],
    human: dict[tuple[str, str], dict[str, str]],
) -> dict[str, Any]:
    raw_by_id = {row["track"]["stable_track_id"]: row for row in dataset["tracks"]}
    rows = []
    for resolver_row in decisions["tracks"]:
        stable_id = resolver_row["stable_track_id"]
        decision = resolver_row["decision"]
        raw_track = raw_by_id[stable_id]
        selected_id = decision["selected_video_id"]
        selected_wrapped = next(
            (
                item for item in raw_track["candidates"]
                if item["candidate"]["youtube_video_id"] == selected_id
            ),
            None,
        )
        human_row = human.get((stable_id, selected_id)) if selected_id else None
        sol_row = sol_candidates.get((stable_id, selected_id)) if selected_id else None
        rows.append(
            {
                "stable_track_id": stable_id,
                "target": raw_track["track"],
                "resolver": decision,
                "selected_raw_candidate": selected_wrapped["candidate"] if selected_wrapped else None,
                "sol_label_for_selected": sol_row["label"] if sol_row else None,
                "sol_reason_for_selected": (
                    {
                        "recording_identity": sol_row["recording_identity_reason"],
                        "source_quality": sol_row["source_quality_reason"],
                        "uncertainty": sol_row["uncertainty_reason"],
                    }
                    if sol_row else None
                ),
                "sol_preferred_video_id": sol_tracks[stable_id]["selected_video_id"],
                "sol_selection_status": sol_tracks[stable_id]["selection_status"],
                "human_label_for_selected": human_row["candidate_review_label"] if human_row else None,
                "human_note_verbatim": human_row["candidate_note"] if human_row else None,
                "selected_candidate_human_audited": human_row is not None,
            }
        )
    return {
        "schema_version": "stage5b1b-three-way-comparison-v1",
        "policy_id": decisions["policy"]["policy_id"],
        "tracks": rows,
        "human_missing_means_unaudited_not_safe": True,
    }


def _policy_artifact(
    selected: str,
    variants: dict[str, dict[str, Any]],
    metrics: dict[str, dict[str, Any]],
    boundaries: Any,
    duration_evidence: dict[str, Any],
    config: CalibrationSolConfig,
    features_path: Path,
) -> dict[str, Any]:
    decisions = variants[selected]
    return {
        "schema_version": "stage5b1b-resolver-policy-candidate-v1",
        "policy_version": "resolver_policy_candidate_v1",
        "status": POLICY_STATUS,
        "production_status": "NOT_PRODUCTION_ACTIVATED",
        "next_gate": "FRESH_CHALLENGE_SET_VALIDATION_REQUIRED",
        "policy": decisions["policy"],
        "hierarchy": [
            "recording eligibility and explicit conflicts",
            "target-relative version compatibility",
            "title and explicit performer identity",
            "empirical duration band",
            "canonical provenance",
            "source preference",
            "description album/release evidence",
            "relative views and search rank as weak tiebreakers",
        ],
        "duration_boundaries": asdict(boundaries),
        "duration_derivation_evidence": duration_evidence,
        "source_preference": [
            "ART_TRACK_TOPIC",
            "OFFICIAL_AUDIO",
            "LYRIC_VIDEO",
            "OFFICIAL_MUSIC_VIDEO",
            "OTHER",
        ],
        "match_uncertain_condition": "no candidate satisfies every hierarchical policy gate",
        "human_evidence_summary": metrics[selected],
        "sol_evidence_summary": {
            "evaluation_sha256": file_sha256(config.evaluations_path),
            "model": config.model,
            "blind_payload_sha256": config.payload_sha256,
            "selected_label_counts": metrics[selected]["sol_selected_label_counts"],
        },
        "source_artifact_hashes": {
            "manifest": config.manifest_sha256,
            "discovery": config.discovery_sha256,
            "human_review": config.human_review_sha256,
            "feature_v1": config.feature_v1_sha256,
            "feature_v2": file_sha256(features_path),
            "blinded_sol_payload": config.payload_sha256,
            "blinded_sol_private_mapping": config.mapping_sha256,
            "sol_evaluations": file_sha256(config.evaluations_path),
        },
        "known_limitations": [
            "The human audit is targeted rather than a representative sample.",
            "Eight selected calibration candidates lack direct human labels under this policy.",
            "Sol judgments on unaudited candidates are diagnostic and not human ground truth.",
            "Duration thresholds were calibrated on this same 50-track universe.",
            "A fresh challenge set is required before any production activation.",
        ],
        "media_activity": {
            "audio_downloads": 0,
            "video_downloads": 0,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
            "new_youtube_searches": 0,
        },
    }


def run_calibration_analysis(
    config: CalibrationSolConfig,
    *,
    feature_v2_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    feature_path = Path(feature_v2_path)
    dataset = _json(feature_path)
    if dataset.get("feature_schema_version") != "stage5b1b-candidate-features-v2":
        raise Stage5B1AValidationError("calibration requires v2 candidate features")
    human_rows = _human_rows(config.human_review_path)
    human = _human_index(human_rows)
    if len(human) != 80 or Counter(row["candidate_review_label"] for row in human.values()) != {
        "IDEAL": 32, "ACCEPTABLE": 28, "WRONG": 5, "UNCERTAIN": 15
    }:
        raise Stage5B1AValidationError("targeted human audit changed before calibration")
    feature_index = _feature_index(dataset)
    sol = mapped_sol_judgments(config)
    sol_candidates, sol_tracks = _sol_index(sol)
    boundaries, duration_evidence = derive_duration_boundaries(
        (feature_index[key]["features"], row["candidate_review_label"])
        for key, row in human.items()
    )
    variant_outputs = {
        spec.policy_id: resolve_dataset(dataset, spec, boundaries)
        for spec in policy_variants()
    }
    metrics = {
        policy_id: _policy_metrics(output, human, sol_candidates)
        for policy_id, output in variant_outputs.items()
    }
    selected, selection = _select_policy(list(metrics.values()))
    if selected is None:
        raise Stage5B1AValidationError("no candidate resolver policy could be selected")
    agreement = sol_human_agreement(human, sol_candidates)
    patterns = feature_label_analysis(feature_index, human, boundaries)
    three_way = _three_way(
        dataset, variant_outputs[selected], sol_candidates, sol_tracks, human
    )
    policy = _policy_artifact(
        selected, variant_outputs, metrics, boundaries, duration_evidence, config, feature_path
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "resolver_policy_variants.json": {
            "schema_version": "stage5b1b-policy-variants-v1",
            "duration_evidence": duration_evidence,
            "metrics": metrics,
            "decisions": variant_outputs,
            "selection": selection,
        },
        "sol_human_agreement.json": agreement,
        "feature_label_analysis.json": patterns,
        "three_way_comparison.json": three_way,
        "resolver_policy_candidate_v1.json": policy,
    }
    for name, value in artifacts.items():
        atomic_json(output / name, value)
    summary = {
        "schema_version": "stage5b1b-calibration-summary-v1",
        "status": CALIBRATION_STATUS,
        "selected_policy_id": selected,
        "policy_artifact": "resolver_policy_candidate_v1.json",
        "policy_artifact_sha256": file_sha256(output / "resolver_policy_candidate_v1.json"),
        "policy_metrics": metrics[selected],
        "duration_boundaries": asdict(boundaries),
        "sol_human_agreement": {
            key: agreement[key]
            for key in (
                "exact_label_agreement_count",
                "exact_label_agreement_rate",
                "all_state_safety_agreement_count",
                "all_state_safety_agreement_rate",
                "both_resolved_safety_agreement_count",
                "both_resolved_safety_agreement_rate",
            )
        },
        "production_auto_match_activated": False,
        "fresh_challenge_validation_required": True,
        "media_activity": policy["media_activity"],
    }
    atomic_json(output / "calibration_summary.json", summary)
    return summary
