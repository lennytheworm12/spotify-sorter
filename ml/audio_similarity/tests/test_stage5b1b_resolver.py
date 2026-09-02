from __future__ import annotations

import pytest

from audio_similarity.stage5b1b_resolver import (
    AUTO_MATCH,
    MATCH_UNCERTAIN,
    DurationBoundaries,
    derive_duration_boundaries,
    duration_band,
    human_label_state,
    policy_variants,
    resolve_track,
)


def feature(*, source="ART_TRACK_TOPIC", delta=1.0, conflict=False, exact=True, artist=True, absent=0, relative=1.0, canonical=True):
    return {
        "recording_eligible": not conflict,
        "ineligible_auto_match_reasons": ["explicit version conflict"] if conflict else [],
        "identity": {
            "title_exact_normalized_match": exact,
            "title_similarity": 1.0 if exact else 0.8,
            "primary_artist_match": artist,
        },
        "versions": {
            "version_match_count": 1,
            "version_absent_count": absent,
            "version_conflict_count": int(conflict),
        },
        "duration": {
            "absolute_duration_delta_seconds": delta,
            "relative_duration_delta": delta / 200,
        },
        "source": {
            "source_type": source,
            "uploader_or_channel_artist_match": artist,
            "provenance": {
                "topic_channel_signal": canonical,
                "provided_to_youtube_by_signal": canonical,
                "auto_generated_by_youtube_signal": False,
                "structured_release_metadata_signal": canonical,
                "raw_evidence": {},
            },
        },
        "description_evidence": {
            "description_album_match": None,
            "description_release_year_match": None,
        },
        "weak_evidence": {
            "relative_view_strength": relative,
            "view_rank_among_plausible_candidates": 1,
            "search_rank": 1,
        },
    }


def track_row(*features):
    return {
        "candidates": [
            {
                "candidate": {
                    "youtube_video_id": f"video{i:06d}",
                    "rank": i,
                    "title": f"candidate {i}",
                },
                "features": value,
            }
            for i, value in enumerate(features, start=1)
        ]
    }


def test_duration_boundaries_are_derived_from_safe_eligible_examples():
    boundaries, evidence = derive_duration_boundaries(
        [
            (feature(delta=1), "IDEAL"),
            (feature(delta=2), "ACCEPTABLE"),
            (feature(delta=7), "IDEAL"),
            (feature(delta=50), "ACCEPTABLE"),
            (feature(delta=999), "WRONG"),
            (feature(delta=3, conflict=True), "IDEAL"),
        ]
    )
    assert evidence["eligible_human_safe_example_count"] == 4
    assert boundaries.very_close_seconds == 5
    assert boundaries.close_seconds == 18
    assert boundaries.moderate_seconds == 38
    assert duration_band(4, boundaries) == "DURATION_VERY_CLOSE"
    assert duration_band(10, boundaries) == "DURATION_CLOSE"
    assert duration_band(30, boundaries) == "DURATION_MODERATE"
    assert duration_band(60, boundaries) == "DURATION_FAR"


@pytest.mark.parametrize(
    ("label", "state"),
    [("IDEAL", "SAFE"), ("ACCEPTABLE", "SAFE"), ("WRONG", "UNSAFE"), ("UNCERTAIN", "UNRESOLVED")],
)
def test_human_label_safety_mapping(label, state):
    assert human_label_state(label) == state


def test_version_conflict_cannot_be_rescued_by_canonical_source_views_or_rank():
    decision = resolve_track(
        track_row(feature(conflict=True, relative=1.0)),
        policy_variants()[-1],
        DurationBoundaries(2, 7, 48),
    )
    assert decision["status"] == MATCH_UNCERTAIN
    assert "version conflict" in " ".join(decision["excluded_candidates"][0]["reasons"])


def test_conservative_policy_prefers_canonical_source_after_identity_and_duration():
    decision = resolve_track(
        track_row(
            feature(source="OFFICIAL_AUDIO", delta=1, canonical=False),
            feature(source="ART_TRACK_TOPIC", delta=1, canonical=True),
        ),
        policy_variants()[0],
        DurationBoundaries(2, 7, 48),
    )
    assert decision["status"] == AUTO_MATCH
    assert decision["selected_video_id"] == "video000002"


def test_balanced_lyric_fallback_needs_relative_views_and_beats_music_video():
    balanced = policy_variants()[1]
    boundaries = DurationBoundaries(2, 7, 48)
    rejected = resolve_track(
        track_row(feature(source="LYRIC_VIDEO", relative=0.0001, canonical=False)),
        balanced,
        boundaries,
    )
    assert rejected["status"] == MATCH_UNCERTAIN
    selected = resolve_track(
        track_row(
            feature(source="OFFICIAL_MUSIC_VIDEO", delta=1, canonical=False),
            feature(source="LYRIC_VIDEO", delta=1, relative=0.1, canonical=False),
        ),
        balanced,
        boundaries,
    )
    assert selected["selected_video_id"] == "video000002"


def test_music_video_duration_and_other_source_gates_preserve_uncertainty():
    balanced = policy_variants()[1]
    boundaries = DurationBoundaries(2, 7, 48)
    assert resolve_track(
        track_row(feature(source="OFFICIAL_MUSIC_VIDEO", delta=6, canonical=False)),
        balanced,
        boundaries,
    )["status"] == MATCH_UNCERTAIN
    assert resolve_track(
        track_row(feature(source="OTHER", delta=1, canonical=False)),
        balanced,
        boundaries,
    )["status"] == MATCH_UNCERTAIN


def test_uploader_mismatch_does_not_create_recording_conflict():
    decision = resolve_track(
        track_row(feature(source="OFFICIAL_AUDIO", canonical=False, artist=True)),
        policy_variants()[0],
        DurationBoundaries(2, 7, 48),
    )
    assert decision["status"] == AUTO_MATCH


def test_policy_variants_are_interpretable_and_ordered_by_acceptance_scope():
    conservative, balanced, permissive = policy_variants()
    assert conservative.policy_id == "POLICY_CONSERVATIVE_V1"
    assert conservative.maximum_duration_band == "DURATION_VERY_CLOSE"
    assert balanced.allow_lyric_fallback is True
    assert permissive.allow_other_source is True
