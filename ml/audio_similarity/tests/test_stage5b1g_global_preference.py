from __future__ import annotations

from pathlib import Path

import pytest

from audio_similarity.stage5b1g_global_preference import (
    AUTO_MATCH,
    DURATION_CLOSE,
    DURATION_EXTENDED_1,
    DURATION_EXTENDED_2,
    DURATION_EXTENDED_3,
    DURATION_TOO_FAR,
    DURATION_VERY_CLOSE,
    POLICY_ID,
    build_global_candidate_evidence,
    duration_bucket,
    evaluate_stage5b1g,
    global_preference_key,
    load_stage5b1g_config,
    resolve_global_candidates,
    verify_frozen_inputs,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1g_global_preference.json"


def _snapshot(
    video_id: str = "candidate",
    *,
    rank: int = 1,
    delta: float = 1.0,
    source: str = "OTHER",
    frozen_stage: str | None = None,
    title_match: bool = True,
    performer_match: bool = True,
    performer_conflict: bool = False,
    versioned: bool = False,
    version_absent: bool = False,
    version_conflict: bool = False,
    modification_conflict: bool = False,
    channel_match: bool = False,
    topic: bool = False,
    provided: bool = False,
    auto_generated: bool = False,
    structured: bool = False,
    release_performer: bool = False,
    title: str = "Artist - Song",
    relative_views: float | None = 0.5,
) -> dict:
    relationships = []
    match_count = absent_count = conflict_count = 0
    if versioned:
        relationship = "CONFLICT" if version_conflict else "ABSENT" if version_absent else "MATCH"
        relationships = [{
            "family": "remix",
            "relationship": relationship,
            "target_raw": "Named Remix",
            "candidate_raw": None if version_absent else "Named Remix",
            "candidate_evidence_source": None if version_absent else "candidate_title",
        }]
        match_count = int(relationship == "MATCH")
        absent_count = int(relationship == "ABSENT")
        conflict_count = int(relationship == "CONFLICT")
    performer_rows = []
    if performer_match:
        performer_rows.append({"source": "candidate_title_prefix", "raw": "Artist", "performer": "Artist"})
    if channel_match:
        performer_rows.append({"source": "channel", "raw": "Artist", "performer": "Artist"})
    if release_performer:
        performer_rows.append({
            "source": "description_release_metadata", "raw": "Artist", "performer": "Artist"
        })
    stages = ("POLICY_BALANCED_V1", "STAGE5B1C_A", "STAGE5B1C_B", "STAGE5B1C_C")
    return {
        "video_id": video_id,
        "search_rank": rank,
        "title": title,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "uploader": "Artist" if channel_match else "Unknown",
        "channel": "Artist" if channel_match else "Unknown",
        "duration_seconds": 200 + delta,
        "view_count": 1000,
        "human_evidence": None,
        "sol_evidence": None,
        "identity": {
            "target": {"credited_artists": ["Artist"]},
            "title_exact_normalized_match": title_match,
            "title_similarity": 1.0 if title_match else 0.2,
            "explicit_core_title_conflict": not title_match,
        },
        "normalized_title": {"structural_core_title_match": title_match},
        "performer_evidence": {
            "primary_performer_match": performer_match,
            "explicit_performer_conflict": performer_conflict,
            "evidence": performer_rows,
        },
        "version_evidence": {
            "relationships": relationships,
            "match_count": match_count,
            "absent_count": absent_count,
            "conflict_count": conflict_count,
        },
        "modification_evidence": {
            "target_families": [],
            "candidate_families": ["cover"] if modification_conflict else [],
            "unrequested_candidate_families": ["cover"] if modification_conflict else [],
            "explicit_conflict": modification_conflict,
        },
        "duration": {
            "target_seconds": 200.0,
            "candidate_seconds": 200.0 + delta,
            "absolute_duration_delta_seconds": delta,
            "relative_duration_delta": delta / 200.0,
        },
        "source": {
            "source_type": source,
            "provenance": {
                "topic_channel_signal": topic,
                "provided_to_youtube_by_signal": provided,
                "auto_generated_by_youtube_signal": auto_generated,
                "structured_release_metadata_signal": structured,
                "raw_evidence": {},
            },
        },
        "description_evidence": {
            "description_album_match": False,
            "description_release_year_match": False,
        },
        "weak_evidence": {
            "relative_view_strength": relative_views,
            "view_rank_among_plausible_candidates": rank,
            "search_rank": rank,
        },
        "gates": {
            **{
                stage: {"eligible": stage == frozen_stage, "reasons": []}
                for stage in stages
            },
            "earliest_eligible_stage": frozen_stage,
        },
    }


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (0.0, DURATION_VERY_CLOSE),
        (2.0, DURATION_VERY_CLOSE),
        (2.0001, DURATION_CLOSE),
        (7.0, DURATION_CLOSE),
        (7.0001, DURATION_EXTENDED_1),
        (12.0, DURATION_EXTENDED_1),
        (12.0001, DURATION_EXTENDED_2),
        (16.0, DURATION_EXTENDED_2),
        (16.0001, DURATION_EXTENDED_3),
        (20.0, DURATION_EXTENDED_3),
        (20.0001, DURATION_TOO_FAR),
    ],
)
def test_duration_bucket_boundaries(delta: float, expected: str) -> None:
    assert duration_bucket(delta) == expected


