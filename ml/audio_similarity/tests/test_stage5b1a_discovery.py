import io
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from audio_similarity.stage5b1a_config import load_config
from audio_similarity.stage5b1a_discovery import (
    FirecrawlDiscoveryAdapter,
    FirecrawlHTTPTransport,
    FirecrawlRequestError,
    FirecrawlTransportResponse,
    build_search_query,
    deduplicate_candidates,
    normalize_firecrawl_web_results,
    parse_youtube_video_id,
)
from audio_similarity.stage5b1a_models import SpotifyTrack, Stage5B1AValidationError


ROOT = Path(__file__).parents[1]
CONFIG_PATH = ROOT / "configs/stage5b1a_firecrawl.json"


def track(title="Low (feat. T-Pain)"):
    return SpotifyTrack.from_dict(
        {
            "stable_track_id": "track-1",
            "spotify_track_id": None,
            "title": title,
            "artists": ["Flo Rida", "T-Pain"],
            "album": None,
            "duration_ms": None,
            "release_year": 2007,
            "isrc": None,
        }
    )


class FakeTransport:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def search(self, payload):
        self.requests.append(payload)
        return FirecrawlTransportResponse(self.payload, attempts=1)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, _limit):
        return self.payload


def test_config_freezes_provider_query_candidate_limit_and_gate():
    config = load_config(CONFIG_PATH)
    assert config.provider.endpoint == "https://api.firecrawl.dev/v2/search"
    assert config.provider.sources == ({"type": "web"},)
    assert config.provider.include_domains == ("youtube.com", "youtu.be")
    assert config.provider.provider_result_limit == 10
    assert config.provider.candidate_limit == 5
    assert config.gate.pass_min_recall_at_5 == 0.9
    assert config.gate.conditional_min_recall_at_5 == 0.8


def test_query_construction_removes_only_featured_artist_noise():
    config = load_config(CONFIG_PATH)
    assert build_search_query(track(), config.query) == '"Flo Rida" "Low" official'
    versioned = track("Roses - Imanbek Remix (feat. Guest)")
    assert build_search_query(versioned, config.query) == '"Flo Rida" "Roses - Imanbek Remix" official'
    version_after_feature = track("Song feat. Guest - Live")
    assert build_search_query(version_after_feature, config.query) == '"Flo Rida" "Song feat. Guest - Live" official'
    assert build_search_query(track('Song "Quoted"'), config.query) == '"Flo Rida" "Song Quoted" official'


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=12", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?si=value", "dQw4w9WgXcQ"),
        ("youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/channel/not-a-video", None),
        ("https://youtube.com/watch?v=too-short", None),
        ("https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ", None),
        ("https://example.com/watch?v=dQw4w9WgXcQ", None),
        (None, None),
    ],
)
def test_youtube_video_id_parsing(url, expected):
    assert parse_youtube_video_id(url) == expected


def test_normalization_deduplicates_by_video_id_and_preserves_best_rank():
    raw = [
        {"url": "https://youtube.com/watch?v=dQw4w9WgXcQ", "title": "first", "description": "one"},
        {"url": "https://youtu.be/dQw4w9WgXcQ", "title": "duplicate", "description": "two"},
        {"url": "https://youtube.com/@artist", "title": "channel"},
        {"url": "https://youtube.com/shorts=bad", "title": "invalid"},
        {"url": "https://youtube.com/shorts/abcDEF123_-", "title": "second video"},
        {"url": "https://youtube.com/watch?v=zYxWV9876_-", "title": "third video"},
    ]
    normalized = normalize_firecrawl_web_results(raw)
    candidates = deduplicate_candidates(
        normalized,
        query='"artist" "song" official',
        stable_track_id="track-1",
        limit=2,
    )
    assert [result.source_rank for result in normalized] == [1, 2, 3, 4, 5, 6]
    assert [candidate.youtube_video_id for candidate in candidates] == [
        "dQw4w9WgXcQ",
        "abcDEF123_-",
    ]
    assert [candidate.rank for candidate in candidates] == [1, 2]
    assert [candidate.firecrawl_rank for candidate in candidates] == [1, 5]
    assert candidates[0].url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert candidates[0].duplicate_occurrences == (
        {"source_rank": 2, "url": "https://youtu.be/dQw4w9WgXcQ", "title": "duplicate"},
    )


def test_adapter_orders_results_handles_empty_and_preserves_request_provenance():
    config = load_config(CONFIG_PATH)
    transport = FakeTransport(
        {"success": True, "data": {"web": []}, "id": "job-1", "creditsUsed": 1}
    )
    outcome = FirecrawlDiscoveryAdapter(config.provider, config.query, transport).discover(track())
    assert outcome.normalized_results == ()
    assert outcome.candidates == ()
    assert transport.requests == [config.provider.request_payload(outcome.query)]
    persisted = outcome.to_dict()
    assert persisted["provider"]["job_id"] == "job-1"
    assert persisted["request"]["payload"]["includeDomains"] == ["youtube.com", "youtu.be"]
    assert "Authorization" not in json.dumps(persisted)


def test_adapter_rejects_firecrawl_failure_and_invalid_result_shape():
    config = load_config(CONFIG_PATH)
    failed = FakeTransport({"success": False, "error": "provider failure"})
    adapter = FirecrawlDiscoveryAdapter(config.provider, config.query, failed)
    with pytest.raises(FirecrawlRequestError, match="success=false"):
        adapter.discover(track())
    malformed = FakeTransport({"success": True, "data": {"web": {}}})
    adapter = FirecrawlDiscoveryAdapter(config.provider, config.query, malformed)
    with pytest.raises(FirecrawlRequestError, match="must be an array"):
        adapter.discover(track())


def test_http_transport_retries_temporary_network_error_without_real_sleep():
    config = load_config(CONFIG_PATH)
    calls = []
    sleeps = []

    def opener(request, timeout):
        calls.append((request, timeout))
        if len(calls) == 1:
            raise URLError("temporary")
        return FakeResponse(b'{"success":true,"data":{"web":[]}}')

    response = FirecrawlHTTPTransport(
        config.provider,
        "test-secret",
        opener=opener,
        sleep=sleeps.append,
    ).search({"query": "test"})
    assert response.attempts == 2
    assert sleeps == [1.0]
    assert len(calls) == 2
    assert calls[0][1] == 30
    assert calls[0][0].get_header("Authorization") == "Bearer test-secret"


def test_http_transport_does_not_retry_permanent_http_error_or_leak_key():
    config = load_config(CONFIG_PATH)
    calls = []

    def opener(request, timeout):
        calls.append((request, timeout))
        raise HTTPError(request.full_url, 401, "unauthorized", {}, io.BytesIO(b"secret"))

    with pytest.raises(FirecrawlRequestError) as captured:
        FirecrawlHTTPTransport(
            config.provider,
            "never-print-this-key",
            opener=opener,
            sleep=lambda _: None,
        ).search({"query": "test"})
    assert captured.value.category == "FIRECRAWL_HTTP_401"
    assert captured.value.attempts == 1
    assert "never-print-this-key" not in str(captured.value)
    assert len(calls) == 1


def test_real_transport_requires_environment_credential_value():
    config = load_config(CONFIG_PATH)
    with pytest.raises(Stage5B1AValidationError, match="FIRECRAWL_API_KEY"):
        FirecrawlHTTPTransport(config.provider, "")
