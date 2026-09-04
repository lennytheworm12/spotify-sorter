from __future__ import annotations

from audio_similarity.stage5b1a2_ytdlp import YtDlpSearchError
from audio_similarity.stage5b1a_models import SpotifyTrack
from audio_similarity.stage5b_selector_aware_fallback import (
    ALL_QUERY_VARIANTS_UNSELECTABLE,
    FALLBACK_SELECTED,
    PRIMARY_SELECTED,
    PROVIDER_ERROR,
    TITLE_ONLY_UNSELECTABLE_FALLBACK,
    build_selection_aware_query_plan,
    discover_and_select_with_fallback,
)


def _track(
    *,
    title: str = "Love Always Leaves Me",
    artists: tuple[str, ...] = ("오안과 편견", "Lee Yerin"),
) -> SpotifyTrack:
    return SpotifyTrack.from_dict(
        {
            "stable_track_id": "stage5c2_019",
            "spotify_track_id": "5" * 22,
            "title": title,
            "artists": list(artists),
            "duration_ms": 202_000,
        }
    )


def _candidate(video_id: str, rank: int, duration: float) -> dict:
    return {
        "rank": rank,
        "provider_rank": rank,
        "youtube_video_id": video_id,
        "title": f"Candidate {video_id}",
        "duration_seconds": duration,
    }


class _Provider:
    def __init__(self, responses: dict[str, object]):
        self.responses = responses
        self.calls: list[str] = []

    def discover_query(self, track, query, *, limit):
        assert limit == 3
        self.calls.append(query)
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


def test_query_plan_ends_with_sanitized_title_only_after_single_artists() -> None:
    plan = build_selection_aware_query_plan(_track())
    assert [(item.index, item.query) for item in plan] == [
        (0, "Love Always Leaves Me 오안과 편견 Lee Yerin"),
        (1, "Love Always Leaves Me 오안과 편견"),
        (2, "Love Always Leaves Me Lee Yerin"),
        (4, "Love Always Leaves Me"),
    ]
    assert plan[-1].discovery_mode == TITLE_ONLY_UNSELECTABLE_FALLBACK


def test_primary_selectable_candidate_stops_all_fallbacks() -> None:
    query = "Love Always Leaves Me 오안과 편견 Lee Yerin"
    provider = _Provider({query: [_candidate("primary0001", 1, 202)]})
    result = discover_and_select_with_fallback(_track(), provider)
    assert result["outcome"] == PRIMARY_SELECTED
    assert result["selected_video_id"] == "primary0001"
    assert provider.calls == [query]


def test_nonempty_but_fully_vetoed_primary_triggers_artist_fallback() -> None:
    provider = _Provider(
        {
            "Love Always Leaves Me 오안과 편견 Lee Yerin": [
                _candidate("rejected001", 1, 275)
            ],
            "Love Always Leaves Me 오안과 편견": [
                _candidate("recovered01", 1, 202)
            ],
        }
    )
    result = discover_and_select_with_fallback(_track(), provider)
    assert result["outcome"] == FALLBACK_SELECTED
    assert result["selected_video_id"] == "recovered01"
    assert provider.calls == [
        "Love Always Leaves Me 오안과 편견 Lee Yerin",
        "Love Always Leaves Me 오안과 편견",
    ]
    assert result["attempts"][0]["selector_reason"] == "ALL_TOP3_CANDIDATES_VETOED"


def test_each_unselectable_pool_continues_until_title_only_is_selectable() -> None:
    rejected = [_candidate("rejected001", 1, 275)]
    provider = _Provider(
        {
            "Love Always Leaves Me 오안과 편견 Lee Yerin": rejected,
            "Love Always Leaves Me 오안과 편견": [],
            "Love Always Leaves Me Lee Yerin": rejected,
            "Love Always Leaves Me": [_candidate("recovered01", 1, 202)],
        }
    )
    result = discover_and_select_with_fallback(_track(), provider)
    assert result["outcome"] == FALLBACK_SELECTED
    assert result["query_variant_index"] == 4
    assert result["discovery_mode"] == TITLE_ONLY_UNSELECTABLE_FALLBACK
    assert result["selected_video_id"] == "recovered01"
    assert provider.calls[-1] == "Love Always Leaves Me"
    assert result["total_provider_requests"] == 4


def test_one_artist_skips_duplicate_single_artist_but_keeps_title_only() -> None:
    track = _track(title="Whiplash", artists=("aespa",))
    assert [item.query for item in build_selection_aware_query_plan(track)] == [
        "Whiplash aespa",
        "Whiplash",
    ]


def test_success_uses_only_one_native_pool_without_merging_or_reranking() -> None:
    provider = _Provider(
        {
            "Love Always Leaves Me 오안과 편견 Lee Yerin": [],
            "Love Always Leaves Me 오안과 편견": [
                _candidate("native00001", 1, 275),
                _candidate("native00002", 2, 202),
                _candidate("native00003", 3, 202),
            ],
        }
    )
    result = discover_and_select_with_fallback(_track(), provider)
    assert [row["youtube_video_id"] for row in result["candidates"]] == [
        "native00001",
        "native00002",
        "native00003",
    ]
    assert result["selected_video_id"] == "native00002"
    assert result["selected_rank"] == 2
    assert result["scope_guards"]["candidate_pool_merges"] == 0


def test_all_unselectable_and_provider_error_remain_distinct() -> None:
    queries = [item.query for item in build_selection_aware_query_plan(_track())]
    empty = discover_and_select_with_fallback(
        _track(), _Provider({query: [] for query in queries})
    )
    assert empty["outcome"] == ALL_QUERY_VARIANTS_UNSELECTABLE
    assert empty["error"] is None

    error = YtDlpSearchError(
        "YTDLP_NETWORK_ERROR",
        "network unavailable",
        attempts=2,
        retryable=True,
    )
    failed = discover_and_select_with_fallback(
        _track(), _Provider({queries[0]: error})
    )
    assert failed["outcome"] == PROVIDER_ERROR
    assert failed["error"]["category"] == "YTDLP_NETWORK_ERROR"


def test_query_sanitation_is_shared_and_no_forced_terms_are_added() -> None:
    track = _track(
        title='All The Stars - From “Black\x00 Panther: The Album”',
        artists=("Kendrick\nLamar", "SZA"),
    )
    queries = [item.query for item in build_selection_aware_query_plan(track)]
    assert queries == [
        "All The Stars - From Black Panther: The Album Kendrick Lamar SZA",
        "All The Stars - From Black Panther: The Album Kendrick Lamar",
        "All The Stars - From Black Panther: The Album SZA",
        "All The Stars - From Black Panther: The Album",
    ]
    assert all("official" not in query.casefold().split() for query in queries)
