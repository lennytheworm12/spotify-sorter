from __future__ import annotations

import csv
from pathlib import Path

from audio_similarity.stage5b1a_models import SpotifyTrack
from audio_similarity.stage5b1b_features import extract_candidate_features
from audio_similarity.stage5b1b_resolver import AUTO_MATCH, MATCH_UNCERTAIN
from audio_similarity.stage5b1c_source_neutral import extract_source_neutral_evidence
from audio_similarity.stage5b1c_strong_metadata import (
    CONTEXTUAL_OFFICIAL_AUDIO_MAX_DELTA_SECONDS,
    FROZEN_UNRESOLVED_IDS,
    RULE_CONTEXTUAL_OFFICIAL_AUDIO_DURATION,
    RULE_PRESENTATION_EQUIVALENCE,
    build_strong_metadata_review_queue,
    evaluate_strong_metadata_challenge,
    extract_strong_metadata_evidence,
    modification_evidence,
    presentation_title_evidence,
    resolve_strong_metadata_track,
    strip_trailing_credited_artist_presentation,
    write_strong_metadata_artifacts,
)
from audio_similarity.stage5b1c_tier2 import extract_tier2_candidate_evidence


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1b_fresh_challenge.json"
TIER2A_DIR = ROOT / "reports/stage5b1c_a"
SOURCE_NEUTRAL_DIR = ROOT / "reports/stage5b1c_b"
DIAGNOSTIC = ROOT / "reports/stage5b1c_c_diagnostic/remaining_tail_diagnostic.json"


def target(
    title: str = "Roses - Imanbek Remix",
    artists: tuple[str, ...] = ("SAINt JHN", "Imanbek"),
    duration_ms: int = 180_000,
) -> SpotifyTrack:
    return SpotifyTrack("track-1", title, artists, duration_ms=duration_ms)


def candidate(**overrides):
    value = {
        "rank": 1,
        "youtube_video_id": "abcdefghijk",
        "title": "SAINt JHN - Roses (Imanbek Remix) [Official Audio]",
        "uploader": "SAINt JHN",
        "channel": "SAINt JHN",
        "duration_seconds": 194.7,
        "view_count": 100_000,
        "description": "",
    }
    value.update(overrides)
    return value


def strong_item(target_value: SpotifyTrack, candidate_value: dict):
    tier1 = extract_candidate_features(target_value, candidate_value)
    tier2a = extract_tier2_candidate_evidence(target_value, candidate_value, tier1)
    base_item = {"candidate": candidate_value, "features": tier2a}
    source_neutral = extract_source_neutral_evidence(base_item)
    item = {
        "candidate": candidate_value,
        "tier2a_features": tier2a,
        "source_neutral": source_neutral,
    }
    item["strong_metadata"] = extract_strong_metadata_evidence(target_value, item)
    return item


def resolve_one(target_value: SpotifyTrack, candidate_value: dict):
    item = strong_item(target_value, candidate_value)
    return resolve_strong_metadata_track(
        {"track": target_value.to_dict(), "query": "frozen", "candidates": [item]}
    )


def test_trailing_with_credits_are_removed_only_when_all_are_expected():
    title = "Taki Taki (with Selena Gomez, Ozuna & Cardi B)"
    stripped, aliases = strip_trailing_credited_artist_presentation(
        title, ("DJ Snake", "Selena Gomez", "Ozuna", "Cardi B")
    )
    assert stripped == "Taki Taki"
    assert aliases == ("selena gomez", "ozuna", "cardi b")
    unchanged, aliases = strip_trailing_credited_artist_presentation(
        title, ("DJ Snake", "Selena Gomez")
    )
    assert unchanged == title
    assert aliases == ()


def test_presentation_equivalence_handles_credit_order_and_letra_without_fuzzy_matching():
    track = target(
        "Taki Taki (with Selena Gomez, Ozuna & Cardi B)",
        ("DJ Snake", "Selena Gomez", "Ozuna", "Cardi B"),
        212_500,
    )
    evidence = presentation_title_evidence(
        track,
        "Cardi B, Ozuna, Selena Gomez & DJ Snake - Taki Taki (LETRA VIDEO OFICIAL)",
    )
    assert evidence["exact_structural_match"] is True
    assert evidence["uses_credit_presentation_equivalence"] is True
    assert evidence["fuzzy_matching_used"] is False


