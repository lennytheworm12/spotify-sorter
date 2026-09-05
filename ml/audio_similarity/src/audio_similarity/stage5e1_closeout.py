"""Diagnostics, human metrics, and closeout report for Stage 5E.1."""
from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5e1_analysis import ARMS, MODES
from .stage5e1_contract import EXPERIMENT_ID, REPORT_DIRECTORY
from .stage5e1_materialize import ARTIFACT_DIRECTORY


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def human_metrics(root: str | Path) -> dict[str, Any]:
    project = Path(root).resolve()
    report = project / REPORT_DIRECTORY
    queue = _load(report / "review_queue.json")
    state = project / ".research_audio/stage5e1_review/human_similarity_review.csv"
    with state.open(encoding="utf-8", newline="") as handle:
        reviews = {row["pair_id"]: row for row in csv.DictReader(handle)}
    ratings = {
        pair_id: int(row["human_label"])
        for pair_id, row in reviews.items()
        if row["human_label"] in {"1", "2", "3", "4", "5"}
    }
    unsure = {pair_id for pair_id, row in reviews.items() if row["human_label"] == "UNSURE"}
    observations: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_query: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for pair in queue["pairs"]:
        pair_id = pair["pair_id"]
        for origin in pair["origins"]:
            key = (origin["arm"], origin["score_mode"])
            row = {
                "query_spotify_id": origin["query_spotify_id"],
                "rank": origin["rank"],
                "pair_id": pair_id,
                "rating": ratings.get(pair_id),
                "unsure": pair_id in unsure,
                "similarity": float(origin["similarity"]),
            }
            observations[key].append(row)
            by_query[(*key, origin["query_spotify_id"])].append(row)
    modes = []
    query_means: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for arm in ARMS:
        for mode in MODES:
            rows = observations[(arm, mode)]
            numeric = [row for row in rows if row["rating"] is not None]
            top1 = [row["rating"] for row in numeric if row["rank"] == 1]
            per_rank = {}
            for rank in range(1, 6):
                values = [row["rating"] for row in numeric if row["rank"] == rank]
                per_rank[str(rank)] = {"reviewed": len(values), "mean": float(np.mean(values)) if values else None}
            for (key_arm, key_mode, query), query_rows in by_query.items():
                if (key_arm, key_mode) != (arm, mode):
                    continue
                values = [row["rating"] for row in query_rows if row["rating"] is not None]
                if len(values) == len(query_rows):
                    query_means[(arm, mode)][query] = float(np.mean(values))
            modes.append(
                {
                    "arm": arm,
                    "score_mode": mode,
                    "raw_top5_relationships": len(rows),
                    "numeric_review_count": len(numeric),
                    "unsure_count": sum(row["unsure"] for row in rows),
                    "coverage": len(numeric) / len(rows) if rows else 0,
                    "mean_top1_rating": float(np.mean(top1)) if top1 else None,
                    "mean_top5_rating": float(np.mean([row["rating"] for row in numeric])) if numeric else None,
                    "fraction_at_least_3": float(np.mean([row["rating"] >= 3 for row in numeric])) if numeric else None,
                    "fraction_at_least_4": float(np.mean([row["rating"] >= 4 for row in numeric])) if numeric else None,
                    "score_human_pearson_correlation": (
                        float(np.corrcoef(
                            [row["similarity"] for row in numeric],
                            [row["rating"] for row in numeric],
                        )[0, 1])
                        if len(numeric) >= 2
                        and np.std([row["similarity"] for row in numeric]) > 0
                        and np.std([row["rating"] for row in numeric]) > 0
                        else None
                    ),
                    "rating_by_rank": per_rank,
                }
            )
    paired = []
    for arm in ("B", "C", "D"):
        for mode in MODES:
            baseline = query_means[("A", mode)]
            current = query_means[(arm, mode)]
            common = sorted(baseline.keys() & current.keys())
            differences = [current[key] - baseline[key] for key in common]
            paired.append(
                {
                    "comparison": f"{arm}_{mode}_VS_A_{mode}",
                    "complete_query_count": len(common),
                    "mean_paired_top5_rating_difference": float(np.mean(differences)) if differences else None,
                }
            )
    reviewed = sum(bool(row["human_label"]) for row in reviews.values())
    payload = {
        "schema_version": "stage5e1-human-review-metrics-v1",
        "experiment_id": EXPERIMENT_ID,
        "status": "HUMAN_REVIEW_COMPLETE" if reviewed == len(reviews) else "HUMAN_REVIEW_PENDING",
        "unique_pair_count": len(reviews),
        "reviewed_pair_count": reviewed,
        "numeric_pair_count": len(ratings),
        "unsure_pair_count": len(unsure),
        "inherited_label_count": sum(row["label_provenance"] == "STAGE5C2_OWNER_REUSE" for row in reviews.values()),
        "new_stage5e1_label_count": sum(row["label_provenance"] == "STAGE5E1_OWNER" for row in reviews.values()),
        "metrics_by_arm_and_mode": modes,
        "paired_differences_vs_a": paired,
        "dependence_note": "Reciprocal pairs are deduplicated, but tracks and pairs recur across queries; rows are not independent samples.",
        "winner_declared": False,
    }
    atomic_json(report / "human_review_metrics.json", payload)
    return payload


