from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import numpy as np

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5c2_analysis import analyze_representations


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _prepare(tmp_path: Path) -> Path:
    report = tmp_path / "reports/stage5c2_representative_100"
    report.mkdir(parents=True)
    contract_dir = tmp_path / "reports/holistic_stage4a_dual"
    contract_dir.mkdir(parents=True)
    shutil.copy2(
        PROJECT_ROOT / "reports/holistic_stage4a_dual/audio_representation_v1.json",
        contract_dir / "audio_representation_v1.json",
    )
    c1_manifest = json.loads(
        (
            PROJECT_ROOT
            / "reports/stage5c1_curated_25_materialization/curated_manifest.json"
        ).read_text()
    )
    source_tracks = c1_manifest["tracks"][:6]
    tracks = [
        {
            "stage5c2_track_id": f"stage5c2_{index:03d}",
            "manifest_index": index,
            "spotify_track_id": (
                source_tracks[index - 1]["spotify_track_id"]
                if index <= 6
                else f"{index:022d}"
            ),
            "title": (
                source_tracks[index - 1]["title"] if index <= 6 else f"Unused {index}"
            ),
            "artists": (
                source_tracks[index - 1]["artists"] if index <= 6 else ["Unused"]
            ),
            "album": "Album",
            "duration_ms": 180_000,
        }
        for index in range(1, 101)
    ]
    manifest = {
        "schema_version": "stage5c2-representative-100-manifest-v1",
        "experiment_id": "stage5c2_representative_100",
        "sampled_track_count": 100,
        "post_freeze_substitutions": 0,
        "tracks": tracks,
    }
    manifest_path = report / "representative_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_path.with_suffix(".sha256").write_text(file_sha256(manifest_path) + "\n")
    selected_tracks = []
    for index, (track, source) in enumerate(zip(tracks[:6], source_tracks, strict=True), start=1):
        video_id = source["selected_youtube_video_id"]
        selected_tracks.append(
            {
                "stage5c2_track_id": track["stage5c2_track_id"],
                "spotify_track_id": track["spotify_track_id"],
                "selected_youtube_video_id": video_id,
                "selected_youtube_url": f"https://www.youtube.com/watch?v={video_id}",
                "selected_candidate_rank": source["selected_candidate_rank"],
                "discovery_mode": source["discovery_mode"],
            }
        )
    selected = {
        "schema_version": "stage5c2-selected-sources-v1",
        "representative_manifest_sha256": file_sha256(manifest_path),
        "automated_selection_count": 6,
        "manual_tail_count": 94,
        "post_freeze_substitutions": 0,
        "exact_id_acquisition_only": True,
        "tracks": selected_tracks,
    }
    selected_path = report / "selected_sources.json"
    selected_path.write_text(json.dumps(selected), encoding="utf-8")
    selected_path.with_suffix(".sha256").write_text(file_sha256(selected_path) + "\n")
    source_dataset = PROJECT_ROOT / "artifacts/stage5c1_curated_25_materialization/representations"
    target_dataset = tmp_path / "artifacts/stage5c2_representative_100/representations"
    target_dataset.mkdir(parents=True)
    for source in source_dataset.glob("part-*.parquet"):
        shutil.copy2(source, target_dataset / source.name)
    return tmp_path


def test_similarity_analysis_matrices_neighbors_and_review_queue_are_deterministic(
    tmp_path: Path,
) -> None:
    root = _prepare(tmp_path)
    first = analyze_representations(root)
    queue_bytes = (
        root / "reports/stage5c2_representative_100/review_queue.json"
    ).read_bytes()
    second = analyze_representations(root)
    report = root / "reports/stage5c2_representative_100"
    assert first == second
    assert first["successful_track_count"] == 6
    assert (report / "review_queue.json").read_bytes() == queue_bytes
    for encoder in ("clap", "muq", "combined"):
        with (report / f"{encoder}_similarity.csv").open(newline="") as handle:
            rows = list(csv.reader(handle))
        matrix = np.asarray([[float(value) for value in row[1:]] for row in rows[1:]])
        assert matrix.shape == (6, 6)
        assert np.isfinite(matrix).all()
        assert np.allclose(matrix, matrix.T)
        assert np.allclose(np.diag(matrix), 1)
        assert (report / f"{encoder}_similarity_heatmap.png").stat().st_size > 0
        assert (report / f"{encoder}_similarity_distribution.png").stat().st_size > 0
    neighbors = json.loads((report / "nearest_neighbors.json").read_text())
    assert all(
        len(row["neighbors"]["combined"]) == 5 for row in neighbors["tracks"]
    )
    assert all(
        neighbor["spotify_track_id"] != row["spotify_track_id"]
        for row in neighbors["tracks"]
        for neighbor in row["neighbors"]["combined"]
    )
    queue = json.loads((report / "review_queue.json").read_text())
    assert queue["query_track_count"] == 6
    assert queue["raw_top5_judgment_count"] == 30
    assert queue["unique_unordered_pair_count"] <= 30
    assert queue["status"] == "HUMAN_REVIEW_PENDING"
    with (report / "human_similarity_review.csv").open(newline="") as handle:
        review = list(csv.DictReader(handle))
    assert len(review) == 30
    assert all(not row["human_label"] for row in review)
