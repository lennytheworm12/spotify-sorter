from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5b1b_artifacts import load_heldout_review
from audio_similarity.stage5b1b_config import load_stage5b1b_config
from audio_similarity.stage5b1b_experiment import READY_FOR_REVIEW, load_heldout_results
from audio_similarity.stage5b1b_manifest import load_heldout_manifest


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs" / "stage5b1b.json"


def inputs():
    config = load_stage5b1b_config(CONFIG)
    manifest = load_heldout_manifest(
        config.heldout_manifest_path, expected_sha256=config.heldout_manifest_sha256
    )
    return config, manifest


def test_committed_dev_dataset_is_complete_and_explicitly_not_held_out_proof():
    config, _ = inputs()
    features = json.loads(config.artifacts["dev_features"].read_text(encoding="utf-8"))
    diagnostics = json.loads(config.artifacts["dev_diagnostics"].read_text(encoding="utf-8"))
    assert features["dataset_role"] == "DEV_ONLY_NOT_HELD_OUT"
    assert (features["track_count"], features["candidate_pair_count"]) == (25, 125)
    assert diagnostics["dataset_role"] == "DEV_ONLY_NOT_HELD_OUT"
    assert diagnostics["selected_track_count"] == 25
    assert all("human_review_note_verbatim" in row for row in diagnostics["tracks"])


def test_committed_heldout_discovery_is_complete_metadata_only_and_hash_bound():
    config, manifest = inputs()
    results = load_heldout_results(config.artifacts["heldout_discovery"], manifest, config)
    assert results["status"] == READY_FOR_REVIEW
    assert results["summary"] == {
        "tracks": 50,
        "ytdlp_search_failures": 0,
        "tracks_with_zero_youtube_candidates": 0,
        "deduplicated_candidate_video_ids": 248,
        "tracks_with_warnings": 0,
        "warning_count": 0,
    }
    assert Counter(len(row["candidates"]) for row in results["tracks"]) == {5: 49, 3: 1}
    assert all(value == 0 for value in results["media_activity"].values())
    assert results["configuration"]["provider"]["metadata_only_options"]["simulate"] is True
    assert results["configuration"]["provider"]["metadata_only_options"]["skip_download"] is True


def test_committed_heldout_features_and_review_are_unlabeled_without_threshold():
    config, _ = inputs()
    features = json.loads(config.artifacts["heldout_features"].read_text(encoding="utf-8"))
    rows = load_heldout_review(config.artifacts["heldout_review"])
    status = json.loads(config.artifacts["run_status"].read_text(encoding="utf-8"))
    assert features["dataset_role"] == "HELD_OUT_UNLABELED"
    assert (features["track_count"], features["candidate_pair_count"]) == (50, 248)
    assert len(rows) == 248
    assert all(not row["candidate_review_label"] for row in rows)
    assert status["status"] == READY_FOR_REVIEW
    assert status["review_labels_completed"] == 0
    assert status["final_auto_match_threshold"] is None
    assert status["heldout_labels_required_before_calibration"] is True
    serialized = json.dumps(features)
    assert "auto_match_score" not in serialized
    assert "confidence_threshold" not in serialized
    for artifact in status["artifacts"].values():
        assert file_sha256(config.project_root / artifact["path"]) == artifact["sha256"]
