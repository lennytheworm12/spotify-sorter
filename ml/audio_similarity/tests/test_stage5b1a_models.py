import json
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import (
    SpotifyTrack,
    Stage5B1AValidationError,
    load_frozen_manifest,
)


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "reports/stage5b1a/frozen_tracks.json"
MANIFEST_SHA256 = "f3592bb8c8dea689959a22da222d8b7ce4911c1804392acb501cffe768700c57"


def valid_track(**changes):
    value = {
        "stable_track_id": "track-1",
        "spotify_track_id": "1A2B3C4D5E6F7G8H9I0J1K",
        "title": "Song (feat. Guest)",
        "artists": ["Artist", "Guest"],
        "album": "Album",
        "duration_ms": 180000,
        "release_year": 2024,
        "isrc": "USABC2400001",
    }
    return value | changes


def test_track_input_round_trip_is_provider_independent():
    track = SpotifyTrack.from_dict(valid_track())
    assert track.artists == ("Artist", "Guest")
    assert track.to_dict() == valid_track()
    assert "query" not in track.to_dict()
    assert "firecrawl" not in json.dumps(track.to_dict()).lower()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"stable_track_id": ""}, "stable_track_id"),
        ({"title": ""}, "title"),
        ({"artists": []}, "artists"),
        ({"artists": ["Artist", "Artist"]}, "duplicates"),
        ({"spotify_track_id": "short"}, "spotify_track_id"),
        ({"duration_ms": 0}, "duration_ms"),
        ({"release_year": 1800}, "release_year"),
        ({"isrc": "bad"}, "isrc"),
    ],
)
def test_track_input_validation(changes, message):
    with pytest.raises(Stage5B1AValidationError, match=message):
        SpotifyTrack.from_dict(valid_track(**changes))


def test_frozen_manifest_is_hash_locked_sorted_and_representative():
    manifest = load_frozen_manifest(MANIFEST, expected_sha256=MANIFEST_SHA256)
    assert len(manifest.tracks) == 25
    assert manifest.stable_track_ids == tuple(sorted(manifest.stable_track_ids))
    tags = {tag for item in manifest.tracks for tag in item.case_tags}
    assert {
        "straightforward_major_hit",
        "older_popular_recording",
        "multiple_artists",
        "feat_in_title",
        "punctuation_heavy_title",
        "parentheses",
        "remastered_or_remixed_recording",
        "explicit_version",
        "ambiguous_title",
        "artist_symbols",
        "electronic",
        "hip_hop",
        "rock_alternative",
        "r_and_b",
        "latin",
        "country",
        "k_pop",
        "official_video_duration_differs",
        "many_covers",
    } <= tags


def test_frozen_manifest_hash_mismatch_fails_before_loading():
    with pytest.raises(Stage5B1AValidationError, match="SHA-256 mismatch"):
        load_frozen_manifest(MANIFEST, expected_sha256="0" * 64)
