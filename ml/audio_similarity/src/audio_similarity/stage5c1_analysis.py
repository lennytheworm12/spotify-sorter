"""Similarity and representation-sanity diagnostics for Stage 5C.1."""
from __future__ import annotations

import csv
import itertools
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
from PIL import Image, ImageDraw, ImageFont

from .stage5a_contract import load_contract
from .stage5b1a_models import Stage5B1AValidationError
from .stage5b1b_artifacts import atomic_json
from .stage5c1_manifest import EXPERIMENT_ID, verify_frozen_manifest


ENCODERS = ("clap", "muq", "combined")


def _load_dataset(dataset_dir: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for path in sorted(dataset_dir.glob("part-*.parquet")):
        for row in pq.read_table(path).to_pylist():
            if row["status"] != "SUCCESS":
                continue
            stable_id = str(row["stable_track_id"])
            if stable_id in rows:
                raise Stage5B1AValidationError(f"duplicate representation row: {stable_id}")
            rows[stable_id] = row
    return rows


def _matrix(vectors: np.ndarray) -> np.ndarray:
    if vectors.ndim != 2 or vectors.shape[0] < 1:
        raise Stage5B1AValidationError("similarity analysis requires a non-empty vector matrix")
    if not np.isfinite(vectors).all():
        raise Stage5B1AValidationError("representation vectors contain NaN/Inf")
    norms = np.linalg.norm(vectors.astype(np.float64), axis=1)
    if np.any(norms <= 0):
        raise Stage5B1AValidationError("representation vectors contain a zero vector")
    normalized = vectors / norms[:, None]
    result = normalized @ normalized.T
    result = (result + result.T) / 2.0
    np.fill_diagonal(result, 1.0)
    return result


def _write_matrix_csv(path: Path, track_ids: list[str], matrix: np.ndarray) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["stage5c1_track_id", *track_ids])
        for track_id, row in zip(track_ids, matrix, strict=True):
            writer.writerow([track_id, *(f"{float(value):.9f}" for value in row)])


def _color(value: float, minimum: float, maximum: float) -> tuple[int, int, int]:
    fraction = 0.5 if maximum <= minimum else (value - minimum) / (maximum - minimum)
    fraction = min(1.0, max(0.0, fraction))
    if fraction < 0.5:
        local = fraction * 2.0
        return (int(35 + 210 * local), int(80 + 165 * local), 245)
    local = (fraction - 0.5) * 2.0
    return (245, int(245 - 190 * local), int(245 - 190 * local))


def _write_heatmap(
    path: Path,
    *,
    title: str,
    track_ids: list[str],
    groups: list[str],
    matrix: np.ndarray,
) -> None:
    cell = 22
    left = 92
    top = 70
    legend = 54
    size = len(track_ids) * cell
    image = Image.new("RGB", (left + size + 20, top + size + legend), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    minimum = float(np.min(matrix))
    maximum = float(np.max(matrix))
    draw.text((10, 10), title, fill="black", font=font)
    draw.text((10, 27), f"cosine scale {minimum:.3f} to {maximum:.3f}; ordered A-E", fill="black", font=font)
    for index, track_id in enumerate(track_ids):
        short = track_id.removeprefix("stage5c1_")
        draw.text((left - 31, top + index * cell + 6), short, fill="black", font=font)
        draw.text((left + index * cell + 4, top - 18), short, fill="black", font=font)
    for row in range(len(track_ids)):
        for column in range(len(track_ids)):
            x0 = left + column * cell
            y0 = top + row * cell
            draw.rectangle(
                (x0, y0, x0 + cell - 1, y0 + cell - 1),
                fill=_color(float(matrix[row, column]), minimum, maximum),
            )
    for boundary in range(5, len(track_ids), 5):
        offset = boundary * cell
        draw.line((left + offset, top, left + offset, top + size), fill="black", width=2)
        draw.line((left, top + offset, left + size, top + offset), fill="black", width=2)
    for index, group in enumerate(groups[::5]):
        center = left + (index * 5 + 2.5) * cell
        draw.text((center - 3, top + size + 8), group, fill="black", font=font)
    image.save(path, format="PNG", optimize=True)


def _pair_values(matrix: np.ndarray, left: list[int], right: list[int] | None = None) -> list[float]:
    if right is None:
        return [float(matrix[a, b]) for a, b in itertools.combinations(left, 2)]
    return [float(matrix[a, b]) for a in left for b in right]


def _stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "minimum": None, "maximum": None, "stddev": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": len(values),
        "mean": float(array.mean()),
        "minimum": float(array.min()),
        "maximum": float(array.max()),
        "stddev": float(array.std()),
    }


