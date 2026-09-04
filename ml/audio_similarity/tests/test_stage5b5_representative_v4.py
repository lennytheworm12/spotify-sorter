from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from audio_similarity.stage5b1a2_config import YtDlpProviderConfig
from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256
from audio_similarity.stage5b4c_artist_decomposition import QUERY_CONTRACT_ID
from audio_similarity.stage5b5_representative_v4 import (
    BENCHMARK_ID,
    SAMPLE_SIZE,
    Stage5B5Config,
    freeze_v4_manifest,
    historical_json_paths,
    historical_review_paths,
    load_v4_config,
    run_frozen_selector,
    run_v4_discovery,
)
from audio_similarity.stage5b5_review import (
    ARTIFACT_NAMES,
    REVIEW_COLUMNS,
    Stage5B5ReviewStore,
    compute_final_metrics,
    next_review_requirement,
    validate_complete_review,
    write_human_review_artifacts,
)


def _track_row(index: int, *, artists: list[str] | None = None) -> dict:
    return {
        "benchmark_id": f"stage5b5_representative_v4_{index:03d}",
        "spotify_track_id": f"{index:022d}",
        "title": f"Fresh Song {index}",
        "artists": artists or [f"Artist {index}", f"Guest {index}"],
        "album": f"Album {index}",
        "duration_ms": 180_000,
        "release_year": 2026,
        "isrc": f"USABC26{index:05d}",
        "sample_seed": "test",
        "library_source_keys": ["LIKED"],
    }


def _manifest(count: int = 3) -> dict:
    return {
        "schema_version": "stage5b5-representative-v4-manifest-v1",
        "benchmark_id": BENCHMARK_ID,
        "sampled_track_count": count,
        "post_freeze_substitutions": 0,
        "tracks": [_track_row(index) for index in range(1, count + 1)],
    }


def _config(tmp_path: Path) -> Stage5B5Config:
    manifest_path = tmp_path / "benchmark_manifest.json"
    manifest_path.write_text(json.dumps(_manifest()))
    source = tmp_path / "source.py"
    source.write_text("# frozen\n")
    return Stage5B5Config(
        path=tmp_path / "benchmark_config.json",
        project_root=tmp_path,
        output_dir=tmp_path,
        manifest_path=manifest_path,
        manifest_sha256=file_sha256(manifest_path),
        provider=YtDlpProviderConfig(
            candidate_limit=3,
            search_prefix="ytsearch3:",
            extract_flat="in_playlist",
            skip_download=True,
            simulate=True,
            ignore_user_config=True,
            cache_enabled=False,
            socket_timeout_seconds=30,
            max_attempts=1,
            retry_backoff_seconds=0,
            sleep_between_tracks_seconds=0,
        ),
        query_source_path=source,
        query_source_sha256=file_sha256(source),
        decomposition_source_path=source,
        decomposition_source_sha256=file_sha256(source),
        selector_source_path=source,
        selector_source_sha256=file_sha256(source),
        sample_size=3,
        sha256="test-config",
    )


def _candidate(number: int, rank: int, query: str) -> dict:
    video_id = f"v{number:07d}{rank:03d}"
    return {
        "rank": rank,
        "provider_rank": rank,
        "youtube_video_id": video_id,
        "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
        "title": f"Fresh Song {number}",
        "uploader": f"Artist {number} - Topic",
        "channel": f"Artist {number} - Topic",
        "duration_seconds": 180.0,
        "view_count": 100,
        "description": "Provided to YouTube",
        "query": query,
    }


class _Provider:
    def __init__(self):
        self.calls: list[str] = []

    def discover_query(self, track, query, *, limit):
        self.calls.append(query)
        number = int(track.stable_track_id.rsplit("_", 1)[1])
        primary = f"Fresh Song {number} Artist {number} Guest {number}"
        q1 = f"Fresh Song {number} Artist {number}"
        candidates = []
        if number == 1 and query == q1:
            candidates = [_candidate(number, rank, query) for rank in (1, 2, 3)]
        elif number != 1 and query == primary:
            candidates = [_candidate(number, rank, query) for rank in (1, 2, 3)]
        return {
            "track": track.to_dict(),
            "query": query,
            "candidates": candidates,
            "warnings": [],
            "error": None,
        }


