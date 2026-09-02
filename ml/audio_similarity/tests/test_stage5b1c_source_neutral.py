from __future__ import annotations

from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import SpotifyTrack
from audio_similarity.stage5b1b_features import extract_candidate_features
from audio_similarity.stage5b1b_resolver import AUTO_MATCH, MATCH_UNCERTAIN
from audio_similarity.stage5b1c_source_neutral import (
    evaluate_source_neutral_challenge,
    extract_source_neutral_evidence,
    extract_source_neutral_track,
    resolve_source_neutral_track,
)
from audio_similarity.stage5b1c_tier2 import extract_tier2_candidate_evidence


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1b_fresh_challenge.json"
TIER2A_DIR = ROOT / "reports/stage5b1c_a"


def target(
    title: str = "Hello", artists: tuple[str, ...] = ("Adele",), duration_ms: int = 295_000
) -> SpotifyTrack:
    return SpotifyTrack("track-1", title, artists, duration_ms=duration_ms)


def candidate(**overrides):
    value = {
        "rank": 1,
        "youtube_video_id": "abcdefghijk",
        "title": "Adele - Hello",
        "uploader": "Unknown Upload",
        "channel": "Unknown Upload",
        "duration_seconds": 295,
        "view_count": 10_000,
        "description": "",
    }
    value.update(overrides)
    return value


def source_neutral_item(target_value: SpotifyTrack, candidate_value: dict):
    tier1 = extract_candidate_features(target_value, candidate_value)
    tier2a = extract_tier2_candidate_evidence(target_value, candidate_value, tier1)
    item = {"candidate": candidate_value, "features": tier2a}
    return {
        "candidate": candidate_value,
        "tier2a_features": tier2a,
        "source_neutral": extract_source_neutral_evidence(item),
    }


def resolve_one(target_value: SpotifyTrack, candidate_value: dict):
    item = source_neutral_item(target_value, candidate_value)
    return resolve_source_neutral_track(
        {"track": target_value.to_dict(), "query": "frozen", "candidates": [item]}
    )


def test_unknown_uploader_and_other_source_are_neutral_for_strong_identity():
    item = source_neutral_item(target(), candidate())
    evidence = item["source_neutral"]
    assert item["tier2a_features"]["source"]["source_type"] == "OTHER"
    assert evidence["provenance_evidence"]["state"] == "UNKNOWN_NEUTRAL"
    assert evidence["provenance_evidence"]["contribution"] == "NEUTRAL"
    assert evidence["eligible"] is True
    assert resolve_one(target(), candidate())["status"] == AUTO_MATCH


def test_recognized_uploader_is_positive_support_not_a_requirement():
    known = source_neutral_item(
        target(), candidate(uploader="Adele", channel="Adele")
    )["source_neutral"]["provenance_evidence"]
    unknown = source_neutral_item(target(), candidate())["source_neutral"][
        "provenance_evidence"
    ]
    assert known["state"] == "POSITIVE_CORROBORATED"
    assert known["contribution"] == "POSITIVE"
    assert unknown["contribution"] == "NEUTRAL"


def test_weak_identity_other_candidate_does_not_pass():
    decision = resolve_one(target(), candidate(title="Unknown Artist - Goodbye"))
    assert decision["status"] == MATCH_UNCERTAIN
    assert any(
        "title" in reason or "performer" in reason
        for reason in decision["strongest_rejected_candidate"]["all_blockers"]
    )


@pytest.mark.parametrize(
    ("target_title", "candidate_title", "expected_marker"),
    [
        ("Hello", "Hello - Adele Cover by John Smith", "cover"),
        ("Roses - Imanbek Remix", "SAINt JHN - Roses (Tiësto Remix)", "version conflict"),
        ("Landslide - 2015 Remaster", "Fleetwood Mac - Landslide", "version evidence"),
        ("Hello", "Adele - Hello (Slowed + Reverb)", "version conflict"),
        ("Hello", "Adele - Hello (Nightcore)", "version conflict"),
        ("Hello", "Adele - Hello (Live)", "version conflict"),
        ("Hello", "Adele - Hello x Hotline Bling (Mashup)", "title"),
    ],
)
def test_recording_conflicts_remain_hard_rejections(
    target_title: str, candidate_title: str, expected_marker: str
):
    target_value = target(target_title)
    decision = resolve_one(target_value, candidate(title=candidate_title))
    assert decision["status"] == MATCH_UNCERTAIN
    assert any(
        expected_marker in reason
        for reason in decision["strongest_rejected_candidate"]["all_blockers"]
    )


