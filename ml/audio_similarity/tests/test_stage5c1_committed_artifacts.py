import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/stage5c1_curated_25_materialization"


def _json(name):
    return json.loads((REPORT / name).read_text(encoding="utf-8"))


def test_committed_stage5c1_artifacts_are_complete_and_internally_consistent():
    manifest = _json("curated_manifest.json")
    metrics = _json("stage5c1_metrics.json")
    artifacts = _json("artifact_manifest.json")
    expected_sha = (REPORT / "curated_manifest.sha256").read_text().split()[0]
    actual_sha = hashlib.sha256((REPORT / "curated_manifest.json").read_bytes()).hexdigest()

    assert expected_sha == actual_sha == metrics["manifest_sha256"]
    assert len(manifest["tracks"]) == 25
    assert manifest["post_freeze_substitutions"] == 0
    assert metrics["verdict"] == "PIPELINE_AND_REPRESENTATION_SANITY_PASSED"
    assert metrics["pipeline_reliability"]["counts"]["full_materialization_successes"] == 25
    assert metrics["pipeline_reliability"]["counts"]["cleanup_successes"] == 25
    assert metrics["pipeline_reliability"]["counts"]["cache_rerun_successes"] == 25
    assert metrics["pipeline_reliability"]["integrity"]["corrupt_cache_entries"] == 0
    assert metrics["representation_sanity"]["collapse_pathology_detected"] is False
    assert all(metrics["representation_sanity"]["broad_relationship_comparisons"].values())
    assert artifacts["scope_guards"] == {
        "discovery_queries": 0,
        "media_substitutions": 0,
        "production_activation": False,
        "representation_tuned": False,
        "source_audio_retained": False,
        "stage5b_selector_modified": False,
    }
    for row in artifacts["report_artifacts"]:
        path = ROOT / row["path"]
        assert path.stat().st_size == row["size_bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
    assert all(row["unchanged"] for row in artifacts["frozen_upstream_integrity"])


def test_committed_review_queue_and_matrices_cover_successful_tracks():
    with (REPORT / "human_sanity_review.csv").open(encoding="utf-8", newline="") as handle:
        review = list(csv.DictReader(handle))
    assert len(review) == 25
    assert not any(row["human_sanity_label"] for row in review)
    assert not any(row["analyst_assessment"] == "NEEDS_HUMAN_REVIEW" for row in review)

    for encoder in ("clap", "muq", "combined"):
        with (REPORT / f"{encoder}_similarity.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        assert len(rows) == 26
        assert len(rows[0]) == 26
        assert all(len(row) == 26 for row in rows)
        assert (REPORT / f"{encoder}_similarity_heatmap.png").stat().st_size > 0
