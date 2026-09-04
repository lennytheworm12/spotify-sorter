from __future__ import annotations

from audio_similarity.stage5c2_closeout import acquisition_and_rate_metrics


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
            },
            {
                "attempt_number": 1,
                "previous_request_start_delta_seconds": 20.25,
                "minimum_spacing_compliant": True,
                "retry_after_seconds": 30.0,
                "http_status": 429,
                "retry_reason": "PROVIDER_RATE_LIMITED",
                "final_outcome": "RETRY_SCHEDULED",
            },
            {
                "attempt_number": 2,
                "previous_request_start_delta_seconds": 30.0,
                "minimum_spacing_compliant": True,
                "retry_after_seconds": None,
                "http_status": None,
                "retry_reason": None,
                "final_outcome": "SUCCESS",
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
            },
            {
                "attempt_number": 1,
                "previous_request_start_delta_seconds": 19.999,
                "minimum_spacing_compliant": False,
                "retry_after_seconds": None,
                "http_status": None,
                "retry_reason": None,
                "final_outcome": "SUCCESS",
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
