from __future__ import annotations

from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256
from audio_similarity.stage5b3_minimal_selector import (
    AUTO_SELECT,
    EXPECTED_PRIOR_HASHES,
    MATCH_UNCERTAIN,
    run_minimal_selector,
    select_native_rank,
    veto_reasons,
)


def _target(*, title: str = "Ordinary Song", duration: float = 180.0) -> dict:
    return {
        "spotify_track_id": "spotify",
        "title": title,
        "artists": ["Target Artist"],
        "album": "Album",
        "duration_ms": int(duration * 1000),
    }


def _candidate(rank: int, *, title: str = "Anything", duration: float | None = 180.0) -> dict:
    return {
        "rank": rank,
        "youtube_video_id": f"video{rank:06d}",
        "title": title,
        "duration_seconds": duration,
        "uploader": "Unknown uploader",
        "channel": "Unknown channel",
    }


def test_unrequested_live_or_stage_is_vetoed_but_requested_live_is_not() -> None:
    assert veto_reasons(_target(), _candidate(1, title="Song — Original Stage")) == [
        "UNREQUESTED_LIVE_OR_PERFORMANCE"
    ]
    assert veto_reasons(_target(), _candidate(1, title="Song live in concert")) == [
        "UNREQUESTED_LIVE_OR_PERFORMANCE"
    ]
    assert veto_reasons(
        _target(title="Song — Live at the Ryman"),
        _candidate(1, title="Song live in concert"),
    ) == []
    album_only = _target()
    album_only["album"] = "Live Today"
    assert veto_reasons(album_only, _candidate(1, title="Song live")) == [
        "UNREQUESTED_LIVE_OR_PERFORMANCE"
    ]


def test_duration_exactly_twenty_survives_and_greater_than_twenty_is_vetoed() -> None:
    assert veto_reasons(_target(duration=100), _candidate(1, duration=120)) == []
    assert veto_reasons(_target(duration=100), _candidate(1, duration=120.001)) == [
        "DURATION_ANOMALY_GT_20_SECONDS"
    ]
    assert veto_reasons(_target(duration=100), _candidate(1, duration=None)) == []


def test_native_rank_fallback_from_one_to_two() -> None:
    result = select_native_rank(_target(), [
        _candidate(1, title="Song live"),
        _candidate(2),
        _candidate(3),
    ])
    assert result["decision"] == AUTO_SELECT
    assert result["selected_rank"] == 2
    assert [row["native_rank"] for row in result["candidate_evaluations"]] == [1, 2]


def test_native_rank_fallback_from_two_to_three() -> None:
    result = select_native_rank(_target(), [
        _candidate(1, duration=300),
        _candidate(2, title="Concert performance"),
        _candidate(3),
    ])
    assert result["decision"] == AUTO_SELECT
    assert result["selected_rank"] == 3


def test_all_three_vetoes_return_match_uncertain() -> None:
    result = select_native_rank(_target(), [
        _candidate(1, duration=300),
        _candidate(2, title="Live"),
        _candidate(3, title="Stage"),
    ])
    assert result["decision"] == MATCH_UNCERTAIN
    assert result["selected_rank"] is None


def test_no_positive_proof_is_required() -> None:
    result = select_native_rank(_target(), [
        _candidate(1, title="Unrelated-looking metadata", duration=None),
        _candidate(2),
        _candidate(3),
    ])
    assert result["decision"] == AUTO_SELECT
    assert result["selected_rank"] == 1
    assert result["selection_reason"] == "FIRST_NATIVE_RANK_WITHOUT_V1_VETO"


def test_native_rank_order_is_required_and_preserved() -> None:
    result = select_native_rank(_target(), [_candidate(1), _candidate(2), _candidate(3)])
    assert result["selected_candidate"]["rank"] == 1
    with pytest.raises(Stage5B1AValidationError, match="preserved native ranks"):
        select_native_rank(_target(), [_candidate(2), _candidate(1)])


def test_frozen_stage5b2_replay_uses_no_existing_resolver(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    prior = root / "reports/stage5b_youtube_prior_v1"
    before = {name: file_sha256(prior / name) for name in EXPECTED_PRIOR_HASHES}
    result = run_minimal_selector(prior, tmp_path / "stage5b3")

    assert result["policy"]["existing_resolver_invocations"] == 0
    assert result["policy"]["positive_proof_requirements"] == []
    assert result["summary"]["auto_select_count"] == 99
    assert result["summary"]["match_uncertain_count"] == 1
    assert result["summary"]["selected_rank_distribution"] == {
        "rank_1": 88,
        "rank_2": 9,
        "rank_3": 2,
        "none": 1,
    }
    assert result["summary"]["safe_rank1_vetoed_count"] == 10
    assert before == {name: file_sha256(prior / name) for name in EXPECTED_PRIOR_HASHES}
