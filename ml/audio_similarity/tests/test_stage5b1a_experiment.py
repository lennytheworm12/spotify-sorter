import itertools
import json
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_config import load_config
from audio_similarity.stage5b1a_discovery import (
    DiscoveryOutcome,
    FirecrawlRequestError,
)
from audio_similarity.stage5b1a_experiment import (
    AWAITING_REVIEW,
    run_discovery_experiment,
    write_discovery_results,
)
from audio_similarity.stage5b1a_models import load_frozen_manifest


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1a_firecrawl.json"


class FakeAdapter:
    def __init__(self, fail_track=None):
        self.fail_track = fail_track
        self.calls = []

    def discover(self, track, limit):
        self.calls.append((track.stable_track_id, limit))
        if track.stable_track_id == self.fail_track:
            raise FirecrawlRequestError(
                "FIRECRAWL_HTTP_503",
                "Firecrawl returned HTTP 503",
                attempts=3,
                retryable=True,
                status_code=503,
            )
        query = f'"{track.artists[0]}" "{track.title}" official'
        return DiscoveryOutcome(
            track=track,
            query=query,
            request={"endpoint": "https://api.firecrawl.dev/v2/search", "payload": {"query": query}},
            provider={"name": "firecrawl", "attempts": 1},
            normalized_results=(),
            candidates=(),
        )


def inputs():
    config = load_config(CONFIG)
    manifest = load_frozen_manifest(
        config.manifest_path,
        expected_sha256=config.manifest_sha256,
    )
    return config, manifest


def test_experiment_is_sequential_failure_isolated_and_auditable():
    config, manifest = inputs()
    adapter = FakeAdapter(fail_track="s5b1a_003")
    counter = itertools.count()
    results = run_discovery_experiment(
        manifest,
        config,
        adapter,
        clock=lambda: f"timestamp-{next(counter):03d}",
    )
    assert [track_id for track_id, _ in adapter.calls] == list(manifest.stable_track_ids)
    assert all(limit == 5 for _, limit in adapter.calls)
    assert results["status"] == AWAITING_REVIEW
    assert results["manifest"]["sha256"] == manifest.sha256
    assert results["configuration"]["query_variant_id"] == config.query.variant_id
    assert results["summary"] == {
        "tracks": 25,
        "firecrawl_request_failures": 1,
        "tracks_with_zero_youtube_candidates": 25,
        "invalid_or_non_video_results": 0,
    }
    failed = results["tracks"][2]
    assert failed["track"]["stable_track_id"] == "s5b1a_003"
    assert failed["error"]["category"] == "FIRECRAWL_HTTP_503"
    assert results["tracks"][3]["error"] is None
    serialized = json.dumps(results)
    assert "Bearer " not in serialized
    assert "never-print-this-key" not in serialized
    assert "FIRECRAWL_API_KEY" in serialized  # environment variable name is provenance, not a secret


def test_discovery_result_write_is_atomic_and_refuses_silent_overwrite(tmp_path):
    config, manifest = inputs()
    results = run_discovery_experiment(manifest, config, FakeAdapter(), clock=lambda: "fixed")
    output = tmp_path / "results.json"
    write_discovery_results(output, results)
    assert json.loads(output.read_text()) == results
    with pytest.raises(FileExistsError):
        write_discovery_results(output, results)
    write_discovery_results(output, results, overwrite=True)
