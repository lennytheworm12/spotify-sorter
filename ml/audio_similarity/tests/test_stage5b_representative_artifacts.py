from __future__ import annotations

from pathlib import Path

from audio_similarity.stage5b_representative_artifacts import (
    default_historical_paths,
    freeze_resolver_stack,
)
from audio_similarity.stage5b1j_representation_rediscovery import load_stage5b1j_config


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1j_representation_fallback.json"


def test_stack_freeze_requires_and_records_completed_human_review() -> None:
    config = load_stage5b1j_config(CONFIG)
    frozen = freeze_resolver_stack(config)

    assert frozen["stack_id"] == "STAGE5B_RESOLVER_CANDIDATE_V1"
    assert frozen["status"] == "FROZEN_CANDIDATE_STACK_NOT_PRODUCTION_ACTIVATED"
    assert frozen["human_review"]["completed"] == 1
    assert frozen["human_review"]["label_counts"] == {"IDEAL": 1}
    assert frozen["human_review"]["all_safe"] is True


def test_historical_exclusion_sources_are_explicit_and_present() -> None:
    paths = default_historical_paths(ROOT)
    assert [path.name for path in paths] == [
        "frozen_tracks.json", "heldout_tracks.json", "challenge_tracks.json"
    ]
    assert all(path.is_file() for path in paths)
