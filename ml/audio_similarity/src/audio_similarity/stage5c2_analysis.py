"""Representative similarity analysis and review-queue generation for Stage 5C.2."""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
from PIL import Image, ImageDraw, ImageFont

from .stage5a_contract import load_contract
from .stage5b1a_models import Stage5B1AValidationError
from .stage5b1b_artifacts import atomic_json
from .stage5c2_discovery import verify_selected_sources
from .stage5c2_manifest import EXPERIMENT_ID, REPORT_DIRECTORY, verify_frozen_manifest
from .stage5c2_pipeline import ARTIFACT_DIRECTORY


ENCODERS = ("clap", "muq", "combined")
REVIEW_COLUMNS = (
    "review_schema_version",
    "pair_id",
    "query_spotify_id",
    "neighbor_spotify_id",
    "neighbor_rank",
    "clap_similarity",
    "muq_similarity",
    "combined_similarity",
    "human_label",
    "human_note",
    "review_timestamp",
)


def canonical_pair_id(left: str, right: str) -> str:
    if not left or not right or left == right:
        raise Stage5B1AValidationError("review pair requires two distinct Spotify IDs")
    ordered = sorted((left, right))
    return hashlib.sha256(f"{ordered[0]}\0{ordered[1]}".encode()).hexdigest()[:24]


def _load_dataset(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for part in sorted(path.glob("part-*.parquet")):
        for row in pq.read_table(part).to_pylist():
            if row["status"] != "SUCCESS":
                continue
            stable_id = str(row["stable_track_id"])
            if stable_id in rows:
                raise Stage5B1AValidationError(f"duplicate representation row: {stable_id}")
            rows[stable_id] = row
    return rows


def _matrix(vectors: np.ndarray) -> np.ndarray:
    if vectors.ndim != 2 or vectors.shape[0] < 2 or not np.isfinite(vectors).all():
        raise Stage5B1AValidationError("invalid representation vector matrix")
    norms = np.linalg.norm(vectors.astype(np.float64), axis=1)
    if np.any(norms <= 0):
        raise Stage5B1AValidationError("zero representation vector")
    normalized = vectors / norms[:, None]
    matrix = normalized @ normalized.T
    matrix = (matrix + matrix.T) / 2
    np.fill_diagonal(matrix, 1.0)
    return matrix


def _write_matrix(path: Path, ids: list[str], matrix: np.ndarray) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["stage5c2_track_id", *ids])
        for track_id, row in zip(ids, matrix, strict=True):
            writer.writerow([track_id, *(f"{float(value):.9f}" for value in row)])


def _color(value: float, minimum: float, maximum: float) -> tuple[int, int, int]:
    fraction = 0.5 if maximum <= minimum else (value - minimum) / (maximum - minimum)
    fraction = min(1.0, max(0.0, fraction))
    if fraction < 0.5:
        local = fraction * 2
        return int(28 + 210 * local), int(84 + 160 * local), 244
    local = (fraction - 0.5) * 2
    return 244, int(244 - 188 * local), int(244 - 188 * local)


def _write_heatmap(path: Path, title: str, ids: list[str], matrix: np.ndarray) -> None:
    cell, left, top = 7, 66, 58
    size = len(ids) * cell
    image = Image.new("RGB", (left + size + 20, top + size + 30), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    off = matrix[np.triu_indices(len(matrix), k=1)]
    minimum, maximum = float(off.min()), float(off.max())
    draw.text((10, 8), title, fill="black", font=font)
    draw.text((10, 25), f"off-diagonal cosine {minimum:.3f} to {maximum:.3f}", fill="black", font=font)
    for row in range(len(ids)):
        for column in range(len(ids)):
            x, y = left + column * cell, top + row * cell
            draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=_color(float(matrix[row, column]), minimum, maximum))
    for index in range(0, len(ids), 10):
        label = str(index + 1)
        draw.text((left - 25, top + index * cell), label, fill="black", font=font)
        draw.text((left + index * cell, top - 16), label, fill="black", font=font)
    image.save(path, format="PNG", optimize=True)


