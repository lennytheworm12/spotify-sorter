import csv
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_config import load_config
from audio_similarity.stage5b1a_models import Stage5B1AValidationError, load_frozen_manifest
from audio_similarity.stage5b1a_review import (
    NOT_IN_TOP_5,
    REVIEW_COLUMNS,
    UNCERTAIN,
    ReviewLabel,
    classify_gate,
    compute_metrics,
    load_review_labels,
    review_rows,
    write_review_csv,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1a_firecrawl.json"


def config_manifest():
    config = load_config(CONFIG)
    return config, load_frozen_manifest(
        config.manifest_path,
        expected_sha256=config.manifest_sha256,
    )


def result_row(stable_id, candidates=5, error=None):
    return {
        "track": {"stable_track_id": stable_id},
        "query": f"query for {stable_id}",
        "candidates": [
            {
                "rank": rank,
                "url": f"https://www.youtube.com/watch?v=video{rank:06d}",
                "youtube_video_id": f"video{rank:06d}",
                "title": f"candidate {rank}",
                "description": f"description {rank}",
            }
            for rank in range(1, candidates + 1)
        ],
        "error": error,
    }


def metrics_results(specs):
    return {
        "experiment_id": "stage5b1a_firecrawl_youtube_discovery_feasibility",
        "tracks": [result_row(stable_id, candidates, error) for stable_id, candidates, error in specs],
    }


def test_review_template_contains_all_tracks_candidate_slots_and_label_fields(tmp_path):
    _, manifest = config_manifest()
    output = tmp_path / "review.csv"
    write_review_csv(output, manifest)
    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 25
    assert list(rows[0]) == REVIEW_COLUMNS
    assert rows[0]["expected_title"] == "Hello"
    assert rows[0]["candidate_1_url"] == ""
    assert rows[0]["candidate_5_description"] == ""
    assert rows[0]["review_label"] == ""
    assert rows[0]["optional_note"] == ""


def test_review_rows_place_ordered_candidates_without_automatic_labels():
    _, manifest = config_manifest()
    results = {
        "tracks": [result_row(stable_id, 5) for stable_id in manifest.stable_track_ids]
    }
    rows = review_rows(manifest, results)
    assert rows[0]["candidate_1_video_id"] == "video000001"
    assert rows[0]["candidate_5_video_id"] == "video000005"
    assert rows[0]["review_label"] == ""


def test_review_label_parser_normalizes_alias_and_rejects_invalid_rank(tmp_path):
    _, manifest = config_manifest()
    output = tmp_path / "review.csv"
    write_review_csv(output, manifest)
    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["review_label"] = "not_in_top_k"
    rows[1]["review_label"] = "uncertain"
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    labels = load_review_labels(output, candidate_counts={stable_id: 5 for stable_id in manifest.stable_track_ids})
    assert labels[0].label == NOT_IN_TOP_5
    assert labels[1].label == UNCERTAIN

    rows[0]["review_label"] = "5"
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(Stage5B1AValidationError, match="exceeds candidates"):
        load_review_labels(output, candidate_counts={stable_id: 4 for stable_id in manifest.stable_track_ids})


def test_recall_at_1_3_5_uncertain_denominator_and_operational_counts():
    config, _ = config_manifest()
    results = metrics_results(
        [
            ("one", 5, None),
            ("two", 5, None),
            ("three", 5, None),
            ("four", 0, None),
            ("five", 0, {"category": "FIRECRAWL_HTTP_503"}),
        ]
    )
    labels = (
        ReviewLabel("one", "1", ""),
        ReviewLabel("two", "3", ""),
        ReviewLabel("three", "5", ""),
        ReviewLabel("four", NOT_IN_TOP_5, ""),
        ReviewLabel("five", UNCERTAIN, "provider failed"),
    )
    metrics = compute_metrics(results, labels, config.gate)
    assert metrics["review"] == {
        "total_tracks": 5,
        "reviewed_tracks": 5,
        "evaluable_tracks": 4,
        "unreviewed_tracks": 0,
        "uncertain_tracks": 1,
        "not_in_top_5_tracks": 1,
        "denominator_semantics": "Confirmed ranks plus NOT_IN_TOP_5; UNCERTAIN and unreviewed tracks are excluded.",
    }
    assert metrics["recall_at_1"] == {"numerator": 1, "denominator": 4, "value": 0.25}
    assert metrics["recall_at_3"] == {"numerator": 2, "denominator": 4, "value": 0.5}
    assert metrics["recall_at_5"] == {"numerator": 3, "denominator": 4, "value": 0.75}
    assert metrics["firecrawl_request_failure_count"] == 1
    assert metrics["tracks_with_zero_youtube_candidates"] == 2
    assert metrics["feasibility_verdict"] == "FAIL"


def test_unreviewed_tracks_hold_verdict_pending_without_entering_denominator():
    config, _ = config_manifest()
    results = metrics_results([("one", 5, None), ("two", 5, None)])
    metrics = compute_metrics(
        results,
        (ReviewLabel("one", "1", ""), ReviewLabel("two", "", "")),
        config.gate,
    )
    assert metrics["review"]["evaluable_tracks"] == 1
    assert metrics["review"]["unreviewed_tracks"] == 1
    assert metrics["recall_at_5"]["value"] == 1.0
    assert metrics["feasibility_verdict"] == "PENDING_HUMAN_REVIEW"


@pytest.mark.parametrize(
    ("recall", "expected"),
    [(1.0, "PASS"), (0.9, "PASS"), (0.899, "CONDITIONAL"), (0.8, "CONDITIONAL"), (0.799, "FAIL"), (0.0, "FAIL")],
)
def test_frozen_gate_classification(recall, expected):
    config, _ = config_manifest()
    assert classify_gate(recall, config.gate) == expected
