from __future__ import annotations

import json
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5b1b_calibration import run_calibration_analysis
from audio_similarity.stage5b1b_calibration_sol import load_calibration_sol_config


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1b_calibration_sol.json"
FEATURES = ROOT / "reports/stage5b1b_calibration/candidate_features_v2.json"


def analyze(tmp_path):
    return run_calibration_analysis(
        load_calibration_sol_config(CONFIG),
        feature_v2_path=FEATURES,
        output_dir=tmp_path,
    )


def test_calibration_selects_only_safety_clean_conservative_candidate(tmp_path):
    summary = analyze(tmp_path)
    assert summary["status"] == "STAGE5B1B_POLICY_READY_FOR_FRESH_CHALLENGE_VALIDATION"
    assert summary["selected_policy_id"] == "POLICY_CONSERVATIVE_V1"
    assert summary["policy_metrics"]["auto_match_count"] == 14
    assert summary["policy_metrics"]["match_uncertain_count"] == 36
    assert summary["policy_metrics"]["known_human_wrong_auto_match_count"] == 0
    assert summary["policy_metrics"]["known_human_uncertain_auto_match_count"] == 0
    assert summary["policy_metrics"]["sol_wrong_auto_match_count"] == 0
    assert summary["policy_metrics"]["sol_selected_label_counts"] == {"IDEAL": 14}
    assert summary["production_auto_match_activated"] is False


def test_targeted_audit_denominators_and_sol_human_agreement_are_explicit(tmp_path):
    analyze(tmp_path)
    agreement = json.loads((tmp_path / "sol_human_agreement.json").read_text())
    assert agreement["targeted_human_candidate_count"] == 80
    assert agreement["exact_label_agreement_count"] == 49
    assert agreement["all_state_safety_agreement_count"] == 58
    assert agreement["both_resolved_candidate_count"] == 62
    assert agreement["both_resolved_safety_agreement_count"] == 56
    assert "targeted audit" in agreement["bias_warning"]


def test_policy_variant_metrics_preserve_human_unknown_and_uncertain_separately(tmp_path):
    analyze(tmp_path)
    variants = json.loads((tmp_path / "resolver_policy_variants.json").read_text())
    balanced = variants["metrics"]["POLICY_BALANCED_V1"]
    permissive = variants["metrics"]["POLICY_PERMISSIVE_V1"]
    assert balanced["automatic_track_coverage"] == 0.6
    assert balanced["known_human_wrong_auto_match_count"] == 0
    assert balanced["known_human_uncertain_auto_match_count"] == 1
    assert balanced["selected_without_human_audit_count"] == 13
    assert permissive["automatic_track_coverage"] == 0.86
    assert permissive["known_human_uncertain_auto_match_count"] == 5
    assert permissive["sol_wrong_auto_match_count"] == 2


def test_canonical_and_lyric_patterns_use_targeted_human_denominators(tmp_path):
    analyze(tmp_path)
    patterns = json.loads((tmp_path / "feature_label_analysis.json").read_text())["patterns"]
    provided = patterns["canonical_pattern:strong_identity+provided_to_youtube+close_duration"]
    official = patterns["canonical_pattern:strong_identity+official_audio+close_duration"]
    lyric = patterns["lyric_pattern:strong_identity+close_duration+relative_views_at_least_0.001"]
    assert provided["human_audited_count"] == 7 and provided["WRONG"] == 0
    assert official["human_audited_count"] == 3 and official["WRONG"] == 0
    assert lyric == {
        "pattern": "lyric_pattern:strong_identity+close_duration+relative_views_at_least_0.001",
        "human_audited_count": 10,
        "IDEAL": 2,
        "ACCEPTABLE": 7,
        "WRONG": 0,
        "UNCERTAIN": 1,
        "resolved_human_count": 9,
        "safe_rate_among_resolved_human_labels": 1.0,
    }
    analysis = json.loads((tmp_path / "feature_label_analysis.json").read_text())
    numeric = analysis["numeric_distributions_by_human_label_and_safety"]
    assert numeric["absolute_duration_delta_seconds"]["SAFE"]["count"] == 60
    assert numeric["title_similarity"]["WRONG"]["count"] == 5
    assert numeric["relative_view_strength"]["UNCERTAIN"]["count"] == 14
    assert analysis["patterns"]["version_state:MATCH"]["human_audited_count"] > 0


def test_policy_freeze_is_deterministic_hashable_and_not_activated(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    analyze(first)
    analyze(second)
    policy = json.loads((first / "resolver_policy_candidate_v1.json").read_text())
    assert file_sha256(first / "resolver_policy_candidate_v1.json") == file_sha256(
        second / "resolver_policy_candidate_v1.json"
    )
    assert policy["status"] == "CANDIDATE_POLICY_ONLY"
    assert policy["production_status"] == "NOT_PRODUCTION_ACTIVATED"
    assert policy["next_gate"] == "FRESH_CHALLENGE_SET_VALIDATION_REQUIRED"
    assert all(value == 0 for value in policy["media_activity"].values())


def test_three_way_artifact_distinguishes_unaudited_from_safe(tmp_path):
    analyze(tmp_path)
    comparison = json.loads((tmp_path / "three_way_comparison.json").read_text())
    assert len(comparison["tracks"]) == 50
    selected = [row for row in comparison["tracks"] if row["resolver"]["status"] == "AUTO_MATCH"]
    assert len(selected) == 14
    assert sum(row["selected_candidate_human_audited"] for row in selected) == 6
    assert sum(row["human_label_for_selected"] is None for row in selected) == 8
    assert comparison["human_missing_means_unaudited_not_safe"] is True


def test_committed_sol_run_is_complete_isolated_and_failure_free():
    config = load_calibration_sol_config(CONFIG)
    state = json.loads(config.evaluations_path.read_text(encoding="utf-8"))
    assert state["status"] == "COMPLETE"
    assert (state["completed_track_count"], state["completed_candidate_count"]) == (50, 248)
    assert state["errors"] == []
    assert all(row["operational"]["forbidden_tool_event_count"] == 0 for row in state["tracks"])
    assert state["blindness"] == {
        "human_labels_supplied": False,
        "resolver_features_supplied": False,
        "search_rank_supplied": False,
        "case_tags_or_rationale_supplied": False,
        "candidate_order_deterministically_shuffled": True,
        "tools_or_web_allowed": False,
        "isolated_ephemeral_working_directory": True,
    }
