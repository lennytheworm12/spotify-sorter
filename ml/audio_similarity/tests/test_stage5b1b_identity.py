from __future__ import annotations

import pytest

from audio_similarity.stage5b1a_models import SpotifyTrack
from audio_similarity.stage5b1b_features import (
    SourceType,
    art_track_provenance,
    classify_source,
    extract_candidate_features,
)
from audio_similarity.stage5b1b_identity import (
    ABSENT,
    CONFLICT,
    MATCH,
    compare_versions,
    parse_target,
    parse_versions,
)


def track(title="Roses - Imanbek Remix", artists=("SAINt JHN", "Imanbek"), duration_ms=176_000):
    return SpotifyTrack("track-1", title, tuple(artists), duration_ms=duration_ms)


def relations(target_title, candidate_title):
    return {
        row["family"]: row["relationship"]
        for row in compare_versions(parse_versions(target_title), parse_versions(candidate_title))
    }


def test_target_parser_preserves_raw_core_version_and_artists():
    parsed = parse_target(track())
    assert parsed.raw_title == "Roses - Imanbek Remix"
    assert parsed.core_title == "Roses"
    assert parsed.normalized_title == "roses"
    assert parsed.primary_artist == "SAINt JHN"
    assert parsed.normalized_artists == ("saint jhn", "imanbek")
    assert parsed.duration_seconds == 176.0
    assert [(item.family, item.qualifier) for item in parsed.versions] == [("remix", "Imanbek")]


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("Roses (Imanbek Remix)", MATCH),
        ("Roses", ABSENT),
        ("Roses (Tiësto Remix)", CONFLICT),
    ],
)
def test_named_remix_relationships(candidate, expected):
    assert relations("Roses - Imanbek Remix", candidate)["remix"] == expected


def test_candidate_remix_conflicts_with_plain_target():
    assert relations("Roses", "Roses (Imanbek Remix)")["remix"] == CONFLICT


def test_named_remix_qualifier_can_appear_after_core_title():
    assert relations(
        "Roses - Imanbek Remix", '"Roses" Imanbek Remix (Official Audio)'
    )["remix"] == MATCH


def test_missing_named_remix_qualifier_is_absent_not_a_match_or_conflict():
    assert relations("Roses - Imanbek Remix", "Roses (Remix)")["remix"] == ABSENT


@pytest.mark.parametrize(
    ("target_title", "candidate_title", "family", "expected"),
    [
        ("Fix You - Live in Buenos Aires", "Fix You (Live in Buenos Aires)", "live", MATCH),
        ("Fix You - Live in Buenos Aires", "Fix You", "live", ABSENT),
        ("Fix You", "Fix You (Live)", "live", CONFLICT),
        ("Dreams - 2004 Remaster", "Dreams (2004 Remaster)", "remaster", MATCH),
        ("Blue Monday - 2016 Remaster", "Blue Monday (2020 Remaster)", "remaster", CONFLICT),
        ("Smells Like Teen Spirit - Remastered 2021", "Smells Like Teen Spirit (2021 Remaster)", "remaster", MATCH),
        ("Song - Radio Edit", "Song (Radio Edit)", "radio_edit", MATCH),
        ("All Too Well (Taylor's Version)", "All Too Well (Taylor's Version)", "rerecording", MATCH),
        ("abcdefu (angrier)", "abcdefu (chill)", "named_version", CONFLICT),
    ],
)
def test_common_version_families(target_title, candidate_title, family, expected):
    assert relations(target_title, candidate_title)[family] == expected


def test_explicit_version_conflict_is_ineligible_despite_source_rank_and_views():
    result = extract_candidate_features(
        track(),
        {
            "rank": 1,
            "youtube_video_id": "abcdefghijk",
            "title": "SAINt JHN - Roses (Tiësto Remix) (Official Audio)",
            "uploader": "SAINt JHN",
            "channel": "SAINt JHN",
            "duration_seconds": 176,
            "view_count": 900_000_000,
        },
    )
    assert result["recording_eligible"] is False
    assert result["versions"]["has_explicit_version_conflict"] is True
    assert result["source"]["source_type"] == "OFFICIAL_AUDIO"
    assert result["weak_evidence"]["search_rank"] == 1


def test_uploader_mismatch_is_provenance_not_artist_conflict():
    result = extract_candidate_features(
        track("Hello", ("Adele",), 295_000),
        {
            "rank": 2,
            "youtube_video_id": "abcdefghijk",
            "title": "Adele - Hello",
            "uploader": "XL Recordings",
            "channel": "XL Recordings",
            "duration_seconds": 296,
        },
    )
    assert result["recording_eligible"] is True
    assert result["identity"]["primary_artist_match"] is True
    assert result["identity"]["uploader_used_as_performer_evidence"] is False


def test_explicit_cover_performer_conflict_is_ineligible():
    result = extract_candidate_features(
        track("Hello", ("Adele",), 295_000),
        {
            "rank": 1,
            "youtube_video_id": "abcdefghijk",
            "title": "Hello - Adele Cover by John Smith",
            "uploader": "John Smith",
            "duration_seconds": 295,
        },
    )
    assert result["recording_eligible"] is False
    assert result["identity"]["explicit_performer_conflict"] is True


def test_explicit_different_title_performer_is_ineligible_but_label_uploader_is_not():
    result = extract_candidate_features(
        track("Hello", ("Adele",), 295_000),
        {
            "rank": 1,
            "youtube_video_id": "abcdefghijk",
            "title": "John Smith - Hello",
            "uploader": "XL Recordings",
            "duration_seconds": 295,
        },
    )
    assert result["recording_eligible"] is False
    assert result["identity"]["explicit_title_performer_conflict"] is True