def _nearest_neighbors(
    tracks: list[dict[str, Any]], matrices: dict[str, np.ndarray]
) -> dict[str, Any]:
    output = []
    for index, track in enumerate(tracks):
        encoder_neighbors = {}
        for encoder, matrix in matrices.items():
            ordered = sorted(
                (candidate for candidate in range(len(tracks)) if candidate != index),
                key=lambda candidate: (-float(matrix[index, candidate]), candidate),
            )[:5]
            encoder_neighbors[encoder] = [
                {
                    "rank": rank,
                    "stage5c1_track_id": tracks[candidate]["stage5c1_track_id"],
                    "spotify_track_id": tracks[candidate]["spotify_track_id"],
                    "title": tracks[candidate]["title"],
                    "artists": tracks[candidate]["artists"],
                    "group": tracks[candidate]["curation_group"],
                    "similarity": float(matrix[index, candidate]),
                }
                for rank, candidate in enumerate(ordered, start=1)
            ]
        output.append(
            {
                "stage5c1_track_id": track["stage5c1_track_id"],
                "spotify_track_id": track["spotify_track_id"],
                "title": track["title"],
                "artists": track["artists"],
                "group": track["curation_group"],
                "neighbors": encoder_neighbors,
            }
        )
    return {
        "schema_version": "stage5c1-nearest-neighbors-v1",
        "experiment_id": EXPERIMENT_ID,
        "self_matches_excluded": True,
        "tracks": output,
    }


def _group_metrics(
    tracks: list[dict[str, Any]], matrices: dict[str, np.ndarray]
) -> dict[str, Any]:
    indexes: dict[str, list[int]] = defaultdict(list)
    for index, track in enumerate(tracks):
        indexes[track["curation_group"]].append(index)
    within = {
        group: {encoder: _stats(_pair_values(matrix, members)) for encoder, matrix in matrices.items()}
        for group, members in indexes.items()
    }
    requested = (("C", "D"), ("A", "E"), ("C", "E"), ("D", "E"))
    between = {
        f"{left}_vs_{right}": {
            encoder: _stats(_pair_values(matrix, indexes[left], indexes[right]))
            for encoder, matrix in matrices.items()
        }
        for left, right in requested
        if left in indexes and right in indexes
    }
    return {
        "schema_version": "stage5c1-group-similarity-metrics-v1",
        "experiment_id": EXPERIMENT_ID,
        "successful_track_count": len(tracks),
        "within_group": within,
        "between_group": between,
        "interpretation_boundary": "Descriptive sanity diagnostics on a curated N=25 set; no statistical significance claim.",
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
                "left_track_id": tracks[left]["stage5c1_track_id"],
                "left_title": tracks[left]["title"],
                "right_track_id": tracks[right]["stage5c1_track_id"],
                "right_title": tracks[right]["title"],
                "clap_similarity": clap,
                "muq_similarity": muq,
                "combined_similarity": float(matrices["combined"][left, right]),
                "clap_minus_muq": clap - muq,
            }
        )
    clap_over = sorted(pairs, key=lambda row: (-row["clap_minus_muq"], row["left_track_id"], row["right_track_id"]))[:10]
    muq_over = sorted(pairs, key=lambda row: (row["clap_minus_muq"], row["left_track_id"], row["right_track_id"]))[:10]
    clap_off = np.asarray([row["clap_similarity"] for row in pairs])
    muq_off = np.asarray([row["muq_similarity"] for row in pairs])
    weighted_clap_variation = float(np.std(clap_off) * weights["clap"])
    weighted_muq_variation = float(np.std(muq_off) * weights["muq"])
    return {
        "schema_version": "stage5c1-encoder-disagreement-v1",
        "experiment_id": EXPERIMENT_ID,
        "weights": weights,
        "largest_clap_over_muq": clap_over,
        "largest_muq_over_clap": muq_over,
        "weighted_off_diagonal_variation": {
            "clap": weighted_clap_variation,
            "muq": weighted_muq_variation,
            "clap_share": weighted_clap_variation / (weighted_clap_variation + weighted_muq_variation)
            if weighted_clap_variation + weighted_muq_variation
            else None,
        },
        "combined_is_weighted_score_not_fused_vector": True,
    }


