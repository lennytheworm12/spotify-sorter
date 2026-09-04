from __future__ import annotations

import io
import json
from urllib.error import HTTPError

import pytest

from audio_similarity.stage5b1a2_ytdlp import YtDlpSearchError
from audio_similarity.stage5b1a_models import (
    SpotifyTrack,
    Stage5B1AValidationError,
)
from audio_similarity.stage5b3_minimal_selector import AUTO_SELECT, select_native_rank
from audio_similarity.stage5b4a_query_contract_repair import (
    natural_title_first3_artists_query,
)
from audio_similarity.stage5b4c_youtube_data_api import (
    MANUAL_YOUTUBE_URL_OVERRIDE,
    SEARCH_ENDPOINT,
    VIDEOS_ENDPOINT,
    YTDLP_SEARCH,
    YOUTUBE_DATA_API_AUTH_FAILED,
    YOUTUBE_DATA_API_CREDENTIAL_MISSING,
    YOUTUBE_DATA_API_FALLBACK,
    YOUTUBE_DATA_API_HYDRATION_FAILED,
    YOUTUBE_DATA_API_QUOTA_EXCEEDED,
    YOUTUBE_DATA_API_SEARCH_ZERO_RESULTS,
    DataApiVideoReference,
    UrlLibJsonTransport,
    YouTubeDataApiClient,
    YouTubeDataApiConfig,
    YouTubeDataApiError,
    discover_with_data_api_fallback,
)


QUERY = "Girl, Interrupted 2xxx Miso"
VIDEO_IDS = ("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc", "ddddddddddd")


def _track() -> SpotifyTrack:
    return SpotifyTrack.from_dict(
        {
            "stable_track_id": "spotify:track:girl-interrupted",
            "spotify_track_id": "0" * 22,
            "title": "Girl, Interrupted",
            "artists": ["2xxx", "Miso"],
            "duration_ms": 201_000,
        }
    )


class _Primary:
    def __init__(self, candidates=None, error: YtDlpSearchError | None = None):
        self.candidates = list(candidates or [])
        self.error = error
        self.calls = []

    def discover_query(self, track, query, *, limit):
        self.calls.append((track.stable_track_id, query, limit))
        if self.error is not None:
            raise self.error
        return {
            "track": track.to_dict(),
            "query": query,
            "candidates": self.candidates,
            "warnings": [],
            "error": None,
        }


class _Transport:
    def __init__(self, search_payload=None, videos_payload=None, error=None):
        self.search_payload = search_payload or {"items": []}
        self.videos_payload = videos_payload or {"items": []}
        self.error = error
        self.calls = []

    def get_json(self, endpoint, parameters, *, api_key, timeout_seconds):
        self.calls.append((endpoint, dict(parameters), api_key, timeout_seconds))
        if self.error is not None:
            raise self.error
        return self.search_payload if endpoint == SEARCH_ENDPOINT else self.videos_payload


def _search_item(video_id: str, *, kind: str = "youtube#video") -> dict:
    return {"id": {"kind": kind, "videoId": video_id}}


def _video_item(
    video_id: str,
    *,
    title: str | None = None,
    duration: str = "PT3M21S",
    views: str = "12345",
) -> dict:
    return {
        "id": video_id,
        "snippet": {
            "title": title or f"Title {video_id}",
            "description": f"Description {video_id}",
            "channelTitle": "Channel",
            "channelId": "UC123",
            "liveBroadcastContent": "none",
        },
        "contentDetails": {"duration": duration},
        "statistics": {"viewCount": views},
        "status": {"privacyStatus": "public"},
    }


def _client(transport: _Transport, key: str | None = "test-key"):
    return YouTubeDataApiClient(key, transport=transport)


def test_primary_candidates_stop_without_calling_data_api() -> None:
    candidate = {"rank": 1, "youtube_video_id": VIDEO_IDS[0]}
    primary = _Primary([candidate])
    transport = _Transport()
    result = discover_with_data_api_fallback(
        _track(), QUERY, primary, _client(transport)
    )
    assert result["provider_path"] == YTDLP_SEARCH
    assert result["candidates"] == [candidate]
    assert result["data_api_search"]["triggered"] is False
    assert transport.calls == []


