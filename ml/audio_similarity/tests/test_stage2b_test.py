from __future__ import annotations

from pathlib import Path

import pytest

from audio_similarity.stage2b_test import (
    TestLockError as RevealLockError,
    choose_verdict,
    ensure_outputs_absent,
    paired_query_bootstrap,
    verify_test_lock,
)

ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/holistic_stage2b_fusion_single_reviewer.yaml"


def comparison(estimate, lower=-0.1, upper=0.1):
    return {"estimate": estimate, "ci_95": [lower, upper]}


def test_paired_query_bootstrap_is_deterministic_and_paired():
    first = {"1": 1.0, "2": 0.5, "3": 0.0}
    second = {"1": 0.0, "2": 0.5, "3": 1.0}
    a = paired_query_bootstrap(first, second, 50000, 42)
    b = paired_query_bootstrap(first, second, 50000, 42)
    assert a == b
    assert a["estimate"] == 0.0
    assert a["draws"] == 50000


def test_all_four_predeclared_verdict_paths():
    fusions = {"f1": comparison(-0.03, 0.01, 0.05), "f2": comparison(-0.04, 0.02, 0.06)}
    assert choose_verdict(False, 16, comparison(0.1, 0.05), fusions, 0.02) == "INSUFFICIENT_HUMAN_EVIDENCE"
    assert choose_verdict(True, 16, comparison(0.03, 0.01, 0.06), fusions, 0.02) == "FUSION_WINS"
    individual_wins = {"f1": comparison(0.03, 0.01, 0.05), "f2": comparison(0.04, 0.02, 0.06)}
    assert choose_verdict(True, 16, comparison(-0.03, -0.06), individual_wins, 0.02) == "SINGLE_ENCODER_WINS"
    equivalent = {"f1": comparison(0.01, -0.03, 0.04), "f2": comparison(-0.01, -0.04, 0.02)}
    assert choose_verdict(True, 16, comparison(0.01, -0.02, 0.04), equivalent, 0.02) == "STATISTICALLY_EQUIVALENT_PICK_SIMPLER"


def test_refuses_existing_final_output(tmp_path):
    output = tmp_path / "test_metrics.json"
    output.write_text("already revealed")
    with pytest.raises(RevealLockError, match="refusing overwrite"):
        ensure_outputs_absent([output])


def test_real_selection_checkpoint_is_tracked_clean_committed_pushed_and_hash_locked():
    lock = verify_test_lock(CONFIG, ROOT)
    assert len(lock["selection_sha256"]) == 64
    assert lock["selection"]["test_labels_accessed"] is False
    assert lock["selection"]["frozen_test_trial_count"] == 96
    assert lock["head"]