def _performance(project: Path) -> dict[str, Any]:
    cache = project / ARTIFACT_DIRECTORY / "representations.sqlite"
    connection = sqlite3.connect(cache)
    connection.row_factory = sqlite3.Row
    try:
        vectors = [dict(row) for row in connection.execute(
            "SELECT arm,status,count(*) AS count,sum(view_count) AS views,sum(inference_seconds) AS seconds FROM vectors GROUP BY arm,status"
        )]
        views = [dict(row) for row in connection.execute(
            "SELECT v.view_kind,count(*) AS count,sum(v.inference_seconds) AS seconds FROM views v GROUP BY v.view_kind"
        )]
    finally:
        connection.close()
    return {
        "schema_version": "stage5e1-performance-metrics-v1",
        "network_downloads": 0,
        "vector_counts_and_inference": vectors,
        "view_counts_and_inference": views,
        "cache_size_bytes": cache.stat().st_size,
        "wal_size_bytes": cache.with_name(cache.name + "-wal").stat().st_size if cache.with_name(cache.name + "-wal").exists() else 0,
    }


def _disagreements(project: Path) -> dict[str, Any]:
    report = project / REPORT_DIRECTORY
    with np.load(report / "similarity_matrices.npz") as data:
        ids = [str(value) for value in data["spotify_ids"]]
        muq = data["muq"]
        rows = []
        upper = np.triu_indices(len(ids), 1)
        for arm in ARMS:
            clap = data[f"{arm.lower()}_clap"]
            delta = clap - muq
            ordered = sorted(zip(upper[0], upper[1], strict=True), key=lambda pair: (-abs(float(delta[pair])), ids[pair[0]], ids[pair[1]]))[:50]
            rows.append(
                {
                    "arm": arm,
                    "largest_absolute_disagreements": [
                        {
                            "left_spotify_id": ids[left],
                            "right_spotify_id": ids[right],
                            "clap_similarity": float(clap[left, right]),
                            "muq_similarity": float(muq[left, right]),
                            "clap_minus_muq": float(delta[left, right]),
                        }
                        for left, right in ordered
                    ],
                }
            )
    return {"schema_version": "stage5e1-encoder-disagreement-v1", "arms": rows}


def _cleanup(project: Path) -> dict[str, Any]:
    scratch = project / ARTIFACT_DIRECTORY / "scratch"
    leaked = sorted(str(path.relative_to(project)) for path in scratch.rglob("*") if path.is_file()) if scratch.exists() else []
    return {
        "schema_version": "stage5e1-cleanup-audit-v1",
        "retained_sources_deleted": 0,
        "network_downloads": 0,
        "scratch_root": str(scratch.relative_to(project)),
        "scratch_files_remaining": leaked,
        "status": "PASSED" if not leaked else "FAILED",
    }