def test_zero_primary_uses_same_query_and_exact_search_list_contract() -> None:
    transport = _Transport(
        search_payload={"items": [_search_item(VIDEO_IDS[0])]},
        videos_payload={"items": [_video_item(VIDEO_IDS[0])]},
    )
    result = discover_with_data_api_fallback(
        _track(), QUERY, _Primary(), _client(transport)
    )
    assert result["provider_path"] == YOUTUBE_DATA_API_FALLBACK
    assert result["query"] == QUERY
    assert transport.calls[0] == (
        SEARCH_ENDPOINT,
        {
            "part": "snippet",
            "q": QUERY,
            "type": "video",
            "maxResults": "3",
        },
        "test-key",
        15.0,
    )
    assert transport.calls[1][0] == VIDEOS_ENDPOINT
    assert transport.calls[1][1] == {
        "part": "snippet,contentDetails,statistics,status",
        "id": VIDEO_IDS[0],
    }


def test_search_filters_invalid_results_and_deduplicates_in_order() -> None:
    transport = _Transport(
        search_payload={
            "items": [
                _search_item(VIDEO_IDS[1]),
                _search_item("not-an-id"),
                _search_item(VIDEO_IDS[1]),
                _search_item(VIDEO_IDS[0], kind="youtube#playlist"),
                _search_item(VIDEO_IDS[2]),
                _search_item(VIDEO_IDS[3]),
            ]
        }
    )
    outcome = _client(transport).search(QUERY)
    assert [result.video_id for result in outcome.results] == [
        VIDEO_IDS[1],
        VIDEO_IDS[2],
        VIDEO_IDS[3],
    ]
    assert [result.rank for result in outcome.results] == [1, 2, 3]


def test_videos_list_response_is_reordered_back_to_search_rank() -> None:
    references = tuple(
        DataApiVideoReference(
            rank=rank,
            video_id=video_id,
            watch_url=f"https://www.youtube.com/watch?v={video_id}",
        )
        for rank, video_id in enumerate(VIDEO_IDS[:3], start=1)
    )
    transport = _Transport(
        videos_payload={
            "items": [
                _video_item(VIDEO_IDS[2]),
                _video_item(VIDEO_IDS[0]),
                _video_item(VIDEO_IDS[1]),
            ]
        }
    )
    outcome = _client(transport).hydrate(_track(), QUERY, references)
    assert [candidate["youtube_video_id"] for candidate in outcome.candidates] == list(
        VIDEO_IDS[:3]
    )
    assert [candidate["provider_rank"] for candidate in outcome.candidates] == [1, 2, 3]
    assert [candidate["rank"] for candidate in outcome.candidates] == [1, 2, 3]


def test_missing_hydration_item_preserves_survivor_order_and_provider_rank() -> None:
    references = tuple(
        DataApiVideoReference(
            rank=rank,
            video_id=video_id,
            watch_url=f"https://www.youtube.com/watch?v={video_id}",
        )
        for rank, video_id in enumerate(VIDEO_IDS[:3], start=1)
    )
    transport = _Transport(
        videos_payload={
            "items": [_video_item(VIDEO_IDS[2]), _video_item(VIDEO_IDS[0])]
        }
    )
    outcome = _client(transport).hydrate(_track(), QUERY, references)
    assert [candidate["youtube_video_id"] for candidate in outcome.candidates] == [
        VIDEO_IDS[0],
        VIDEO_IDS[2],
    ]
    assert [candidate["rank"] for candidate in outcome.candidates] == [1, 2]
    assert [candidate["provider_rank"] for candidate in outcome.candidates] == [1, 3]
    assert [record["status"] for record in outcome.records] == [
        "HYDRATED",
        "FAILED",
        "HYDRATED",
    ]


def test_data_api_metadata_normalizes_for_the_existing_selector() -> None:
    transport = _Transport(videos_payload={"items": [_video_item(VIDEO_IDS[0])]})
    reference = DataApiVideoReference(
        rank=1,
        video_id=VIDEO_IDS[0],
        watch_url=f"https://www.youtube.com/watch?v={VIDEO_IDS[0]}",
    )
    outcome = _client(transport).hydrate(_track(), QUERY, (reference,))
    candidate = outcome.candidates[0]
    assert candidate["duration_seconds"] == 201.0
    assert candidate["view_count"] == 12345
    assert candidate["live_status"] == "not_live"
    assert candidate["discovery_source"] == YOUTUBE_DATA_API_FALLBACK
    decision = select_native_rank(_track().to_dict(), list(outcome.candidates))
    assert decision["decision"] == AUTO_SELECT
    assert decision["selected_video_id"] == VIDEO_IDS[0]


