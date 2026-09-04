from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256
from audio_similarity.stage5d0a_control import (
    PersistentCircuitBreaker,
    TrackJobLimiter,
    TrackJobPacingPolicy,
    initial_runtime_state,
    persist_runtime_state,
    request_graceful_stop,
    request_resume,
    run_batch_one,
    runtime_status,
)
from audio_similarity.stage5d0a_manifest import (
    MAX_BATCH_SIZE,
    build_batch_manifest,
    build_global_manifest,
    freeze_catalog_and_batch_one,
)


def catalog(count: int = 1_025) -> dict:
    return {
        "schema_version": "stage5d0a-commercial-seed-catalog-input-v1",
        "catalog_design": {
            "design_id": "TEST_COMMERCIAL_CATALOG_V1",
            "source_policy": "fixture",
        },
        "tracks": [
            {
                "spotify_track_id": f"{index:022d}",
                "title": f"Song {index}",
                "artists": [f"Artist {index % 31}"],
                "album": f"Album {index % 101}",
                "duration_ms": 180_000 + index,
                "release_year": 2000 + index % 27,
                "isrc": None,
                "source_memberships": [f"YEAR:{2000 + index % 27}"],
            }
            for index in range(count)
        ],
    }


def manifest(count: int = 1_025) -> dict:
    return build_global_manifest(catalog(count), catalog_input_sha256="a" * 64)


def test_global_manifest_and_batch_partition_are_deterministic() -> None:
    first = manifest()
    second = manifest()
    assert first == second
    assert first["unique_track_count"] == 1_025
    assert first["batch_count"] == 3
    batches = [build_batch_manifest(first, number) for number in (1, 2, 3)]
    assert [len(row["tracks"]) for row in batches] == [500, 500, 25]
    assigned = [
        track["spotify_track_id"]
        for batch in batches
        for track in batch["tracks"]
    ]
    assert len(assigned) == len(set(assigned)) == 1_025
    assert batches[0]["automatic_next_batch"] is False


def test_seeded_order_is_not_input_or_alphabetical_order() -> None:
    value = manifest(600)
    ids = [row["spotify_track_id"] for row in value["tracks"]]
    assert ids != sorted(ids)
    assert ids != [f"{index:022d}" for index in range(600)]


def test_spotify_id_deduplication_merges_source_memberships() -> None:
    source = catalog(2)
    duplicate = dict(source["tracks"][0])
    duplicate["source_memberships"] = ["ANOTHER_SOURCE"]
    source["tracks"].append(duplicate)
    value = build_global_manifest(source, catalog_input_sha256="b" * 64)
    row = next(
        item
        for item in value["tracks"]
        if item["spotify_track_id"] == duplicate["spotify_track_id"]
    )
    assert value["spotify_id_duplicate_count"] == 1
    assert row["source_memberships"] == ["ANOTHER_SOURCE", "YEAR:2000"]


def test_catalog_requires_explicit_design_and_2000_2026_bounds() -> None:
    missing = catalog()
    del missing["catalog_design"]
    with pytest.raises(Stage5B1AValidationError, match="design"):
        build_global_manifest(missing, catalog_input_sha256="c" * 64)
    invalid_year = catalog()
    invalid_year["tracks"][0]["release_year"] = 1999
    with pytest.raises(Stage5B1AValidationError, match="outside"):
        build_global_manifest(invalid_year, catalog_input_sha256="d" * 64)


def test_freeze_writes_only_global_and_batch_one_manifests(tmp_path: Path) -> None:
    source = tmp_path / "catalog.json"
    source.write_text(json.dumps(catalog()), encoding="utf-8")
    report = tmp_path / "report"
    global_manifest, batch = freeze_catalog_and_batch_one(source, report)
    assert len(batch["tracks"]) == MAX_BATCH_SIZE
    assert file_sha256(report / "global_seed_catalog_manifest.json") == (
        report / "global_seed_catalog_manifest.sha256"
    ).read_text(encoding="utf-8").strip()
    assert global_manifest["catalog_input_sha256"] == file_sha256(source)
    assert not list(report.glob("batch_000[2-9]_manifest.json"))
    freeze_catalog_and_batch_one(source, report)
    changed = json.loads(source.read_text(encoding="utf-8"))
    changed["tracks"][0]["title"] = "Changed"
    source.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(Stage5B1AValidationError, match="refusing"):
        freeze_catalog_and_batch_one(source, report)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_track_job_pacing_is_randomized_serial_and_bounded() -> None:
    clock = Clock()
    limiter = TrackJobLimiter(monotonic=clock.monotonic, sleep=clock.sleep)
    rows = [limiter.wait_and_start(str(index)) for index in range(20)]
    deltas = [row["previous_start_delta_seconds"] for row in rows[1:]]
    assert all(30 <= value <= 60 for value in deltas)
    assert len({round(value, 6) for value in deltas}) > 1
    assert all(row["spacing_compliant"] for row in rows)


def test_retry_after_or_backoff_can_extend_track_spacing_past_sixty() -> None:
    clock = Clock()
    limiter = TrackJobLimiter(monotonic=clock.monotonic, sleep=clock.sleep)
    limiter.wait_and_start("first")
    row = limiter.wait_and_start("retry", required_backoff_seconds=121.0)
    assert row["previous_start_delta_seconds"] == 121.0
    assert row["spacing_compliant"] is True


def test_pacing_policy_rejects_unsafe_or_unbounded_ordinary_delays() -> None:
    with pytest.raises(ValueError, match="below 30"):
        TrackJobPacingPolicy(minimum_seconds=29)
    with pytest.raises(ValueError, match="exceed 60"):
        TrackJobPacingPolicy(maximum_seconds=61)