def _library_item(index: int) -> dict:
    return {
        "id": f"{index:022d}",
        "name": f"Fresh Song {index}",
        "artists": [{"name": f"Artist {index}"}],
        "album": {"name": f"Album {index}", "release_date": "2026-01-01"},
        "duration_ms": 180_000,
        "external_ids": {"isrc": f"USABC26{index:05d}"},
        "is_local": False,
    }


def test_fresh_manifest_excludes_every_prior_json_and_review_source(
    tmp_path, monkeypatch
) -> None:
    project = tmp_path
    prior = _library_item(1)
    for path in historical_json_paths(project):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "tracks": [
                        {
                            "spotify_track_id": prior["id"],
                            "title": prior["name"],
                            "artists": ["Artist 1"],
                        }
                    ]
                }
            )
        )
    for path in historical_review_paths(project):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"spotify_track_id\n{prior['id']}\n")
    snapshot = project / "library.private.json"
    snapshot.write_text(
        json.dumps(
            {
                "schema_version": "stage5b-owner-library-snapshot-v1",
                "sources": [
                    {
                        "source_key": "LIKED",
                        "tracks": [_library_item(index) for index in range(1, 111)],
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(
        "audio_similarity.stage5b5_representative_v4._frozen_contracts",
        lambda _root: {"discovery": {"contract_id": QUERY_CONTRACT_ID}},
    )
    result = freeze_v4_manifest(project, snapshot, project / "reports/v4")
    assert result["manifest"]["sampled_track_count"] == 100
    assert prior["id"] not in {
        row["spotify_track_id"] for row in result["manifest"]["tracks"]
    }
    assert result["manifest"]["freshness_scope"] == (
        "NEVER_USED_IN_V1_V2_V3_OR_STAGE5B4A_C"
    )
    assert result["manifest"]["prior_review_exclusion_audit"][
        "uncovered_reviewed_spotify_track_count"
    ] == 0


def test_discovery_runs_decomposition_only_after_zero_and_preserves_pool(tmp_path) -> None:
    config = _config(tmp_path)
    provider = _Provider()
    discovery = run_v4_discovery(config, provider, sleep=lambda _seconds: None)
    summary = discovery["summary"]
    assert summary["primary_success_count"] == 2
    assert summary["fallback_trigger_count"] == 1
    assert summary["fallback_success_count"] == 1
    assert summary["tracks_with_candidates"] == 3
    assert summary["provider_request_count"] == 4
    assert provider.calls[:3] == [
        "Fresh Song 1 Artist 1 Guest 1",
        "Fresh Song 1 Artist 1",
        "Fresh Song 2 Artist 2 Guest 2",
    ]
    recovered = discovery["tracks"][0]["discovery"]
    assert recovered["successful_query"] == "Fresh Song 1 Artist 1"
    assert [candidate["rank"] for candidate in recovered["candidates"]] == [1, 2, 3]
    assert discovery["scope_guards"]["candidate_pool_merges"] == 0
    assert discovery["scope_guards"]["audio_downloads"] == 0


def test_selector_is_frozen_before_review_and_reads_no_human_labels(tmp_path) -> None:
    config = _config(tmp_path)
    run_v4_discovery(config, _Provider(), sleep=lambda _seconds: None)
    decisions, metrics = run_frozen_selector(config)
    assert decisions["human_labels_visible"] is False
    assert decisions["scope_guards"]["human_labels_read"] == 0
    assert decisions["selector"]["modified_for_v4"] is False
    assert metrics["auto_select_count"] == 3
    assert metrics["human_outcomes"] is None


def test_review_queue_and_session_do_not_expose_selector_outputs(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("audio_similarity.stage5b5_review.SAMPLE_SIZE", 3)
    config = _config(tmp_path)
    run_v4_discovery(config, _Provider(), sleep=lambda _seconds: None)
    run_frozen_selector(config)
    queue, review_path = write_human_review_artifacts(config)
    assert all("selected_rank" not in case for case in queue["cases"])
    assert all("selected_video_id" not in case for case in queue["cases"])
    assert queue["selector_decisions_visible_to_reviewer"] is False
    store = Stage5B5ReviewStore(
        review_path, tmp_path / "automated_selector_decisions.json"
    )
    session = store.session()
    assert session["selector_decisions_visible"] is False
    case = session["cases"][0]
    assert case["review_phase"] == "TOP3_ORACLE"
    assert [candidate["rank"] for candidate in case["candidates"]] == [1]


def test_blind_supplement_is_required_without_revealing_selection() -> None:
    rows = [
        {"youtube_rank": "1", "candidate_review_label": "IDEAL"},
        {"youtube_rank": "2", "candidate_review_label": ""},
    ]
    assert next_review_requirement(rows, 2) == ("BLIND_COVERAGE_SUPPLEMENT", 2)
    rows[1]["candidate_review_label"] = "WRONG"
    assert next_review_requirement(rows, 2) is None


def test_complete_blinded_labels_produce_end_to_end_metrics(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("audio_similarity.stage5b5_review.SAMPLE_SIZE", 3)
    config = _config(tmp_path)
    discovery = run_v4_discovery(config, _Provider(), sleep=lambda _seconds: None)
    decisions, _ = run_frozen_selector(config)
    _, review_path = write_human_review_artifacts(config)
    with review_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row["youtube_rank"] == "1":
            row["candidate_review_label"] = "IDEAL"
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    grouped = validate_complete_review(
        review_path, tmp_path / "automated_selector_decisions.json"
    )
    metrics, failures = compute_final_metrics(grouped, decisions, discovery)
    assert metrics["human_oracle"]["top1_safe_rate"] == 1.0
    assert metrics["automated_selection"]["human_safe_precision"] == 1.0
    assert metrics["automated_selection"]["end_to_end_automated_safe_yield"] == 1.0
    assert metrics["automated_selection"]["unresolved_or_manual_tail_count"] == 0
    assert metrics["discovery"]["request_amplification"] == pytest.approx(4 / 3)
    assert failures["automated_wrong_count"] == 0


def test_recorded_v4_is_fresh_complete_hash_locked_and_scope_safe() -> None:
    project_root = Path(__file__).resolve().parents[1]
    output = project_root / "reports/stage5b5_representative_v4"
    required = set(ARTIFACT_NAMES) | {"artifact_manifest.json"}
    assert required == {path.name for path in output.iterdir() if path.is_file()}
    manifest = json.loads((output / "artifact_manifest.json").read_text())
    metrics = json.loads((output / "final_metrics.json").read_text())
    config = load_v4_config(output / "benchmark_config.json")
    frozen = json.loads(config.manifest_path.read_text())
    prior_ids = set()
    for path in historical_json_paths(project_root):
        text = path.read_text()
        prior_ids.update(
            value
            for value in (
                row.get("spotify_track_id")
                for row in _walk_objects(json.loads(text))
            )
            if value
        )
    assert not ({row["spotify_track_id"] for row in frozen["tracks"]} & prior_ids)
    assert metrics["scope_guards"]["production_activation"] is False
    assert metrics["scope_guards"]["query_tuning"] is False
    for name, identity in manifest["artifacts"].items():
        assert identity["sha256"] == file_sha256(output / name)
    for identity in manifest["implementation"].values():
        assert identity["sha256"] == file_sha256(project_root / identity["path"])


def _walk_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_objects(child)
