from __future__ import annotations

from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import SpotifyTrack, Stage5B1AValidationError
from audio_similarity.stage5b1d_queries import (
    MAX_QUERY_VARIANTS,
    build_targeted_queries,
    load_stage5b1d_config,
    verify_stage5b1d_frozen_inputs,
)
from audio_similarity.stage5b1d_rediscovery import (
    CANDIDATE_SET_FAILURE,
    _candidate_set_failures,
    _deduplicate_pool,
    build_targeted_query_artifact,
    verify_frozen_resolver_stack,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1d_targeted_rediscovery.json"


def track(title: str, artists=("Artist",), release_year=2020):
    return SpotifyTrack(
        "synthetic-track",
        title,
        tuple(artists),
        release_year=release_year,
        duration_ms=240_000,
    )


def queries(title: str, artists=("Artist",)):
    config = load_stage5b1d_config(CONFIG)
    return build_targeted_queries(track(title, artists), config.variants)


def test_config_is_metadata_only_bounded_and_hash_locked():
    config = load_stage5b1d_config(CONFIG)
    assert len(config.variants) == MAX_QUERY_VARIANTS == 3
    assert config.provider.search_prefix == "ytsearch5:"
    assert config.provider.metadata_only_options()["skip_download"] is True
    assert config.provider.metadata_only_options()["simulate"] is True
    assert verify_stage5b1d_frozen_inputs(config)["strong_metadata_decisions"] == (
        "740b085b2061935b1d66586534ed4bc418c4ed2562f0cd96efeb4b596748793c"
    )


def test_named_remix_and_remix_artist_are_retained():
    result = queries("Bad Habits - FISHER Remix", ("Ed Sheeran", "FISHER"))
    assert result["structured_identity"]["core_title"] == "Bad Habits"
    assert result["structured_identity"]["exact_version_phrase"] == "FISHER Remix"
    assert all("FISHER" in row["query"] for row in result["queries"])
    assert all("Ed Sheeran" in row["query"] for row in result["queries"])


def test_live_venue_and_year_are_retained():
    result = queries("Song - Live at Red Rocks 2019")
    phrase = result["structured_identity"]["exact_version_phrase"]
    assert "Live at Red Rocks 2019" in phrase
    assert all("Red Rocks 2019" in row["query"] for row in result["queries"])


def test_remaster_year_is_retained():
    result = queries("Landslide - 2015 Remaster", ("Fleetwood Mac",))
    assert result["structured_identity"]["exact_version_phrase"] == "2015 Remaster"
    assert all("2015 Remaster" in row["query"] for row in result["queries"])


def test_modified_version_descriptors_are_retained():
    result = queries("Dandelions - slowed + reverb", ("Ruth B.",))
    phrase = result["structured_identity"]["exact_version_phrase"].casefold()
    assert "slowed" in phrase
    assert "reverb" in phrase
    assert all("dandelions" in row["query"].casefold() for row in result["queries"])


def test_generic_presentation_noise_is_excluded_but_identity_is_retained():
    result = queries(
        "Roses - Imanbek Remix (Official Lyric Video)",
        ("SAINt JHN", "Imanbek"),
    )
    assert result["structured_identity"]["core_title"] == "Roses"
    assert all("Official Lyric Video" not in row["query"] for row in result["queries"])
    assert all("Roses" in row["query"] for row in result["queries"])
    assert all("SAINt JHN" in row["query"] for row in result["queries"])


def test_query_generation_is_deterministic_and_contains_no_track_id():
    first = queries("Roses - Imanbek Remix", ("SAINt JHN", "Imanbek"))
    second = queries("Roses - Imanbek Remix", ("SAINt JHN", "Imanbek"))
    assert first == second
    assert all("synthetic-track" not in row["query"] for row in first["queries"])
    assert len(first["queries"]) <= MAX_QUERY_VARIANTS


def test_target_without_version_evidence_is_rejected():
    config = load_stage5b1d_config(CONFIG)
    with pytest.raises(Stage5B1AValidationError, match="explicit target-version"):
        build_targeted_queries(track("Plain Song"), config.variants)


def test_frozen_resolver_and_diagnostic_scope_replay_exactly():
    config = load_stage5b1d_config(CONFIG)
    replay = verify_frozen_resolver_stack(config)
    assert replay["combined_auto_match_count"] == 42
    assert replay["combined_match_uncertain_count"] == 8
    failures = _candidate_set_failures(config)
    assert len(failures) == 4
    assert all(row["recoverability"] == CANDIDATE_SET_FAILURE for row in failures)
    assert {row["stable_track_id"] for row in failures}.isdisjoint(
        {"s5b1c_030", "s5b1c_033", "s5b1c_034", "s5b1c_041"}
    )


def test_query_artifact_is_bounded_to_frozen_candidate_set_failures():
    config = load_stage5b1d_config(CONFIG)
    artifact = build_targeted_query_artifact(config)
    assert artifact["track_count"] == 4
    assert artifact["query_count"] == 12
    assert all(len(row["queries"]) == 3 for row in artifact["tracks"])


def test_pool_dedup_preserves_original_and_marks_only_new_ids():
    original = [
        {"youtube_video_id": "AAAAAAAAAAA", "rank": 1, "query": "generic"}
    ]
    outcomes = [
        {
            "variant_id": "q1",
            "candidates": [
                {"youtube_video_id": "AAAAAAAAAAA", "rank": 1, "query": "targeted"},
                {"youtube_video_id": "BBBBBBBBBBB", "rank": 2, "query": "targeted"},
            ],
        },
        {
            "variant_id": "q2",
            "candidates": [
                {"youtube_video_id": "BBBBBBBBBBB", "rank": 1, "query": "targeted2"}
            ],
        },
    ]
    pool, new_ids = _deduplicate_pool(original, outcomes)
    assert [row["youtube_video_id"] for row in pool] == ["AAAAAAAAAAA", "BBBBBBBBBBB"]
    assert new_ids == {"BBBBBBBBBBB"}
    assert len(pool[0]["rediscovery_occurrences"]) == 2
    assert len(pool[1]["rediscovery_occurrences"]) == 2
