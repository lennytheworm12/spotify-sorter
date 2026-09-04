from __future__ import annotations

import pytest

from audio_similarity.stage5b1a2_ytdlp import YtDlpSearchError
from audio_similarity.stage5b1a_models import SpotifyTrack
from audio_similarity.stage5b4c_artist_decomposition import (
    ALL_QUERY_VARIANTS_EMPTY,
    FALLBACK_SUCCESS,
    PRIMARY_MULTI_ARTIST,
    PRIMARY_SUCCESS,
    PROVIDER_ERROR,
    SINGLE_ARTIST_ZERO_RESULT_FALLBACK,
    build_artist_decomposition_plan,
    discover_with_artist_decomposition,
)


def _track(
    title: str = "Girl, Interrupted",
    artists: tuple[str, ...] = ("2xxx", "Miso"),
) -> SpotifyTrack:
    return SpotifyTrack.from_dict(
        {
            "stable_track_id": "spotify:track:test",
            "spotify_track_id": "0" * 22,
            "title": title,
            "artists": list(artists),
            "duration_ms": 181_000,
        }
    )


def _candidate(video_id: str, rank: int) -> dict:
    return {
        "rank": rank,
        "provider_rank": rank,
        "youtube_video_id": video_id,
        "title": f"Candidate {video_id}",
    }


class _Provider:
    def __init__(self, responses: dict[str, object]):
        self.responses = responses
        self.calls: list[tuple[str, int]] = []

    def discover_query(self, track, query, *, limit):
        self.calls.append((query, limit))
        response = self.responses[query]
        if isinstance(response, Exception):
            raise response
        return {
            "track": track.to_dict(),
            "query": query,
            "candidates": list(response),
            "warnings": [],
            "error": None,
        }


def test_q0_uses_title_and_first_three_distinct_credited_artists() -> None:
    plan = build_artist_decomposition_plan(
        _track(artists=("A", " a ", "B", "C", "D"))
    )
    assert plan.artists == ("A", "B", "C")
    assert plan.primary.query == "Girl, Interrupted A B C"
    assert "D" not in plan.primary.query


def test_fallback_queries_each_contain_one_artist_in_credited_order() -> None:
    plan = build_artist_decomposition_plan(_track(artists=("A", "B", "C")))
    assert [(item.index, item.query, item.artist) for item in plan.fallbacks] == [
        (1, "Girl, Interrupted A", "A"),
        (2, "Girl, Interrupted B", "B"),
        (3, "Girl, Interrupted C", "C"),
    ]


def test_primary_candidates_prevent_fallback() -> None:
    primary = _candidate("primary0001", 1)
    provider = _Provider({"Girl, Interrupted 2xxx Miso": [primary]})
    result = discover_with_artist_decomposition(_track(), provider)
    assert result["outcome"] == PRIMARY_SUCCESS
    assert provider.calls == [("Girl, Interrupted 2xxx Miso", 3)]
    assert result["discovery_mode"] == PRIMARY_MULTI_ARTIST
    assert result["query_variant_index"] == 0
    assert result["query_artist"] is None


def test_zero_primary_triggers_q1_before_q2_and_stops_on_q2() -> None:
    recovered = _candidate("recovered01", 1)
    provider = _Provider(
        {
            "Girl, Interrupted 2xxx Miso": [],
            "Girl, Interrupted 2xxx": [],
            "Girl, Interrupted Miso": [recovered],
        }
    )
    result = discover_with_artist_decomposition(_track(), provider)
    assert provider.calls == [
        ("Girl, Interrupted 2xxx Miso", 3),
        ("Girl, Interrupted 2xxx", 3),
        ("Girl, Interrupted Miso", 3),
    ]
    assert result["outcome"] == FALLBACK_SUCCESS
    assert result["successful_query"] == "Girl, Interrupted Miso"
    assert result["query_variant_index"] == 2
    assert result["query_artist"] == "Miso"


def test_later_queries_are_not_run_and_candidate_pools_are_not_merged() -> None:
    q1_candidates = [_candidate("q1candidate", 1)]
    provider = _Provider(
        {
            "Girl, Interrupted A B C": [],
            "Girl, Interrupted A": q1_candidates,
        }
    )
    result = discover_with_artist_decomposition(
        _track(artists=("A", "B", "C")), provider
    )
    assert provider.calls == [
        ("Girl, Interrupted A B C", 3),
        ("Girl, Interrupted A", 3),
    ]
    assert result["candidate_video_ids"] == ["q1candidate"]


def test_one_artist_has_no_duplicate_fallback_request() -> None:
    plan = build_artist_decomposition_plan(_track(artists=("Miso",)))
    assert plan.primary.query == "Girl, Interrupted Miso"
    assert plan.fallbacks == ()
    assert plan.duplicate_fallback_queries_removed == 1
    provider = _Provider({"Girl, Interrupted Miso": []})
    result = discover_with_artist_decomposition(_track(artists=("Miso",)), provider)
    assert result["outcome"] == ALL_QUERY_VARIANTS_EMPTY
    assert result["total_provider_requests"] == 1