def _collapse_diagnostics(
    tracks: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    vectors: dict[str, np.ndarray],
    matrices: dict[str, np.ndarray],
    neighbors: dict[str, Any],
) -> dict[str, Any]:
    pathologies: list[str] = []
    vector_checks = {}
    for encoder in ("clap", "muq"):
        norms = np.linalg.norm(vectors[encoder].astype(np.float64), axis=1)
        vector_checks[encoder] = {
            "zero_vectors": int(np.sum(norms == 0)),
            "non_finite_values": int(np.sum(~np.isfinite(vectors[encoder]))),
            "maximum_norm_error": float(np.max(np.abs(norms - 1.0))),
            "unique_embedding_hashes": len({row[f"{encoder}_embedding_sha256"] for row in rows}),
        }
        if vector_checks[encoder]["zero_vectors"]:
            pathologies.append(f"{encoder.upper()}_ZERO_VECTOR")
        if vector_checks[encoder]["non_finite_values"]:
            pathologies.append(f"{encoder.upper()}_NON_FINITE")
        if vector_checks[encoder]["unique_embedding_hashes"] != len(rows):
            pathologies.append(f"{encoder.upper()}_REPEATED_EMBEDDING_HASH")

    similarity_checks = {}
    for encoder, matrix in matrices.items():
        off = matrix[np.triu_indices(len(matrix), k=1)]
        stats = _stats([float(value) for value in off])
        similarity_checks[encoder] = stats | {
            "pairs_near_one": int(np.sum(off > 0.999)),
            "suspiciously_narrow_variance": bool(np.std(off) < 1e-4),
            "similarities_clustered_near_one": bool(np.mean(off) > 0.99),
        }
        if similarity_checks[encoder]["suspiciously_narrow_variance"]:
            pathologies.append(f"{encoder.upper()}_SUSPICIOUSLY_NARROW_VARIANCE")
        if similarity_checks[encoder]["similarities_clustered_near_one"]:
            pathologies.append(f"{encoder.upper()}_SIMILARITIES_NEAR_ONE")

    top1_counts = {}
    for encoder in ENCODERS:
        values = [row["neighbors"][encoder][0]["stage5c1_track_id"] for row in neighbors["tracks"]]
        top1_counts[encoder] = dict(Counter(values).most_common())
        if values and Counter(values).most_common(1)[0][1] > max(5, math.ceil(len(values) / 2)):
            pathologies.append(f"{encoder.upper()}_SAME_NEIGHBOR_DOMINANCE")

    representation_ids = [row["representation_identity"] for row in rows]
    source_hashes = [row["source_audio_sha256"] for row in rows]
    if len(set(representation_ids)) != len(representation_ids):
        pathologies.append("REPEATED_REPRESENTATION_IDENTITY")
    if len(set(source_hashes)) != len(source_hashes):
        pathologies.append("SOURCE_AUDIO_REUSED_ACROSS_TRACKS")
    matrices_identical = bool(np.allclose(matrices["clap"], matrices["muq"], atol=1e-7))
    if matrices_identical:
        pathologies.append("CLAP_MUQ_OUTPUTS_IDENTICAL")
    return {
        "schema_version": "stage5c1-representation-collapse-diagnostics-v1",
        "experiment_id": EXPERIMENT_ID,
        "successful_track_count": len(tracks),
        "vector_checks": vector_checks,
        "similarity_checks": similarity_checks,
        "clap_muq_similarity_matrices_identical": matrices_identical,
        "unique_representation_identities": len(set(representation_ids)),
        "unique_source_audio_hashes": len(set(source_hashes)),
        "top1_neighbor_frequency": top1_counts,
        "pathologies_detected": sorted(set(pathologies)),
        "collapse_pathology_detected": bool(pathologies),
    }


def _write_human_review(
    path: Path, tracks: list[dict[str, Any]], neighbors: dict[str, Any]
) -> None:
    fields = (
        "stage5c1_track_id",
        "spotify_track_id",
        "spotify_target",
        "group",
        "top5_combined_neighbors",
        "expected_group_relationship",
        "inspection_priority",
        "analyst_assessment",
        "observed_relationship_note",
        "human_sanity_label",
        "human_note",
    )
    neighbor_rows = {row["spotify_track_id"]: row for row in neighbors["tracks"]}
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for track in tracks:
            nearest = neighbor_rows[track["spotify_track_id"]]["neighbors"]["combined"]
            same_group_top5 = sum(row["group"] == track["curation_group"] for row in nearest)
            priority = "REVIEW" if same_group_top5 == 0 and track["curation_group"] != "E" else "ROUTINE"
            distinct_neighbor_groups = len({row["group"] for row in nearest})
            if track["curation_group"] == "E":
                assessment = "NEGATIVE_CONTROL_VARIED"
                observed = (
                    f"Top-5 spans {distinct_neighbor_groups} groups; local acoustic, rap, piano, or ballad affinities may still be musically meaningful."
                )
            elif same_group_top5 >= 2:
                assessment = "EXPECTED_STRUCTURE_VISIBLE"
                observed = f"{same_group_top5}/5 combined neighbors are from the intended group."
            elif same_group_top5 == 1:
                assessment = "MIXED_BUT_PLAUSIBLE"
                observed = (
                    "One same-group neighbor appears in the Top-5; cross-group matches should be inspected for shared production or instrumentation."
                )
            else:
                assessment = "NEEDS_HUMAN_REVIEW"
                observed = "No same-group track appears in the combined Top-5."
            writer.writerow(
                {
                    "stage5c1_track_id": track["stage5c1_track_id"],
                    "spotify_track_id": track["spotify_track_id"],
                    "spotify_target": f"{track['title']} — {', '.join(track['artists'])}",
                    "group": track["curation_group"],
                    "top5_combined_neighbors": " | ".join(
                        f"{row['stage5c1_track_id']} {row['title']} [{row['group']}]={row['similarity']:.4f}"
                        for row in nearest
                    ),
                    "expected_group_relationship": track["expected_relationship_notes"],
                    "inspection_priority": priority,
                    "analyst_assessment": assessment,
                    "observed_relationship_note": observed,
                    "human_sanity_label": "",
                    "human_note": "",
                }
            )