def test_wrong_performer_remains_rejected_even_with_matching_title():
    decision = resolve_one(target(), candidate(title="John Smith - Hello"))
    assert decision["status"] == MATCH_UNCERTAIN
    assert any(
        "performer" in reason
        for reason in decision["strongest_rejected_candidate"]["all_blockers"]
    )


def test_duration_and_music_video_boundaries_are_unchanged():
    far = resolve_one(target(), candidate(duration_seconds=303))
    video = resolve_one(
        target(),
        candidate(
            title="Adele - Hello (Official Video)",
            duration_seconds=298,
        ),
    )
    assert far["status"] == MATCH_UNCERTAIN
    assert "duration exceeds frozen Balanced DURATION_CLOSE boundary" in far[
        "strongest_rejected_candidate"
    ]["all_blockers"]
    assert video["status"] == MATCH_UNCERTAIN
    assert "music-video duration exceeds frozen Balanced DURATION_VERY_CLOSE boundary" in video[
        "strongest_rejected_candidate"
    ]["all_blockers"]


def test_tier1_exact_title_can_corroborate_frozen_tier2a_multi_artist_split():
    target_value = target(
        "Something Just Like This - Alesso Remix",
        ("The Chainsmokers", "Coldplay", "Alesso"),
        247_000,
    )
    value = candidate(
        title="The Chainsmokers & Coldplay - Something Just Like This (Alesso Remix Audio)",
        uploader="The Chainsmokers",
        channel="The Chainsmokers",
        duration_seconds=250,
    )
    item = source_neutral_item(target_value, value)
    assert item["tier2a_features"]["title"]["structural_core_title_match"] is False
    assert item["tier2a_features"]["tier1_before"]["title_exact_normalized_match"] is True
    assert item["source_neutral"]["eligible"] is True
    assert resolve_source_neutral_track(
        {"track": target_value.to_dict(), "query": "frozen", "candidates": [item]}
    )["status"] == AUTO_MATCH


def test_full_frozen_cascade_replay_is_exact_and_deterministic():
    features, decisions = evaluate_source_neutral_challenge(CONFIG, tier2a_dir=TIER2A_DIR)
    repeated_features, repeated_decisions = evaluate_source_neutral_challenge(
        CONFIG, tier2a_dir=TIER2A_DIR
    )
    assert repeated_features == features
    assert repeated_decisions == decisions
    assert features["track_count"] == 15
    assert features["candidate_pair_count"] == 75
    assert decisions["frozen_regressions"]["balanced_v1"] == {
        "exact_decision_replay": True,
        "track_count": 50,
        "auto_match_count": 29,
        "match_uncertain_count": 21,
    }
    assert decisions["frozen_regressions"]["tier2a"]["auto_match_count"] == 6
    assert decisions["summary"]["source_neutral_auto_match_count"] == 5
    assert decisions["summary"]["source_neutral_match_uncertain_count"] == 10
    assert decisions["summary"]["combined_auto_match_count"] == 40
    assert decisions["summary"]["combined_coverage"] == 0.8
    assert decisions["summary"]["percentage_point_gain_over_tier2a"] == 10
    assert {
        row["stable_track_id"]: row["selected_video_id"]
        for row in decisions["selected"]
    } == {
        "s5b1c_020": "OUkkaqSNduU",
        "s5b1c_022": "oS6wfWu0JvA",
        "s5b1c_025": "9gnyYxEWgi4",
        "s5b1c_028": "k4HWjQNN1K8",
        "s5b1c_044": "DQJpFVzeNp8",
    }
    assert decisions["summary"]["selected_sol_label_counts"] == {
        "ACCEPTABLE": 3,
        "IDEAL": 2,
    }
    assert decisions["summary"]["human_validated_selection_count"] == 0


def test_frozen_negative_controls_remain_uncertain():
    _, decisions = evaluate_source_neutral_challenge(CONFIG, tier2a_dir=TIER2A_DIR)
    by_id = {row["stable_track_id"]: row["decision"] for row in decisions["tracks"]}
    for stable_id in (
        "s5b1c_021",
        "s5b1c_029",
        "s5b1c_030",
        "s5b1c_032",
        "s5b1c_033",
        "s5b1c_040",
        "s5b1c_041",
    ):
        assert by_id[stable_id]["status"] == MATCH_UNCERTAIN


def test_extractor_does_not_change_frozen_tier2a_features():
    target_value = target()
    value = candidate()
    tier1 = extract_candidate_features(target_value, value)
    tier2a = extract_tier2_candidate_evidence(target_value, value, tier1)
    row = {
        "track": target_value.to_dict(),
        "query": "frozen",
        "candidates": [{"candidate": value, "features": tier2a}],
    }
    extracted = extract_source_neutral_track(row)
    assert extracted["candidates"][0]["tier2a_features"] == tier2a