def test_missing_credential_is_structured_and_never_calls_transport() -> None:
    transport = _Transport()
    outcome = _client(transport, key=None).search(QUERY)
    assert outcome.error["category"] == YOUTUBE_DATA_API_CREDENTIAL_MISSING
    assert transport.calls == []
    assert "test-key" not in str(outcome.to_dict())


def test_empty_api_search_transitions_to_manual_url_override() -> None:
    result = discover_with_data_api_fallback(
        _track(), QUERY, _Primary(), _client(_Transport())
    )
    assert result["error"]["category"] == YOUTUBE_DATA_API_SEARCH_ZERO_RESULTS
    assert result["data_api_hydration"]["triggered"] is False
    assert result["next_step"] == MANUAL_YOUTUBE_URL_OVERRIDE


def test_all_hydration_misses_transition_to_manual_url_override() -> None:
    transport = _Transport(
        search_payload={"items": [_search_item(VIDEO_IDS[0])]},
        videos_payload={"items": []},
    )
    result = discover_with_data_api_fallback(
        _track(), QUERY, _Primary(), _client(transport)
    )
    assert result["error"]["category"] == YOUTUBE_DATA_API_HYDRATION_FAILED
    assert result["next_step"] == MANUAL_YOUTUBE_URL_OVERRIDE


def test_primary_extractor_error_still_counts_as_zero_usable_candidates() -> None:
    error = YtDlpSearchError(
        "YTDLP_EXTRACTION_ERROR",
        "provider failed",
        attempts=1,
        retryable=True,
    )
    transport = _Transport(
        search_payload={"items": [_search_item(VIDEO_IDS[0])]},
        videos_payload={"items": [_video_item(VIDEO_IDS[0])]},
    )
    result = discover_with_data_api_fallback(
        _track(), QUERY, _Primary(error=error), _client(transport)
    )
    assert result["primary"]["error"]["category"] == "YTDLP_EXTRACTION_ERROR"
    assert result["candidates"][0]["youtube_video_id"] == VIDEO_IDS[0]


@pytest.mark.parametrize(
    ("status", "reason", "category"),
    [
        (403, "quotaExceeded", YOUTUBE_DATA_API_QUOTA_EXCEEDED),
        (403, "keyInvalid", YOUTUBE_DATA_API_AUTH_FAILED),
    ],
)


def test_http_errors_are_structured_without_leaking_the_key(
    monkeypatch, status, reason, category
) -> None:
    secret = "super-secret-api-key"
    body = io.BytesIO(
        json.dumps(
            {
                "error": {
                    "message": f"request rejected for {secret}",
                    "errors": [{"reason": reason}],
                }
            }
        ).encode()
    )
    error = HTTPError(
        f"{SEARCH_ENDPOINT}?key={secret}", status, "failure", {}, body
    )

    def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(
        "audio_similarity.stage5b4c_youtube_data_api.urlopen", fail
    )
    with pytest.raises(YouTubeDataApiError) as caught:
        UrlLibJsonTransport().get_json(
            SEARCH_ENDPOINT,
            {"q": QUERY},
            api_key=secret,
            timeout_seconds=5,
        )
    assert getattr(caught.value, "category") == category
    assert secret not in str(caught.value)
    assert secret not in str(caught.value.to_dict())


def test_config_and_diagnostics_never_serialize_the_credential() -> None:
    config = YouTubeDataApiConfig()
    document = config.to_dict()
    assert document["api_key_environment_variable"] == "YOUTUBE_DATA_API_KEY"
    assert document["credential_persisted"] is False
    assert "api_key" not in document
    transport = _Transport(search_payload={"items": []})
    outcome = _client(transport).search(QUERY)
    assert "test-key" not in str(outcome.to_dict())


def test_config_rejects_nonofficial_endpoints_before_sending_credentials() -> None:
    with pytest.raises(Stage5B1AValidationError):
        YouTubeDataApiConfig(search_endpoint="https://example.com/search")


def test_video_reference_rejects_mismatched_watch_url() -> None:
    with pytest.raises(Stage5B1AValidationError):
        DataApiVideoReference(
            rank=1,
            video_id=VIDEO_IDS[0],
            watch_url=f"https://www.youtube.com/watch?v={VIDEO_IDS[1]}",
        )


def test_frozen_natural_query_is_reused_without_new_heuristics() -> None:
    assert natural_title_first3_artists_query(_track()) == QUERY
    assert "official" not in QUERY.casefold()
    assert '"' not in QUERY