def test_presentation_equivalence_preserves_versions_and_rejects_unrelated_titles():
    track = target()
    exact = presentation_title_evidence(
        track, "SAINt JHN - Roses (Imanbek Remix) Official Lyric Video"
    )
    wrong = presentation_title_evidence(
        track, "SAINt JHN - Trap (Imanbek Remix) Official Lyric Video"
    )
    assert exact["exact_structural_match"] is True
    assert exact["candidate"]["version_descriptors"][0]["family"] == "remix"
    assert wrong["exact_structural_match"] is False


def test_unrequested_modified_audio_is_explicitly_preserved():
    evidence = modification_evidence("Taki Taki", "Taki Taki (NCS Bass Boosted)")
    assert evidence["explicit_conflict"] is True
    assert evidence["unrequested_candidate_families"] == ["bass_boosted"]
    matching = modification_evidence(
        "Dandelions - slowed + reverb", "Dandelions (Slowed + Reverb) Lyrics"
    )
    assert matching["explicit_conflict"] is False


def test_strong_named_version_official_audio_can_use_bounded_duration_path():
    item = strong_item(target(), candidate())
    duration = item["strong_metadata"]["contextual_duration_evidence"]
    assert CONTEXTUAL_OFFICIAL_AUDIO_MAX_DELTA_SECONDS == 15
    assert duration["absolute_duration_delta_seconds"] == 14.699999999999989
    assert duration["eligible"] is True
    decision = resolve_one(target(), candidate())
    assert decision["status"] == AUTO_MATCH
    assert decision["selection_rule_ids"] == [RULE_CONTEXTUAL_OFFICIAL_AUDIO_DURATION]


def test_duration_exception_is_not_a_global_threshold_change():
    weak = candidate(
        title="SAINt JHN - Roses (Imanbek Remix)",
        uploader="Unknown",
        channel="Unknown",
    )
    too_far = candidate(duration_seconds=195.1)
    no_explicit_version = target("Roses", ("SAINt JHN",), 180_000)
    no_version_candidate = candidate(
        title="SAINt JHN - Roses (Official Audio)", duration_seconds=194.0
    )
    assert resolve_one(target(), weak)["status"] == MATCH_UNCERTAIN
    assert resolve_one(target(), too_far)["status"] == MATCH_UNCERTAIN
    assert resolve_one(no_explicit_version, no_version_candidate)["status"] == MATCH_UNCERTAIN


def test_modified_audio_families_do_not_receive_duration_exception():
    slowed_target = target("Roses - Slowed Down", ("SAINt JHN",), 180_000)
    slowed_candidate = candidate(
        title="SAINt JHN - Roses (Slowed) [Official Audio]",
        duration_seconds=194.0,
    )
    reverb_target = target("Roses - slowed + reverb", ("SAINt JHN",), 180_000)
    reverb_candidate = candidate(
        title="SAINt JHN - Roses (Slowed + Reverb) [Official Audio]",
        duration_seconds=194.0,
    )
    assert resolve_one(slowed_target, slowed_candidate)["status"] == MATCH_UNCERTAIN
    assert resolve_one(reverb_target, reverb_candidate)["status"] == MATCH_UNCERTAIN


def test_identity_conflicts_cannot_be_rescued_by_source_or_duration():
    cases = [
        (target(), candidate(title="SAINt JHN - Roses (Tiësto Remix) [Official Audio]")),
        (
            target("Roses - 2022 Remaster", ("SAINt JHN",), 180_000),
            candidate(title="SAINt JHN - Roses (2015 Remaster) [Official Audio]"),
        ),
        (
            target("Roses", ("SAINt JHN",), 180_000),
            candidate(title="SAINt JHN - Roses (Live) [Official Audio]"),
        ),
        (target(), candidate(title="John Smith - Roses (Imanbek Remix) [Official Audio]")),
        (target(), candidate(title="Roses (Imanbek Remix) Cover by John Smith")),
        (target(), candidate(title="Roses x Goodbye (Imanbek Mashup) [Official Audio]")),
    ]
    for target_value, candidate_value in cases:
        assert resolve_one(target_value, candidate_value)["status"] == MATCH_UNCERTAIN


