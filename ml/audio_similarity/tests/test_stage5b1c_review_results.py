from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5b1b_challenge_audit import REVIEW_COLUMNS
from audio_similarity.stage5b1c_review import evaluate_tier2_review


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1b_fresh_challenge.json"
REPORT = ROOT / "reports/stage5b1c_b"
QUEUE = REPORT / "tier2_human_audit_queue.json"
REVIEW = REPORT / "tier2_human_review.csv"
TIER2A = ROOT / "reports/stage5b1c_a/tier2_decisions.json"
SOURCE_NEUTRAL = REPORT / "source_neutral_decisions.json"


def evaluate(review_path: Path):
    return evaluate_tier2_review(
        config_path=CONFIG,
        tier2a_decisions_path=TIER2A,
        source_neutral_decisions_path=SOURCE_NEUTRAL,
        queue_path=QUEUE,
        review_path=review_path,
    )


def rewrite(path: Path, transform) -> None:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    transform(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_completed_tier2_audit_has_eleven_safe_human_judgments():
    results = evaluate(REVIEW)
    assert results["status"] == "STAGE5B1C_TIER2_HUMAN_AUDIT_SAFETY_HOLDS"
    assert results["recommendation"] == "PROCEED_TO_STAGE5B1C_C_DIAGNOSTIC"
    assert results["summary"] == {
        "required_judgments": 11,
        "reviewed_judgments": 11,
        "remaining_judgments": 0,
        "ideal_count": 5,
        "acceptable_count": 6,
        "wrong_count": 0,
        "uncertain_count": 0,
        "safe_count": 11,
        "safe_rate_among_reviewed": 1.0,
        "tier1_plus_tier2_auto_match_count": 40,
        "tier1_plus_tier2_coverage": 0.8,
    }
    assert results["stage_label_counts"] == {
        "STAGE5B1C_A_NORMALIZATION": {"ACCEPTABLE": 3, "IDEAL": 3},
        "STAGE5B1C_B_SOURCE_NEUTRAL": {"ACCEPTABLE": 3, "IDEAL": 2},
    }
    assert all(row["safety_class"] == "SAFE" for row in results["judgments"])


def test_incomplete_wrong_and_uncertain_states_are_not_treated_as_safe(tmp_path):
    incomplete = tmp_path / "incomplete.csv"
    wrong = tmp_path / "wrong.csv"
    uncertain = tmp_path / "uncertain.csv"
    for path in (incomplete, wrong, uncertain):
        shutil.copyfile(REVIEW, path)
    rewrite(incomplete, lambda rows: rows[0].update(candidate_review_label=""))
    rewrite(wrong, lambda rows: rows[0].update(candidate_review_label="WRONG"))
    rewrite(uncertain, lambda rows: rows[0].update(candidate_review_label="UNCERTAIN"))
    assert evaluate(incomplete)["status"] == "STAGE5B1C_TIER2_HUMAN_AUDIT_INCOMPLETE"
    assert evaluate(wrong)["status"] == (
        "STAGE5B1C_TIER2_HUMAN_AUDIT_REQUIRES_RESOLVER_REVIEW"
    )
    assert evaluate(wrong)["summary"]["wrong_count"] == 1
    assert evaluate(uncertain)["summary"]["uncertain_count"] == 1


def test_review_metadata_mutation_is_rejected(tmp_path):
    changed = tmp_path / "changed.csv"
    shutil.copyfile(REVIEW, changed)
    rewrite(changed, lambda rows: rows[0].update(candidate_video_id="badidentity"))
    with pytest.raises(Stage5B1AValidationError, match="metadata changed"):
        evaluate(changed)


def test_oversized_review_note_is_rejected(tmp_path):
    changed = tmp_path / "oversized.csv"
    shutil.copyfile(REVIEW, changed)
    rewrite(changed, lambda rows: rows[0].update(candidate_note="x" * 2001))
    with pytest.raises(Stage5B1AValidationError, match="note exceeds"):
        evaluate(changed)
