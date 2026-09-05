from __future__ import annotations

import json
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5b4c_experiment import (
    fallback_config_document,
    verify_stage5b4c_history,
)
from audio_similarity.stage5b4c_youtube_data_api import (
    MANUAL_YOUTUBE_URL_OVERRIDE,
    YOUTUBE_DATA_API_SEARCH_ZERO_RESULTS,
)


QUERY = "Girl, Interrupted 2xxx Miso"


def test_history_and_config_pin_existing_selector_and_fallback_evidence() -> None:
    project_root = Path(__file__).resolve().parents[1]
    history = verify_stage5b4c_history(project_root)
    config = fallback_config_document(project_root)
    assert history["production_activation"] is False
    assert config["architecture"]["fallback_trigger"] == (
        "ZERO_USABLE_PRIMARY_CANDIDATES_ONLY"
    )
    assert config["architecture"]["unresolved_next_step"] == (
        MANUAL_YOUTUBE_URL_OVERRIDE
    )
    assert config["data_api"]["search_parameters"] == {
        "part": "snippet",
        "q": "SAME_NATURAL_QUERY",
        "type": "video",
        "maxResults": 3,
    }
    assert config["scope_guards"]["playwright_invocations"] == 0
    assert config["scope_guards"]["audio_downloads"] == 0


def test_recorded_live_result_is_empty_api_items_not_parser_rejection() -> None:
    output_dir = (
        Path(__file__).resolve().parents[1]
        / "reports/stage5b4c_youtube_data_api_fallback"
    )
    search = json.loads((output_dir / "data_api_search.json").read_text())
    hydration = json.loads((output_dir / "hydrated_candidates.json").read_text())
    assert search["query"] == QUERY
    assert search["triggered"] is True
    assert search["outcome"]["results"] == []
    assert search["bounded_diagnostic"]["item_count"] == 0
    assert search["bounded_diagnostic"]["query_unchanged"] is True
    assert hydration["triggered"] is False
    assert hydration["candidates"] == []
    assert hydration["next_step"] == MANUAL_YOUTUBE_URL_OVERRIDE
    assert hydration["error"]["category"] == YOUTUBE_DATA_API_SEARCH_ZERO_RESULTS


def test_failed_live_supplement_is_complete_and_hash_locked() -> None:
    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "reports/stage5b4c_youtube_data_api_fallback"
    required = {
        "fallback_config.json",
        "primary_discovery.json",
        "data_api_search.json",
        "hydrated_candidates.json",
        "human_review.csv",
        "fallback_metrics.json",
        "fallback_report.md",
        "artifact_manifest.json",
    }
    assert required == {path.name for path in output_dir.iterdir() if path.is_file()}
    manifest = json.loads((output_dir / "artifact_manifest.json").read_text())
    metrics = json.loads((output_dir / "fallback_metrics.json").read_text())
    assert manifest["verdict"] == "YOUTUBE_DATA_API_FALLBACK_FAILED"
    assert metrics["counts"] == {
        "primary_candidates": 0,
        "data_api_video_results": 0,
        "hydrated_candidates": 0,
    }
    assert metrics["unresolved_next_step"] == MANUAL_YOUTUBE_URL_OVERRIDE
    assert metrics["selector_evaluation_after_human_review"] is None
    assert metrics["scope_guards"]["credential_serialized"] is False
    for name, identity in manifest["artifacts"].items():
        assert identity["sha256"] == file_sha256(output_dir / name)
    for identity in manifest["implementation"].values():
        assert identity["sha256"] == file_sha256(project_root / identity["path"])
    for identity in manifest["frozen_inputs"].values():
        assert identity["sha256"] == file_sha256(project_root / identity["path"])
