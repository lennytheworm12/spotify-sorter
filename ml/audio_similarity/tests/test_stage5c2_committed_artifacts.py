from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import file_sha256


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/stage5c2_representative_100"


REQUIRED = {
    "representative_manifest.json",
    "representative_manifest.sha256",
    "discovery_results.json",
    "selected_sources.json",
    "selected_sources.sha256",
    "acquisition_attempts.json",
    "acquisition_metrics.json",
    "rate_limit_metrics.json",
    "materialization_results.json",
    "cache_rerun_results.json",
    "cleanup_audit.json",
    "cache_audit.json",
    "clap_similarity.csv",
    "muq_similarity.csv",
    "combined_similarity.csv",
    "nearest_neighbors.json",
    "encoder_disagreement_analysis.json",
    "representation_diagnostics.json",
    "review_queue.json",
    "human_similarity_review.csv",
    "clap_similarity_heatmap.png",
    "muq_similarity_heatmap.png",
    "combined_similarity_heatmap.png",
    "stage5c2_metrics.json",
    "stage5c2_report.md",
    "artifact_manifest.json",
}


def _json(name: str):
    return json.loads((REPORT / name).read_text(encoding="utf-8"))


def test_committed_stage5c2_artifact_set_is_complete_hash_locked_and_human_pending() -> None:
    assert REQUIRED <= {path.name for path in REPORT.iterdir() if path.is_file()}
    manifest = _json("representative_manifest.json")
    selected = _json("selected_sources.json")
    metrics = _json("stage5c2_metrics.json")
    artifact_manifest = _json("artifact_manifest.json")
    assert manifest["sampled_track_count"] == 100
    assert len({row["spotify_track_id"] for row in manifest["tracks"]}) == 100
    assert selected["automated_selection_count"] + selected["manual_tail_count"] == 100
    assert selected["post_freeze_substitutions"] == 0
    assert metrics["human_similarity_quality_verdict"] == "HUMAN_REVIEW_PENDING"
    assert metrics["scope_guards"]["human_labels_fabricated"] == 0
    with (REPORT / "human_similarity_review.csv").open(newline="") as handle:
        review = list(csv.DictReader(handle))
    assert review
    assert all(not row["human_label"] for row in review)
    for record in artifact_manifest["artifacts"].values():
        path = ROOT / record["path"]
        assert path.stat().st_size == record["size_bytes"]
        assert file_sha256(path) == record["sha256"]


def test_live_attempts_are_serial_exact_id_and_at_least_20_seconds_apart() -> None:
    attempts = _json("acquisition_attempts.json")
    rate = _json("rate_limit_metrics.json")
    assert attempts["exact_id_only"] is True
    assert attempts["discovery_requests"] == 0
    assert attempts["concurrent_downloads"] == 0
    assert all(row["minimum_spacing_compliant"] for row in attempts["attempts"])
    assert rate["minimum_start_to_start_spacing_seconds"] >= 20.0 - 1e-6
    assert rate["passed"] is True


def test_cache_cleanup_and_representation_integrity_pass() -> None:
    cleanup = _json("cleanup_audit.json")
    cache = _json("cache_audit.json")
    rerun = _json("cache_rerun_results.json")["cache_rerun_validation"]
    diagnostics = _json("representation_diagnostics.json")
    assert cleanup["temporary_root_absent_after_cleanup"] is True
    assert cleanup["unintended_retained_source_audio_files"] == 0
    assert cache["passed"] is True
    assert rerun["network_acquisition_attempts"] == 0
    assert rerun["encoder_segments_inferred"] == 0
    assert all(rerun["representation_hash_equality"].values())
    assert diagnostics["representation_pathology_detected"] is False


def test_fresh_sample_excludes_v4_and_curated_25() -> None:
    current = {row["spotify_track_id"] for row in _json("representative_manifest.json")["tracks"]}
    for relative in (
        "reports/stage5b5_representative_v4/benchmark_manifest.json",
        "reports/stage5c1_curated_25_materialization/curated_manifest.json",
    ):
        prior = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        assert current.isdisjoint(row["spotify_track_id"] for row in prior["tracks"])


@pytest.mark.parametrize("encoder", ["clap", "muq", "combined"])
def test_similarity_matrices_cover_every_successful_track(encoder: str) -> None:
    successful = _json("stage5c2_metrics.json")["pipeline"]["full_materialization_successes"]
    with (REPORT / f"{encoder}_similarity.csv").open(newline="") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) == successful + 1
    assert all(len(row) == successful + 1 for row in rows)
