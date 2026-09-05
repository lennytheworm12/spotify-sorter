from __future__ import annotations

import json
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/stage5c2a_persistent_research_audio"


def _json(name: str):
    return json.loads((REPORT / name).read_text(encoding="utf-8"))


def test_committed_retention_evidence_is_complete_and_cache_rerun_only() -> None:
    reference = _json("amended_100_source_reference.json")
    results = _json("retention_results.json")
    metrics = _json("retention_metrics.json")
    assert reference["source_experiment_id"] == (
        "STAGE5C2_REPRESENTATIVE_100_SELECTOR_AWARE_AMENDMENT_V2"
    )
    assert len(reference["tracks"]) == 100
    assert results["status"] == "COMPLETE"
    assert len(results["tracks"]) == len(results["attempts"]) == 100
    assert all(row["status"] == "SUCCESS" for row in results["tracks"])
    assert all(
        row["retention_mode"] == "RETENTION_CACHE_HIT"
        for row in results["tracks"]
    )
    assert metrics["verdict"] == "PERSISTENT_100_RESEARCH_AUDIO_CACHE_READY"
    assert metrics["retained_successful"] == metrics["retention_cache_hits_last_run"] == 100
    assert metrics["acquisition_failures_last_run"] == 0
    assert metrics["acquisition_start_spacing_seconds"]["minimum"] >= 20
    assert metrics["clap_reruns"] == metrics["muq_reruns"] == 0
    assert metrics["scratch_artifacts"] == []
    assert metrics["media_files_git_ignored"] is True
    assert metrics["media_files_tracked_by_git"] == 0


def test_committed_playback_evidence_uses_unchanged_amended_100_queue() -> None:
    playback = _json("playback_validation.json")
    assert playback["browser_validation"] == "PASS"
    assert playback["ordinary_full_response"] == "PASS"
    assert playback["http_206_range_response"] == "PASS"
    assert playback["beginning_seek"] == playback["mid_song_seek"] == "PASS"
    assert playback["near_end_seek"] == playback["repeated_seek"] == "PASS"
    assert playback["query_neighbor_switching"] == "PASS"
    assert playback["review_query_count"] == 100
    assert playback["review_directional_relationship_count"] == 500
    assert playback["review_unique_pair_count"] == 359
    assert playback["review_queue_sha256"] == (
        "e0b36ed25206970d5dad9b8122f3e74d176da9a3827dfb239d45f9fc848cbba0"
    )
    browser = playback["browser_details"]
    assert browser["clean_ephemeral_context"] is True
    assert browser["personal_profile_loaded"] is False
    assert browser["youtube_iframe_hidden"] is True
    assert browser["console_errors"] == []


def test_artifact_manifest_hashes_only_non_media_files() -> None:
    manifest = _json("artifact_manifest.json")
    for row in manifest["artifacts"]:
        path = REPORT / row["path"]
        assert path.is_file()
        assert file_sha256(path) == row["sha256"]
        assert path.stat().st_size == row["size_bytes"]
        assert row["contains_media"] is False
        assert path.suffix in {".json", ".md"}
    assert manifest["local_media_root"] == ".research_audio"
    assert manifest["local_media_committed"] is False


def test_committed_reports_contain_no_machine_specific_absolute_paths() -> None:
    for path in REPORT.iterdir():
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            assert "/home/bphan944/" not in content
            assert "C:\\" not in content