def _artifact_manifest(report: Path) -> dict[str, Any]:
    excluded = {"artifact_manifest.json"}
    files = []
    for path in sorted(report.iterdir()):
        if not path.is_file() or path.name in excluded:
            continue
        files.append({"path": path.name, "size_bytes": path.stat().st_size, "sha256": file_sha256(path)})
    return {
        "schema_version": "stage5e1-artifact-manifest-v1",
        "experiment_id": EXPERIMENT_ID,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }


def finalize_stage5e1(root: str | Path) -> dict[str, Any]:
    project = Path(root).resolve()
    report = project / REPORT_DIRECTORY
    required = [
        "corpus_manifest.json", "experiment_config.json", "materialization_results.json",
        "cache_rerun_results.json", "nearest_neighbors.json", "retrieval_overlap.json",
        "review_queue.json", "representation_diagnostics.json", "similarity_matrices.npz",
    ]
    missing = [name for name in required if not (report / name).is_file()]
    if missing:
        raise Stage5B1AValidationError(f"Stage 5E.1 closeout missing artifacts: {missing}")
    performance = _performance(project)
    cleanup = _cleanup(project)
    disagreements = _disagreements(project)
    review = human_metrics(project)
    atomic_json(report / "performance_metrics.json", performance)
    atomic_json(report / "cleanup_audit.json", cleanup)
    atomic_json(report / "encoder_disagreement_analysis.json", disagreements)
    manifest = _load(report / "corpus_manifest.json")
    materialization = _load(report / "materialization_results.json")
    diagnostics = _load(report / "representation_diagnostics.json")
    queue = _load(report / "review_queue.json")
    cache_rerun = _load(report / "cache_rerun_results.json")
    result = {
        "schema_version": "stage5e1-closeout-v1",
        "experiment_id": EXPERIMENT_ID,
        "corpus_track_count": manifest["track_count"],
        "cache_status": cache_rerun["status"],
        "representation_pathology_detected": diagnostics["representation_pathology_detected"],
        "review_status": review["status"],
        "review_pair_count": queue["unique_unordered_pair_count"],
        "network_downloads": materialization["network_downloads"],
        "winner_declared": False,
        "production_activation": False,
        "status": "REPRESENTATIONS_READY_HUMAN_REVIEW_PENDING" if review["status"] == "HUMAN_REVIEW_PENDING" else "HUMAN_REVIEW_COMPLETE_ANALYSIS_READY",
    }
    report_text = f"""# Stage 5E.1 four-arm retrieval comparison

**Status:** `{result['status']}`

## Controlled design

- A/C use the frozen music-specialized HTSAT-base checkpoint.
- B/D use the matched official general-audio HTSAT-tiny fusion checkpoint and identical frozen global/front/middle/back views.
- A versus C isolates centered-window versus full-song chunk-mean sampling within one checkpoint.
- B versus D isolates learned native AFF versus equal embedding mean within one checkpoint.
- Cross-pair comparisons retain a checkpoint and architecture confound and must not be described as pure aggregation effects.
- MuQ and the CLAP/MuQ weights are unchanged.

## Corpus and execution

- Frozen eligible tracks: {manifest['track_count']}
- Network downloads: 0
- Cache rerun: `{cache_rerun['status']}`
- Representation pathology detected: `{diagnostics['representation_pathology_detected']}`
- Scratch cleanup: `{cleanup['status']}`

## Retrieval review

- Raw directional Top-5 relationships: {queue['raw_directional_top5_relationships']}
- Unique unordered pairs: {queue['unique_unordered_pair_count']}
- Reused compatible owner labels: {queue['reused_historical_label_count']}
- New judgments required: {queue['new_pair_count']}
- Human status: `{review['status']}`

No arm is selected or production-activated by this experiment. Human review is evidence collection and no tuning is performed.
"""
    (report / "experiment_report.md").write_text(report_text, encoding="utf-8")
    atomic_json(report / "artifact_manifest.json", _artifact_manifest(report))
    return result
