"""Stage 5B.1C-C strong-metadata fallback over the frozen challenge tail.

This layer runs only after Balanced V1, 1C-A, and 1C-B.  It adds two narrowly
scoped mechanisms: deterministic presentation-credit equivalence and a bounded
duration exception for strongly corroborated, explicit-version Official Audio.
It does not modify any preceding policy or their feature extraction.
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_challenge import load_challenge_config, load_challenge_manifest
from .stage5b1b_challenge_audit import QUEUE_SCHEMA_VERSION, REVIEW_COLUMNS
from .stage5b1b_identity import MATCH
from .stage5b1b_resolver import AUTO_MATCH, MATCH_UNCERTAIN
from .stage5b1c_diagnostic import (
    FROZEN_UNRESOLVED_IDS,
    STRONG_METADATA_RECOVERY,
    verify_frozen_source_neutral,
    verify_frozen_tier2_human_audit,
)
from .stage5b1c_normalization import (
    Tier2TitleIdentity,
    normalize_performer,
    parse_tier2_title,
    split_title_performer,
)
from .stage5b1c_review import tier2_review_rows
from .stage5b1c_source_neutral import _source_neutral_ordering_key
from .stage5b1c_tier2 import _human_labels, _mapped_sol


STRONG_METADATA_POLICY_ID = "POLICY_TIER2_STRONG_METADATA_V1"
STRONG_METADATA_FEATURE_SCHEMA_VERSION = "stage5b1c-strong-metadata-candidate-features-v1"
STRONG_METADATA_DATASET_SCHEMA_VERSION = "stage5b1c-strong-metadata-feature-dataset-v1"
STRONG_METADATA_DECISION_SCHEMA_VERSION = "stage5b1c-strong-metadata-decisions-v1"
STRONG_METADATA_REVIEW_CONTRACT_VERSION = "stage5b1c-strong-metadata-human-review-v1"
STRONG_METADATA_REVIEW_STATUS = "AWAITING_STRONG_METADATA_HUMAN_REVIEW"

FROZEN_DIAGNOSTIC_SHA256 = (
    "9968f84d5dbd4825f88dd0fdc329971d93db87e0b2cd9f2b89364f2cbf145ebf"
)
NORMAL_DURATION_CLOSE_SECONDS = 7
CONTEXTUAL_OFFICIAL_AUDIO_MAX_DELTA_SECONDS = 15
DIAGNOSTIC_DURATION_OUTLIER_SECONDS = 14.76400000000001
FROZEN_HUMAN_SAFE_MAX_DELTA_SECONDS = 6.800000000000011

TITLE_MISMATCH_REASON = "normalized structural core title does not match"
DURATION_REASON = "duration exceeds frozen Balanced DURATION_CLOSE boundary"
UNREQUESTED_MODIFICATION_REASON = "explicit unrequested modified-audio presentation"

RULE_PRESENTATION_EQUIVALENCE = "STRONG_PRESENTATION_EQUIVALENCE_V1"
RULE_CONTEXTUAL_OFFICIAL_AUDIO_DURATION = "STRONG_OFFICIAL_AUDIO_VERSION_DURATION_V1"

_CREDIT_SUFFIX = re.compile(
    r"\(\s*(?:with|feat(?:uring)?|ft)\.?\s+([^)]*)\)\s*$", re.I
)
_CREDIT_SEPARATOR = re.compile(
    r"\s*(?:,|&|\band\b|\bfeat(?:uring)?\.?\b|\bft\.?\b)\s*", re.I
)
_MODIFICATION_PATTERNS = {
    "acoustic": re.compile(r"\bacoustic\b", re.I),
    "bass_boosted": re.compile(r"\bbass[\s-]*boost(?:ed)?\b", re.I),
    "clean": re.compile(r"\bclean\b", re.I),
    "cover": re.compile(r"\bcover(?:ed)?(?:\s+by)?\b", re.I),
    "instrumental": re.compile(r"\binstrumental\b", re.I),
    "karaoke": re.compile(r"\bkaraoke\b", re.I),
    "live": re.compile(r"\blive\b", re.I),
    "mashup": re.compile(r"\bmash[\s-]*up\b", re.I),
    "nightcore": re.compile(r"\bnightcore\b", re.I),
    "reverb": re.compile(r"\breverb(?:ed)?\b", re.I),
    "slowed": re.compile(r"\b(?:slowed|slow\s+version)\b", re.I),
    "sped_up": re.compile(r"\b(?:sped\s*up|\d+(?:\.\d+)?x\s*speed)\b", re.I),
}
_DURATION_EXCEPTION_FORBIDDEN_FAMILIES = {
    "acoustic",
    "bass_boosted",
    "instrumental",
    "karaoke",
    "live",
    "mashup",
    "nightcore",
    "reverb",
    "slowed",
    "sped_up",
}


def _normalized_artist_set(artists: Iterable[str]) -> set[str]:
    return {value for artist in artists if (value := normalize_performer(artist))}


def _credit_aliases(value: str) -> tuple[str, ...]:
    return tuple(
        alias
        for part in _CREDIT_SEPARATOR.split(value)
        if (alias := normalize_performer(part))
    )


def strip_trailing_credited_artist_presentation(
    title: str, expected_artists: Iterable[str]
) -> tuple[str, tuple[str, ...]]:
    """Strip a trailing ``(with/feat <artists>)`` only when every name is credited."""

    match = _CREDIT_SUFFIX.search(title)
    if not match:
        return title, ()
    aliases = _credit_aliases(match.group(1))
    expected = _normalized_artist_set(expected_artists)
    if not aliases or any(alias not in expected for alias in aliases):
        return title, ()
    return title[: match.start()].rstrip(), aliases


def _strict_prefix_candidate_parse(
    title: str, expected_artists: Iterable[str]
) -> tuple[Tier2TitleIdentity, tuple[str, ...]]:
    """Allow reordered performer prefixes only when every delimited name is credited."""

    separated = split_title_performer(title)
    if separated:
        aliases = _credit_aliases(separated[0])
        expected = _normalized_artist_set(expected_artists)
        if aliases and all(alias in expected for alias in aliases):
            return parse_tier2_title(separated[1], candidate=False), aliases
    return parse_tier2_title(title, expected_artists=expected_artists, candidate=True), ()


def presentation_title_evidence(
    track: SpotifyTrack, candidate_title: str
) -> dict[str, Any]:
    target_text, removed_credits = strip_trailing_credited_artist_presentation(
        track.title, track.artists
    )
    target = parse_tier2_title(target_text, candidate=False)
    candidate, prefix_credits = _strict_prefix_candidate_parse(
        candidate_title, track.artists
    )
    return {
        "target": target.to_dict(),
        "candidate": candidate.to_dict(),
        "removed_target_credit_aliases": list(removed_credits),
        "validated_candidate_prefix_aliases": list(prefix_credits),
        "exact_structural_match": bool(
            target.normalized_core_title
            and target.normalized_core_title == candidate.normalized_core_title
        ),
        "uses_credit_presentation_equivalence": bool(removed_credits or prefix_credits),
        "fuzzy_matching_used": False,
    }


def modification_evidence(target_title: str, candidate_title: str) -> dict[str, Any]:
    target_families = {
        family for family, pattern in _MODIFICATION_PATTERNS.items()
        if pattern.search(target_title)
    }
    candidate_families = {
        family for family, pattern in _MODIFICATION_PATTERNS.items()
        if pattern.search(candidate_title)
    }
    conflicts = sorted(candidate_families - target_families)
    return {
        "target_families": sorted(target_families),
        "candidate_families": sorted(candidate_families),
        "unrequested_candidate_families": conflicts,
        "explicit_conflict": bool(conflicts),
    }


def _duration_exception_evidence(
    feature: dict[str, Any],
    source_neutral: dict[str, Any],
    presentation: dict[str, Any],
    modifications: dict[str, Any],
) -> dict[str, Any]:
    versions = feature["versions"]
    relationships = versions["relationships"]
    target_families = {
        row["family"] for row in relationships if row.get("target_raw") is not None
    }
    explicit_version_match = bool(
        relationships
        and all(row["relationship"] == MATCH for row in relationships)
        and versions["match_count"] == len(relationships)
        and all(row.get("candidate_evidence_source") is not None for row in relationships)
    )
    performers = feature["performers"]
    delta = feature["duration"]["absolute_duration_delta_seconds"]
    provenance = source_neutral["provenance_evidence"]
    conditions = {
        "exact_structural_title": bool(
            feature["title"]["structural_core_title_match"]
            or presentation["exact_structural_match"]
        ),
        "primary_performer_match": bool(performers["primary_performer_match"]),
        "no_performer_conflict": not performers["explicit_performer_conflict"],
        "explicit_complete_version_match": explicit_version_match,
        "no_version_conflict_or_absence": bool(
            versions["conflict_count"] == 0 and versions["absent_count"] == 0
        ),
        "official_audio_source": feature["source"]["source_type"] == "OFFICIAL_AUDIO",
        "positive_corroborated_provenance": provenance["state"] == "POSITIVE_CORROBORATED",
        "no_unrequested_modified_audio": not modifications["explicit_conflict"],
        "version_family_allows_duration_exception": not bool(
            target_families & _DURATION_EXCEPTION_FORBIDDEN_FAMILIES
        ),
        "duration_above_normal_gate": bool(
            delta is not None and math.isfinite(delta) and delta > NORMAL_DURATION_CLOSE_SECONDS
        ),
        "duration_within_contextual_cap": bool(
            delta is not None
            and math.isfinite(delta)
            and delta <= CONTEXTUAL_OFFICIAL_AUDIO_MAX_DELTA_SECONDS
        ),
    }
    return {
        "conditions": conditions,
        "eligible": all(conditions.values()),
        "target_version_families": sorted(target_families),
        "normal_duration_close_seconds": NORMAL_DURATION_CLOSE_SECONDS,
        "contextual_max_delta_seconds": CONTEXTUAL_OFFICIAL_AUDIO_MAX_DELTA_SECONDS,
        "absolute_duration_delta_seconds": delta,
    }


def extract_strong_metadata_evidence(
    track: SpotifyTrack, item: dict[str, Any]
) -> dict[str, Any]:
    candidate = item["candidate"]
    feature = item["tier2a_features"]
    source_neutral = item["source_neutral"]
    presentation = presentation_title_evidence(track, str(candidate.get("title") or ""))
    modifications = modification_evidence(track.title, str(candidate.get("title") or ""))
    duration_exception = _duration_exception_evidence(
        feature, source_neutral, presentation, modifications
    )
    prior_reasons = list(source_neutral["remaining_gate_reasons"])
    remaining = list(prior_reasons)
    waivers: list[dict[str, str]] = []
    new_hard_reasons: list[str] = []

    if modifications["explicit_conflict"]:
        new_hard_reasons.append(UNREQUESTED_MODIFICATION_REASON)
    if (
        TITLE_MISMATCH_REASON in remaining
        and presentation["exact_structural_match"]
        and not modifications["explicit_conflict"]
    ):
        remaining.remove(TITLE_MISMATCH_REASON)
        waivers.append(
            {
                "reason": TITLE_MISMATCH_REASON,
                "rule_id": RULE_PRESENTATION_EQUIVALENCE,
                "basis": (
                    "exact structural title after removing only validated credited-artist "
                    "and source-presentation text"
                ),
            }
        )
    if DURATION_REASON in remaining and duration_exception["eligible"]:
        remaining.remove(DURATION_REASON)
        waivers.append(
            {
                "reason": DURATION_REASON,
                "rule_id": RULE_CONTEXTUAL_OFFICIAL_AUDIO_DURATION,
                "basis": (
                    "exact identity and explicit version MATCH on corroborated Official "
                    "Audio within the frozen 15-second experimental cap"
                ),
            }
        )
    remaining.extend(reason for reason in new_hard_reasons if reason not in remaining)
    return {
        "schema_version": STRONG_METADATA_FEATURE_SCHEMA_VERSION,
        "track_id": track.stable_track_id,
        "candidate_video_id": candidate["youtube_video_id"],
        "presentation_title_evidence": presentation,
        "modification_evidence": modifications,
        "contextual_duration_evidence": duration_exception,
        "prior_source_neutral_gate_reasons": prior_reasons,
        "strong_metadata_waivers": waivers,
        "new_hard_reasons": new_hard_reasons,
        "remaining_gate_reasons": remaining,
        "eligible": not remaining,
    }


def extract_strong_metadata_track(track_row: dict[str, Any]) -> dict[str, Any]:
    track = SpotifyTrack.from_dict(track_row["track"])
    return {
        "track": track.to_dict(),
        "query": track_row.get("query"),
        "candidates": [
            {
                **item,
                "strong_metadata": extract_strong_metadata_evidence(track, item),
            }
            for item in track_row["candidates"]
        ],
    }


def resolve_strong_metadata_track(track_row: dict[str, Any]) -> dict[str, Any]:
    accepted = [
        item for item in track_row["candidates"] if item["strong_metadata"]["eligible"]
    ]
    accepted.sort(key=_source_neutral_ordering_key)
    excluded = [
        {
            "video_id": item["candidate"]["youtube_video_id"],
            "candidate_rank": item["candidate"]["rank"],
            "title": item["candidate"].get("title"),
            "remaining_gate_reasons": item["strong_metadata"]["remaining_gate_reasons"],
        }
        for item in track_row["candidates"]
        if not item["strong_metadata"]["eligible"]
    ]
    if not accepted:
        return {
            "status": MATCH_UNCERTAIN,
            "policy_rule_id": STRONG_METADATA_POLICY_ID,
            "selected_video_id": None,
            "selected_candidate_rank": None,
            "uncertainty_reason": (
                "no candidate passes strong presentation or corroborated Official Audio "
                "duration fallback without remaining identity conflicts"
            ),
            "excluded_candidates": excluded,
        }

    selected = accepted[0]
    evidence = selected["strong_metadata"]
    rules = [row["rule_id"] for row in evidence["strong_metadata_waivers"]]
    return {
        "status": AUTO_MATCH,
        "policy_rule_id": STRONG_METADATA_POLICY_ID,
        "selected_video_id": selected["candidate"]["youtube_video_id"],
        "selected_candidate_rank": selected["candidate"]["rank"],
        "selection_rule_ids": rules,
        "selection_reason": (
            "all frozen identity/version/source gates pass after only the recorded strong-"
            "metadata waiver; explicit modification conflicts remain ineligible"
        ),
        "evidence_summary": evidence,
        "ranked_plausible_candidates": [
            item["candidate"]["youtube_video_id"] for item in accepted
        ],
        "excluded_candidates": excluded,
    }


def _load_frozen_diagnostic(path: Path) -> dict[str, Any]:
    if file_sha256(path) != FROZEN_DIAGNOSTIC_SHA256:
        raise Stage5B1AValidationError("frozen Stage 5B.1C-C diagnostic changed")
    value = json.loads(path.read_text(encoding="utf-8"))
    strong = {
        row["stable_track_id"]
        for row in value["tracks"]
        if row["recoverability"] == STRONG_METADATA_RECOVERY
    }
    if strong != {"s5b1c_012", "s5b1c_023"}:
        raise Stage5B1AValidationError("frozen strong-recovery diagnostic set changed")
    return value


def _frozen_human_safe_max_delta(
    config_path: Path, source_neutral_dir: Path
) -> tuple[float, dict[str, Any]]:
    audit = verify_frozen_tier2_human_audit(source_neutral_dir)
    audit_results = json.loads(
        (source_neutral_dir / "tier2_human_audit_results.json").read_text(encoding="utf-8")
    )
    safe_identities = {
        (row["stable_track_id"], row["candidate_video_id"])
        for row in audit_results["judgments"]
        if row["safety_class"] == "SAFE"
    }
    config = load_challenge_config(config_path)
    base_features = json.loads(config.artifacts["features"].read_text(encoding="utf-8"))
    deltas = {
        (track["track"]["stable_track_id"], item["candidate"]["youtube_video_id"]):
        item["features"]["duration"]["absolute_duration_delta_seconds"]
        for track in base_features["tracks"]
        for item in track["candidates"]
    }
    try:
        maximum = max(float(deltas[identity]) for identity in safe_identities)
    except KeyError as exc:
        raise Stage5B1AValidationError(
            f"human-safe Tier-2 candidate is absent from frozen features: {exc.args[0]}"
        ) from exc
    if not math.isclose(maximum, FROZEN_HUMAN_SAFE_MAX_DELTA_SECONDS, abs_tol=1e-12):
        raise Stage5B1AValidationError("frozen human-safe duration distribution changed")
    return maximum, audit


def _duration_bound_basis(
    diagnostic: dict[str, Any], human_safe_max_delta: float
) -> dict[str, Any]:
    duration_tracks = [
        row for row in diagnostic["tracks"]
        if row["recoverability"] == STRONG_METADATA_RECOVERY
        and row["primary_failed_gate"] == "DURATION_THRESHOLD"
    ]
    observed = max(
        row["diagnostic_strongest_candidate"]["tier2a_features"]["duration"][
            "absolute_duration_delta_seconds"
        ]
        for row in duration_tracks
    )
    derived = math.ceil(observed)
    if not math.isclose(observed, DIAGNOSTIC_DURATION_OUTLIER_SECONDS, abs_tol=1e-12):
        raise Stage5B1AValidationError("diagnostic duration outlier changed")
    if derived != CONTEXTUAL_OFFICIAL_AUDIO_MAX_DELTA_SECONDS:
        raise Stage5B1AValidationError("contextual duration cap is no longer diagnostic-bound")
    return {
        "normal_gate_seconds": NORMAL_DURATION_CLOSE_SECONDS,
        "frozen_human_safe_existing_max_delta_seconds": human_safe_max_delta,
        "diagnostic_strong_outlier_delta_seconds": observed,
        "derivation": "ceil(diagnostic strong duration outlier to next whole second)",
        "contextual_cap_seconds": derived,
        "global_duration_gate_changed": False,
    }


def evaluate_strong_metadata_challenge(
    config_path: Path,
    *,
    tier2a_dir: Path,
    source_neutral_dir: Path,
    diagnostic_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_features, source_decisions, source_hashes = verify_frozen_source_neutral(
        config_path, tier2a_dir, source_neutral_dir
    )
    diagnostic = _load_frozen_diagnostic(diagnostic_path)
    human_safe_max_delta, audit = _frozen_human_safe_max_delta(
        config_path, source_neutral_dir
    )
    bound_basis = _duration_bound_basis(diagnostic, human_safe_max_delta)
    decision_by_id = {
        row["stable_track_id"]: row["decision"] for row in source_decisions["tracks"]
    }
    unresolved_ids = tuple(
        stable_id for stable_id in FROZEN_UNRESOLVED_IDS
        if decision_by_id[stable_id]["status"] == MATCH_UNCERTAIN
    )
    if unresolved_ids != FROZEN_UNRESOLVED_IDS:
        raise Stage5B1AValidationError("frozen 1C-B unresolved tail changed")
    attempted = [
        extract_strong_metadata_track(row)
        for row in source_features["tracks"]
        if row["track"]["stable_track_id"] in unresolved_ids
    ]
    features = {
        "schema_version": STRONG_METADATA_DATASET_SCHEMA_VERSION,
        "dataset_role": "FROZEN_FRESH_CHALLENGE_AFTER_SOURCE_NEUTRAL_UNRESOLVED_ONLY",
        "source_neutral_features_sha256": source_hashes[
            "source_neutral_candidate_features.json"
        ],
        "diagnostic_sha256": FROZEN_DIAGNOSTIC_SHA256,
        "duration_bound_basis": bound_basis,
        "track_count": len(attempted),
        "candidate_pair_count": sum(len(row["candidates"]) for row in attempted),
        "tracks": attempted,
    }
    track_decisions = [
        {
            "stable_track_id": row["track"]["stable_track_id"],
            "decision": resolve_strong_metadata_track(row),
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
                "selection_rule_ids": decision["selection_rule_ids"],
                "sol_label": sol.get(identity, {}).get("label"),
                "sol_reason": sol.get(identity, {}).get("recording_identity_reason"),
                "human_label": human.get(identity, {}).get("label"),
                "human_note": human.get(identity, {}).get("note"),
                "evidence_summary": decision["evidence_summary"],
            }
        )
    selected_ids = {row["stable_track_id"] for row in selected}
    remaining = [stable_id for stable_id in unresolved_ids if stable_id not in selected_ids]
    combined = source_decisions["summary"]["combined_auto_match_count"] + len(selected)
    decisions = {
        "schema_version": STRONG_METADATA_DECISION_SCHEMA_VERSION,
        "policy_id": STRONG_METADATA_POLICY_ID,
        "production_auto_match_activated": False,
        "frozen_regressions": {
            **source_decisions["frozen_regressions"],
            "stage5b1c_b": {
                "exact_decision_replay": True,
                "auto_match_count": source_decisions["summary"][
                    "source_neutral_auto_match_count"
                ],
                "match_uncertain_count": source_decisions["summary"][
                    "source_neutral_match_uncertain_count"
                ],
            },
            "combined_before_stage5b1c_c": {
                "auto_match_count": 40,
                "match_uncertain_count": 10,
                "coverage": 0.8,
            },
        },
        "input_sha256": {
            "stage5b1c_b": source_hashes,
            "tier2_human_audit": audit["sha256"],
            "stage5b1c_c_diagnostic": FROZEN_DIAGNOSTIC_SHA256,
        },
        "duration_bound_basis": bound_basis,
        "summary": {
            "strong_metadata_attempted_tracks": len(track_decisions),
            "strong_metadata_auto_match_count": len(selected),
            "strong_metadata_match_uncertain_count": len(remaining),
            "combined_auto_match_count": combined,
            "combined_match_uncertain_count": 50 - combined,
            "combined_coverage": combined / 50,
            "percentage_point_gain_over_frozen_80_percent": len(selected) / 50 * 100,
            "selected_sol_label_counts": dict(
                sorted(Counter(row["sol_label"] or "MISSING" for row in selected).items())
            ),
            "selected_human_label_counts": dict(
                sorted(Counter(row["human_label"] or "MISSING" for row in selected).items())
            ),
        },
        "selected": selected,
        "remaining_unresolved_track_ids": remaining,
        "tracks": track_decisions,
        "scope_guards": {
            "balanced_v1_changed": False,
            "stage5b1c_a_changed": False,
            "stage5b1c_b_changed": False,
            "global_duration_gate_seconds": NORMAL_DURATION_CLOSE_SECONDS,
            "global_duration_gate_changed": False,
            "fuzzy_title_matching": False,
            "explicit_version_conflicts_are_hard_rejections": True,
            "explicit_performer_conflicts_are_hard_rejections": True,
            "yt_dlp_searches": 0,
            "sol_runs": 0,
            "audio_downloads": 0,
            "video_downloads": 0,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
    }
    return features, decisions


def build_strong_metadata_review_queue(
    config_path: Path, decisions: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = load_challenge_config(config_path)
    manifest = load_challenge_manifest(
        config.manifest_path, expected_sha256=config.manifest_sha256
    )
    cases = [
        {
            "stable_track_id": row["stable_track_id"],
            "candidate_video_ids": [row["selected_video_id"]],
            "selection_reasons": row["selection_rule_ids"],
        }
        for row in decisions["selected"]
    ]
    queue = {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "audit_contract_version": STRONG_METADATA_REVIEW_CONTRACT_VERSION,
        "status": STRONG_METADATA_REVIEW_STATUS,
        "manifest_sha256": manifest.sha256,
        "discovery_sha256": file_sha256(config.artifacts["discovery"]),
        "policy_id": STRONG_METADATA_POLICY_ID,
        "track_count": len(cases),
        "candidate_count": len(cases),
        "cases": cases,
    }
    return queue, tier2_review_rows(config, manifest, queue)


def _write_review_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            existing = list(csv.DictReader(handle))
        reviewer_fields = {"candidate_review_label", "candidate_note", "track_note"}
        for old, new in zip(existing, rows):
            for name in REVIEW_COLUMNS:
                if name not in reviewer_fields and old[name] != str(new[name]):
                    raise Stage5B1AValidationError(
                        "refusing to overwrite changed strong-metadata review evidence"
                    )
        if len(existing) != len(rows):
            raise Stage5B1AValidationError("strong-metadata review row count changed")
        return
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_strong_metadata_artifacts(
    config_path: Path,
    *,
    tier2a_dir: Path,
    source_neutral_dir: Path,
    diagnostic_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    features, decisions = evaluate_strong_metadata_challenge(
        config_path,
        tier2a_dir=tier2a_dir,
        source_neutral_dir=source_neutral_dir,
        diagnostic_path=diagnostic_path,
    )
    features_path = output_dir / "strong_metadata_candidate_features.json"
    decisions_path = output_dir / "strong_metadata_decisions.json"
    queue_path = output_dir / "strong_metadata_human_audit_queue.json"
    review_path = output_dir / "strong_metadata_human_review.csv"
    atomic_json(features_path, features)
    decisions["strong_metadata_features_sha256"] = file_sha256(features_path)
    atomic_json(decisions_path, decisions)
    queue, rows = build_strong_metadata_review_queue(config_path, decisions)
    queue["strong_metadata_decisions_sha256"] = file_sha256(decisions_path)
    atomic_json(queue_path, queue)
    _write_review_csv(review_path, rows)
    return {
        "features": features_path,
        "decisions": decisions_path,
        "queue": queue_path,
        "review": review_path,
        "summary": decisions["summary"],
    }
