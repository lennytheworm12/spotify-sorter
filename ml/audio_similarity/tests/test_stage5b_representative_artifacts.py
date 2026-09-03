from __future__ import annotations

from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5b_representative_artifacts import (
    default_historical_paths,
    freeze_resolver_stack,
)
from audio_similarity.stage5b1j_representation_rediscovery import load_stage5b1j_config


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1j_representation_fallback.json"


def test_stack_freeze_is_hard_gated_by_completed_human_review() -> None:
    config = load_stage5b1j_config(CONFIG)
    with pytest.raises(Stage5B1AValidationError, match="human-safe gate"):
        freeze_resolver_stack(config)


def test_historical_exclusion_sources_are_explicit_and_present() -> None:
    paths = default_historical_paths(ROOT)
    assert [path.name for path in paths] == [
        "frozen_tracks.json", "heldout_tracks.json", "challenge_tracks.json"
    ]
    assert all(path.is_file() for path in paths)
