from __future__ import annotations

import csv

from audio_similarity.stage5c2_analysis import REVIEW_COLUMNS
from audio_similarity.stage5c2_closeout import (
    _human_review_metrics,
    acquisition_and_rate_metrics,
)


def test_rate_metrics_separate_attempts_retries_and_verify_spacing() -> None:
    attempts = {
        "exact_id_only": True,
        "discovery_requests": 0,
        "concurrent_downloads": 0,
        "attempts": [
            {
                "attempt_number": 1,
                "previous_request_start_delta_seconds": None,
                "minimum_spacing_compliant": True,
                "retry_after_seconds": None,
                "http_status": None,
                "retry_reason": None,
                "final_outcome": "SUCCESS",
                "acquisition_duration_seconds": 1.0,
            },
            {
                "attempt_number": 1,
                "previous_request_start_delta_seconds": 20.25,
                "minimum_spacing_compliant": True,
                "retry_after_seconds": 30.0,
                "http_status": 429,
                "retry_reason": "PROVIDER_RATE_LIMITED",
                "final_outcome": "RETRY_SCHEDULED",
                "acquisition_duration_seconds": 1.0,
            },
            {
                "attempt_number": 2,
                "previous_request_start_delta_seconds": 30.0,
                "minimum_spacing_compliant": True,
                "retry_after_seconds": None,
                "http_status": None,
                "retry_reason": None,
                "final_outcome": "SUCCESS",
                "acquisition_duration_seconds": 1.0,
            },
        ],
    }
    materialization = {
        "automated_selected_tracks": 2,
        "acquisitions": [
            {"provider_result": "SUCCESS", "network_attempt_count": 1},
            {"provider_result": "SUCCESS", "network_attempt_count": 2},
        ],
    }
    acquisition, rate = acquisition_and_rate_metrics(attempts, materialization)
    assert acquisition["acquisition_successes"] == 2
    assert acquisition["tracks_with_live_acquisition_attempts"] == 2
    assert rate["total_live_download_attempts"] == 3
    assert rate["retry_attempts"] == 1
    assert rate["minimum_start_to_start_spacing_seconds"] == 20.25
    assert rate["retry_after_events"] == 1
    assert rate["http_429_count"] == 1
    assert rate["passed"] is True


def test_rate_metric_fails_when_any_attempt_breaks_20_second_floor() -> None:
    attempts = {
        "exact_id_only": True,
        "discovery_requests": 0,
        "concurrent_downloads": 0,
        "attempts": [
            {
                "attempt_number": 1,
                "previous_request_start_delta_seconds": None,
                "minimum_spacing_compliant": True,
                "retry_after_seconds": None,
                "http_status": None,
                "retry_reason": None,
                "final_outcome": "SUCCESS",
                "acquisition_duration_seconds": 1.0,
            },
            {
                "attempt_number": 1,
                "previous_request_start_delta_seconds": 19.999,
                "minimum_spacing_compliant": False,
                "retry_after_seconds": None,
                "http_status": None,
                "retry_reason": None,
                "final_outcome": "SUCCESS",
                "acquisition_duration_seconds": 1.0,
            },
        ],
    }
    materialization = {
        "automated_selected_tracks": 2,
        "acquisitions": [
            {"provider_result": "SUCCESS", "network_attempt_count": 1},
            {"provider_result": "SUCCESS", "network_attempt_count": 1},
        ],
    }
    _, rate = acquisition_and_rate_metrics(attempts, materialization)
    assert rate["passed"] is False


def test_human_metrics_remain_pending_and_unsure_is_never_numeric_zero(tmp_path) -> None:
    path = tmp_path / "review.csv"
    rows = [
        {
            "review_schema_version": "stage5c2-human-similarity-review-v1",
            "pair_id": "pair-a",
            "query_spotify_id": "a",
            "neighbor_spotify_id": "b",
            "neighbor_rank": "1",
            "clap_similarity": "0.8",
            "muq_similarity": "0.7",
            "combined_similarity": "0.77",
            "human_label": "",
            "human_note": "",
            "review_timestamp": "",
        },
        {
            "review_schema_version": "stage5c2-human-similarity-review-v1",
            "pair_id": "pair-b",
            "query_spotify_id": "a",
            "neighbor_spotify_id": "c",
            "neighbor_rank": "2",
            "clap_similarity": "0.6",
            "muq_similarity": "0.5",
            "combined_similarity": "0.57",
            "human_label": "UNSURE",
            "human_note": "cannot judge",
            "review_timestamp": "test",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    pending = _human_review_metrics(path)
    assert pending["status"] == "HUMAN_REVIEW_PENDING"
    assert pending["quality_metrics"] is None
    rows[0]["human_label"] = "3"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    complete = _human_review_metrics(path)
    assert complete["status"] == "HUMAN_REVIEW_COMPLETE"
    assert complete["quality_metrics"]["numeric_directional_judgment_count"] == 1
    assert complete["quality_metrics"]["unsure_directional_judgment_count"] == 1
    assert complete["quality_metrics"]["mean_human_rating_top5"] == 3.0