def test_more_than_twenty_seconds_is_hard_rejection_even_if_frozen_admitted() -> None:
    feature = build_global_candidate_evidence(
        _snapshot(delta=20.01, frozen_stage="POLICY_BALANCED_V1", channel_match=True)
    )
    assert feature["duration"]["bucket"] == DURATION_TOO_FAR
    assert not feature["eligibility"]["eligible"]


def test_extended_duration_requires_increasing_corroboration() -> None:
    assert build_global_candidate_evidence(_snapshot(delta=10))["eligibility"]["eligible"]
    assert not build_global_candidate_evidence(_snapshot(delta=14))["eligibility"]["eligible"]
    assert build_global_candidate_evidence(
        _snapshot(delta=14, channel_match=True)
    )["eligibility"]["eligible"]
    assert not build_global_candidate_evidence(
        _snapshot(delta=18, provided=True, structured=True, release_performer=True)
    )["eligibility"]["eligible"]
    assert build_global_candidate_evidence(
        _snapshot(delta=18, channel_match=True)
    )["eligibility"]["eligible"]


@pytest.mark.parametrize(
    "changes",
    [
        {"performer_conflict": True},
        {"versioned": True, "version_conflict": True},
        {"modification_conflict": True},
    ],
)
def test_explicit_recording_conflict_cannot_be_rescued(changes: dict) -> None:
    feature = build_global_candidate_evidence(
        _snapshot(delta=1, frozen_stage="POLICY_BALANCED_V1", channel_match=True, **changes)
    )
    assert feature["hard_conflicts"]
    assert not feature["eligibility"]["eligible"]


def test_unrequested_featured_performer_is_a_hard_conflict() -> None:
    feature = build_global_candidate_evidence(
        _snapshot(title="Artist - Song (feat. Different Performer)", channel_match=True)
    )
    assert feature["unexpected_featured_performers"] == ["Different Performer"]
    assert not feature["eligibility"]["eligible"]


def test_requested_modified_version_is_not_intrinsically_rejected() -> None:
    snapshot = _snapshot(title="Artist - Song (Slowed + Reverb)")
    snapshot["modification_evidence"] = {
        "target_families": ["slowed", "reverb"],
        "candidate_families": ["slowed", "reverb"],
        "unrequested_candidate_families": [],
        "explicit_conflict": False,
    }
    assert build_global_candidate_evidence(snapshot)["eligibility"]["eligible"]


def test_unknown_uploader_is_neutral_inside_normal_duration_band() -> None:
    feature = build_global_candidate_evidence(_snapshot(delta=4, source="OTHER"))
    assert feature["provenance"]["contribution"] == "NEUTRAL"
    assert feature["eligibility"]["eligible"]


def _wrapped(snapshot: dict) -> dict:
    return {"snapshot": snapshot, "global_features": build_global_candidate_evidence(snapshot)}