def test_presentation_rule_recovers_clean_candidate_but_not_bass_boosted_sibling():
    track = target(
        "Taki Taki (with Selena Gomez, Ozuna & Cardi B)",
        ("DJ Snake", "Selena Gomez", "Ozuna", "Cardi B"),
        212_500,
    )
    clean = candidate(
        title="Dj snake feat selena gomez  Ozuna & CARDI B - TAKi TAKI (LETRA VIDEO OFICIAL",
        uploader="Unknown",
        channel="Unknown",
        duration_seconds=212.0,
    )
    modified = candidate(
        youtube_video_id="lmnopqrstuv",
        rank=2,
        title="DJ Snake - Taki Taki ft. Selena Gomez, Ozuna, Cardi B (NCS Bass Boosted)",
        uploader="Unknown",
        channel="Unknown",
        duration_seconds=212.0,
    )
    clean_item = strong_item(track, clean)
    modified_item = strong_item(track, modified)
    decision = resolve_strong_metadata_track(
        {
            "track": track.to_dict(),
            "query": "frozen",
            "candidates": [clean_item, modified_item],
        }
    )
    assert clean_item["strong_metadata"]["eligible"] is True
    assert clean_item["strong_metadata"]["strong_metadata_waivers"][0][
        "rule_id"
    ] == RULE_PRESENTATION_EQUIVALENCE
    assert modified_item["strong_metadata"]["eligible"] is False
    assert decision["selected_video_id"] == clean["youtube_video_id"]


def test_full_frozen_replay_recovers_only_two_strong_cases():
    features, decisions = evaluate_strong_metadata_challenge(
        CONFIG,
        tier2a_dir=TIER2A_DIR,
        source_neutral_dir=SOURCE_NEUTRAL_DIR,
        diagnostic_path=DIAGNOSTIC,
    )
    assert features["track_count"] == 10
    assert features["candidate_pair_count"] == 50
    assert decisions["frozen_regressions"]["combined_before_stage5b1c_c"] == {
        "auto_match_count": 40,
        "match_uncertain_count": 10,
        "coverage": 0.8,
    }
    assert decisions["summary"]["strong_metadata_auto_match_count"] == 2
    assert decisions["summary"]["strong_metadata_match_uncertain_count"] == 8
    assert decisions["summary"]["combined_auto_match_count"] == 42
    assert decisions["summary"]["combined_coverage"] == 0.84
    assert decisions["summary"]["percentage_point_gain_over_frozen_80_percent"] == 4
    assert {
        row["stable_track_id"]: row["selected_video_id"]
        for row in decisions["selected"]
    } == {
        "s5b1c_012": "kxZYxojih3E",
        "s5b1c_023": "1UESu4eyalA",
    }
    assert decisions["remaining_unresolved_track_ids"] == [
        stable_id for stable_id in FROZEN_UNRESOLVED_IDS
        if stable_id not in {"s5b1c_012", "s5b1c_023"}
    ]
    assert decisions["summary"]["selected_sol_label_counts"] == {
        "ACCEPTABLE": 1,
        "IDEAL": 1,
    }
    assert decisions["summary"]["selected_human_label_counts"] == {"MISSING": 2}


def test_risky_and_failure_controls_remain_uncertain():
    _, decisions = evaluate_strong_metadata_challenge(
        CONFIG,
        tier2a_dir=TIER2A_DIR,
        source_neutral_dir=SOURCE_NEUTRAL_DIR,
        diagnostic_path=DIAGNOSTIC,
    )
    by_id = {row["stable_track_id"]: row["decision"] for row in decisions["tracks"]}
    for stable_id in (
        "s5b1c_021",
        "s5b1c_029",
        "s5b1c_030",
        "s5b1c_032",
        "s5b1c_033",
        "s5b1c_034",
        "s5b1c_040",
        "s5b1c_041",
    ):
        assert by_id[stable_id]["status"] == MATCH_UNCERTAIN


def test_review_queue_contains_only_incremental_selections_and_blank_labels(tmp_path):
    output = tmp_path / "artifacts"
    artifacts = write_strong_metadata_artifacts(
        CONFIG,
        tier2a_dir=TIER2A_DIR,
        source_neutral_dir=SOURCE_NEUTRAL_DIR,
        diagnostic_path=DIAGNOSTIC,
        output_dir=output,
    )
    with artifacts["review"].open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["stable_track_id"] for row in rows] == ["s5b1c_012", "s5b1c_023"]
    assert all(row["candidate_review_label"] == "" for row in rows)
    assert all(row["candidate_note"] == "" for row in rows)
    assert artifacts["summary"]["combined_auto_match_count"] == 42


def test_review_queue_builder_is_deterministic():
    _, decisions = evaluate_strong_metadata_challenge(
        CONFIG,
        tier2a_dir=TIER2A_DIR,
        source_neutral_dir=SOURCE_NEUTRAL_DIR,
        diagnostic_path=DIAGNOSTIC,
    )
    first = build_strong_metadata_review_queue(CONFIG, decisions)
    second = build_strong_metadata_review_queue(CONFIG, decisions)
    assert first == second
