from pathlib import Path

import pytest
import yt_dlp

from audio_similarity.stage5b1a2_config import load_ytdlp_config
from audio_similarity.stage5b1a2_ytdlp import (
    YtDlpBackendResponse,
    YtDlpDiscoveryAdapter,
    YtDlpPythonBackend,
    YtDlpSearchError,
    deduplicate_ytdlp_candidates,
    normalize_ytdlp_entries,
)
from audio_similarity.stage5b1a_models import SpotifyTrack


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1a2_ytdlp.json"


def track():
    return SpotifyTrack.from_dict(
        {
            "stable_track_id": "track-1",
            "spotify_track_id": None,
            "title": "Low (feat. T-Pain)",
            "artists": ["Flo Rida", "T-Pain"],
            "album": "Mail on Sunday",
            "duration_ms": 231000,
            "release_year": 2007,
            "isrc": None,
        }
    )


def entry(video_id="dQw4w9WgXcQ", **changes):
    value = {
        "_type": "url",
        "ie_key": "Youtube",
        "id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": "Candidate",
        "uploader": "Uploader",
        "channel": "Channel",
        "duration": 212,
        "description": "Description",
        "availability": "public",
        "live_status": "not_live",
    }
    value.update(changes)
    return value


def test_normalization_preserves_rich_metadata_and_filters_non_video_entries():
    results = normalize_ytdlp_entries(
        [entry(), {"_type": "playlist", "id": "PL123", "title": "container"}, None]
    )
    first = results[0]
    assert first.youtube_video_id == "dQw4w9WgXcQ"
    assert first.canonical_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert first.duration_seconds == 212.0
    assert first.uploader == "Uploader"
    assert first.channel == "Channel"
    assert first.availability == "public"
    assert first.live_status == "not_live"
    assert results[1].youtube_video_id is None
    assert results[2].youtube_video_id is None


def test_video_id_mismatch_and_non_youtube_extractor_are_rejected():
    mismatch = entry(url="https://youtube.com/watch?v=abcdefghijk")
    external = entry(ie_key="Generic", url="https://example.com/video")
    results = normalize_ytdlp_entries([mismatch, external])
    assert [item.youtube_video_id for item in results] == [None, None]


def test_deduplication_preserves_first_order_and_limits_top_five():
    entries = [entry(), entry(title="duplicate")]
    entries.extend(entry(f"abcDEF12{i:03d}"[-11:]) for i in range(6))
    normalized = normalize_ytdlp_entries(entries)
    candidates = deduplicate_ytdlp_candidates(
        normalized,
        query='"artist" "title" official',
        stable_track_id="track-1",
        limit=5,
    )
    assert len(candidates) == 5
    assert candidates[0].youtube_video_id == "dQw4w9WgXcQ"
    assert candidates[0].rank == 1
    assert candidates[0].provider_rank == 1
    assert candidates[0].provider == "yt_dlp"
    assert candidates[0].duplicate_occurrences[0]["source_rank"] == 2
    assert len({candidate.youtube_video_id for candidate in candidates}) == 5


def test_empty_and_invalid_result_shapes():
    assert normalize_ytdlp_entries(None) == ()
    assert normalize_ytdlp_entries([]) == ()
    with pytest.raises(YtDlpSearchError, match="must be an array"):
        normalize_ytdlp_entries({})


def test_python_backend_invokes_metadata_only_extract_without_download():
    config = load_ytdlp_config(CONFIG)
    observed = {}

    class FakeYDL:
        def __init__(self, options):
            observed["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def extract_info(self, expression, download):
            observed["expression"] = expression
            observed["download"] = download
            return {"entries": [entry()]}

        def sanitize_info(self, value):
            return value

    backend = YtDlpPythonBackend(config.provider, youtube_dl_factory=FakeYDL)
    response = backend.search('ytsearch5:"Flo Rida" "Low" official')
    assert response.info["entries"][0]["id"] == "dQw4w9WgXcQ"
    assert observed["download"] is False
    assert observed["options"]["simulate"] is True
    assert observed["options"]["skip_download"] is True
    assert observed["options"]["extract_flat"] == "in_playlist"
    assert observed["options"]["cachedir"] is False
    assert "outtmpl" not in observed["options"]


class FakeBackend:
    version = "test-version"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def search(self, expression):
        self.calls.append(expression)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_adapter_constructs_ytsearch_query_retries_with_bounded_backoff():
    config = load_ytdlp_config(CONFIG)
    temporary = YtDlpSearchError(
        "YTDLP_EXTRACTION_ERROR", "temporary", attempts=1, retryable=True, warnings=("warn",)
    )
    success = YtDlpBackendResponse({"entries": [entry()]}, ("recovered",), "test-version")
    backend = FakeBackend([temporary, success])
    sleeps = []
    outcome = YtDlpDiscoveryAdapter(
        config.provider, config.query, backend, sleep=sleeps.append
    ).discover(track())
    assert backend.calls == ['ytsearch5:"Flo Rida" "Low" official'] * 2
    assert sleeps == [2.0]
    assert outcome.provider["attempts"] == 2
    assert outcome.warnings == ("warn", "recovered")
    assert outcome.candidates[0].duration_seconds == 212.0


def test_adapter_records_final_extraction_error_after_bounded_attempts():
    config = load_ytdlp_config(CONFIG)
    errors = [
        YtDlpSearchError("YTDLP_EXTRACTION_ERROR", "temporary", attempts=1, retryable=True)
        for _ in range(2)
    ]
    backend = FakeBackend(errors)
    with pytest.raises(YtDlpSearchError) as captured:
        YtDlpDiscoveryAdapter(config.provider, config.query, backend, sleep=lambda _: None).discover(track())
    assert captured.value.attempts == 2
    assert len(backend.calls) == 2