def _stats(values: np.ndarray) -> dict[str, float | int | None]:
    if not values.size:
        return {"count": 0, "mean": None, "minimum": None, "maximum": None, "stddev": None}
    return {
        "count": int(values.size),
        "mean": float(values.mean()),
        "minimum": float(values.min()),
        "maximum": float(values.max()),
        "stddev": float(values.std()),
    }


def _write_distribution(path: Path, title: str, values: np.ndarray) -> None:
    width, height = 760, 360
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    counts, edges = np.histogram(values, bins=30)
    maximum = max(1, int(counts.max()))
    left, top, right, bottom = 55, 45, width - 20, height - 45
    draw.text((12, 10), title, fill="black", font=font)
    draw.line((left, bottom, right, bottom), fill="black")
    draw.line((left, top, left, bottom), fill="black")
    bar_width = (right - left) / len(counts)
    for index, count in enumerate(counts):
        if not count:
            continue
        x0 = left + index * bar_width
        x1 = left + (index + 1) * bar_width - 1
        y0 = bottom - (bottom - top) * int(count) / maximum
        draw.rectangle((x0, y0, x1, bottom - 1), fill=(77, 163, 255))
    draw.text((left, bottom + 10), f"{edges[0]:.3f}", fill="black", font=font)
    draw.text((right - 35, bottom + 10), f"{edges[-1]:.3f}", fill="black", font=font)
    image.save(path, format="PNG", optimize=True)


