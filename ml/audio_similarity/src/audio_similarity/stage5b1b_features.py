"""Inspectable hierarchical candidate evidence for Stage 5B.1B."""
from __future__ import annotations

import math
import re
from enum import Enum
from typing import Any

from .stage5b1a_models import SpotifyTrack
from .stage5b1b_identity import (
    ABSENT,
    CONFLICT,
    MATCH,
    compare_versions,
    normalize_text,
    parse_candidate_identity,
    parse_target,
    text_similarity,
)


FEATURE_SCHEMA_VERSION = "stage5b1b-candidate-features-v1"


class SourceType(str, Enum):
    ART_TRACK_TOPIC = "ART_TRACK_TOPIC"
    OFFICIAL_AUDIO = "OFFICIAL_AUDIO"
    LYRIC_VIDEO = "LYRIC_VIDEO"
    OFFICIAL_MUSIC_VIDEO = "OFFICIAL_MUSIC_VIDEO"
    OTHER = "OTHER"


SOURCE_PREFERENCE = {
    SourceType.ART_TRACK_TOPIC: 5,
    SourceType.OFFICIAL_AUDIO: 4,
    SourceType.LYRIC_VIDEO: 3,
    SourceType.OFFICIAL_MUSIC_VIDEO: 2,
    SourceType.OTHER: 1,
}


def classify_source(candidate: dict[str, Any]) -> SourceType:
    title = str(candidate.get("title") or "")
    uploader = str(candidate.get("uploader") or "")
    channel = str(candidate.get("channel") or "")
    description = str(candidate.get("description") or "")
    combined = " ".join((title, description)).casefold()
    title_only = title.casefold()
    if (
        uploader.casefold().endswith(" - topic")
        or channel.casefold().endswith(" - topic")
        or "provided to youtube by" in combined
    ):
        return SourceType.ART_TRACK_TOPIC
    if re.search(r"\bofficial\s+audio\b", title_only):
        return SourceType.OFFICIAL_AUDIO
    if re.search(r"\b(?:lyrics?|lyric video)\b", title_only):
        return SourceType.LYRIC_VIDEO
    if re.search(r"\b(?:official\s+(?:music\s+)?video|music video|m/?v)\b", title_only):
        return SourceType.OFFICIAL_MUSIC_VIDEO
    return SourceType.OTHER


def _contains_normalized(haystack: str, needle: str) -> bool:
    normalized_haystack = f" {normalize_text(haystack)} "
    normalized_needle = normalize_text(needle)
    return bool(normalized_needle) and f" {normalized_needle} " in normalized_haystack


def _performer_evidence(track: SpotifyTrack, candidate: dict[str, Any]) -> dict[str, Any]:
    title = str(candidate.get("title") or "")
    description = str(candidate.get("description") or "")
    evidence_text = f"{title} {description}"
    matches = [artist for artist in track.artists if _contains_normalized(evidence_text, artist)]
    cover_match = re.search(r"\bcover(?:ed)?\s+by\s+([^|()\[\]-]+)", title, re.I)
    cover_signal = bool(re.search(r"\bcover\b", evidence_text, re.I))
    primary_candidate = parse_candidate_identity(candidate).primary_artist
    title_performer_conflict = bool(primary_candidate and not matches and " - " in title)
    explicit_conflict = bool(
        (cover_signal and (cover_match or not matches)) or title_performer_conflict
    )
    return {
        "primary_artist_match": bool(matches and matches[0] == track.artists[0]),
        "artist_similarity": max(
            (text_similarity(artist, primary_candidate or title) for artist in track.artists),
            default=0.0,
        ),
        "credited_artist_overlap": len(matches) / len(track.artists),
        "featured_artist_overlap": (
            len(matches[1:]) / len(track.artists[1:]) if len(track.artists) > 1 else None
        ),
        "matched_artists": matches,
        "candidate_performer_text": primary_candidate,
        "explicit_cover_signal": cover_signal,
        "explicit_title_performer_conflict": title_performer_conflict,
        "explicit_performer_conflict": explicit_conflict,
        "uploader": candidate.get("uploader"),
        "channel": candidate.get("channel"),
        "uploader_used_as_performer_evidence": False,
    }


