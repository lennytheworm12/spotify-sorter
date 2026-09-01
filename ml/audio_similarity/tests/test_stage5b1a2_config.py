import json
from pathlib import Path

import pytest

from audio_similarity.cli.stage5b1a2 import verify_inputs
from audio_similarity.stage5b1a2_config import load_ytdlp_config
from audio_similarity.stage5b1a_discovery import build_search_query
from audio_similarity.stage5b1a_models import Stage5B1AValidationError, load_frozen_manifest


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1a2_ytdlp.json"
FROZEN_HASH = "f3592bb8c8dea689959a22da222d8b7ce4911c1804392acb501cffe768700c57"


def test_config_reuses_exact_manifest_query_gate_and_separate_paths():
    config = load_ytdlp_config(CONFIG)
    manifest = load_frozen_manifest(config.manifest_path, expected_sha256=FROZEN_HASH)
    assert manifest.sha256 == FROZEN_HASH
    assert len(manifest.tracks) == 25
    assert config.query.template == '"{primary_artist}" "{normalized_title}" official'
    assert config.query.variant_id == "quoted-primary-artist-title-official-v1"
    assert config.gate.pass_min_recall_at_5 == 0.9
    assert config.gate.conditional_min_recall_at_5 == 0.8
    assert all("stage5b1a_ytdlp" in str(path) for path in config.artifacts.values())
    assert "stage5b1a/firecrawl_discovery_results.json" in str(
        config.comparison_sources["firecrawl_results"]
    )


def test_config_freezes_metadata_only_top_five_and_pacing():
    provider = load_ytdlp_config(CONFIG).provider
    assert provider.search_prefix == "ytsearch5:"
    assert provider.candidate_limit == 5
    assert provider.sleep_between_tracks_seconds == 1.0
    assert provider.max_attempts == 2
    assert provider.metadata_only_options() == {
        "cachedir": False,
        "extract_flat": "in_playlist",
        "ignoreconfig": True,
        "ignoreerrors": False,
        "lazy_playlist": False,
        "noprogress": True,
        "playlistend": 5,
        "quiet": True,
        "retries": 0,
        "simulate": True,
        "skip_download": True,
        "socket_timeout": 30,
    }


def test_query_builder_is_identical_to_firecrawl_semantics():
    config = load_ytdlp_config(CONFIG)
    manifest = load_frozen_manifest(config.manifest_path, expected_sha256=FROZEN_HASH)
    low = manifest.tracks[3].track
    mix = manifest.tracks[6].track
    assert build_search_query(low, config.query) == '"Flo Rida" "Low" official'
    assert build_search_query(mix, config.query) == '"The Beatles" "Here Comes The Sun - 2019 Mix" official'


def test_config_rejects_gate_or_media_safeguard_changes(tmp_path):
    payload = json.loads(CONFIG.read_text())
    payload["feasibility_gate"]["pass_min_recall_at_5"] = 0.85
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(payload))
    with pytest.raises(Stage5B1AValidationError, match="gate changed"):
        load_ytdlp_config(changed)
    payload = json.loads(CONFIG.read_text())
    payload["provider"]["skip_download"] = False
    changed.write_text(json.dumps(payload))
    with pytest.raises(Stage5B1AValidationError, match="safeguards"):
        load_ytdlp_config(changed)


def test_verify_is_network_free_and_reports_frozen_contract():
    verified = verify_inputs(CONFIG)
    assert verified["manifest_sha256"] == FROZEN_HASH
    assert verified["track_count"] == 25
    assert verified["candidate_limit"] == 5
    assert verified["search_prefix"] == "ytsearch5:"
    assert verified["pacing_seconds"] == 1.0
