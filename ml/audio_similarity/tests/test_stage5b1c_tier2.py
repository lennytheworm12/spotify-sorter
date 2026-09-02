from __future__ import annotations

from pathlib import Path

from audio_similarity.stage5b1a_models import SpotifyTrack
from audio_similarity.stage5b1b_features import extract_candidate_features
from audio_similarity.stage5b1b_resolver import AUTO_MATCH, MATCH_UNCERTAIN
from audio_similarity.stage5b1c_tier2 import (
    evaluate_frozen_challenge,
    extract_tier2_candidate_evidence,
    extract_tier2_track_features,
    resolve_tier2_track,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1b_fresh_challenge.json"


def track(
    title: str = "Hello", artists: tuple[str, ...] = ("Adele",), duration_ms: int = 295_000
) -> SpotifyTrack:
    return SpotifyTrack("track-1", title, artists, duration_ms=duration_ms)


def candidate(**overrides):
    value = {
        "rank": 1,
        "youtube_video_id": "abcdefghijk",
        "title": "Adele - Hello (Official Audio)",
        "uploader": "Adele",
        "channel": "Adele",
        "duration_seconds": 295,
        "view_count": 10_000,
        "description": "",
    }
    value.update(overrides)
    return value


def wrapped(candidate_value, target=None):
    target = target or track()
    return {
        "candidate": candidate_value,
        "features": extract_candidate_features(target, candidate_value),
    }


def test_art_track_description_and_channel_fuse_performer_and_live_version():
    target = track(
        "Free Fallin' - Live at the Nokia Theatre, Los Angeles, CA - December 2007",
        ("John Mayer",),
        264_267,
    )
    value = candidate(
        title="Free Fallin' (Live at the Nokia Theatre, Los Angeles, CA - December 2007)",
        uploader="John Mayer",
        channel="John Mayer",
        duration_seconds=264,
        description=(
            "Provided to YouTube by Columbia\n"
            "Free Fallin' (Live at the Nokia Theatre, Los Angeles, CA - December 2007) "
            "· John Mayer"
        ),
    )
    evidence = extract_tier2_candidate_evidence(
        target, value, extract_candidate_features(target, value)
    )
    assert evidence["identity_eligible"] is True
    assert evidence["title"]["structural_core_title_match"] is True
    assert evidence["performers"]["primary_performer_match"] is True
    assert evidence["versions"]["relationships"][0]["relationship"] == "MATCH"


def test_explicit_wrong_performer_and_wrong_version_remain_ineligible():
    target = track("Roses - Imanbek Remix", ("SAINt JHN", "Imanbek"), 176_000)
    value = candidate(
        title="John Smith - Roses (Tiësto Remix) (Official Audio)",
        uploader="John Smith",
        channel="John Smith",
        duration_seconds=176,
    )
    evidence = extract_tier2_candidate_evidence(
        target, value, extract_candidate_features(target, value)
    )
    assert evidence["identity_eligible"] is False
    assert evidence["performers"]["explicit_performer_conflict"] is True
    assert evidence["versions"]["conflict_count"] == 1


def test_explicit_cover_signal_remains_ineligible_even_when_target_artist_is_named():
    target = track()
    value = candidate(
        title="Hello - Adele Cover by John Smith",
        uploader="John Smith",
        channel="John Smith",
    )
    evidence = extract_tier2_candidate_evidence(
        target, value, extract_candidate_features(target, value)
    )
    assert evidence["identity_eligible"] is False
    assert evidence["performers"]["explicit_cover_signal"] is True
    assert evidence["performers"]["explicit_performer_conflict"] is True


def test_other_and_duration_gates_are_not_relaxed():
    target = track()
    other = candidate(title="Adele - Hello", uploader="Fan", channel="Fan")
    far = candidate(duration_seconds=310)
    row = {
        "track": target.to_dict(),
        "candidates": [wrapped(other, target), wrapped(far, target)],
    }
    decision = resolve_tier2_track(extract_tier2_track_features(row))
    assert decision["status"] == MATCH_UNCERTAIN
    reasons = [reason for item in decision["excluded_candidates"] for reason in item["reasons"]]
    assert "Tier 2A does not allow OTHER-source fallback" in reasons
    assert "duration exceeds frozen Balanced DURATION_CLOSE boundary" in reasons


def test_corrected_eligibility_recomputes_relative_lyric_views():
    target = track("Iris", ("The Goo Goo Dolls",), 289_533)
    lyric = candidate(
        title="Goo Goo Dolls - Iris (Official Lyric Video)",
        uploader="Goo Goo Dolls",
        channel="Goo Goo Dolls",
        duration_seconds=290,
        view_count=34_000_000,
    )
    row = {"track": target.to_dict(), "candidates": [wrapped(lyric, target)]}
    extracted = extract_tier2_track_features(row)
    feature = extracted["candidates"][0]["features"]
    assert feature["performers"]["primary_performer_match"] is True
    assert feature["weak_evidence"]["relative_view_strength"] == 1.0
    assert resolve_tier2_track(extracted)["status"] == AUTO_MATCH


def test_frozen_challenge_replay_and_tier2_recoveries_are_deterministic():
    features, decisions = evaluate_frozen_challenge(CONFIG)
    repeated_features, repeated_decisions = evaluate_frozen_challenge(CONFIG)
    assert repeated_features == features
    assert repeated_decisions == decisions
    assert features["track_count"] == 21
    assert features["candidate_pair_count"] == 105
    assert decisions["frozen_balanced_regression"] == {
        "exact_decision_replay": True,
        "track_count": 50,
        "auto_match_count": 29,
        "match_uncertain_count": 21,
    }
    assert decisions["summary"]["tier2_auto_match_count"] == 6
    assert decisions["summary"]["tier2_match_uncertain_count"] == 15
    assert decisions["summary"]["tier1_plus_tier2_auto_match_count"] == 35
    assert decisions["summary"]["tier1_plus_tier2_coverage"] == 0.7
    assert {
        row["stable_track_id"]: row["selected_video_id"] for row in decisions["selected"]
    } == {
        "s5b1c_015": "ZNEuWldWPD4",
        "s5b1c_016": "WXx5-HGERcg",
        "s5b1c_017": "62TrmUvQGjo",
        "s5b1c_026": "sKzoEwQaF7Y",
        "s5b1c_027": "aEi646akxko",
        "s5b1c_043": "zDOILKOOUCo",
    }
    assert decisions["summary"]["tier2_selected_sol_label_counts"] == {
        "ACCEPTABLE": 3,
        "IDEAL": 3,
    }
    assert decisions["summary"]["tier2_human_validated_selection_count"] == 0


def test_negative_control_tracks_remain_uncertain():
    _, decisions = evaluate_frozen_challenge(CONFIG)
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