def test_second_429_opens_persistent_circuit() -> None:
    breaker = PersistentCircuitBreaker(first_429_cooldown_seconds=900)
    first = breaker.record("one", "PROVIDER_RATE_LIMITED")
    assert first == {"circuit_status": "CLOSED", "cooldown_seconds": 900.0}
    second = breaker.record("two", "PROVIDER_RATE_LIMITED")
    assert second["circuit_status"] == "OPEN"
    assert breaker.state["opened_reason"] == "SECOND_HTTP_429_AFTER_COOLDOWN"


def test_repeated_challenges_open_circuit_but_content_failure_does_not() -> None:
    breaker = PersistentCircuitBreaker()
    breaker.record("removed", "MEDIA_UNAVAILABLE")
    assert breaker.state["status"] == "CLOSED"
    breaker.record("one", "LOGIN_REQUIRED")
    assert breaker.state["status"] == "CLOSED"
    breaker.record("two", "CAPTCHA_CHALLENGE")
    assert breaker.state["status"] == "OPEN"
    assert breaker.state["opened_reason"] == "REPEATED_VERIFICATION_OR_CHALLENGE"


def test_runtime_state_is_batch_one_only_resumable_and_stoppable(tmp_path: Path) -> None:
    batch = build_batch_manifest(manifest(17), 1)
    state = initial_runtime_state(batch)
    state["tracks"][batch["tracks"][0]["spotify_track_id"]]["state"] = "COMPLETE"
    path = tmp_path / "state.json"
    persist_runtime_state(path, state)
    stopped = request_graceful_stop(path)
    status = runtime_status(stopped)
    assert status["batch"] == "0001"
    assert status["stop_requested"] is True
    assert status["terminal_count"] == 1
    assert status["total_count"] == 17
    resumed = request_resume(path)
    assert resumed["stop_requested"] is False
    later = build_batch_manifest(manifest(501), 2)
    with pytest.raises(Stage5B1AValidationError, match="only Batch 0001"):
        initial_runtime_state(later)


class Processor:
    def __init__(self, conditions: dict[str, str], outcomes: dict[str, dict]) -> None:
        self.conditions = conditions
        self.outcomes = outcomes
        self.processed: list[str] = []

    def inspect(self, track: dict) -> str:
        return self.conditions[track["spotify_track_id"]]

    def process(self, track: dict, _condition: str) -> dict:
        spotify_id = track["spotify_track_id"]
        self.processed.append(spotify_id)
        return self.outcomes.get(spotify_id, {"state": "COMPLETE"})


def test_batch_runner_skips_complete_tracks_and_never_starts_batch_two(
    tmp_path: Path,
) -> None:
    batch = build_batch_manifest(manifest(4), 1)
    state = initial_runtime_state(batch)
    first_id = batch["tracks"][0]["spotify_track_id"]
    state["tracks"][first_id]["state"] = "COMPLETE"
    path = tmp_path / "state.json"
    persist_runtime_state(path, state)
    conditions = {
        row["spotify_track_id"]: "SOURCE_AND_REPRESENTATION_PRESENT"
        for row in batch["tracks"]
    }
    processor = Processor(conditions, {})
    status = run_batch_one(batch, path, processor)
    assert status["worker_status"] == "COMPLETE"
    assert first_id not in processor.processed
    assert len(processor.processed) == 3

    batch_two = build_batch_manifest(manifest(501), 2)
    with pytest.raises(Stage5B1AValidationError, match="only Batch 0001"):
        run_batch_one(batch_two, path, processor)


def test_manual_tail_continues_and_network_jobs_are_serially_paced(
    tmp_path: Path,
) -> None:
    batch = build_batch_manifest(manifest(3), 1)
    state = initial_runtime_state(batch)
    path = tmp_path / "state.json"
    persist_runtime_state(path, state)
    ids = [row["spotify_track_id"] for row in batch["tracks"]]
    processor = Processor(
        {spotify_id: "BOTH_MISSING" for spotify_id in ids},
        {ids[0]: {"state": "MANUAL_TAIL"}},
    )
    clock = Clock()
    limiter = TrackJobLimiter(monotonic=clock.monotonic, sleep=clock.sleep)
    status = run_batch_one(batch, path, processor, limiter=limiter)
    assert status["track_state_counts"]["MANUAL_TAIL"] == 1
    assert status["track_state_counts"]["COMPLETE"] == 2
    assert len(limiter.starts) == 3
    assert all(
        row["previous_start_delta_seconds"] >= 30 for row in limiter.starts[1:]
    )


def test_runner_persists_second_429_circuit_and_stops_new_jobs(tmp_path: Path) -> None:
    batch = build_batch_manifest(manifest(4), 1)
    path = tmp_path / "state.json"
    persist_runtime_state(path, initial_runtime_state(batch))
    ids = [row["spotify_track_id"] for row in batch["tracks"]]
    processor = Processor(
        {spotify_id: "BOTH_MISSING" for spotify_id in ids},
        {
            ids[0]: {
                "state": "ACQUISITION_FAILED",
                "provider_signal": "PROVIDER_RATE_LIMITED",
            },
            ids[1]: {
                "state": "ACQUISITION_FAILED",
                "provider_signal": "PROVIDER_RATE_LIMITED",
            },
        },
    )
    clock = Clock()
    limiter = TrackJobLimiter(monotonic=clock.monotonic, sleep=clock.sleep)
    status = run_batch_one(batch, path, processor, limiter=limiter)
    assert status["worker_status"] == "CIRCUIT_OPEN"
    assert processor.processed == ids[:2]
    assert clock.sleeps[-1] == 900.0
    assert status["circuit"]["http_429_count"] == 2
    assert status["track_state_counts"]["PENDING"] == 2
