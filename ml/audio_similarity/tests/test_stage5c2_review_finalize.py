from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5c2_analysis import REVIEW_COLUMNS, canonical_pair_id
from audio_similarity.stage5c2_review_finalize import finalize_review, validate_completed_review


def fixture():
    pair = canonical_pair_id("a", "b")
    neighbor = {"spotify_track_id": "b", "rank": 1, "pair_id": pair,
                "clap_similarity": 0.7, "muq_similarity": 0.6, "combined_similarity": 0.67}
    queue = {"schema_version": "stage5c2-similarity-review-queue-v1",
             "raw_top5_judgment_count": 1, "unique_unordered_pair_count": 1,
             "cases": [{"spotify_track_id": "a", "neighbors": [neighbor]}]}
    row = {"review_schema_version": "stage5c2-human-similarity-review-v2",
           "pair_id": pair, "query_spotify_id": "a", "neighbor_spotify_id": "b",
           "neighbor_rank": "1", "clap_similarity": "0.700000000",
           "muq_similarity": "0.600000000", "combined_similarity": "0.670000000",
           "human_label": "4", "human_note": "", "review_timestamp": "2026-01-01T00:00:00+00:00"}
    return queue, row


def test_complete_review_must_exactly_match_frozen_queue():
    queue, row = fixture()
    assert validate_completed_review(queue, [row]) == {"directional_rows": 1, "unique_unordered_pairs": 1}
    for field, value in (("human_label", ""), ("neighbor_rank", "2"), ("combined_similarity", "0.68")):
        changed = row | {field: value}
        with pytest.raises(Stage5B1AValidationError):
            validate_completed_review(queue, [changed])


def test_unknown_extra_or_duplicate_relationship_rejected():
    queue, row = fixture()
    with pytest.raises(Stage5B1AValidationError):
        validate_completed_review(queue, [row, row])
    with pytest.raises(Stage5B1AValidationError):
        validate_completed_review(queue, [row | {"neighbor_spotify_id": "c"}])


def test_reciprocal_pair_evidence_must_agree():
    queue, row = fixture()
    reciprocal = row | {"query_spotify_id": "b", "neighbor_spotify_id": "a", "neighbor_rank": "1"}
    queue["cases"].append({"spotify_track_id": "b", "neighbors": [{
        "spotify_track_id": "a", "rank": 1, "pair_id": row["pair_id"],
        "clap_similarity": 0.7, "muq_similarity": 0.6, "combined_similarity": 0.67}]})
    queue["raw_top5_judgment_count"] = 2
    assert validate_completed_review(queue, [row, reciprocal])["unique_unordered_pairs"] == 1
    with pytest.raises(Stage5B1AValidationError, match="reciprocal"):
        validate_completed_review(queue, [row, reciprocal | {"human_label": "3"}])


def test_finalize_review_writes_complete_artifacts_when_correlation_unavailable(tmp_path: Path):
    queue, row = fixture()
    report = tmp_path / "reports/stage5c2_representative_100_amended_v2"
    report.mkdir(parents=True)
    (report / "review_queue.json").write_text(json.dumps(queue), encoding="utf-8")
    with (report / "human_similarity_review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerow(row)

    metrics = finalize_review(tmp_path)

    assert metrics["status"] == "HUMAN_REVIEW_COMPLETE"
    assert metrics["quality_metrics"]["combined_correlation"] is None
    assert "combined **unavailable**" in (
        report / "human_similarity_review_report.md"
    ).read_text(encoding="utf-8")
    assert (report / "human_similarity_review_manifest.json").is_file()


def test_completed_review_rejects_invalid_timestamp_and_oversized_note():
    queue, row = fixture()
    with pytest.raises(Stage5B1AValidationError, match="timestamp"):
        validate_completed_review(queue, [row | {"review_timestamp": "not-a-time"}])
    with pytest.raises(Stage5B1AValidationError, match="note"):
        validate_completed_review(queue, [row | {"human_note": "x" * 2_001}])
