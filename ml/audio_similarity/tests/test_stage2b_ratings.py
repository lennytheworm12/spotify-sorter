from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from audio_similarity.stage2b_collection import validate_collection_bundle
from audio_similarity.stage2b_contract import ContractError
from audio_similarity.stage2b_ratings import canonicalize_single_reviewer, validate_and_freeze_ratings
from audio_similarity.stage2b_store import RATING_COLUMNS

ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/holistic_stage2b_fusion_single_reviewer.yaml"


def event(event_id, trial_id, rater, choice, supersedes=""):
    return {
        "event_id": event_id,
        "trial_id": trial_id,
        "rater_id": rater,
        "choice": choice,
        "note": "",
        "submitted_at": "1",
        "supersedes_event_id": supersedes,
    }


def frame(rows):
    return pd.DataFrame(rows, columns=RATING_COLUMNS)


def test_single_reviewer_latest_self_correction_is_canonical():
    keys = {"t1": {}, "t2": {}}
    result = canonicalize_single_reviewer(frame([
        event("e1", "t1", "alice", "A"),
        event("e2", "t2", "alice", "Tie"),
        event("e3", "t1", "alice", "Neither", "e1"),
    ]), keys)
    assert dict(zip(result["trial_id"], result["choice"])) == {"t1": "Neither", "t2": "Tie"}
    assert dict(zip(result["trial_id"], result["event_id"]))["t1"] == "e3"


def test_missing_coverage_and_multiple_reviewers_fail_closed():
    keys = {"t1": {}, "t2": {}}
    with pytest.raises(ContractError, match="coverage incomplete"):
        canonicalize_single_reviewer(frame([event("e1", "t1", "alice", "A")]), keys)
    with pytest.raises(ContractError, match="one designated reviewer"):
        canonicalize_single_reviewer(frame([
            event("e1", "t1", "alice", "A"), event("e2", "t2", "bob", "B")
        ]), keys)


def test_invalid_supersession_and_choice_fail_closed():
    with pytest.raises(ContractError, match="unknown/later"):
        canonicalize_single_reviewer(frame([event("e2", "t1", "alice", "A", "e1")]), {"t1": {}})
    with pytest.raises(ContractError, match="invalid choice"):
        canonicalize_single_reviewer(frame([event("e1", "t1", "alice", "Maybe")]), {"t1": {}})


def test_real_amended_protocol_freezes_complete_labels_and_preserves_original_bundle():
    validate_collection_bundle(ROOT)
    summary = validate_and_freeze_ratings(CONFIG, ROOT)
    assert summary["protocol_version"] == "single_reviewer_v2"
    assert summary["canonical_trial_count"] == 240
    assert summary["distinct_reviewers"] == 1
    assert summary["test_queries_with_ab_choice"] == summary["test_query_count"] == 16
    assert summary["protocol_passed"] is True
    validate_collection_bundle(ROOT)