def analyze_representations(
    project_root: str | Path,
    *,
    dataset_dir: str | Path | None = None,
    report_dir: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    report = Path(report_dir) if report_dir else root / "reports/stage5c1_curated_25_materialization"
    dataset = Path(dataset_dir) if dataset_dir else root / "artifacts/stage5c1_curated_25_materialization/representations"
    if not report.is_absolute():
        report = root / report
    if not dataset.is_absolute():
        dataset = root / dataset
    manifest, manifest_sha = verify_frozen_manifest(report / "curated_manifest.json")
    contract = load_contract(root / "reports/holistic_stage4a_dual/audio_representation_v1.json")
    dataset_rows = _load_dataset(dataset)
    tracks = [track for track in manifest["tracks"] if track["spotify_track_id"] in dataset_rows]
    rows = [dataset_rows[track["spotify_track_id"]] for track in tracks]
    if not tracks:
        raise Stage5B1AValidationError("no successful representations are available")
    vectors = {
        "clap": np.asarray([row["clap_embedding"] for row in rows], dtype=np.float32),
        "muq": np.asarray([row["muq_embedding"] for row in rows], dtype=np.float32),
    }
    matrices = {encoder: _matrix(array) for encoder, array in vectors.items()}
    matrices["combined"] = (
        contract.clap_weight * matrices["clap"] + contract.muq_weight * matrices["muq"]
    )
    track_ids = [track["stage5c1_track_id"] for track in tracks]
    groups = [track["curation_group"] for track in tracks]
    for encoder in ENCODERS:
        _write_matrix_csv(report / f"{encoder}_similarity.csv", track_ids, matrices[encoder])
        _write_heatmap(
            report / f"{encoder}_similarity_heatmap.png",
            title=f"Stage 5C.1 {encoder.upper()} similarity",
            track_ids=track_ids,
            groups=groups,
            matrix=matrices[encoder],
        )

    neighbors = _nearest_neighbors(tracks, matrices)
    group_metrics = _group_metrics(tracks, matrices)
    weights = {"clap": contract.clap_weight, "muq": contract.muq_weight}
    disagreements = _disagreements(tracks, matrices, weights)
    collapse = _collapse_diagnostics(tracks, rows, vectors, matrices, neighbors)
    atomic_json(report / "nearest_neighbors.json", neighbors)
    atomic_json(report / "group_similarity_metrics.json", group_metrics)
    atomic_json(report / "encoder_disagreement_analysis.json", disagreements)
    atomic_json(report / "representation_collapse_diagnostics.json", collapse)
    _write_human_review(report / "human_sanity_review.csv", tracks, neighbors)
    result = {
        "schema_version": "stage5c1-analysis-summary-v1",
        "experiment_id": EXPERIMENT_ID,
        "manifest_sha256": manifest_sha,
        "successful_track_count": len(tracks),
        "failed_track_count": len(manifest["tracks"]) - len(tracks),
        "weights": weights,
        "matrix_symmetry_max_error": {
            encoder: float(np.max(np.abs(matrix - matrix.T)))
            for encoder, matrix in matrices.items()
        },
        "matrix_diagonal_max_error": {
            encoder: float(np.max(np.abs(np.diag(matrix) - 1.0)))
            for encoder, matrix in matrices.items()
        },
        "collapse_diagnostics": collapse,
    }
    atomic_json(report / "representation_analysis_summary.json", result)
    return result
