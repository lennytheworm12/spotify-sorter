from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_similarity.stage5b1a2_ytdlp import (
    YtDlpBackendResponse,
    YtDlpDiscoveryAdapter,
)
from audio_similarity.stage5b1a_models import SpotifyTrack
from audio_similarity.stage5b1j_representation_rediscovery import (
    FALLBACK_LIVE_TO_STUDIO,
    FALLBACK_REMASTER_TO_MASTER,
    NO_FALLBACK,
    REPRESENTATION_EQUIVALENT_MASTER_FALLBACK,
    build_fallback_queries,
    classify_fallback_target,
    derive_base_target,
    load_stage5b1j_config,
    q0_query_config,
    run_fallback_discovery,
    verify_frozen_baseline,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1j_representation_fallback.json"


def _track(title: str, duration_ms: int = 240_000) -> SpotifyTrack:
    return SpotifyTrack.from_dict({
        "stable_track_id": "track",
        "spotify_track_id": None,
        "title": title,
        "artists": ["Artist"],
        "album": "Album",
        "duration_ms": duration_ms,
        "release_year": 2020,
        "isrc": "USABC1234567",
    })


@pytest.mark.parametrize("title", ["Song - Live", "Song - Live at Venue", "Song - Live, 2023"])
def test_ordinary_live_base_title_and_query(title: str) -> None:
    track = _track(title)
    classification = classify_fallback_target(track)
    assert classification["eligible"]
    assert classification["fallback_family"] == FALLBACK_LIVE_TO_STUDIO
    assert classification["base_title"] == "Song"
    base = derive_base_target(track, classification)
    assert base.title == "Song"
    assert base.duration_ms is None
    assert base.album is None


@pytest.mark.parametrize("title", ["Song - 2015 Remaster", "Song (2022 Remastered)", "Song - 50th Anniversary Remaster"])
def test_true_remaster_base_title_derivation(title: str) -> None:
    track = _track(title)
    classification = classify_fallback_target(track)
    assert classification["eligible"]
    assert classification["fallback_family"] == FALLBACK_REMASTER_TO_MASTER
    assert classification["match_mode"] == REPRESENTATION_EQUIVALENT_MASTER_FALLBACK
    base = derive_base_target(track, classification)
    assert base.title == "Song"
    assert base.duration_ms == track.duration_ms


@pytest.mark.parametrize(
    "title",
    [
        "Song - Live Acoustic",
        "Song - Live Orchestral",
        "Song - Live Remix",
        "Song - Live Instrumental",
        "Song - Remix",
        "Song - Slowed + Reverb",
        "Song - Sped Up",
        "Song - Acoustic",
        "Song - Taylor's Version",
        "Song - 2022 Mix",
        "Song - Radio Edit",
        "Song - Extended Mix",
    ],
)
def test_exact_only_families_never_derive_fallback(title: str) -> None:
    classification = classify_fallback_target(_track(title))
    assert not classification["eligible"]
    assert classification["fallback_family"] == NO_FALLBACK


def test_frozen_baseline_and_query_scope() -> None:
    config = load_stage5b1j_config(CONFIG)
    assert verify_frozen_baseline(config) == {
        "exact_replay": True,
        "auto_match_count": 42,
        "match_uncertain_count": 8,
        "coverage": 0.84,
        "existing_selected_candidate_ids_unchanged": True,
        "live_target_count": 4,
    }
    queries = build_fallback_queries(config)
    assert queries["track_count"] == 4
    assert [row["stable_track_id"] for row in queries["tracks"]] == [
        "s5b1c_029", "s5b1c_032", "s5b1c_033", "s5b1c_034",
    ]
    assert [row["fallback_classification"]["fallback_family"] for row in queries["tracks"]] == [
        FALLBACK_LIVE_TO_STUDIO,
        FALLBACK_REMASTER_TO_MASTER,
        FALLBACK_REMASTER_TO_MASTER,
        FALLBACK_REMASTER_TO_MASTER,
    ]
    assert queries["tracks"][0]["query"] == '"Lord Huron" "The Night We Met" official'
    assert all(len(row["original_q0_candidate_video_ids"]) == 5 for row in queries["tracks"])


class _FakeBackend:
    version = "test-yt-dlp"

    def __init__(self) -> None:
        self.expressions: list[str] = []

    def search(self, expression: str) -> YtDlpBackendResponse:
        self.expressions.append(expression)
        video_id = f"J{len(self.expressions):010d}"
        return YtDlpBackendResponse(
            info={"entries": [{
                "id": video_id,
                "ie_key": "Youtube",
                "title": "Artist - Song (Official Audio)",
                "uploader": "Artist",
                "channel": "Artist",
                "duration": 240,
            }]},
            warnings=(),
            version=self.version,
        )


def test_discovery_is_sequential_bounded_and_metadata_only() -> None:
    config = load_stage5b1j_config(CONFIG)
    queries = build_fallback_queries(config)
    assert json.loads(config.artifacts["queries"].read_text()) == queries
    backend = _FakeBackend()
    adapter = YtDlpDiscoveryAdapter(
        config.provider, q0_query_config(), backend, sleep=lambda _: None
    )
    sleeps: list[float] = []
    ticks = iter(f"2026-01-01T00:00:{index:02d}+00:00" for index in range(30))
    result = run_fallback_discovery(
        config, queries, adapter, sleep=sleeps.append, now=lambda: next(ticks)
    )
    assert len(backend.expressions) == 4
    assert sleeps == [3.0, 3.0, 3.0]
    assert result["summary"]["tracks_attempted"] == 4
    assert result["summary"]["search_failures"] == 0
    assert result["media_activity"] == {
        "audio_downloads": 0,
        "video_downloads": 0,
        "stage5a_calls": 0,
        "clap_calls": 0,
        "muq_calls": 0,
    }
    assert all(expression.startswith("ytsearch5:") for expression in backend.expressions)