def extract_candidate_features(track: SpotifyTrack, candidate: dict[str, Any]) -> dict[str, Any]:
    target = parse_target(track)
    observed = parse_candidate_identity(candidate)
    version_rows = compare_versions(target.versions, observed.versions)
    counts = {
        relationship: sum(row["relationship"] == relationship for row in version_rows)
        for relationship in (MATCH, ABSENT, CONFLICT)
    }
    artist = _performer_evidence(track, candidate)
    target_title_tokens = set(target.normalized_title.split())
    candidate_title_tokens = set(observed.normalized_title.split())
    title_token_overlap = (
        len(target_title_tokens & candidate_title_tokens)
        / len(target_title_tokens | candidate_title_tokens)
        if target_title_tokens and candidate_title_tokens else None
    )
    explicit_title_conflict = title_token_overlap == 0.0
    target_duration = target.duration_seconds
    candidate_duration = observed.duration_seconds
    absolute_delta = (
        abs(candidate_duration - target_duration)
        if candidate_duration is not None and target_duration is not None
        else None
    )
    relative_delta = (
        absolute_delta / target_duration
        if absolute_delta is not None and target_duration and target_duration > 0
        else None
    )
    source_type = classify_source(candidate)
    reasons = []
    if counts[CONFLICT]:
        conflicts = [
            f"{row['family']}: target={row['target_qualifier'] or row['target_raw'] or 'none'}, "
            f"candidate={row['candidate_qualifier'] or row['candidate_raw'] or 'none'}"
            for row in version_rows
            if row["relationship"] == CONFLICT
        ]
        reasons.append("explicit version conflict: " + "; ".join(conflicts))
    if artist["explicit_performer_conflict"]:
        reasons.append("explicit cover/different-performer evidence")
    if explicit_title_conflict:
        reasons.append("explicit core-title contradiction: no normalized title-token overlap")
    eligible = not reasons
    return {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "track_id": track.stable_track_id,
        "candidate_video_id": candidate.get("youtube_video_id"),
        "recording_eligible": eligible,
        "ineligible_auto_match_reasons": reasons,
        "identity": {
            "target": target.to_dict(),
            "candidate": observed.to_dict(),
            "title_exact_normalized_match": target.normalized_title == observed.normalized_title,
            "title_similarity": text_similarity(target.core_title, observed.core_title),
            "core_title_token_overlap": title_token_overlap,
            "explicit_core_title_conflict": explicit_title_conflict,
            **artist,
        },
        "versions": {
            "relationships": version_rows,
            "version_match_count": counts[MATCH],
            "version_absent_count": counts[ABSENT],
            "version_conflict_count": counts[CONFLICT],
            "has_explicit_version_conflict": bool(counts[CONFLICT]),
        },
        "duration": {
            "target_seconds": target_duration,
            "candidate_seconds": candidate_duration,
            "absolute_duration_delta_seconds": absolute_delta,
            "relative_duration_delta": relative_delta,
        },
        "source": {
            "source_type": source_type.value,
            "source_preference_tier": SOURCE_PREFERENCE[source_type],
            "uploader": candidate.get("uploader"),
            "channel": candidate.get("channel"),
        },
        "description_evidence": {
            "album_evidence_match": (
                _contains_normalized(str(candidate.get("description") or ""), track.album)
                if track.album else None
            ),
            "release_year_evidence_match": (
                str(track.release_year) in str(candidate.get("description") or "")
                if track.release_year else None
            ),
        },
        "weak_evidence": {
            "candidate_view_count": candidate.get("view_count"),
            "max_view_count_among_plausible_candidates": None,
            "relative_view_strength": None,
            "log_relative_view_strength": None,
            "view_rank_among_plausible_candidates": None,
            "search_rank": candidate.get("rank"),
        },
        "hierarchy": [
            "core_target_identity",
            "explicit_version_compatibility",
            "title_and_performer_agreement",
            "duration_compatibility",
            "source_provenance_and_quality",
            "description_album_release_evidence",
            "weak_relative_views_and_search_rank",
            "future_empirical_acceptance_policy",
        ],
    }


def extract_track_features(track: SpotifyTrack, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = [extract_candidate_features(track, candidate) for candidate in candidates]
    plausible_views = [
        value["weak_evidence"]["candidate_view_count"]
        for value in features
        if value["recording_eligible"]
        and value["weak_evidence"]["candidate_view_count"] is not None
    ]
    maximum = max(plausible_views) if plausible_views else None
    ranked = sorted(set(plausible_views), reverse=True)
    for value in features:
        weak = value["weak_evidence"]
        views = weak["candidate_view_count"]
        if value["recording_eligible"] and views is not None and maximum is not None:
            weak["max_view_count_among_plausible_candidates"] = maximum
            weak["relative_view_strength"] = views / maximum if maximum else None
            weak["log_relative_view_strength"] = (
                math.log1p(views) / math.log1p(maximum) if maximum else None
            )
            weak["view_rank_among_plausible_candidates"] = ranked.index(views) + 1
    return features