def _nearest(
    tracks: list[dict[str, Any]], matrices: dict[str, np.ndarray], source_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    output = []
    for index, track in enumerate(tracks):
        neighbors: dict[str, list[dict[str, Any]]] = {}
        for encoder, matrix in matrices.items():
            limit = 10 if encoder == "combined" else 5
            ordered = sorted(
                (candidate for candidate in range(len(tracks)) if candidate != index),
                key=lambda candidate: (-float(matrix[index, candidate]), candidate),
            )[:limit]
            neighbors[encoder] = [
                {
                    "rank": rank,
                    "stage5c2_track_id": tracks[candidate]["stage5c2_track_id"],
                    "spotify_track_id": tracks[candidate]["spotify_track_id"],
                    "title": tracks[candidate]["title"],
                    "artists": tracks[candidate]["artists"],
                    "similarity": float(matrix[index, candidate]),
                    "selected_youtube_rank": source_by_id[tracks[candidate]["spotify_track_id"]]["selected_candidate_rank"],
                    "discovery_mode": source_by_id[tracks[candidate]["spotify_track_id"]]["discovery_mode"],
                }
                for rank, candidate in enumerate(ordered, start=1)
            ]
        output.append(
            {
                "stage5c2_track_id": track["stage5c2_track_id"],
                "spotify_track_id": track["spotify_track_id"],
                "title": track["title"],
                "artists": track["artists"],
                "album": track.get("album"),
                "neighbors": neighbors,
            }
        )
    return {
        "schema_version": "stage5c2-nearest-neighbors-v1",
        "experiment_id": EXPERIMENT_ID,
        "self_matches_excluded": True,
        "top_k": {"clap": 5, "muq": 5, "combined": 10},
        "tracks": output,
    }


def _diagnostics(
    tracks: list[dict[str, Any]],
    materialized: list[dict[str, Any]],
    vectors: dict[str, np.ndarray],
    matrices: dict[str, np.ndarray],
    neighbors: dict[str, Any],
    selected: dict[str, Any],
) -> dict[str, Any]:
    pathologies: list[str] = []
    vector_checks = {}
    for encoder in ("clap", "muq"):
        norms = np.linalg.norm(vectors[encoder].astype(np.float64), axis=1)
        unique = len({row[f"{encoder}_embedding_sha256"] for row in materialized})
        vector_checks[encoder] = {
            "zero_vectors": int(np.sum(norms == 0)),
            "non_finite_values": int(np.sum(~np.isfinite(vectors[encoder]))),
            "maximum_norm_error": float(np.max(np.abs(norms - 1))),
            "unique_embedding_hashes": unique,
        }
        if unique != len(materialized):
            pathologies.append(f"{encoder.upper()}_DUPLICATE_EMBEDDING")
        if vector_checks[encoder]["zero_vectors"] or vector_checks[encoder]["non_finite_values"]:
            pathologies.append(f"{encoder.upper()}_INVALID_VECTOR")
    similarity_checks = {}
    for encoder, matrix in matrices.items():
        off = matrix[np.triu_indices(len(matrix), k=1)]
        similarity_checks[encoder] = _stats(off) | {
            "pairs_near_one": int(np.sum(off > 0.999)),
            "suspiciously_narrow_variance": bool(np.std(off) < 1e-4),
            "similarities_clustered_near_one": bool(np.mean(off) > 0.99),
            "symmetry_max_error": float(np.max(np.abs(matrix - matrix.T))),
            "diagonal_max_error": float(np.max(np.abs(np.diag(matrix) - 1))),
        }
        if similarity_checks[encoder]["suspiciously_narrow_variance"]:
            pathologies.append(f"{encoder.upper()}_NARROW_VARIANCE")
        if similarity_checks[encoder]["similarities_clustered_near_one"]:
            pathologies.append(f"{encoder.upper()}_NEAR_ONE_COLLAPSE")
    top1 = {}
    for encoder in ENCODERS:
        values = [row["neighbors"][encoder][0]["spotify_track_id"] for row in neighbors["tracks"]]
        top1[encoder] = dict(Counter(values).most_common())
        if Counter(values).most_common(1)[0][1] > max(10, math.ceil(len(values) / 3)):
            pathologies.append(f"{encoder.upper()}_UNIVERSAL_NEIGHBOR")
    representation_ids = [row["representation_identity"] for row in materialized]
    source_hashes = [row["source_audio_sha256"] for row in materialized]
    selected_video_ids = [row["selected_youtube_video_id"] for row in selected["tracks"]]
    if len(set(representation_ids)) != len(representation_ids):
        pathologies.append("CACHE_IDENTITY_COLLISION")
    if len(set(source_hashes)) != len(source_hashes):
        pathologies.append("SOURCE_AUDIO_REUSE")
    if len(set(selected_video_ids)) != len(selected_video_ids):
        pathologies.append("SELECTED_VIDEO_REUSE")
    identical = bool(np.allclose(matrices["clap"], matrices["muq"], atol=1e-7))
    if identical:
        pathologies.append("CLAP_MUQ_IDENTICAL")
    return {
        "schema_version": "stage5c2-representation-diagnostics-v1",
        "experiment_id": EXPERIMENT_ID,
        "successful_track_count": len(tracks),
        "vector_checks": vector_checks,
        "similarity_checks": similarity_checks,
        "top1_neighbor_frequency": top1,
        "unique_representation_identities": len(set(representation_ids)),
        "unique_source_audio_hashes": len(set(source_hashes)),
        "unique_selected_video_ids": len(set(selected_video_ids)),
        "clap_muq_similarity_matrices_identical": identical,
        "pathologies_detected": sorted(set(pathologies)),
        "representation_pathology_detected": bool(pathologies),
    }


def _disagreements(
    tracks: list[dict[str, Any]], matrices: dict[str, np.ndarray], weights: dict[str, float]
) -> dict[str, Any]:
    pairs = []
    for left, right in itertools.combinations(range(len(tracks)), 2):
        clap = float(matrices["clap"][left, right])
        muq = float(matrices["muq"][left, right])
        pairs.append(
            {
                "pair_id": canonical_pair_id(tracks[left]["spotify_track_id"], tracks[right]["spotify_track_id"]),
                "left_spotify_id": tracks[left]["spotify_track_id"],
                "left_title": tracks[left]["title"],
                "right_spotify_id": tracks[right]["spotify_track_id"],
                "right_title": tracks[right]["title"],
                "clap_similarity": clap,
                "muq_similarity": muq,
                "combined_similarity": float(matrices["combined"][left, right]),
                "clap_minus_muq": clap - muq,
            }
        )
    per_track = []
    for index, track in enumerate(tracks):
        clap_order = np.argsort(-matrices["clap"][index])
        muq_order = np.argsort(-matrices["muq"][index])
        clap_best = next(int(item) for item in clap_order if int(item) != index)
        muq_best = next(int(item) for item in muq_order if int(item) != index)
        per_track.append(
            {
                "spotify_track_id": track["spotify_track_id"],
                "clap_top1_spotify_id": tracks[clap_best]["spotify_track_id"],
                "muq_top1_spotify_id": tracks[muq_best]["spotify_track_id"],
                "top1_agreement": clap_best == muq_best,
            }
        )
    return {
        "schema_version": "stage5c2-encoder-disagreement-v1",
        "experiment_id": EXPERIMENT_ID,
        "weights": weights,
        "largest_clap_over_muq": sorted(pairs, key=lambda row: (-row["clap_minus_muq"], row["pair_id"]))[:25],
        "largest_muq_over_clap": sorted(pairs, key=lambda row: (row["clap_minus_muq"], row["pair_id"]))[:25],
        "per_track_top1_preferences": per_track,
        "top1_encoder_agreement_count": sum(row["top1_agreement"] for row in per_track),
        "combined_is_weighted_score_not_fused_vector": True,
    }


def _write_review_artifacts(
    report: Path,
    tracks: list[dict[str, Any]],
    neighbors: dict[str, Any],
    matrices: dict[str, np.ndarray],
    manifest_sha: str,
) -> dict[str, Any]:
    index_by_id = {track["spotify_track_id"]: index for index, track in enumerate(tracks)}
    cases = []
    review_rows = []
    pair_ids: set[str] = set()
    for query_index, neighbor_row in enumerate(neighbors["tracks"]):
        query = tracks[query_index]
        combined_top5 = neighbor_row["neighbors"]["combined"][:5]
        rendered = []
        for neighbor in combined_top5:
            neighbor_index = index_by_id[neighbor["spotify_track_id"]]
            pair_id = canonical_pair_id(query["spotify_track_id"], neighbor["spotify_track_id"])
            pair_ids.add(pair_id)
            item = neighbor | {
                "pair_id": pair_id,
                "clap_similarity": float(matrices["clap"][query_index, neighbor_index]),
                "muq_similarity": float(matrices["muq"][query_index, neighbor_index]),
                "combined_similarity": float(matrices["combined"][query_index, neighbor_index]),
            }
            rendered.append(item)
            review_rows.append(
                {
                    "review_schema_version": "stage5c2-human-similarity-review-v1",
                    "pair_id": pair_id,
                    "query_spotify_id": query["spotify_track_id"],
                    "neighbor_spotify_id": neighbor["spotify_track_id"],
                    "neighbor_rank": str(neighbor["rank"]),
                    "clap_similarity": f"{item['clap_similarity']:.9f}",
                    "muq_similarity": f"{item['muq_similarity']:.9f}",
                    "combined_similarity": f"{item['combined_similarity']:.9f}",
                    "human_label": "",
                    "human_note": "",
                    "review_timestamp": "",
                }
            )
        cases.append(
            {
                "stage5c2_track_id": query["stage5c2_track_id"],
                "spotify_track_id": query["spotify_track_id"],
                "title": query["title"],
                "artists": query["artists"],
                "album": query.get("album"),
                "neighbors": rendered,
            }
        )
    queue = {
        "schema_version": "stage5c2-similarity-review-queue-v1",
        "experiment_id": EXPERIMENT_ID,
        "status": "HUMAN_REVIEW_PENDING",
        "representative_manifest_sha256": manifest_sha,
        "query_track_count": len(cases),
        "raw_top5_judgment_count": len(review_rows),
        "unique_unordered_pair_count": len(pair_ids),
        "labels": {
            "3": "VERY_SIMILAR",
            "2": "SIMILAR",
            "1": "SOMEWHAT_RELATED",
            "0": "NOT_SIMILAR",
            "UNSURE": "SKIP_NON_NUMERIC",
        },
        "reciprocal_pair_labels_reused": True,
        "cases": cases,
    }
    atomic_json(report / "review_queue.json", queue)
    review_path = report / "human_similarity_review.csv"
    if not review_path.exists():
        with review_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(review_rows)
    return queue


def analyze_representations(
    project_root: str | Path,
    *,
    report_dir: str | Path | None = None,
    dataset_dir: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    report = Path(report_dir).resolve() if report_dir else root / REPORT_DIRECTORY
    dataset = Path(dataset_dir).resolve() if dataset_dir else root / ARTIFACT_DIRECTORY / "representations"
    manifest, manifest_sha = verify_frozen_manifest(report / "representative_manifest.json")
    selected, _ = verify_selected_sources(report / "selected_sources.json")
    selected_by_id = {row["spotify_track_id"]: row for row in selected["tracks"]}
    dataset_rows = _load_dataset(dataset)
    tracks = [row for row in manifest["tracks"] if row["spotify_track_id"] in dataset_rows]
    materialized = [dataset_rows[row["spotify_track_id"]] for row in tracks]
    if len(tracks) < 2:
        raise Stage5B1AValidationError("Stage 5C.2 requires at least two representations")
    vectors = {
        "clap": np.asarray([row["clap_embedding"] for row in materialized], dtype=np.float32),
        "muq": np.asarray([row["muq_embedding"] for row in materialized], dtype=np.float32),
    }
    matrices = {name: _matrix(vector) for name, vector in vectors.items()}
    contract = load_contract(root / "reports/holistic_stage4a_dual/audio_representation_v1.json")
    matrices["combined"] = contract.clap_weight * matrices["clap"] + contract.muq_weight * matrices["muq"]
    ids = [row["stage5c2_track_id"] for row in tracks]
    for encoder in ENCODERS:
        _write_matrix(report / f"{encoder}_similarity.csv", ids, matrices[encoder])
        _write_heatmap(report / f"{encoder}_similarity_heatmap.png", f"Stage 5C.2 {encoder.upper()} similarity", ids, matrices[encoder])
        off = matrices[encoder][np.triu_indices(len(tracks), k=1)]
        _write_distribution(report / f"{encoder}_similarity_distribution.png", f"Stage 5C.2 {encoder.upper()} pairwise similarity", off)
    neighbors = _nearest(tracks, matrices, selected_by_id)
    weights = {"clap": contract.clap_weight, "muq": contract.muq_weight}
    diagnostics = _diagnostics(tracks, materialized, vectors, matrices, neighbors, selected)
    disagreements = _disagreements(tracks, matrices, weights)
    queue = _write_review_artifacts(report, tracks, neighbors, matrices, manifest_sha)
    atomic_json(report / "nearest_neighbors.json", neighbors)
    atomic_json(report / "representation_diagnostics.json", diagnostics)
    atomic_json(report / "encoder_disagreement_analysis.json", disagreements)
    summary = {
        "schema_version": "stage5c2-representation-analysis-summary-v1",
        "experiment_id": EXPERIMENT_ID,
        "representative_manifest_sha256": manifest_sha,
        "successful_track_count": len(tracks),
        "manifest_track_count": len(manifest["tracks"]),
        "weights": weights,
        "matrix_symmetry_max_error": {name: float(np.max(np.abs(matrix - matrix.T))) for name, matrix in matrices.items()},
        "matrix_diagonal_max_error": {name: float(np.max(np.abs(np.diag(matrix) - 1))) for name, matrix in matrices.items()},
        "representation_pathology_detected": diagnostics["representation_pathology_detected"],
        "review_queue_status": queue["status"],
        "review_query_count": queue["query_track_count"],
        "raw_top5_judgment_count": queue["raw_top5_judgment_count"],
        "unique_unordered_pair_count": queue["unique_unordered_pair_count"],
    }
    atomic_json(report / "representation_analysis_summary.json", summary)
    return summary
