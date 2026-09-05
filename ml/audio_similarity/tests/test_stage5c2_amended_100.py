from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import audio_similarity.stage5c2_amended_100 as amended_module
from audio_similarity.cli.stage5c2_review_server import DEFAULT_REPORT_DIRECTORY
from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256
from audio_similarity.stage5c2_amended_100 import migrate_review_labels
from audio_similarity.stage5c2_analysis import REVIEW_COLUMNS


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/stage5c2_representative_100"
REPORT = ROOT / "reports/stage5c2_representative_100_amended_v2"
SUPPLEMENT = (
    ROOT / "reports/stage5c2_representative_100_amended_v2_supplement_materialization"
)


def _json(directory: Path, name: str) -> dict:
    return json.loads((directory / name).read_text(encoding="utf-8"))


def test_amendment_freezes_all_100_sources_without_rewriting_original() -> None:
    amendment = _json(REPORT, "amendment_manifest.json")
    selected = _json(REPORT, "selected_sources.json")
    assert amendment["base_track_count"] == 98
    assert amendment["recovered_track_count"] == 2
    assert amendment["amended_track_count"] == 100
    assert selected["automated_selection_count"] == 100
    assert selected["manual_tail_count"] == 0
    assert len(selected["tracks"]) == 100
    assert len({row["spotify_track_id"] for row in selected["tracks"]}) == 100
    assert len({row["selected_youtube_video_id"] for row in selected["tracks"]}) == 100
    assert file_sha256(REPORT / "selected_sources.json") == (
        REPORT / "selected_sources.sha256"
    ).read_text(encoding="utf-8").strip()
    for name, expected_sha in amendment["original_frozen_artifacts"].items():
        assert file_sha256(BASE / name) == expected_sha


def test_two_recoveries_use_exact_owner_sources_and_frozen_representation() -> None:
    selected = _json(SUPPLEMENT, "selected_sources.json")
    materialized = _json(SUPPLEMENT, "materialization_results.json")
    expected = {
        "5quFr5s5PXYfUX5jV2EBZ1": "v224EdAkZr8",
        "5l45vVLs4JKkhzN0tvkWJv": "i4YFngxyJ0k",
    }
    assert {
        row["spotify_track_id"]: row["selected_youtube_video_id"]
        for row in selected["tracks"]
    } == expected
    assert materialized["full_materialization_successes"] == 2
    assert materialized["full_materialization_failures"] == 0
    assert materialized["frozen_contract"]["centers_seconds"] == [5, 15, 25]
    assert materialized["frozen_contract"]["clap_weight"] == 0.7172981519
    assert materialized["frozen_contract"]["muq_weight"] == 0.2827018481
    for row in materialized["tracks"]:
        assert row["status"] == "SUCCESS"
        assert len(row["segments"]) == 6
        assert {segment["center_sec"] for segment in row["segments"]} == {5, 15, 25}
    assert {
        row["video_id"]: row["exact_url"] for row in materialized["acquisitions"]
    } == {
        video_id: f"https://www.youtube.com/watch?v={video_id}"
        for video_id in expected.values()
    }


def test_supplement_rate_cleanup_cache_and_rerun_audits_pass() -> None:
    attempts = _json(SUPPLEMENT, "acquisition_attempts.json")
    rate = _json(SUPPLEMENT, "rate_limit_metrics.json")
    cleanup = _json(SUPPLEMENT, "cleanup_audit.json")
    cache = _json(SUPPLEMENT, "cache_audit.json")
    rerun = _json(SUPPLEMENT, "cache_rerun_results.json")["cache_rerun_validation"]
    assert attempts["exact_id_only"] is True
    assert attempts["discovery_requests"] == 0
    assert attempts["concurrent_downloads"] == 0
    assert rate["total_live_download_attempts"] == 2
    assert rate["minimum_start_to_start_spacing_seconds"] >= 20.0
    assert rate["passed"] is True
    assert cleanup["temporary_root_absent_after_cleanup"] is True
    assert cleanup["directory_level_audit"]["retained_source_media_count"] == 0
    assert cleanup["directory_level_audit"]["passed"] is True
    assert cache["passed"] is True
    assert rerun["network_acquisition_attempts"] == 0
    assert rerun["encoder_segments_inferred"] == 0
    assert all(rerun["representation_hash_equality"].values())


