from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5b1f_diagnostic import (
    METADATA_INSUFFICIENT,
    TRUE_DISCOVERY_FAILURE,
    build_diagnostic,
    load_stage5b1f_config,
    replay_frozen_q0,
    verify_frozen_inputs,
    write_artifacts,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1f_resolver_false_rejection.json"


@pytest.fixture(scope="module")
def diagnostic():
    return build_diagnostic(load_stage5b1f_config(CONFIG))


def test_frozen_inputs_verify_and_q0_replays_exactly_without_mutation():
    config = load_stage5b1f_config(CONFIG)
    before = {
        name: file_sha256(config.project_root / row["path"])
        for name, row in config.frozen_inputs.items()
    }
    assert set(verify_frozen_inputs(config)) == set(config.frozen_inputs)
    replays = replay_frozen_q0(config)
    assert len(replays) == 50
    assert sum(
        row["replay"]["final_decision"]["status"] == "AUTO_MATCH"
        for row in replays
    ) == 42
    assert sum(
        row["replay"]["final_decision"]["status"] == "MATCH_UNCERTAIN"
        for row in replays
    ) == 8
    after = {
        name: file_sha256(config.project_root / row["path"])
        for name, row in config.frozen_inputs.items()
    }
    assert after == before


def test_safe_definition_false_rejection_and_preference_pairing(diagnostic):
    false_rejections, pairs, _tail = diagnostic
    assert false_rejections["definitions"]["SAFE"] == ["IDEAL", "ACCEPTABLE"]
    summary = false_rejections["summary"]
    assert summary["tracks_with_known_human_safe_q0_candidate"] == 40
    assert summary["tracks_selecting_known_human_safe_q0_candidate"] == 38
    assert summary["strict_false_rejection_count"] == 0
    assert summary["confirmed_human_label_downgrade_count"] == 4
    assert summary["selected_candidate_human_evidence_gap_count"] == 1
    assert [row["stable_track_id"] for row in pairs["comparisons"]] == [
        "s5b1c_004",
        "s5b1c_024",
        "s5b1c_035",
        "s5b1c_044",
        "s5b1c_049",
    ]


def test_gate_extraction_and_candidate_pair_details_are_deterministic(diagnostic):
    _false_rejections, pairs, _tail = diagnostic
    by_id = {row["stable_track_id"]: row for row in pairs["comparisons"]}
    kill_bill = by_id["s5b1c_004"]
    assert kill_bill["primary_cause"] == (
        "DURATION_PRECEDES_PROVENANCE_AND_SOURCE_IN_ORDERING"
    )
    assert kill_bill["resolver_selected_candidate"]["human_evidence"]["label"] == (
        "ACCEPTABLE"
    )
    assert kill_bill["best_known_human_safe_candidate"]["human_evidence"]["label"] == (
        "IDEAL"
    )
    makeba = by_id["s5b1c_024"]
    assert makeba["primary_cause"] == (
        "FALLBACK_ONLY_CASCADE_PREVENTS_CROSS_TIER_RERANK"
    )
    assert makeba["best_known_human_safe_candidate"]["gates"][
        "earliest_eligible_stage"
    ] == "STAGE5B1C_B"
    shinunoga = by_id["s5b1c_049"]
    assert shinunoga["primary_cause"] == (
        "OFFICIAL_MUSIC_VIDEO_DURATION_RESTRICTION"
    )
    assert "SOURCE_CLASSIFICATION_PRESENTATION_ERROR" in shinunoga[
        "all_cause_categories"
    ]


def test_remaining_tail_separates_metadata_limits_from_discovery_failure(diagnostic):
    _false_rejections, _pairs, tail = diagnostic
    summary = tail["summary"]
    assert summary["unresolved_track_count"] == 8
    assert summary["classification_counts"] == {
        METADATA_INSUFFICIENT: 3,
        TRUE_DISCOVERY_FAILURE: 5,
    }
    assert summary["strong_resolver_recovery_count"] == 0
    assert summary["possible_resolver_recovery_count"] == 0
    assert summary["hypothetical_strong_only_ceiling"] == {
        "auto_match": 42,
        "total": 50,
        "rate": 0.84,
    }
    assert tail["resolver_only_path_to_90_percent_visible"] is False
    by_id = {row["stable_track_id"]: row for row in tail["tracks"]}
    assert by_id["s5b1c_021"]["candidate_count"] == 0
    assert by_id["s5b1c_032"]["candidate_count"] == 0
    assert by_id["s5b1c_034"]["candidate_count"] == 0
    assert by_id["s5b1c_041"]["strongest_plausible_candidate"]["sol_evidence"][
        "label"
    ] == "UNCERTAIN"


def test_artifact_generation_is_deterministic_and_hashable(tmp_path):
    config = load_stage5b1f_config(CONFIG)
    artifacts = {
        name: tmp_path / path.name for name, path in config.artifacts.items()
    }
    temp = replace(config, artifacts=artifacts)
    first = write_artifacts(temp)
    first_bytes = {
        name: path.read_bytes() for name, path in artifacts.items()
    }
    second = write_artifacts(temp)
    assert second == first
    assert {name: path.read_bytes() for name, path in artifacts.items()} == first_bytes
    manifest = json.loads(artifacts["manifest"].read_text())
    assert manifest["scope_guards"]["resolver_changed"] is False
    assert manifest["scope_guards"]["yt_dlp_searches"] == 0