def test_strong_provenance_can_beat_weak_exact_duration_candidate() -> None:
    weak = _wrapped(_snapshot("weak", delta=0.5, rank=1, source="OTHER"))
    official = _wrapped(
        _snapshot("official", delta=10, rank=2, source="OFFICIAL_AUDIO", channel_match=True)
    )
    decision = resolve_global_candidates({"candidates": [weak, official]})
    assert decision["selected_video_id"] == "official"


def test_candidates_compete_across_frozen_tiers_without_tier_lock() -> None:
    early = _wrapped(
        _snapshot("early", delta=1, source="LYRIC_VIDEO", frozen_stage="POLICY_BALANCED_V1")
    )
    later = _wrapped(
        _snapshot("later", delta=3, source="OTHER", frozen_stage="STAGE5B1C_B", channel_match=True)
    )
    decision = resolve_global_candidates({"candidates": [early, later]})
    assert decision["selected_video_id"] == "later"
    assert global_preference_key(later) < global_preference_key(early)


def test_internally_inconsistent_art_track_is_not_canonical() -> None:
    feature = build_global_candidate_evidence(
        _snapshot(source="ART_TRACK_TOPIC", provided=True)
    )
    assert not feature["provenance"]["art_track_internally_consistent"]
    assert feature["source"]["effective_preference_source_type"] == "OTHER"


def test_music_video_does_not_outrank_cleaner_audio_when_other_evidence_matches() -> None:
    video = _wrapped(
        _snapshot("video", source="OFFICIAL_MUSIC_VIDEO", channel_match=True, rank=1)
    )
    audio = _wrapped(
        _snapshot("audio", source="OFFICIAL_AUDIO", channel_match=True, rank=2)
    )
    assert resolve_global_candidates({"candidates": [video, audio]})["selected_video_id"] == "audio"


def test_views_and_search_rank_are_only_late_tiebreakers() -> None:
    canonical = _wrapped(
        _snapshot("canonical", source="OFFICIAL_AUDIO", channel_match=True, rank=5, relative_views=0.01)
    )
    popular = _wrapped(
        _snapshot("popular", source="LYRIC_VIDEO", rank=1, relative_views=1.0)
    )
    assert resolve_global_candidates({"candidates": [popular, canonical]})["selected_video_id"] == "canonical"


def test_frozen_challenge_replay_and_global_results() -> None:
    config = load_stage5b1g_config(CONFIG)
    assert len(verify_frozen_inputs(config)) == 6
    features, decisions, changed, duration, tail, queue = evaluate_stage5b1g(config)
    assert features["track_count"] == 50
    assert decisions["frozen_regression"] == {
        "baseline_auto_match_count": 42,
        "baseline_match_uncertain_count": 8,
        "same_baseline_selected_candidate_ids": True,
    }
    assert decisions["summary"]["global_auto_match_count"] == 42
    assert decisions["summary"]["global_match_uncertain_count"] == 8
    changed_by_id = {
        row["stable_track_id"]: row["new_selected_candidate"]["snapshot"]["video_id"]
        for row in changed["comparisons"]
    }
    assert changed_by_id["s5b1c_004"] == "SQnc1QibapQ"
    assert changed_by_id["s5b1c_024"] == "VI9gIPBH_dM"
    assert changed_by_id["s5b1c_035"] == "igIfiqqVHtA"
    assert changed_by_id["s5b1c_049"] == "dawrQnvwMTY"
    assert all(
        (row["new_selected_candidate"]["snapshot"].get("human_evidence") or {}).get("label") != "WRONG"
        for row in changed["comparisons"]
    )
    assert all(
        (row["new_selected_candidate"]["snapshot"].get("sol_evidence") or {}).get("label") != "WRONG"
        for row in changed["comparisons"]
    )
    assert tail["remaining_unresolved_count"] == 8
    assert queue["candidate_count"] == changed["comparison_count"]
    assert sum(row["candidates_selected"] for row in duration["rows"]) == 42
    assert decisions["policy_id"] == POLICY_ID
