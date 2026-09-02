from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5b1b_calibration_sol import (
    build_blinded_payload,
    load_calibration_sol_config,
    validate_sol_response,
    write_blinded_payload,
)


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "reports/stage5b1b/heldout_tracks.json"
DISCOVERY = ROOT / "reports/stage5b1b/heldout_ytdlp_discovery.json"
MANIFEST_SHA = "39557ede8f07bde129ad23d2bc64a0faf0fff755356cd87f2054e14f91d81e5a"
DISCOVERY_SHA = "2c318ac0853ffe3395c6a934265585afcb0a39a2f9ce73e5a00ba35276d056e4"
CONFIG = ROOT / "configs/stage5b1b_calibration_sol.json"


def payload_and_mapping(seed="fixture-seed"):
    return build_blinded_payload(
        manifest_path=MANIFEST,
        manifest_sha256=MANIFEST_SHA,
        discovery_path=DISCOVERY,
        discovery_sha256=DISCOVERY_SHA,
        shuffle_seed=seed,
        description_max_characters=1200,
    )


def response(rows):
    return {
        "schema_version": "stage5b1b-calibration-sol-batch-response-v1",
        "tracks": [
            {
                "stable_track_id": row["stable_track_id"],
                "selection_status": "SELECTED",
                "selected_candidate_key": row["candidates"][0]["candidate_key"],
                "selection_rationale": "raw metadata supports this clean source",
                "candidates": [
                    {
                        "candidate_key": candidate["candidate_key"],
                        "label": "IDEAL" if index == 0 else "WRONG",
                        "recording_identity_reason": "raw title/version evidence",
                        "source_quality_reason": "raw provenance evidence",
                        "uncertainty_reason": None,
                    }
                    for index, candidate in enumerate(row["candidates"])
                ],
            }
            for row in rows
        ],
    }


def test_committed_calibration_config_hash_locks_blind_inputs_and_model():
    config = load_calibration_sol_config(CONFIG)
    assert config.model == "gpt-5.6-sol"
    assert config.manifest_sha256 == MANIFEST_SHA
    assert config.discovery_sha256 == DISCOVERY_SHA
    assert config.human_review_sha256 == (
        "8e5282310ff44c9441e81a1cb538613f004b92361ec8b8c21172b4d40b69e97e"
    )
    assert config.payload_sha256 == (
        "dc7c90f24d26b1f50cdb8868f22e7b3c041f0f49ceab16a439162b4916bb063c"
    )


def test_blinded_payload_is_complete_deterministic_shuffled_and_feature_free():
    payload, mapping = payload_and_mapping()
    repeated, repeated_mapping = payload_and_mapping()
    changed, _ = payload_and_mapping("different-seed")
    assert payload == repeated
    assert mapping == repeated_mapping
    assert len(payload["tracks"]) == 50
    assert sum(len(row["candidates"]) for row in payload["tracks"]) == 248
    assert payload["candidate_order_is_search_rank"] is False
    assert payload["tracks"][0]["candidates"] != changed["tracks"][0]["candidates"]

    serialized = json.dumps(payload)
    for forbidden in (
        "candidate_review_label",
        "title_similarity",
        "version_relationships",
        "recording_eligible",
        "source_type",
        "case_tags",
        "case_rationale",
        "original_search_rank",
        "youtube_video_id",
        '"rank"',
        '"query"',
    ):
        assert forbidden not in serialized
    assert "original_search_rank" in json.dumps(mapping)
    assert "youtube_video_id" in json.dumps(mapping)


def test_private_mapping_is_written_separately_from_blinded_payload(tmp_path):
    payload, mapping = payload_and_mapping()
    payload_path = tmp_path / "payload.json"
    mapping_path = tmp_path / "mapping.json"
    write_blinded_payload(payload_path, mapping_path, payload, mapping)
    blind_text = payload_path.read_text(encoding="utf-8")
    private_text = mapping_path.read_text(encoding="utf-8")
    assert "youtube_video_id" not in blind_text
    assert "youtube_video_id" in private_text


def test_sol_response_validation_accepts_full_opaque_candidate_coverage():
    payload, _ = payload_and_mapping()
    rows = payload["tracks"][:2]
    assert validate_sol_response(response(rows), rows)["tracks"][0]["selection_status"] == "SELECTED"


def test_sol_response_validation_rejects_candidate_coverage_change():
    payload, _ = payload_and_mapping()
    rows = payload["tracks"][:1]
    result = response(rows)
    result["tracks"][0]["candidates"].pop()
    with pytest.raises(Stage5B1AValidationError, match="coverage/order"):
        validate_sol_response(result, rows)


def test_sol_response_validation_rejects_wrong_selected_candidate():
    payload, _ = payload_and_mapping()
    rows = payload["tracks"][:1]
    result = response(rows)
    result["tracks"][0]["candidates"][0]["label"] = "WRONG"
    with pytest.raises(Stage5B1AValidationError, match="safe-labeled"):
        validate_sol_response(result, rows)
