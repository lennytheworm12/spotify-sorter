"""Stage 5B.1C-A deterministic Tier-2 metadata resolver.

Tier 2 is attempted only after the frozen POLICY_BALANCED_V1 returns
MATCH_UNCERTAIN.  It improves interpretation of title, performer, version, and
raw-backed release provenance while retaining the frozen source and duration
limits.
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_challenge import load_challenge_config, load_challenge_manifest, load_frozen_policies
from .stage5b1b_identity import ABSENT, CONFLICT, MATCH
from .stage5b1b_resolver import AUTO_MATCH, MATCH_UNCERTAIN, resolve_dataset
from .stage5b1c_normalization import (
    TIER2_NORMALIZATION_VERSION,
    compare_tier2_versions,
    normalize_performer,
    parse_tier2_title,
    parse_tier2_versions,
    performer_credit_aliases,
    performer_equivalent,
    split_title_performer,
    title_performer_prefix,
)


TIER2_POLICY_ID = "POLICY_TIER2_METADATA_FUSION_V1"
TIER2_FEATURE_SCHEMA_VERSION = "stage5b1c-tier2-candidate-features-v1"
TIER2_DATASET_SCHEMA_VERSION = "stage5b1c-tier2-feature-dataset-v1"
TIER2_DECISION_SCHEMA_VERSION = "stage5b1c-tier2-decisions-v1"
FROZEN_BALANCED_AUTO_MATCH_COUNT = 29
FROZEN_BALANCED_UNCERTAIN_COUNT = 21
FROZEN_INPUT_HASHES = {
    "challenge_candidate_features.json": "451e72e27c0b52c3b6109f57ea0f5c7a3421271f3283b1f1232082160c37a08c",
    "challenge_policy_decisions.json": "58181c40bd54a8d4fabbc8d627ddaee6ccf7b5812a17331fe9c8d6600357fe87",
    "challenge_tracks.json": "e2e9a1ab43f568dd9de853c2964f341ee0d0e2631ca87f732d0d4326ab990f79",
    "challenge_ytdlp_discovery.json": "95bb1ca905a05fcc4167da10e3dfd6cf267600a4dfb1898b491d28ba855e6fb4",
    "frozen_policy_definitions.json": "bbc527aa9a734b0aebbfafcb2775b479541a5e0248503627c14b8f429f708d5a",
    "human_review.csv": "0342c46d4506994c61cf0b3e422f34f6d466bf6297a6b8973fd75f711884b842",
    "sol_evaluations.json": "b00ecb7c9ffb668b581e571065235676d62832c868fe6bed26812fbbd30f50ea",
    "blinded_sol_private_mapping.json": "6f7991fba8f4c190f20b0214f03488c3e6bc523b9507704c278a4858d3e622bc",
}

_PROVIDED_ARTIST = re.compile(r"(?:^|\s)·\s*([^\n·]+)", re.I)
_STRUCTURED_ARTIST = re.compile(
    r"(?:^|[\n•])\s*(?:artist|performer|vocalist)\s*:\s*([^\n•]+)", re.I
)
_COVER = re.compile(r"\bcover(?:ed)?(?:\s+by)?\b", re.I)
_SOURCE_ORDER = {
    "ART_TRACK_TOPIC": 0,
    "OFFICIAL_AUDIO": 1,
    "LYRIC_VIDEO": 2,
    "OFFICIAL_MUSIC_VIDEO": 3,
    "OTHER": 4,
}


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _contains_performer(text: str, expected: str) -> bool:
    haystack = f" {normalize_performer(text)} "
    needle = normalize_performer(expected)
    return bool(needle and f" {needle} " in haystack)


def _provenance_performer_evidence(
    track: SpotifyTrack, candidate: dict[str, Any], tier1: dict[str, Any]
) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for field in ("uploader", "channel"):
        raw = str(candidate.get(field) or "").strip()
        for artist in track.artists:
            if performer_equivalent(raw, artist):
                evidence.append({"source": field, "raw": raw, "performer": artist})
                break
    provenance = tier1["source"]["provenance"]
    if not (
        provenance["topic_channel_signal"]
        or provenance["provided_to_youtube_by_signal"]
        or provenance["structured_release_metadata_signal"]
    ):
        return evidence
    description = str(candidate.get("description") or "")
    structured = [match.group(1).strip() for match in _PROVIDED_ARTIST.finditer(description)]
    structured.extend(match.group(1).strip() for match in _STRUCTURED_ARTIST.finditer(description))
    for raw in structured:
        for artist in track.artists:
            if _contains_performer(raw, artist):
                evidence.append({"source": "description_release_metadata", "raw": raw, "performer": artist})
                break
    return evidence


def _performer_evidence(
    track: SpotifyTrack,
    candidate: dict[str, Any],
    tier1: dict[str, Any],
    target_core_title: str,
) -> dict[str, Any]:
    title = str(candidate.get("title") or "")
    parsed = parse_tier2_title(title, expected_artists=track.artists, candidate=True)
    matches: list[dict[str, str]] = []
    if parsed.title_performer_text:
        for artist in track.artists:
            if normalize_performer(artist) in performer_credit_aliases(parsed.title_performer_text):
                matches.append({
                    "source": "candidate_title_prefix",
                    "raw": parsed.title_performer_text,
                    "performer": artist,
                })
                break
    elif any(_contains_performer(title, artist) for artist in track.artists):
        artist = next(artist for artist in track.artists if _contains_performer(title, artist))
        matches.append({"source": "candidate_title", "raw": title, "performer": artist})
    matches.extend(_provenance_performer_evidence(track, candidate, tier1))

    prefix = title_performer_prefix(title)
    separated = split_title_performer(title)
    suffix_matches = False
    if separated:
        suffix = parse_tier2_title(separated[1], candidate=False)
        suffix_matches = suffix.normalized_core_title == target_core_title
    conflicting_prefix = bool(
        prefix
        and suffix_matches
        and not any(_contains_performer(prefix, artist) for artist in track.artists)
    )
    cover_signal = bool(_COVER.search(title))
    explicit_conflict = conflicting_prefix or cover_signal
    primary = track.artists[0]
    primary_match = any(item["performer"] == primary for item in matches)
    return {
        "primary_performer_match": primary_match,
        "credited_performer_matches": sorted({item["performer"] for item in matches}),
        "normalized_target_performers": [normalize_performer(value) for value in track.artists],
        "evidence": matches,
        "explicit_title_performer_conflict": conflicting_prefix,
        "explicit_cover_signal": cover_signal,
        "explicit_performer_conflict": explicit_conflict,
    }


def _release_versions(candidate: dict[str, Any], tier1: dict[str, Any]) -> tuple[Any, ...]:
    provenance = tier1["source"]["provenance"]
    if not (
        provenance["topic_channel_signal"]
        or provenance["provided_to_youtube_by_signal"]
        or provenance["structured_release_metadata_signal"]
    ):
        return ()
    return parse_tier2_versions(str(candidate.get("description") or ""))


def extract_tier2_candidate_evidence(
    track: SpotifyTrack, candidate: dict[str, Any], tier1: dict[str, Any]
) -> dict[str, Any]:
    target_title = parse_tier2_title(track.title, candidate=False)
    candidate_title = parse_tier2_title(
        str(candidate.get("title") or ""), expected_artists=track.artists, candidate=True
    )
    title_match = bool(
        target_title.normalized_core_title
        and target_title.normalized_core_title == candidate_title.normalized_core_title
    )
    performer = _performer_evidence(
        track, candidate, tier1, target_title.normalized_core_title
    )
    version_rows = compare_tier2_versions(
        target_title.versions,
        candidate_title.versions,
        _release_versions(candidate, tier1),
    )
    counts = {
        state: sum(row["relationship"] == state for row in version_rows)
        for state in (MATCH, ABSENT, CONFLICT)
    }
    reasons: list[str] = []
    if not title_match:
        reasons.append("normalized structural core title does not match")
    if performer["explicit_performer_conflict"]:
        reasons.append("explicit cover/different-performer evidence")
    if not performer["primary_performer_match"]:
        reasons.append("primary performer lacks deterministic title/provenance evidence")
    if counts[CONFLICT]:
        reasons.append("explicit target-relative version conflict")
    if counts[ABSENT]:
        reasons.append("important target version evidence remains absent")
    target_seconds = track.duration_ms / 1000.0 if track.duration_ms is not None else None
    candidate_seconds = candidate.get("duration_seconds")
    delta = (
        abs(float(candidate_seconds) - target_seconds)
        if candidate_seconds is not None and target_seconds is not None
        else None
    )
    return {
        "schema_version": TIER2_FEATURE_SCHEMA_VERSION,
        "normalization_version": TIER2_NORMALIZATION_VERSION,
        "track_id": track.stable_track_id,
        "candidate_video_id": candidate.get("youtube_video_id"),
        "identity_eligible": not reasons,
        "identity_reasons": reasons,
        "title": {
            "target": target_title.to_dict(),
            "candidate": candidate_title.to_dict(),
            "structural_core_title_match": title_match,
        },
        "performers": performer,
        "versions": {
            "relationships": version_rows,
            "match_count": counts[MATCH],
            "absent_count": counts[ABSENT],
            "conflict_count": counts[CONFLICT],
        },
        "duration": {
            "target_seconds": target_seconds,
            "candidate_seconds": float(candidate_seconds) if candidate_seconds is not None else None,
            "absolute_duration_delta_seconds": delta,
        },
        "source": {
            "source_type": tier1["source"]["source_type"],
            "source_descriptors": list(candidate_title.source_descriptors),
            "provenance": tier1["source"]["provenance"],
        },
        "weak_evidence": {
            "candidate_view_count": candidate.get("view_count"),
            "max_view_count_among_identity_eligible": None,
            "relative_view_strength": None,
            "search_rank": candidate.get("rank"),
        },
        "tier1_before": {
            "recording_eligible": tier1["recording_eligible"],
            "ineligible_auto_match_reasons": list(tier1["ineligible_auto_match_reasons"]),
            "title_exact_normalized_match": tier1["identity"]["title_exact_normalized_match"],
            "primary_artist_match": tier1["identity"]["primary_artist_match"],
            "version_relationships": list(tier1["versions"]["relationships"]),
        },
    }


def extract_tier2_track_features(track_row: dict[str, Any]) -> dict[str, Any]:
    track = SpotifyTrack.from_dict(track_row["track"])
    wrapped = [
        {
            "candidate": item["candidate"],
            "features": extract_tier2_candidate_evidence(track, item["candidate"], item["features"]),
        }
        for item in track_row["candidates"]
    ]
    eligible_views = [
        int(item["candidate"]["view_count"])
        for item in wrapped
        if item["features"]["identity_eligible"] and item["candidate"].get("view_count") is not None
    ]
    maximum = max(eligible_views) if eligible_views else None
    for item in wrapped:
        views = item["candidate"].get("view_count")
        weak = item["features"]["weak_evidence"]
        weak["max_view_count_among_identity_eligible"] = maximum
        weak["relative_view_strength"] = (
            float(views) / maximum if views is not None and maximum and maximum > 0 else None
        )
    return {
        "track": track.to_dict(),
        "query": track_row.get("query"),
        "candidates": wrapped,
    }


def _provenance_rank(feature: dict[str, Any]) -> int:
    provenance = feature["source"]["provenance"]
    if provenance["topic_channel_signal"] and provenance["provided_to_youtube_by_signal"]:
        return 0
    if (
        provenance["topic_channel_signal"]
        or provenance["provided_to_youtube_by_signal"]
        or provenance["auto_generated_by_youtube_signal"]
    ):
        return 1
    if provenance["structured_release_metadata_signal"]:
        return 2
    if feature["performers"]["evidence"]:
        return 3
    return 4


def _tier2_gate(feature: dict[str, Any]) -> list[str]:
    reasons = list(feature["identity_reasons"])
    delta = feature["duration"]["absolute_duration_delta_seconds"]
    source = feature["source"]["source_type"]
    if delta is None or not math.isfinite(delta):
        reasons.append("duration evidence is unavailable")
    elif delta > 7:
        reasons.append("duration exceeds frozen Balanced DURATION_CLOSE boundary")
    if source == "OFFICIAL_MUSIC_VIDEO" and (delta is None or delta > 2):
        reasons.append("music-video duration exceeds frozen Balanced DURATION_VERY_CLOSE boundary")
    if source == "OTHER":
        reasons.append("Tier 2A does not allow OTHER-source fallback")
    if source == "LYRIC_VIDEO":
        relative = feature["weak_evidence"]["relative_view_strength"]
        if relative is None or relative < 0.001:
            reasons.append("lyric fallback lacks frozen Balanced relative-view support")
    return list(dict.fromkeys(reasons))


def _ordering_key(item: dict[str, Any]) -> tuple[Any, ...]:
    feature = item["features"]
    delta = feature["duration"]["absolute_duration_delta_seconds"]
    relative = feature["weak_evidence"]["relative_view_strength"]
    return (
        0 if delta is not None and delta <= 2 else 1,
        _provenance_rank(feature),
        _SOURCE_ORDER[feature["source"]["source_type"]],
        float(delta) if delta is not None else math.inf,
        -(relative if relative is not None else -1.0),
        int(feature["weak_evidence"]["search_rank"]),
    )


def resolve_tier2_track(track_row: dict[str, Any]) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for item in track_row["candidates"]:
        reasons = _tier2_gate(item["features"])
        evidence = {
            "video_id": item["candidate"]["youtube_video_id"],
            "candidate_rank": item["candidate"]["rank"],
            "title": item["candidate"].get("title"),
            "reasons": reasons,
            "features": item["features"],
        }
        (excluded if reasons else accepted).append(evidence)
    accepted.sort(key=_ordering_key)
    public_excluded = [
        {
            "video_id": item["video_id"],
            "candidate_rank": item["candidate_rank"],
            "title": item["title"],
            "reasons": item["reasons"],
        }
        for item in excluded
    ]
    if not accepted:
        return {
            "status": MATCH_UNCERTAIN,
            "policy_rule_id": TIER2_POLICY_ID,
            "selected_video_id": None,
            "selected_candidate_rank": None,
            "ranked_plausible_candidates": [],
            "uncertainty_reason": "no candidate satisfies Tier-2 normalization/evidence-fusion safety gates",
            "excluded_candidates": public_excluded,
        }
    selected = accepted[0]
    before = selected["features"]["tier1_before"]
    recovered = []
    if not before["title_exact_normalized_match"]:
        recovered.append("STRUCTURAL_TITLE_NORMALIZATION")
    if not before["primary_artist_match"]:
        recovered.append("PERFORMER_ALIAS_OR_PROVENANCE_FUSION")
    if any(row["relationship"] != MATCH for row in before["version_relationships"]):
        recovered.append("VERSION_NORMALIZATION_OR_PROVENANCE_FUSION")
    return {
        "status": AUTO_MATCH,
        "policy_rule_id": TIER2_POLICY_ID,
        "selected_video_id": selected["video_id"],
        "selected_candidate_rank": selected["candidate_rank"],
        "selection_reason": (
            "structural title, performer, and version evidence pass after deterministic "
            "normalization/fusion; frozen Balanced source and duration gates also pass"
        ),
        "recovery_evidence": recovered,
        "evidence_summary": {
            "title": selected["features"]["title"],
            "performers": selected["features"]["performers"],
            "versions": selected["features"]["versions"],
            "duration": selected["features"]["duration"],
            "source": selected["features"]["source"],
            "weak_evidence": selected["features"]["weak_evidence"],
            "tier1_before": selected["features"]["tier1_before"],
        },
        "ranked_plausible_candidates": [item["video_id"] for item in accepted],
        "excluded_candidates": public_excluded,
    }


def _mapped_sol(report_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    evaluations = _json_object(report_dir / "sol_evaluations.json")
    mapping = _json_object(report_dir / "blinded_sol_private_mapping.json")
    maps = {
        row["stable_track_id"]: {
            item["candidate_key"]: item["youtube_video_id"] for item in row["candidates"]
        }
        for row in mapping["tracks"]
    }
    output = {}
    for row in evaluations["tracks"]:
        stable_id = row["stable_track_id"]
        for candidate in row["candidates"]:
            video_id = maps[stable_id][candidate["candidate_key"]]
            output[(stable_id, video_id)] = candidate
    return output


def _human_labels(report_dir: Path) -> dict[tuple[str, str], dict[str, str]]:
    output = {}
    with (report_dir / "human_review.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            label = row["candidate_review_label"].strip()
            if label:
                output[(row["stable_track_id"], row["candidate_video_id"])] = {
                    "label": label,
                    "note": row["candidate_note"],
                }
    return output


def verify_frozen_inputs(report_dir: Path) -> dict[str, str]:
    actual = {name: file_sha256(report_dir / name) for name in FROZEN_INPUT_HASHES}
    changed = {name: value for name, value in actual.items() if value != FROZEN_INPUT_HASHES[name]}
    if changed:
        raise Stage5B1AValidationError(f"frozen Stage 5B.1B input changed: {sorted(changed)}")
    return actual


def replay_balanced(config_path: Path, feature_dataset: dict[str, Any]) -> dict[str, Any]:
    config = load_challenge_config(config_path)
    load_challenge_manifest(config.manifest_path, expected_sha256=config.manifest_sha256)
    boundaries, policies = load_frozen_policies(config)
    replayed = resolve_dataset(feature_dataset, policies["POLICY_BALANCED_V1"], boundaries)
    saved = _json_object(config.artifacts["policy_decisions"])["policies"]["POLICY_BALANCED_V1"]
    if replayed != saved:
        raise Stage5B1AValidationError("frozen Balanced V1 replay changed candidate decisions")
    if replayed["summary"] != {
        "track_count": 50,
        "auto_match_count": FROZEN_BALANCED_AUTO_MATCH_COUNT,
        "match_uncertain_count": FROZEN_BALANCED_UNCERTAIN_COUNT,
    }:
        raise Stage5B1AValidationError("frozen Balanced V1 summary changed")
    return replayed


def evaluate_frozen_challenge(config_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = load_challenge_config(config_path)
    report_dir = config.artifacts["features"].parent
    input_hashes = verify_frozen_inputs(report_dir)
    frozen_features = _json_object(config.artifacts["features"])
    balanced = replay_balanced(config_path, frozen_features)
    balanced_by_id = {row["stable_track_id"]: row["decision"] for row in balanced["tracks"]}
    attempted_rows = [
        row for row in frozen_features["tracks"]
        if balanced_by_id[row["track"]["stable_track_id"]]["status"] == MATCH_UNCERTAIN
    ]
    tier2_tracks = [extract_tier2_track_features(row) for row in attempted_rows]
    tier2_features = {
        "schema_version": TIER2_DATASET_SCHEMA_VERSION,
        "normalization_version": TIER2_NORMALIZATION_VERSION,
        "dataset_role": "FROZEN_FRESH_CHALLENGE_TIER1_UNRESOLVED_ONLY",
        "source_feature_sha256": input_hashes["challenge_candidate_features.json"],
        "track_count": len(tier2_tracks),
        "candidate_pair_count": sum(len(row["candidates"]) for row in tier2_tracks),
        "tracks": tier2_tracks,
    }
    decisions = [
        {"stable_track_id": row["track"]["stable_track_id"], "decision": resolve_tier2_track(row)}
        for row in tier2_tracks
    ]
    sol = _mapped_sol(report_dir)
    human = _human_labels(report_dir)
    selected = []
    for row in decisions:
        decision = row["decision"]
        if decision["status"] != AUTO_MATCH:
            continue
        identity = (row["stable_track_id"], decision["selected_video_id"])
        selected.append({
            "stable_track_id": row["stable_track_id"],
            "selected_video_id": decision["selected_video_id"],
            "selected_candidate_rank": decision["selected_candidate_rank"],
            "recovery_evidence": decision["recovery_evidence"],
            "sol_label": sol.get(identity, {}).get("label"),
            "sol_reason": sol.get(identity, {}).get("recording_identity_reason"),
            "human_label": human.get(identity, {}).get("label"),
            "human_note": human.get(identity, {}).get("note"),
        })
    sol_counts = Counter(row["sol_label"] or "MISSING" for row in selected)
    recovered_count = len(selected)
    tier2_decisions = {
        "schema_version": TIER2_DECISION_SCHEMA_VERSION,
        "policy_id": TIER2_POLICY_ID,
        "production_auto_match_activated": False,
        "frozen_balanced_regression": {
            "exact_decision_replay": True,
            **balanced["summary"],
        },
        "input_sha256": input_hashes,
        "summary": {
            "tier2_attempted_tracks": len(decisions),
            "tier2_auto_match_count": recovered_count,
            "tier2_match_uncertain_count": len(decisions) - recovered_count,
            "tier1_plus_tier2_auto_match_count": FROZEN_BALANCED_AUTO_MATCH_COUNT + recovered_count,
            "tier1_plus_tier2_coverage": (FROZEN_BALANCED_AUTO_MATCH_COUNT + recovered_count) / 50,
            "tier2_selected_sol_label_counts": dict(sorted(sol_counts.items())),
            "tier2_human_validated_selection_count": sum(row["human_label"] is not None for row in selected),
        },
        "selected": selected,
        "tracks": decisions,
        "scope_guards": {
            "other_source_fallback": False,
            "duration_close_seconds": 7,
            "official_music_video_very_close_seconds": 2,
            "audio_downloads": 0,
            "video_downloads": 0,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
    }
    return tier2_features, tier2_decisions


def write_frozen_evaluation(
    config_path: Path, *, output_dir: Path
) -> tuple[Path, Path, dict[str, Any]]:
    features, decisions = evaluate_frozen_challenge(config_path)
    feature_path = output_dir / "tier2_candidate_features.json"
    decision_path = output_dir / "tier2_decisions.json"
    atomic_json(feature_path, features)
    decisions["tier2_features_sha256"] = file_sha256(feature_path)
    atomic_json(decision_path, decisions)
    return feature_path, decision_path, decisions
