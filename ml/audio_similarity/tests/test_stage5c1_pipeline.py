import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import torch
import torchaudio

from audio_similarity.stage5c1_analysis import analyze_representations
from audio_similarity.stage5c1_pipeline import run_materialization_attempt
from audio_similarity.stage5c1_closeout import (
    audit_stage5a_cache,
    build_pipeline_reliability_metrics,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeEncoder:
    embedding_dim = 512

    def __init__(self, encoder_id):
        self.encoder_id = encoder_id
        self.calls = 0

    def encode_segment(self, waveform, sample_rate):
        assert sample_rate == 24_000
        self.calls += 1
        mean = float(np.mean(waveform))
        vector = np.zeros(512, dtype=np.float32)
        if self.encoder_id == "laion_clap":
            vector[:3] = (1.0, mean, mean * mean + 0.1)
        else:
            vector[:3] = (mean + 0.2, 1.0, 0.5 - mean)
        return vector


class FakeAcquirer:
    def __init__(self, *, fail_track_id=None):
        self.calls = []
        self.fail_track_id = fail_track_id

    def acquire(self, track, output_dir):
        video_id = track["selected_youtube_video_id"]
        exact_url = f"https://www.youtube.com/watch?v={video_id}"
        assert track["selected_youtube_url"] == exact_url
        assert "ytsearch" not in exact_url
        self.calls.append((track["spotify_track_id"], exact_url))
        path = output_dir / f"{track['stage5c1_track_id']}-{video_id}.wav"
        if track["spotify_track_id"] == self.fail_track_id:
            path.with_suffix(".part").write_bytes(b"partial")
            raise RuntimeError("controlled exact-ID acquisition failure")
        amplitude = 0.01 + track["manifest_index"] / 100.0
        waveform = torch.full((1, 24_000 * 30), amplitude, dtype=torch.float32)
        torchaudio.save(str(path), waveform, 24_000)
        return {
            "provider": "fake_exact_url",
            "provider_result": "SUCCESS",
            "video_id": video_id,
            "exact_url": exact_url,
            "requested_section_seconds": [0.0, 30.0],
            "acquisition_started_at": "test",
            "acquisition_ended_at": "test",
            "elapsed_seconds": 0.01,
            "output_format": "wav",
            "temporary_file_path": str(path),
            "file_size_bytes": path.stat().st_size,
            "provider_title": track["title"],
            "provider_duration_seconds": track["spotify_duration_ms"] / 1000,
            "warnings": [],
            "errors": [],
        }


def _fixture_root(tmp_path):
    report = tmp_path / "reports/stage5c1_curated_25_materialization"
    contract = tmp_path / "reports/holistic_stage4a_dual"
    report.mkdir(parents=True)
    contract.mkdir(parents=True)
    for name in ("curated_manifest.json", "curated_manifest.sha256"):
        shutil.copy2(
            PROJECT_ROOT / "reports/stage5c1_curated_25_materialization" / name,
            report / name,
        )
    shutil.copy2(
        PROJECT_ROOT / "reports/holistic_stage4a_dual/audio_representation_v1.json",
        contract / "audio_representation_v1.json",
    )
    return tmp_path


@pytest.fixture(scope="module")
def successful_pipeline(tmp_path_factory):
    root = _fixture_root(tmp_path_factory.mktemp("stage5c1-success"))
    acquirer = FakeAcquirer()
    clap = FakeEncoder("laion_clap")
    muq = FakeEncoder("muq_mulan_large")
    encoders = {clap.encoder_id: clap, muq.encoder_id: muq}
    first = run_materialization_attempt(
        root, run_kind="first", acquirer=acquirer, encoders=encoders
    )
    first_call_count = (clap.calls, muq.calls)
    rerun = run_materialization_attempt(
        root, run_kind="cache_rerun", acquirer=acquirer, encoders=encoders
    )
    return root, acquirer, encoders, first, rerun, first_call_count


def test_exact_frozen_ids_are_acquired_without_discovery_and_all_segments_materialize(successful_pipeline):
    root, acquirer, encoders, first, _, first_call_count = successful_pipeline
    manifest = json.loads(
        (root / "reports/stage5c1_curated_25_materialization/curated_manifest.json").read_text()
    )
    assert len(acquirer.calls) == 25
    assert [url for _, url in acquirer.calls] == [
        row["selected_youtube_url"] for row in manifest["tracks"]
    ]
    assert first["tracks_attempted"] == 25
    assert first["full_materialization_successes"] == 25
    assert all(row["failure_category"] == "" for row in first["tracks"])
    assert first_call_count == (75, 75)
    assert all(len(row["segments"]) == 6 for row in first["tracks"])
    assert all(
        {segment["center_sec"] for segment in row["segments"]} == {5, 15, 25}
        for row in first["tracks"]
    )
    assert first["frozen_contract"]["clap_weight"] == 0.7172981519
    assert first["frozen_contract"]["muq_weight"] == 0.2827018481
    assert first["manifest_unchanged"] is True


def test_cache_rerun_prevents_acquisition_and_encoder_inference(successful_pipeline):
    _, acquirer, encoders, first, rerun, first_call_count = successful_pipeline
    validation = rerun["cache_rerun_validation"]
    assert len(acquirer.calls) == 25
    assert validation["acquisition_requests"] == 0
    assert validation["reacquisition_prevented"] == 25
    assert validation["encoder_segments_inferred"] == 0
    assert validation["encoder_rerun"] is False
    assert all(validation["representation_hash_equality"].values())
    assert (encoders["laion_clap"].calls, encoders["muq_mulan_large"].calls) == first_call_count
    assert {
        row["spotify_track_id"]: row["representation_identity"] for row in first["tracks"]
    } == {
        row["spotify_track_id"]: row["representation_identity"] for row in rerun["tracks"]
    }


def test_temporary_audio_is_cleaned_and_cache_identities_do_not_collide(successful_pipeline):
    root, _, _, first, rerun, _ = successful_pipeline
    cleanup = json.loads(
        (root / "reports/stage5c1_curated_25_materialization/cleanup_results.json").read_text()
    )
    assert cleanup["temporary_root_absent_after_cleanup"] is True
    assert all(row["cleanup_attempted"] for row in cleanup["tracks"])
    assert all(row["temp_files_absent_after_cleanup"] for row in cleanup["tracks"])
    assert len({row["source_audio_sha256"] for row in first["tracks"]}) == 25
    assert len({row["representation_identity"] for row in first["tracks"]}) == 25
    assert rerun["cleanup"]["temporary_root_absent_after_cleanup"] is True


def test_cleanup_runs_after_handled_acquisition_failure(tmp_path):
    root = _fixture_root(tmp_path)
    manifest = json.loads(
        (root / "reports/stage5c1_curated_25_materialization/curated_manifest.json").read_text()
    )
    failed_id = manifest["tracks"][0]["spotify_track_id"]
    acquirer = FakeAcquirer(fail_track_id=failed_id)
    encoders = {
        "laion_clap": FakeEncoder("laion_clap"),
        "muq_mulan_large": FakeEncoder("muq_mulan_large"),
    }
    result = run_materialization_attempt(
        root, run_kind="first", acquirer=acquirer, encoders=encoders
    )
    cleanup = json.loads(
        (root / "reports/stage5c1_curated_25_materialization/cleanup_results.json").read_text()
    )
    failed = next(row for row in result["tracks"] if row["spotify_track_id"] == failed_id)
    failed_cleanup = next(row for row in cleanup["tracks"] if row["spotify_track_id"] == failed_id)
    assert result["full_materialization_successes"] == 24
    assert failed["failure_category"] == "ACQUISITION_FAILED"
    assert failed_cleanup["cleanup_attempted"] is True
    assert failed_cleanup["temp_files_absent_after_cleanup"] is True
    assert cleanup["temporary_root_absent_after_cleanup"] is True
    acquisition = json.loads(
        (root / "reports/stage5c1_curated_25_materialization/acquisition_results.json").read_text()
    )
    failed_acquisition = next(
        row for row in acquisition["tracks"] if row["spotify_track_id"] == failed_id
    )
    assert failed_acquisition["errors"] == ["controlled exact-ID acquisition failure"]


def test_similarity_analysis_is_symmetric_finite_and_excludes_self(successful_pipeline):
    root, _, _, _, _, _ = successful_pipeline
    result = analyze_representations(root)
    report = root / "reports/stage5c1_curated_25_materialization"
    assert result["successful_track_count"] == 25
    assert all(value == 0.0 for value in result["matrix_symmetry_max_error"].values())
    assert all(value == 0.0 for value in result["matrix_diagonal_max_error"].values())
    for name in ("clap", "muq", "combined"):
        rows = list(csv_rows(report / f"{name}_similarity.csv"))
        matrix = np.asarray([[float(value) for value in row[1:]] for row in rows[1:]])
        assert matrix.shape == (25, 25)
        assert np.isfinite(matrix).all()
        assert np.allclose(matrix, matrix.T)
        assert np.allclose(np.diag(matrix), 1.0)
        assert (report / f"{name}_similarity_heatmap.png").stat().st_size > 0
    neighbors = json.loads((report / "nearest_neighbors.json").read_text())
    for track in neighbors["tracks"]:
        for encoder in ("clap", "muq", "combined"):
            nearest = track["neighbors"][encoder]
            assert len(nearest) == 5
            assert all(row["spotify_track_id"] != track["spotify_track_id"] for row in nearest)
    metrics = json.loads((report / "group_similarity_metrics.json").read_text())
    assert set(metrics["within_group"]) == set("ABCDE")
    assert set(metrics["between_group"]) == {"C_vs_D", "A_vs_E", "C_vs_E", "D_vs_E"}


def csv_rows(path):
    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        yield from csv.reader(handle)


def test_frozen_historical_artifacts_are_not_written_by_pipeline(successful_pipeline):
    manifest = json.loads(
        (PROJECT_ROOT / "reports/stage5c1_curated_25_materialization/curated_manifest.json").read_text()
    )
    for source in manifest["source_artifacts"]:
        path = PROJECT_ROOT / source["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]


def test_pipeline_metrics_separate_reliability_counts(successful_pipeline):
    root, _, _, _, _, _ = successful_pipeline
    report = root / "reports/stage5c1_curated_25_materialization"
    metrics = build_pipeline_reliability_metrics(
        json.loads((report / "acquisition_results.json").read_text()),
        json.loads((report / "materialization_results.json").read_text()),
        json.loads((report / "cleanup_results.json").read_text()),
        json.loads((report / "cache_rerun_results.json").read_text()),
        audit_stage5a_cache(root / "artifacts/stage5c1_curated_25_materialization/representations.sqlite"),
    )
    assert metrics["counts"] == {
        "tracks_attempted": 25,
        "acquisition_successes": 25,
        "acquisition_failures": 0,
        "decode_successes": 25,
        "segment_extraction_successes": 25,
        "clap_successes": 25,
        "muq_successes": 25,
        "full_materialization_successes": 25,
        "cache_write_successes": 25,
        "cleanup_successes": 25,
        "cache_rerun_successes": 25,
    }
    assert metrics["pipeline_reliability_passed"] is True
    assert metrics["integrity"]["cache_audit"]["row_counts"] == {
        "segments": 150,
        "pooled": 50,
        "tracks": 25,
    }
    assert metrics["integrity"]["corrupt_cache_entries"] == 0