def test_normalized_duplicate_artist_names_do_not_create_queries() -> None:
    plan = build_artist_decomposition_plan(
        _track(artists=("Miso", "ＭＩＳＯ", "miso", "2xxx"))
    )
    assert plan.artists == ("Miso", "2xxx")
    assert [item.query for item in plan.fallbacks] == [
        "Girl, Interrupted Miso",
        "Girl, Interrupted 2xxx",
    ]


def test_native_candidate_order_and_ranks_are_preserved() -> None:
    candidates = [
        _candidate("native00001", 1),
        _candidate("native00002", 2),
        _candidate("native00003", 3),
    ]
    provider = _Provider(
        {
            "Girl, Interrupted 2xxx Miso": [],
            "Girl, Interrupted 2xxx": candidates,
        }
    )
    result = discover_with_artist_decomposition(_track(), provider)
    assert result["candidate_video_ids"] == [
        "native00001",
        "native00002",
        "native00003",
    ]
    assert [candidate["rank"] for candidate in result["candidates"]] == [1, 2, 3]


def test_query_and_candidate_provenance_are_recorded_but_not_scored() -> None:
    provider = _Provider(
        {
            "Girl, Interrupted 2xxx Miso": [],
            "Girl, Interrupted 2xxx": [_candidate("fallback001", 1)],
        }
    )
    result = discover_with_artist_decomposition(_track(), provider)
    candidate = result["candidates"][0]
    assert candidate["discovery_mode"] == SINGLE_ARTIST_ZERO_RESULT_FALLBACK
    assert candidate["query_variant_index"] == 1
    assert candidate["query_artist"] == "2xxx"
    assert "score" not in candidate


def test_provider_error_does_not_trigger_zero_result_fallback() -> None:
    error = YtDlpSearchError(
        "YTDLP_NETWORK_ERROR",
        "network unavailable",
        attempts=2,
        retryable=True,
        warnings=("warning",),
    )
    provider = _Provider({"Girl, Interrupted 2xxx Miso": error})
    result = discover_with_artist_decomposition(_track(), provider)
    assert result["outcome"] == PROVIDER_ERROR
    assert result["error"]["category"] == "YTDLP_NETWORK_ERROR"
    assert result["attempts"][0]["result_count"] == 0
    assert provider.calls == [("Girl, Interrupted 2xxx Miso", 3)]


def test_fallback_provider_error_remains_distinct_from_all_empty() -> None:
    error = YtDlpSearchError(
        "YTDLP_PROVIDER_ERROR",
        "provider failed",
        attempts=1,
        retryable=False,
    )
    provider = _Provider(
        {
            "Girl, Interrupted 2xxx Miso": [],
            "Girl, Interrupted 2xxx": error,
        }
    )
    result = discover_with_artist_decomposition(_track(), provider)
    assert result["outcome"] == PROVIDER_ERROR
    assert result["total_provider_requests"] == 2


def test_all_empty_variants_are_explicitly_unresolved() -> None:
    provider = _Provider(
        {
            "Girl, Interrupted 2xxx Miso": [],
            "Girl, Interrupted 2xxx": [],
            "Girl, Interrupted Miso": [],
        }
    )
    result = discover_with_artist_decomposition(_track(), provider)
    assert result["outcome"] == ALL_QUERY_VARIANTS_EMPTY
    assert result["error"] is None
    assert result["candidates"] == []


def test_primary_and_fallback_share_quote_control_and_whitespace_sanitation() -> None:
    track = _track(
        title='All The Stars - From “Black\u0000 Panther: The Album”',
        artists=("Kendrick\nLamar", "SZA"),
    )
    plan = build_artist_decomposition_plan(track)
    assert plan.primary.query == (
        "All The Stars - From Black Panther: The Album Kendrick Lamar SZA"
    )
    assert [item.query for item in plan.fallbacks] == [
        "All The Stars - From Black Panther: The Album Kendrick Lamar",
        "All The Stars - From Black Panther: The Album SZA",
    ]


def test_unicode_parentheses_and_harmless_punctuation_are_preserved() -> None:
    plan = build_artist_decomposition_plan(
        _track(title="넘어와 (Feat. 백예린) & 東京", artists=("DEAN", "Yerin Baek"))
    )
    assert plan.primary.query == "넘어와 (Feat. 백예린) & 東京 DEAN Yerin Baek"


def test_no_forced_official_or_title_only_variant_exists() -> None:
    plan = build_artist_decomposition_plan(_track())
    queries = [variant.query for variant in plan.variants]
    assert all("official" not in query.casefold().split() for query in queries)
    assert plan.title not in queries
    assert all(variant.artist is not None for variant in plan.fallbacks)


def test_only_top_three_provider_candidates_are_retained_without_rescoring() -> None:
    candidates = [_candidate(f"candidate{i:02}", i) for i in range(1, 5)]
    provider = _Provider({"Girl, Interrupted 2xxx Miso": candidates})
    result = discover_with_artist_decomposition(_track(), provider)
    assert result["candidate_video_ids"] == [
        "candidate01",
        "candidate02",
        "candidate03",
    ]
    assert [candidate["provider_rank"] for candidate in result["candidates"]] == [
        1,
        2,
        3,
    ]


def test_non_top3_limit_is_rejected() -> None:
    with pytest.raises(ValueError, match="frozen Top-3"):
        discover_with_artist_decomposition(_track(), _Provider({}), limit=2)
