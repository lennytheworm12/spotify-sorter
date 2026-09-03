from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5b_representative_benchmark import (
    REVIEW_SCHEMA_VERSION,
    load_benchmark_config,
    verify_benchmark_inputs,
    write_review_csv,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b_representative_library_v1.json"


def _decision(video_id: str = "abcdefghijk") -> dict:
    return {
        "tracks": [{
            "benchmark_id": "stage5b_library_v1_001",
            "spotify_track_id": "0" * 22,
            "spotify_target": {
                "title": "Song - Live",
                "artists": ["Artist"],
                "album": "Live Album",
                "duration_ms": 240_000,
                "release_year": 2024,
            },
            "status": "AUTO_MATCH",
            "selected_video_id": video_id,
            "match_mode": "REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK",
            "fallback_reason": "ordinary live exact resolution failed",
            "selected_candidate": {
                "youtube_video_id": video_id,
                "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
                "title": "Artist - Song (Official Audio)",
                "uploader": "Artist",
                "channel": "Artist",
                "duration_seconds": 200.0,
                "view_count": 10_000,
                "description": "Official release audio",
            },
        }]
    }


def test_frozen_benchmark_inputs_and_stack_are_bound() -> None:
    config = load_benchmark_config(CONFIG)
    result = verify_benchmark_inputs(config)

    assert result["manifest"]["sampled_track_count"] == 100
    assert result["manifest"]["post_freeze_substitutions"] == 0
    assert result["stack"]["stack_id"] == "STAGE5B_RESOLVER_CANDIDATE_V1"
    assert result["stack"]["scope_guards"]["benchmark_tuning_permitted"] is False


def test_every_selected_candidate_enters_review_with_match_mode(tmp_path: Path) -> None:
    config = load_benchmark_config(CONFIG)
    config = replace(config, artifacts=config.artifacts | {"human_review": tmp_path / "review.csv"})
    write_review_csv(config, _decision())

    with config.artifacts["human_review"].open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["review_schema_version"] == REVIEW_SCHEMA_VERSION
    assert rows[0]["match_mode"] == "REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK"
    assert rows[0]["candidate_review_label"] == ""


def test_review_identity_cannot_change_after_queue_is_created(tmp_path: Path) -> None:
    config = load_benchmark_config(CONFIG)
    config = replace(config, artifacts=config.artifacts | {"human_review": tmp_path / "review.csv"})
    write_review_csv(config, _decision())

    with pytest.raises(Stage5B1AValidationError, match="selections changed"):
        write_review_csv(config, _decision("zyxwvutsrqp"))
