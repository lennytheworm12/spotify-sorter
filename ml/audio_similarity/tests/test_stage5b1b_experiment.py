from __future__ import annotations

from pathlib import Path

from audio_similarity.stage5b1a2_ytdlp import YtDlpBackendResponse, YtDlpDiscoveryAdapter
from audio_similarity.stage5b1b_config import load_stage5b1b_config
from audio_similarity.stage5b1b_experiment import load_heldout_results, run_heldout_discovery
from audio_similarity.stage5b1b_manifest import load_heldout_manifest


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs" / "stage5b1b.json"


class Backend:
    version = "test-version"

    def __init__(self):
        self.expressions = []

    def search(self, expression):
        self.expressions.append(expression)
        index = len(self.expressions)
        return YtDlpBackendResponse(
            info={
                "entries": [
                    {
                        "_type": "url",
                        "ie_key": "Youtube",
                        "id": f"video{index:06d}"[-11:],
                        "url": f"https://www.youtube.com/watch?v={f'video{index:06d}'[-11:]}",
                        "title": f"Artist - Song {index} (Official Audio)",
                        "uploader": "Label",
                        "duration": 200,
                        "view_count": index * 100,
                    }
                ]
            },
            warnings=(),
            version=self.version,
        )


def test_heldout_run_is_sequential_metadata_only_and_sleep_injected(tmp_path):
    config = load_stage5b1b_config(CONFIG)
    manifest = load_heldout_manifest(config.heldout_manifest_path, expected_sha256=config.heldout_manifest_sha256)
    backend = Backend()
    sleeps = []
    adapter = YtDlpDiscoveryAdapter(config.discovery.provider, config.discovery.query, backend, sleep=sleeps.append)
    ticks = iter([0.0, 10.0])
    results = run_heldout_discovery(
        manifest,
        config,
        adapter,
        sleep=sleeps.append,
        timer=lambda: next(ticks),
        clock=lambda: "2026-09-01T00:00:00Z",
    )
    assert len(backend.expressions) == 50
    assert backend.expressions[0].startswith('ytsearch5:"The Weeknd" "Blinding Lights" official')
    assert len(sleeps) == 49
    assert all(value == 1.0 for value in sleeps)
    assert results["summary"]["deduplicated_candidate_video_ids"] == 50
    assert results["media_activity"] == {
        "audio_downloads": 0,
        "video_downloads": 0,
        "clap_calls": 0,
        "muq_calls": 0,
        "stage5a_materializations": 0,
    }
    assert results["configuration"]["provider"]["metadata_only_options"]["skip_download"] is True
    assert results["tracks"][0]["candidates"][0]["view_count"] == 100


def test_committed_config_preserves_frozen_query_manifest_and_no_threshold():
    config = load_stage5b1b_config(CONFIG)
    assert config.dev_manifest_sha256 == "f3592bb8c8dea689959a22da222d8b7ce4911c1804392acb501cffe768700c57"
    assert config.heldout_manifest_sha256 == "39557ede8f07bde129ad23d2bc64a0faf0fff755356cd87f2054e14f91d81e5a"
    assert config.discovery.query.template == '"{primary_artist}" "{normalized_title}" official'
    assert config.discovery.provider.search_prefix == "ytsearch5:"