def test_zero_overlap_core_title_conflict_is_ineligible_without_similarity_cutoff():
    result = extract_candidate_features(
        track("Hello", ("Adele",), 295_000),
        {
            "rank": 1,
            "youtube_video_id": "abcdefghijk",
            "title": "Adele - Rolling in the Deep (Official Audio)",
            "uploader": "Adele",
            "duration_seconds": 228,
            "view_count": 1_000_000_000,
        },
    )
    assert result["identity"]["core_title_token_overlap"] == 0.0
    assert result["identity"]["explicit_core_title_conflict"] is True
    assert result["recording_eligible"] is False
    assert result["source"]["source_type"] == "OFFICIAL_AUDIO"


@pytest.mark.parametrize(
    ("title", "family"),
    [
        ("Song (Acoustic)", "acoustic"),
        ("Song (Instrumental)", "instrumental"),
        ("Song (Karaoke)", "karaoke"),
        ("Song (Slowed + Reverb)", "slowed"),
        ("Song (Slowed + Reverb)", "reverb"),
        ("Song (Sped Up)", "sped_up"),
        ("Song (Nightcore)", "nightcore"),
        ("Song (Extended Mix)", "extended"),
        ("Song (Clean Version)", "content_rating"),
        ("Song (Explicit Version)", "content_rating"),
    ],
)
def test_additional_version_families(title, family):
    assert family in {item.family for item in parse_versions(title)}


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ({"uploader": "Adele - Topic", "title": "Hello"}, SourceType.ART_TRACK_TOPIC),
        ({"title": "Hello", "description": "Provided to YouTube by Universal Music Group"}, SourceType.ART_TRACK_TOPIC),
        ({"title": "Adele - Hello (Official Audio)"}, SourceType.OFFICIAL_AUDIO),
        ({"title": "Adele - Hello (Lyrics)"}, SourceType.LYRIC_VIDEO),
        ({"title": "Adele - Hello (Official Music Video)"}, SourceType.OFFICIAL_MUSIC_VIDEO),
        ({"title": "Adele - Hello"}, SourceType.OTHER),
    ],
)
def test_source_classification(candidate, expected):
    assert classify_source(candidate) == expected


def test_art_track_provenance_subfeatures_preserve_raw_triggers():
    evidence = art_track_provenance(
        {
            "uploader": "Taylor Swift - Topic",
            "channel": "Taylor Swift - Topic",
            "description": (
                "Provided to YouTube by Universal Music Group\n\n"
                "Red (Taylor's Version)\n\n"
                "℗ 2021 Taylor Swift\n\n"
                "Released on: 2021-11-12\n\n"
                "Auto-generated by YouTube."
            ),
        }
    )
    assert evidence["topic_channel_signal"] is True
    assert evidence["provided_to_youtube_by_signal"] is True
    assert evidence["auto_generated_by_youtube_signal"] is True
    assert evidence["structured_release_metadata_signal"] is True
    assert evidence["raw_evidence"]["provided_to_youtube_by"] == [
        "Provided to YouTube by Universal Music Group"
    ]
    assert evidence["raw_evidence"]["auto_generated_by_youtube"] == [
        "Auto-generated by YouTube."
    ]


def test_description_album_year_and_matching_uploader_are_supporting_evidence():
    result = extract_candidate_features(
        SpotifyTrack(
            "track-1",
            "All Too Well (Taylor's Version)",
            ("Taylor Swift",),
            album="Red (Taylor's Version)",
            duration_ms=613_000,
            release_year=2021,
        ),
        {
            "rank": 1,
            "youtube_video_id": "abcdefghijk",
            "title": "All Too Well (10 Minute Version) (Taylor's Version)",
            "uploader": "Taylor Swift - Topic",
            "channel": "Taylor Swift - Topic",
            "duration_seconds": 613,
            "description": (
                "Provided to YouTube by Universal Music Group\n"
                "Red (Taylor's Version)\n℗ 2021 Taylor Swift"
            ),
        },
    )
    assert result["source"]["uploader_or_channel_artist_match"] is True
    assert result["description_evidence"]["description_album_match"] is True
    assert result["description_evidence"]["description_release_year_match"] is True


def test_uploader_mismatch_remains_neutral_provenance():
    result = extract_candidate_features(
        track("Hello", ("Adele",), 295_000),
        {
            "rank": 1,
            "youtube_video_id": "abcdefghijk",
            "title": "Adele - Hello",
            "uploader": "XL Recordings",
            "channel": "XL Recordings",
            "duration_seconds": 295,
        },
    )
    assert result["recording_eligible"] is True
    assert result["source"]["uploader_or_channel_artist_match"] is False
    assert result["identity"]["explicit_performer_conflict"] is False


def test_duration_features_are_numeric_not_a_hard_gate():
    result = extract_candidate_features(
        track("Telephone", ("Lady Gaga", "Beyoncé"), 221_000),
        {"rank": 1, "youtube_video_id": "abcdefghijk", "title": "Lady Gaga - Telephone", "duration_seconds": 571},
    )
    assert result["duration"]["absolute_duration_delta_seconds"] == 350
    assert result["duration"]["relative_duration_delta"] == pytest.approx(350 / 221)
    assert result["recording_eligible"] is True


def test_hierarchy_is_explicit_and_rank_is_last_weak_evidence():
    result = extract_candidate_features(
        track("Hello", ("Adele",), 295_000),
        {"rank": 5, "youtube_video_id": "abcdefghijk", "title": "Adele - Hello", "duration_seconds": 295},
    )
    assert result["hierarchy"][0] == "core_target_identity"
    assert result["hierarchy"][-2] == "weak_relative_views_and_search_rank"
    assert result["weak_evidence"]["search_rank"] == 5
