from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import SpotifyTrack, Stage5B1AValidationError
from audio_similarity.stage5b1e_queries import (
    STRATEGY_IDS,
    build_natural_query,
    build_query_strategy_artifact,
    load_stage5b1e_config,
    verify_frozen_inputs,
)
from audio_similarity.stage5b1b_challenge import load_challenge_config, load_challenge_manifest


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1e_natural_query_evaluation.json"


def track(title: str = "Taki Taki (with Selena Gomez, Ozuna & Cardi B)") -> SpotifyTrack:
    return SpotifyTrack(
        stable_track_id="fixture",
        spotify_track_id="spotify-fixture",
        title=title,
        artists=("DJ Snake", "Selena Gomez", "Ozuna", "Cardi B"),
        album="Fixture",
        duration_ms=212_500,
        release_year=2018,
        isrc=None,
    )


def test_config_is_frozen_metadata_only_top_five():
    config = load_stage5b1e_config(CONFIG)
    assert tuple(item.strategy_id for item in config.strategies) == STRATEGY_IDS
    assert config.provider.search_prefix == "ytsearch5:"
    assert config.provider.metadata_only_options()["skip_download"] is True
    assert config.provider.metadata_only_options()["simulate"] is True
    assert verify_frozen_inputs(config)


def test_strict_control_remains_exactly_reproducible():
    assert build_natural_query(track(), "Q0_CURRENT_CONTROL") == (
        '"DJ Snake" "Taki Taki (with Selena Gomez, Ozuna & Cardi B)" official'
    )


def test_natural_queries_have_no_quotes_or_forced_official_token():
    assert build_natural_query(track(), "Q1_NATURAL_SPOTIFY_TITLE") == (
        "Taki Taki (with Selena Gomez, Ozuna & Cardi B)"
    )
    assert build_natural_query(track(), "Q2_NATURAL_TITLE_PLUS_ARTIST") == (
        "Taki Taki (with Selena Gomez, Ozuna & Cardi B) DJ Snake"
    )
    for strategy_id in STRATEGY_IDS[1:]:
        query = build_natural_query(track(), strategy_id)
        assert '"' not in query
        assert " official" not in query.lower()


def test_frozen_q3_preserves_current_parser_treatment_of_with_credit():
    # This was frozen before live discovery. The parser retains parenthetical
    # `with` credits in core_title; changing it now would create a new strategy.
    assert build_natural_query(track(), "Q3_CORE_TITLE_ARTIST_VERSION") == (
        "DJ Snake Taki Taki with Selena Gomez, Ozuna & Cardi B"
    )


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Bad Habits - FISHER Remix", "Ed Sheeran Bad Habits FISHER Remix"),
        ("Landslide - 2015 Remaster", "Ed Sheeran Landslide 2015 Remaster"),
        ("The Night We Met - Live at the Ryman 2019", "Ed Sheeran The Night We Met Live at the Ryman 2019"),
        ("Song (Acoustic Version)", "Ed Sheeran Song Acoustic Version"),
    ],
)
def test_q3_preserves_identity_critical_version_evidence(title, expected):
    value = SpotifyTrack(
        stable_track_id="fixture",
        spotify_track_id=None,
        title=title,
        artists=("Ed Sheeran",),
        album=None,
        duration_ms=200_000,
        release_year=2020,
        isrc=None,
    )
    assert build_natural_query(value, "Q3_CORE_TITLE_ARTIST_VERSION") == expected


def test_query_generation_is_deterministic_and_has_no_challenge_branching():
    value = track("Song feat. Guest - Radio Edit")
    first = [build_natural_query(value, item) for item in STRATEGY_IDS]
    second = [build_natural_query(value, item) for item in STRATEGY_IDS]
    assert first == second
    assert all(value.stable_track_id not in query for query in first)


def test_unknown_strategy_is_rejected():
    with pytest.raises(Stage5B1AValidationError, match="unknown"):
        build_natural_query(track(), "Q_TRACK_SPECIFIC_HACK")


def test_strategy_artifact_covers_frozen_challenge_in_order():
    config = load_stage5b1e_config(CONFIG)
    challenge = load_challenge_config(config.challenge_config_path)
    manifest = load_challenge_manifest(
        challenge.manifest_path, expected_sha256=challenge.manifest_sha256
    )
    artifact = build_query_strategy_artifact(
        config, [item.track for item in manifest.tracks]
    )
    assert artifact["track_count"] == 50
    assert artifact["strategy_count"] == 4
    assert artifact["frozen_before_discovery"] is True
    assert all(len(row["queries"]) == 4 for row in artifact["tracks"])