def test_existing_first_run_is_reused_instead_of_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / amended_module.SUPPLEMENT_RUN_DIRECTORY
    artifacts = tmp_path / amended_module.SUPPLEMENT_ARTIFACT_DIRECTORY
    report.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    selected_sha = "frozen-selected-sha"
    (report / "selected_sources.json").write_text("{}", encoding="utf-8")
    (report / "selected_sources.sha256").write_text("unused\n", encoding="utf-8")
    first = {
        "run_kind": "first",
        "selected_sources_sha256": selected_sha,
        "full_materialization_successes": 2,
        "automated_selected_tracks": 2,
        "acquisitions": [],
    }
    (report / "materialization_results.json").write_text(
        json.dumps(first), encoding="utf-8"
    )
    (report / "acquisition_attempts.json").write_text(
        json.dumps({"attempts": []}), encoding="utf-8"
    )
    (report / "cleanup_audit.json").write_text(
        json.dumps({"temporary_root_absent_after_cleanup": True}), encoding="utf-8"
    )
    monkeypatch.setattr(
        amended_module,
        "verify_selected_sources",
        lambda path: ({}, selected_sha),
    )
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(kwargs["run_kind"])
        return {
            "cache_rerun_validation": {
                "network_acquisition_attempts": 0,
                "encoder_segments_inferred": 0,
                "representation_hash_equality": {"one": True, "two": True},
            }
        }

    monkeypatch.setattr(amended_module, "run_materialization", fake_run)
    monkeypatch.setattr(
        amended_module,
        "acquisition_and_rate_metrics",
        lambda attempts, materialization: (
            {"rate_limit_metrics_path": "old"},
            {"passed": True},
        ),
    )
    monkeypatch.setattr(
        amended_module, "audit_stage5a_cache", lambda path: {"passed": True}
    )
    result = amended_module.materialize_recoveries(tmp_path)
    assert calls == ["cache_rerun"]
    assert result["first"] == first


@pytest.mark.parametrize("encoder", ["clap", "muq", "combined"])
def test_amended_similarity_matrices_cover_100_tracks(encoder: str) -> None:
    with (REPORT / f"{encoder}_similarity.csv").open(newline="") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) == 101
    assert all(len(row) == 101 for row in rows)


def test_default_review_workspace_uses_complete_amended_queue() -> None:
    assert DEFAULT_REPORT_DIRECTORY == "reports/stage5c2_representative_100_amended_v2"
    queue = _json(REPORT, "review_queue.json")
    selected = _json(REPORT, "selected_sources.json")
    assert queue["query_track_count"] == 100
    assert len(queue["cases"]) == 100
    assert {row["spotify_track_id"] for row in selected["tracks"]} == {
        row["spotify_track_id"] for row in queue["cases"]
    }


def _write_review(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _review_row(pair_id: str, label: str = "") -> dict[str, str]:
    return dict.fromkeys(REVIEW_COLUMNS, "") | {
        "review_schema_version": "stage5c2-human-similarity-review-v1",
        "pair_id": pair_id,
        "query_spotify_id": "left",
        "neighbor_spotify_id": "right",
        "neighbor_rank": "1",
        "clap_similarity": "0.5",
        "muq_similarity": "0.5",
        "combined_similarity": "0.5",
        "human_label": label,
    }


def test_review_label_migration_is_incremental_and_conflict_safe(tmp_path: Path) -> None:
    base = tmp_path / "base.csv"
    amended = tmp_path / "amended.csv"
    _write_review(base, [_review_row("shared", "2"), _review_row("base-only", "3")])
    _write_review(amended, [_review_row("shared"), _review_row("new-only")])
    result = migrate_review_labels(base, amended)
    with amended.open(encoding="utf-8", newline="") as handle:
        rows = {row["pair_id"]: row for row in csv.DictReader(handle)}
    assert rows["shared"]["human_label"] == "2"
    assert rows["new-only"]["human_label"] == ""
    assert result["migrated_unique_pairs"] == 1
    assert result["preserved_only_in_original_queue"] == 1

    _write_review(base, [_review_row("shared", "3")])
    with pytest.raises(Stage5B1AValidationError, match="conflicting review labels"):
        migrate_review_labels(base, amended)


def test_amended_artifact_manifest_hashes_are_valid() -> None:
    manifest = _json(REPORT, "artifact_manifest.json")
    assert manifest["artifacts"]["human_similarity_review.csv"][
        "mutable_human_evidence"
    ] is True
    records = [
        *manifest["artifacts"].values(),
        *manifest["supplemental_materialization_artifacts"].values(),
    ]
    for record in records:
        path = ROOT / record["path"]
        if record.get("mutable_human_evidence"):
            assert path.is_file()
            assert record["hash_scope"] == "INITIAL_QUEUE_STATE"
            continue
        assert path.stat().st_size == record["size_bytes"]
        assert file_sha256(path) == record["sha256"]
