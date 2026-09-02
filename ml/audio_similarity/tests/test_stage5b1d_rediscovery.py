from __future__ import annotations

import json
from pathlib import Path

from audio_similarity.stage5b1a2_ytdlp import (
    YtDlpBackendResponse,
    YtDlpDiscoveryAdapter,
)
from audio_similarity.stage5b1d_queries import load_stage5b1d_config
from audio_similarity.stage5b1d_rediscovery import (
    DISCOVERY_SCHEMA_VERSION,
    METADATA_INSUFFICIENT_AFTER_REDISCOVERY,
    STILL_CANDIDATE_SET_FAILURE,
    _query_config,
    build_targeted_query_artifact,
    evaluate_rediscovery,
    run_targeted_discovery,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1d_targeted_rediscovery.json"
REPORT = ROOT / "reports/stage5b1d_targeted_rediscovery"


class FakeBackend:
    version = "test-yt-dlp"

    def __init__(self):
        self.expressions: list[str] = []

    def search(self, expression: str) -> YtDlpBackendResponse:
        self.expressions.append(expression)
        index = len(self.expressions)
        video_id = f"T{index:010d}"
        return YtDlpBackendResponse(
            info={
                "entries": [
                    {
                        "id": video_id,
                        "ie_key": "Youtube",
                        "title": f"Candidate {index}",
                        "duration": 200,
                    }
                ]
            },
            warnings=(),
            version=self.version,
        )


def test_live_runner_is_sequential_bounded_and_metadata_only():
    config = load_stage5b1d_config(CONFIG)
    queries = build_targeted_query_artifact(config)
    backend = FakeBackend()
    adapter = YtDlpDiscoveryAdapter(config.provider, _query_config(), backend, sleep=lambda _: None)
    sleeps: list[float] = []
    ticks = iter(f"2026-01-01T00:00:{index:02d}+00:00" for index in range(100))
    result = run_targeted_discovery(
        config,
        queries,
        adapter,
        sleep=sleeps.append,
        now=lambda: next(ticks),
    )
    assert result["schema_version"] == DISCOVERY_SCHEMA_VERSION
    assert len(backend.expressions) == 12
    assert result["summary"]["tracks_attempted"] == 4
    assert result["summary"]["queries_attempted"] == 12
    assert result["summary"]["query_failures"] == 0
    assert result["media_activity"] == {
        "audio_downloads": 0,
        "video_downloads": 0,
        "stage5a_calls": 0,
        "clap_calls": 0,
        "muq_calls": 0,
    }
    assert sleeps.count(config.sleep_between_queries_seconds) == 8
    assert sleeps.count(config.sleep_between_tracks_seconds) == 3
    assert all(expression.startswith("ytsearch5:") for expression in backend.expressions)


def test_frozen_live_discovery_replays_through_unchanged_resolver():
    config = load_stage5b1d_config(CONFIG)
    discovery = json.loads((REPORT / "targeted_discovery.json").read_text())
    features, decisions = evaluate_rediscovery(config, discovery)
    assert features["track_count"] == 4
    assert decisions["frozen_regression"]["combined_auto_match_count"] == 42
    assert decisions["summary"]["rediscovery_auto_match_count"] == 0
    assert decisions["summary"]["combined_auto_match_count"] == 42
    assert decisions["summary"]["combined_coverage"] == 0.84
    assert decisions["summary"]["classification_counts"] == {
        METADATA_INSUFFICIENT_AFTER_REDISCOVERY: 1,
        STILL_CANDIDATE_SET_FAILURE: 3,
    }
    assert all(
        row["combined_decision"]["status"] == "MATCH_UNCERTAIN"
        for row in decisions["tracks"]
    )


def test_committed_query_artifact_matches_frozen_builder():
    config = load_stage5b1d_config(CONFIG)
    expected = build_targeted_query_artifact(config)
    committed = json.loads((REPORT / "targeted_queries.json").read_text())
    assert committed == expected
