"""Fair-corpus retrieval analysis and blinded queue generation for Stage 5E.1."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5c2_analysis import canonical_pair_id
from .stage5e1_cache import Stage5E1Cache, representation_identity
from .stage5e1_contract import EXPERIMENT_ID, REPORT_DIRECTORY
from .stage5e1_materialize import ARTIFACT_DIRECTORY, _identity_fields, _load_frozen_inputs


ARMS = ("A", "B", "C", "D")
MODES = ("CLAP", "COMBINED")
REVIEW_COLUMNS = (
    "review_schema_version",
    "pair_id",
    "left_spotify_id",
    "right_spotify_id",
    "human_label",
    "human_note",
    "review_timestamp",
    "label_provenance",
)


def _matrix(vectors: np.ndarray) -> np.ndarray:
    values = np.asarray(vectors, dtype=np.float64)
    if values.ndim != 2 or len(values) < 2 or not np.isfinite(values).all():
        raise Stage5B1AValidationError("invalid Stage 5E.1 vector matrix")
    norms = np.linalg.norm(values, axis=1)
    if np.any(norms <= 0):
        raise Stage5B1AValidationError("zero Stage 5E.1 vector")
    values /= norms[:, None]
    result = values @ values.T
    result = (result + result.T) / 2
    np.fill_diagonal(result, 1.0)
    return result.astype(np.float32)


def _duplicate_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left["source_sha256"] == right["source_sha256"]
        or left["youtube_video_id"] == right["youtube_video_id"]
    )


def _neighbors(
    tracks: list[dict[str, Any]], matrices: dict[tuple[str, str], np.ndarray]
) -> dict[str, Any]:
    rows = []
    for query_index, query in enumerate(tracks):
        retrievals = {}
        for (arm, mode), matrix in matrices.items():
            ordered = sorted(
                (
                    index for index, candidate in enumerate(tracks)
                    if index != query_index and not _duplicate_pair(query, candidate)
                ),
                key=lambda index: (-float(matrix[query_index, index]), tracks[index]["spotify_track_id"]),
            )[:10]
            retrievals[f"{arm}_{mode}"] = [
                {
                    "rank": rank,
                    "spotify_track_id": tracks[index]["spotify_track_id"],
                    "title": tracks[index]["title"],
                    "artists": tracks[index]["artists"],
                    "similarity": float(matrix[query_index, index]),
                }
                for rank, index in enumerate(ordered, start=1)
            ]
        rows.append(
            {
                "spotify_track_id": query["spotify_track_id"],
                "title": query["title"],
                "artists": query["artists"],
                "retrievals": retrievals,
            }
        )
    return {
        "schema_version": "stage5e1-nearest-neighbors-v1",
        "experiment_id": EXPERIMENT_ID,
        "top_k_materialized": 10,
        "self_matches_excluded": True,
        "duplicate_policy": "same retained source SHA-256 or same YouTube ID excluded",
        "tracks": rows,
    }


def _overlap(neighbors: dict[str, Any]) -> dict[str, Any]:
    comparisons = []
    for arm in ("B", "C", "D"):
        for mode in MODES:
            overlaps = []
            rank_changes = []
            for track in neighbors["tracks"]:
                baseline = [row["spotify_track_id"] for row in track["retrievals"][f"A_{mode}"][:5]]
                current = [row["spotify_track_id"] for row in track["retrievals"][f"{arm}_{mode}"][:5]]
                overlaps.append(len(set(baseline) & set(current)))
                baseline_ranks = {spotify_id: index for index, spotify_id in enumerate(baseline, 1)}
                rank_changes.extend(abs(index - baseline_ranks[spotify_id]) for index, spotify_id in enumerate(current, 1) if spotify_id in baseline_ranks)
            comparisons.append(
                {
                    "comparison": f"{arm}_{mode}_VS_A_{mode}",
                    "mean_top5_overlap_count": float(np.mean(overlaps)),
                    "mean_top5_jaccard": float(np.mean([value / (10 - value) for value in overlaps])),
                    "mean_absolute_rank_change_for_shared_top5": float(np.mean(rank_changes)) if rank_changes else None,
                }
            )
    for arm in ARMS:
        overlaps = []
        for track in neighbors["tracks"]:
            clap = {
                row["spotify_track_id"] for row in track["retrievals"][f"{arm}_CLAP"][:5]
            }
            combined = {
                row["spotify_track_id"]
                for row in track["retrievals"][f"{arm}_COMBINED"][:5]
            }
            overlaps.append(len(clap & combined))
        comparisons.append(
            {
                "comparison": f"{arm}_CLAP_VS_{arm}_COMBINED",
                "mean_top5_overlap_count": float(np.mean(overlaps)),
                "mean_top5_jaccard": float(
                    np.mean([value / (10 - value) for value in overlaps])
                ),
            }
        )
    return {"schema_version": "stage5e1-retrieval-overlap-v1", "comparisons": comparisons}


def _historical_labels(root: Path, current_by_id: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
    report = root / "reports/stage5c2_representative_100_amended_v2"
    selected_path = report / "selected_sources.json"
    review_path = report / "human_similarity_review.csv"
    if not selected_path.is_file() or not review_path.is_file():
        return {}
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    old_sources = {
        row["spotify_track_id"]: row["selected_youtube_video_id"] for row in selected["tracks"]
    }
    labels = {}
    with review_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            label = row.get("human_label", "").strip().upper()
            left, right = row["query_spotify_id"], row["neighbor_spotify_id"]
            if not label or left not in current_by_id or right not in current_by_id:
                continue
            if (
                current_by_id[left]["youtube_video_id"] != old_sources.get(left)
                or current_by_id[right]["youtube_video_id"] != old_sources.get(right)
            ):
                continue
            pair_id = canonical_pair_id(left, right)
            evidence = {"label": label, "note": row.get("human_note", "")}
            if pair_id in labels and labels[pair_id] != evidence:
                raise Stage5B1AValidationError("historical reciprocal labels disagree")
            labels[pair_id] = evidence
    return labels


def build_review_queue(
    root: Path,
    tracks: list[dict[str, Any]],
    neighbors: dict[str, Any],
) -> dict[str, Any]:
    by_id = {row["spotify_track_id"]: row for row in tracks}
    origins: dict[str, list[dict[str, Any]]] = {}
    pair_members: dict[str, tuple[str, str]] = {}
    raw = 0
    for query in neighbors["tracks"]:
        for retrieval_id, rows in query["retrievals"].items():
            arm, mode = retrieval_id.split("_", 1)
            for row in rows[:5]:
                raw += 1
                pair_id = canonical_pair_id(query["spotify_track_id"], row["spotify_track_id"])
                pair_members[pair_id] = tuple(sorted((query["spotify_track_id"], row["spotify_track_id"])))
                origins.setdefault(pair_id, []).append(
                    {
                        "query_spotify_id": query["spotify_track_id"],
                        "arm": arm,
                        "score_mode": mode,
                        "rank": row["rank"],
                        "similarity": row["similarity"],
                    }
                )
    seed = "stage5e1-blinded-review-order-v1"
    ordered = sorted(pair_members, key=lambda pair_id: hashlib.sha256(f"{seed}\0{pair_id}".encode()).hexdigest())
    history = _historical_labels(root, by_id)
    pairs = []
    for index, pair_id in enumerate(ordered, 1):
        left_id, right_id = pair_members[pair_id]
        pairs.append(
            {
                "review_index": index,
                "pair_id": pair_id,
                "left": {key: by_id[left_id].get(key) for key in ("spotify_track_id", "title", "artists", "album", "retained_source_path", "source_sha256", "youtube_video_id")},
                "right": {key: by_id[right_id].get(key) for key in ("spotify_track_id", "title", "artists", "album", "retained_source_path", "source_sha256", "youtube_video_id")},
                "origins": sorted(origins[pair_id], key=lambda row: (row["arm"], row["score_mode"], row["query_spotify_id"], row["rank"])),
                "historical_label_available": pair_id in history,
            }
        )
    return {
        "schema_version": "stage5e1-blinded-review-queue-v1",
        "experiment_id": EXPERIMENT_ID,
        "order_seed": seed,
        "display_blinding": ["arm", "score", "originating_rank", "model_identity"],
        "raw_directional_top5_relationships": raw,
        "unique_unordered_pair_count": len(pairs),
        "reused_historical_label_count": sum(row["historical_label_available"] for row in pairs),
        "new_pair_count": sum(not row["historical_label_available"] for row in pairs),
        "pairs": pairs,
    }


def _initialize_review_state(root: Path, queue: dict[str, Any]) -> Path:
    state = root / ".research_audio/stage5e1_review/human_similarity_review.csv"
    state.parent.mkdir(parents=True, exist_ok=True)
    tracks = {side["spotify_track_id"]: side for pair in queue["pairs"] for side in (pair["left"], pair["right"])}
    history = _historical_labels(root, tracks)
    existing = {}
    if state.is_file():
        with state.open(encoding="utf-8", newline="") as handle:
            existing = {row["pair_id"]: row for row in csv.DictReader(handle)}
    rows = []
    for pair in queue["pairs"]:
        pair_id = pair["pair_id"]
        left, right = pair["left"]["spotify_track_id"], pair["right"]["spotify_track_id"]
        if pair_id in existing:
            prior = existing[pair_id]
            if (prior["left_spotify_id"], prior["right_spotify_id"]) != (left, right):
                raise Stage5B1AValidationError("mutable Stage 5E.1 review pair identity changed")
            rows.append(prior)
        else:
            inherited = history.get(pair_id)
            rows.append(
                {
                    "review_schema_version": "stage5e1-human-similarity-review-v1",
                    "pair_id": pair_id,
                    "left_spotify_id": left,
                    "right_spotify_id": right,
                    "human_label": inherited["label"] if inherited else "",
                    "human_note": inherited["note"] if inherited else "",
                    "review_timestamp": "",
                    "label_provenance": "STAGE5C2_OWNER_REUSE" if inherited else "",
                }
            )
    temporary = state.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(state)
    return state


def analyze_retrieval(root: str | Path) -> dict[str, Any]:
    project = Path(root).resolve()
    manifest, config, plans = _load_frozen_inputs(project)
    report = project / REPORT_DIRECTORY
    config_sha = file_sha256(report / "experiment_config.json")
    plan_by_id = {row["spotify_track_id"]: row["plan"] for row in plans["tracks"]}
    source_tracks = {row["spotify_track_id"]: row for row in manifest["tracks"]}
    vectors: dict[str, dict[str, np.ndarray]] = {arm: {} for arm in (*ARMS, "MUQ")}
    with Stage5E1Cache(project / ARTIFACT_DIRECTORY / "representations.sqlite") as cache:
        for track in manifest["tracks"]:
            plan_sha = plan_by_id[track["spotify_track_id"]]["sampling_plan_sha256"]
            for arm in ARMS:
                checkpoint_sha = config["arms"][arm]["checkpoint_sha256"]
                identity, _ = _identity_fields(track, arm, config_sha, plan_sha, checkpoint_sha)
                vector = cache.vector(identity)
                if vector is not None:
                    vectors[arm][track["spotify_track_id"]] = vector
            muq_checkpoint = load_muq_checkpoint_identity(project)
            identity, _ = _identity_fields(track, "MUQ", config_sha, plan_sha, muq_checkpoint)
            vector = cache.vector(identity)
            if vector is not None:
                vectors["MUQ"][track["spotify_track_id"]] = vector
    common = set(source_tracks)
    for values in vectors.values():
        common &= values.keys()
    ids = sorted(common)
    if len(ids) < 2:
        raise Stage5B1AValidationError("Stage 5E.1 common represented corpus is incomplete")
    tracks = [source_tracks[spotify_id] for spotify_id in ids]
    matrices: dict[tuple[str, str], np.ndarray] = {}
    muq = _matrix(np.stack([vectors["MUQ"][spotify_id] for spotify_id in ids]))
    for arm in ARMS:
        clap = _matrix(np.stack([vectors[arm][spotify_id] for spotify_id in ids]))
        combined = float(config["similarity"]["clap_weight"]) * clap + float(config["similarity"]["muq_weight"]) * muq
        matrices[(arm, "CLAP")] = clap
        matrices[(arm, "COMBINED")] = combined.astype(np.float32)
    # A single compressed, indexed matrix bundle avoids committing nine large,
    # redundant text matrices for the retained corpus.
    np.savez_compressed(report / "similarity_matrices.npz", spotify_ids=np.asarray(ids), muq=muq, **{f"{arm}_{mode}".lower(): matrix for (arm, mode), matrix in matrices.items()})
    nearest = _neighbors(tracks, matrices)
    overlap = _overlap(nearest)
    queue = build_review_queue(project, tracks, nearest)
    atomic_json(report / "nearest_neighbors.json", nearest)
    atomic_json(report / "retrieval_overlap.json", overlap)
    atomic_json(report / "review_queue.json", queue)
    state_path = _initialize_review_state(project, queue)
    diagnostics = representation_diagnostics(ids, vectors, matrices, muq, source_tracks)
    atomic_json(report / "representation_diagnostics.json", diagnostics)
    status = {
        "schema_version": "stage5e1-analysis-summary-v1",
        "frozen_corpus_count": manifest["track_count"],
        "successes_per_representation": {key: len(value) for key, value in vectors.items()},
        "common_comparison_count": len(ids),
        "excluded_from_common": [
            {
                "spotify_track_id": spotify_id,
                "missing_representations": [arm for arm in (*ARMS, "MUQ") if spotify_id not in vectors[arm]],
            }
            for spotify_id in sorted(set(source_tracks) - common)
        ],
        "raw_directional_top5_relationships": queue["raw_directional_top5_relationships"],
        "unique_unordered_pairs": queue["unique_unordered_pair_count"],
        "reused_labels": queue["reused_historical_label_count"],
        "new_pairs_requiring_judgment": queue["new_pair_count"],
        "mutable_review_state": str(state_path.relative_to(project)),
        "human_review_status": "HUMAN_REVIEW_PENDING" if queue["new_pair_count"] else "HUMAN_REVIEW_COMPLETE",
    }
    atomic_json(report / "human_review_metrics.json", status)
    return status


def load_muq_checkpoint_identity(root: Path) -> str:
    contract = json.loads((root / "reports/holistic_stage4a_dual/audio_representation_v1.json").read_text(encoding="utf-8"))
    payload = contract["encoders"]["muq"]
    canonical = json.dumps(
        {key: payload[key] for key in ("repository", "revision", "weights_sha256", "config_sha256")},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def representation_diagnostics(
    ids: list[str],
    vectors: dict[str, dict[str, np.ndarray]],
    matrices: dict[tuple[str, str], np.ndarray],
    muq: np.ndarray,
    source_tracks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    pathologies = []
    checks = {}
    for arm in (*ARMS, "MUQ"):
        matrix = np.stack([vectors[arm][spotify_id] for spotify_id in ids])
        norms = np.linalg.norm(matrix.astype(np.float64), axis=1)
        hashes = [hashlib.sha256(row.astype("<f4").tobytes()).hexdigest() for row in matrix]
        groups: dict[str, list[str]] = {}
        for spotify_id, digest in zip(ids, hashes, strict=True):
            groups.setdefault(digest, []).append(spotify_id)
        unexpected_duplicates = [
            members for members in groups.values()
            if len(members) > 1
            and len({source_tracks[spotify_id]["source_sha256"] for spotify_id in members}) > 1
        ]
        checks[arm] = {
            "non_finite_values": int(np.sum(~np.isfinite(matrix))),
            "zero_vectors": int(np.sum(norms == 0)),
            "maximum_norm_error": float(np.max(np.abs(norms - 1))),
            "unique_embedding_count": len(set(hashes)),
            "unexpected_duplicate_embedding_groups": unexpected_duplicates,
        }
        if checks[arm]["non_finite_values"] or checks[arm]["zero_vectors"]:
            pathologies.append(f"{arm}_INVALID_VECTOR")
        if unexpected_duplicates:
            pathologies.append(f"{arm}_DUPLICATE_VECTOR")
    similarity = {}
    for key, matrix in [*((f"{arm}_{mode}", value) for (arm, mode), value in matrices.items()), ("MUQ", muq)]:
        off = matrix[np.triu_indices(len(matrix), 1)]
        similarity[key] = {
            "symmetry_max_error": float(np.max(np.abs(matrix - matrix.T))),
            "diagonal_max_error": float(np.max(np.abs(np.diag(matrix) - 1))),
            "off_diagonal_mean": float(np.mean(off)),
            "off_diagonal_stddev": float(np.std(off)),
            "off_diagonal_minimum": float(np.min(off)),
            "off_diagonal_maximum": float(np.max(off)),
        }
        if similarity[key]["off_diagonal_stddev"] < 1e-6:
            pathologies.append(f"{key}_SIMILARITY_COLLAPSE")
    identical_clap_muq = {arm: bool(np.array_equal(matrices[(arm, "CLAP")], muq)) for arm in ARMS}
    if any(identical_clap_muq.values()):
        pathologies.append("CLAP_MUQ_OUTPUT_IDENTITY")
    universal_neighbors = {}
    for (arm, mode), matrix in matrices.items():
        counts: Counter[str] = Counter()
        for index, spotify_id in enumerate(ids):
            ordered = sorted(
                (candidate for candidate in range(len(ids)) if candidate != index),
                key=lambda candidate: (-float(matrix[index, candidate]), ids[candidate]),
            )[:5]
            counts.update(ids[candidate] for candidate in ordered)
        universal_neighbors[f"{arm}_{mode}"] = [
            {"spotify_track_id": spotify_id, "top5_appearance_count": count}
            for spotify_id, count in counts.most_common(10)
        ]
    return {
        "schema_version": "stage5e1-representation-diagnostics-v1",
        "track_count": len(ids),
        "vector_checks": checks,
        "similarity_checks": similarity,
        "clap_muq_matrices_identical": identical_clap_muq,
        "most_repeated_top5_neighbors": universal_neighbors,
        "pathologies": sorted(set(pathologies)),
        "representation_pathology_detected": bool(pathologies),
    }
