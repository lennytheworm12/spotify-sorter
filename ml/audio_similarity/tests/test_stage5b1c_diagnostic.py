from __future__ import annotations

from pathlib import Path

from audio_similarity.stage5b1c_diagnostic import (
    CANDIDATE_SET_FAILURE,
    FROZEN_SOURCE_NEUTRAL_SELECTED,
    FROZEN_TIER2A_SELECTED,
    FROZEN_UNRESOLVED_IDS,
    METADATA_INSUFFICIENT,
    POSSIBLE_METADATA_RECOVERY,
    STRONG_METADATA_RECOVERY,
    build_remaining_tail_diagnostic,
    write_remaining_tail_diagnostic,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1b_fresh_challenge.json"
TIER2A_DIR = ROOT / "reports/stage5b1c_a"
SOURCE_NEUTRAL_DIR = ROOT / "reports/stage5b1c_b"


def diagnostic():
    return build_remaining_tail_diagnostic(
        CONFIG,
        tier2a_dir=TIER2A_DIR,
        source_neutral_dir=SOURCE_NEUTRAL_DIR,
    )


def test_frozen_cascade_replay_remains_exact():
    result = diagnostic()["frozen_regression"]
    assert result["balanced_v1"] == {
        "auto_match_count": 29,
        "match_uncertain_count": 21,
        "exact_selected_candidate_replay": True,
    }
    assert result["stage5b1c_a"]["selected_video_ids"] == FROZEN_TIER2A_SELECTED
    assert result["stage5b1c_b"]["selected_video_ids"] == FROZEN_SOURCE_NEUTRAL_SELECTED
    assert result["combined"] == {
        "auto_match_count": 40,
        "match_uncertain_count": 10,
        "coverage": 0.8,
    }


def test_unresolved_tail_is_derived_and_each_track_has_all_five_candidates():
    result = diagnostic()
    assert tuple(result["confirmed_unresolved_track_ids"]) == FROZEN_UNRESOLVED_IDS
    assert result["summary"]["candidate_pair_count"] == 50
    assert all(len(track["all_five_candidates"]) == 5 for track in result["tracks"])
    for track in result["tracks"]:
        ids = {
            row["candidate"]["youtube_video_id"]
            for row in track["all_five_candidates"]
        }
        assert track["diagnostic_strongest_candidate"]["candidate"][
            "youtube_video_id"
        ] in ids


def test_diagnostic_classification_and_metadata_ceiling_are_explicit():
    result = diagnostic()
    assert result["summary"]["recoverability_counts"] == {
        CANDIDATE_SET_FAILURE: 4,
        METADATA_INSUFFICIENT: 2,
        POSSIBLE_METADATA_RECOVERY: 2,
        STRONG_METADATA_RECOVERY: 2,
    }
    assert result["summary"]["hypothetical_strong_only_ceiling"] == {
        "auto_match": 42,
        "total": 50,
        "rate": 0.84,
    }
    assert result["summary"]["hypothetical_strong_plus_possible_ceiling"] == {
        "auto_match": 44,
        "total": 50,
        "rate": 0.88,
    }
    assert result["summary"]["ceiling_is_diagnostic_not_validated_coverage"] is True


def test_primary_and_combined_blocker_counts_are_deterministic():
    summary = diagnostic()["summary"]
    assert summary["primary_failed_gate_track_counts"] == {
        "DURATION_THRESHOLD": 4,
        "EXACT_TITLE_REQUIREMENT_OR_PARSER_NORMALIZATION": 1,
        "EXPLICIT_VERSION_CONFLICT": 1,
        "INCOMPLETE_OR_MISSING_VERSION_EVIDENCE": 4,
    }
    assert summary["strongest_candidate_failed_gate_track_counts"] == {
        "DURATION_THRESHOLD": 6,
        "EXACT_TITLE_REQUIREMENT_OR_PARSER_NORMALIZATION": 4,
        "EXPLICIT_VERSION_CONFLICT": 1,
        "INCOMPLETE_OR_MISSING_VERSION_EVIDENCE": 4,
    }
    assert summary["common_strongest_candidate_blocker_combinations"] == {
        "DURATION_THRESHOLD": 3,
        "DURATION_THRESHOLD + EXACT_TITLE_REQUIREMENT_OR_PARSER_NORMALIZATION": 1,
        "DURATION_THRESHOLD + EXACT_TITLE_REQUIREMENT_OR_PARSER_NORMALIZATION + INCOMPLETE_OR_MISSING_VERSION_EVIDENCE": 1,
        "DURATION_THRESHOLD + EXPLICIT_VERSION_CONFLICT": 1,
        "EXACT_TITLE_REQUIREMENT_OR_PARSER_NORMALIZATION": 1,
        "EXACT_TITLE_REQUIREMENT_OR_PARSER_NORMALIZATION + INCOMPLETE_OR_MISSING_VERSION_EVIDENCE": 1,
        "INCOMPLETE_OR_MISSING_VERSION_EVIDENCE": 2,
    }


def test_sol_gap_buckets_and_absent_human_evidence_are_not_overstated():
    result = diagnostic()
    assert result["summary"]["sol_gap_counts"] == {
        "CANDIDATE_SET_ITSELF_INADEQUATE": 4,
        "METADATA_INSUFFICIENT_EVEN_FOR_SOL": 3,
        "RESOLVER_COULD_ENCODE_SAME_REASONING_DETERMINISTICALLY": 2,
        "SOL_CONTEXTUAL_EVIDENCE_WEIGHTING_ADVANTAGE": 1,
    }
    assert all(
        row["frozen_human_evidence"] is None
        for track in result["tracks"]
        for row in track["all_five_candidates"]
    )


def test_no_policy_or_external_work_is_performed():
    guards = diagnostic()["scope_guards"]
    assert guards["new_policy_implemented"] is False
    assert guards["duration_threshold_changed"] is False
    assert guards["version_equivalence_added"] is False
    assert guards["resolver_features_changed"] is False
    assert guards["yt_dlp_searches"] == 0
    assert guards["sol_runs"] == 0
    assert guards["human_labels_changed"] is False
    assert guards["audio_downloads"] == 0


def test_output_is_deterministic(tmp_path: Path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_remaining_tail_diagnostic(
        CONFIG,
        tier2a_dir=TIER2A_DIR,
        source_neutral_dir=SOURCE_NEUTRAL_DIR,
        output_path=first,
    )
    write_remaining_tail_diagnostic(
        CONFIG,
        tier2a_dir=TIER2A_DIR,
        source_neutral_dir=SOURCE_NEUTRAL_DIR,
        output_path=second,
    )
    assert first.read_bytes() == second.read_bytes()
