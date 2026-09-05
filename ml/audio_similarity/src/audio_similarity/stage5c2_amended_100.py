"""Versioned 100-track amendment for the two selector-aware recoveries."""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .stage5a_contract import load_contract
from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5c1_closeout import audit_stage5a_cache
from .stage5c2_analysis import (
    ENCODERS,
    REVIEW_COLUMNS,
    _diagnostics,
    _disagreements,
    _load_dataset,
    _matrix,
    _nearest,
    _write_distribution,
    _write_heatmap,
    _write_matrix,
    _write_review_artifacts,
)
from .stage5c2_closeout import SOURCE_MEDIA_SUFFIXES, acquisition_and_rate_metrics
from .stage5c2_discovery import verify_selected_sources
from .stage5c2_manifest import verify_frozen_manifest
from .stage5c2_pipeline import run_materialization


EXPERIMENT_ID = "STAGE5C2_REPRESENTATIVE_100_SELECTOR_AWARE_AMENDMENT_V2"
BASE_REPORT = Path("reports/stage5c2_representative_100")
FALLBACK_REPORT = Path("reports/stage5c2_selector_aware_fallback_supplement")
REPORT_DIRECTORY = Path("reports/stage5c2_representative_100_amended_v2")
SUPPLEMENT_RUN_DIRECTORY = Path(
    "reports/stage5c2_representative_100_amended_v2_supplement_materialization"
)
BASE_ARTIFACT_DIRECTORY = Path("artifacts/stage5c2_representative_100")
SUPPLEMENT_ARTIFACT_DIRECTORY = Path(
    "artifacts/stage5c2_representative_100_amended_v2/supplement"
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _write_bytes_or_verify(path: Path, value: bytes) -> None:
    if path.exists() and path.read_bytes() != value:
        raise Stage5B1AValidationError(f"refusing to replace amended artifact: {path}")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)


def _write_json_or_verify(path: Path, value: dict[str, Any]) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    _write_bytes_or_verify(path, encoded)


def _selected_row(
    target: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    candidate = result.get("selected_candidate")
    if not isinstance(candidate, dict):
        raise Stage5B1AValidationError("amendment recovery has no selected candidate")
    video_id = result.get("selected_video_id")
    return {
        "stage5c2_track_id": target["stage5c2_track_id"],
        "manifest_index": target["manifest_index"],
        "spotify_track_id": target["spotify_track_id"],
        "title": target["title"],
        "artists": target["artists"],
        "album": target.get("album"),
        "spotify_duration_ms": target.get("duration_ms"),
        "release_year": target.get("release_year"),
        "selected_youtube_video_id": video_id,
        "selected_youtube_url": f"https://www.youtube.com/watch?v={video_id}",
        "selected_candidate_rank": result["selected_rank"],
        "discovery_mode": result["discovery_mode"],
        "query_variant_index": result["query_variant_index"],
        "successful_query": result["successful_query"],
        "selector_decision": result["selector_decision"]["decision"],
        "selector_reason": result["selector_decision"]["selection_reason"],
        "candidate_metadata": candidate,
        "selection_contract": result["query_contract_id"],
        "amendment_provenance": "STAGE5C2_SELECTOR_AWARE_FALLBACK_SUPPLEMENT",
    }


def prepare_amendment(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    base = root / BASE_REPORT
    fallback = root / FALLBACK_REPORT
    report = root / REPORT_DIRECTORY
    supplement_run = root / SUPPLEMENT_RUN_DIRECTORY
    report.mkdir(parents=True, exist_ok=True)
    supplement_run.mkdir(parents=True, exist_ok=True)

    manifest_bytes = (base / "representative_manifest.json").read_bytes()
    manifest_sha_bytes = (base / "representative_manifest.sha256").read_bytes()
    _write_bytes_or_verify(report / "representative_manifest.json", manifest_bytes)
    _write_bytes_or_verify(report / "representative_manifest.sha256", manifest_sha_bytes)
    _write_bytes_or_verify(
        supplement_run / "representative_manifest.json", manifest_bytes
    )
    _write_bytes_or_verify(
        supplement_run / "representative_manifest.sha256", manifest_sha_bytes
    )
    manifest, manifest_sha = verify_frozen_manifest(
        report / "representative_manifest.json"
    )
    base_selected, base_selected_sha = verify_selected_sources(
        base / "selected_sources.json"
    )
    fallback_result = _json(fallback / "targeted_discovery.json")
    manifest_by_id = {row["stage5c2_track_id"]: row for row in manifest["tracks"]}
    recovered = []
    for row in fallback_result["tracks"]:
        result = row["selector_aware_result"]
        if not row["owner_reference_recovered"]:
            raise Stage5B1AValidationError("owner-supplied source was not recovered")
        if result["selected_video_id"] != row["owner_supplied_reference"]["owner_video_id"]:
            raise Stage5B1AValidationError(
                "selector-aware recovery does not match the owner-supplied video"
            )
        recovered.append(_selected_row(manifest_by_id[row["stage5c2_track_id"]], result))
    if len(recovered) != 2:
        raise Stage5B1AValidationError("the amendment requires exactly two recoveries")

    frozen_at = fallback_result["created_at_utc"]
    discovery_sha = file_sha256(fallback / "targeted_discovery.json")
    common = {
        "schema_version": "stage5c2-selected-sources-v1",
        "experiment_id": EXPERIMENT_ID,
        "frozen_at_utc": frozen_at,
        "representative_manifest_sha256": manifest_sha,
        "discovery_sha256": discovery_sha,
        "selector_decisions_sha256": discovery_sha,
        "post_freeze_substitutions": 0,
        "exact_id_acquisition_only": True,
    }
    supplement_selected = common | {
        "manifest_track_count": 100,
        "automated_selection_count": 2,
        "manual_tail_count": 0,
        "tracks": recovered,
    }
    _write_json_or_verify(
        supplement_run / "selected_sources.json", supplement_selected
    )
    supplement_sha = file_sha256(supplement_run / "selected_sources.json")
    _write_bytes_or_verify(
        supplement_run / "selected_sources.sha256", (supplement_sha + "\n").encode()
    )

    tracks = sorted(
        [*base_selected["tracks"], *recovered], key=lambda row: row["manifest_index"]
    )
    if len(tracks) != 100 or len({row["spotify_track_id"] for row in tracks}) != 100:
        raise Stage5B1AValidationError("amended selected sources must contain 100 tracks")
    if len({row["selected_youtube_video_id"] for row in tracks}) != 100:
        raise Stage5B1AValidationError("amended sources must use 100 distinct videos")
    full_selected = common | {
        "manifest_track_count": 100,
        "automated_selection_count": 100,
        "manual_tail_count": 0,
        "base_automated_selection_count": 98,
        "selector_aware_recovery_count": 2,
        "base_selected_sources_sha256": base_selected_sha,
        "tracks": tracks,
    }
    _write_json_or_verify(report / "selected_sources.json", full_selected)
    full_sha = file_sha256(report / "selected_sources.json")
    _write_bytes_or_verify(report / "selected_sources.sha256", (full_sha + "\n").encode())
    amendment = {
        "schema_version": "stage5c2-amended-100-manifest-v1",
        "experiment_id": EXPERIMENT_ID,
        "created_at_utc": frozen_at,
        "representative_manifest_sha256": manifest_sha,
        "base_selected_sources_sha256": base_selected_sha,
        "supplement_selected_sources_sha256": supplement_sha,
        "amended_selected_sources_sha256": full_sha,
        "base_track_count": 98,
        "recovered_track_count": 2,
        "amended_track_count": 100,
        "recovered_tracks": [
            {
                "stage5c2_track_id": row["stage5c2_track_id"],
                "spotify_track_id": row["spotify_track_id"],
                "title": row["title"],
                "selected_youtube_video_id": row["selected_youtube_video_id"],
                "successful_query": row["successful_query"],
                "selected_rank": row["selected_candidate_rank"],
            }
            for row in recovered
        ],
        "original_frozen_artifacts": {
            name: file_sha256(base / name)
            for name in (
                "representative_manifest.json",
                "discovery_results.json",
                "automated_selector_decisions.json",
                "selected_sources.json",
                "materialization_results.json",
                "cache_rerun_results.json",
                "stage5c2_metrics.json",
            )
        },
        "immutability": {
            "base_report_modified": False,
            "versioned_amendment": True,
        },
    }
    _write_json_or_verify(report / "amendment_manifest.json", amendment)
    return amendment


def materialize_recoveries(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    report = root / SUPPLEMENT_RUN_DIRECTORY
    artifacts = root / SUPPLEMENT_ARTIFACT_DIRECTORY
    first_path = report / "materialization_results.json"
    if first_path.exists():
        first = _json(first_path)
        _, selected_sha = verify_selected_sources(report / "selected_sources.json")
        if (
            first.get("run_kind") != "first"
            or first.get("selected_sources_sha256") != selected_sha
        ):
            raise Stage5B1AValidationError(
                "recorded amendment materialization does not match frozen sources"
            )
    else:
        first = run_materialization(
            root,
            run_kind="first",
            report_dir=report,
            artifact_dir=artifacts,
        )
    if first["full_materialization_successes"] != 2:
        raise Stage5B1AValidationError("both amendment tracks must materialize")
    rerun = run_materialization(
        root,
        run_kind="cache_rerun",
        report_dir=report,
        artifact_dir=artifacts,
    )
    attempts = _json(report / "acquisition_attempts.json")
    acquisition, rate = acquisition_and_rate_metrics(attempts, first)
    acquisition["experiment_id"] = EXPERIMENT_ID
    acquisition["rate_limit_metrics_path"] = str(
        (report / "rate_limit_metrics.json").relative_to(root)
    )
    rate["experiment_id"] = EXPERIMENT_ID
    cache = audit_stage5a_cache(artifacts / "representations.sqlite")
    leaked_media = sorted(
        str(path.relative_to(root))
        for directory in (report, artifacts)
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.casefold() in SOURCE_MEDIA_SUFFIXES
    )
    cleanup = _json(report / "cleanup_audit.json")
    cleanup["experiment_id"] = EXPERIMENT_ID
    cleanup["directory_level_audit"] = {
        "directories": [
            str(report.relative_to(root)),
            str(artifacts.relative_to(root)),
        ],
        "retained_source_media_files": leaked_media,
        "retained_source_media_count": len(leaked_media),
        "passed": not leaked_media,
    }
    atomic_json(report / "acquisition_metrics.json", acquisition)
    atomic_json(report / "rate_limit_metrics.json", rate)
    atomic_json(report / "cache_audit.json", cache)
    atomic_json(report / "cleanup_audit.json", cleanup)
    validation = rerun["cache_rerun_validation"]
    if (
        not rate["passed"]
        or not cache["passed"]
        or not cleanup["temporary_root_absent_after_cleanup"]
        or not cleanup["directory_level_audit"]["passed"]
        or validation["network_acquisition_attempts"]
        or validation["encoder_segments_inferred"]
        or not all(validation["representation_hash_equality"].values())
    ):
        raise Stage5B1AValidationError("amendment materialization audit failed")
    return {
        "first": first,
        "cache_rerun": rerun,
        "acquisition_metrics": acquisition,
        "rate_limit_metrics": rate,
        "cache_audit": cache,
        "cleanup_audit": cleanup,
    }


def migrate_review_labels(base_path: Path, amended_path: Path) -> dict[str, int]:
    def rows(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
                raise Stage5B1AValidationError("unexpected similarity review columns")
            return list(reader)

    source = rows(base_path)
    amended = rows(amended_path)
    labels = {
        row["pair_id"]: (
            row["human_label"], row["human_note"], row["review_timestamp"]
        )
        for row in source
        if row["human_label"]
    }
    migrated_pairs = set()
    already_present = set()
    for row in amended:
        saved = labels.get(row["pair_id"])
        if saved:
            current = (
                row["human_label"], row["human_note"], row["review_timestamp"]
            )
            if current[0]:
                if current[0] != saved[0]:
                    raise Stage5B1AValidationError(
                        f"conflicting review labels for pair {row['pair_id']}"
                    )
                already_present.add(row["pair_id"])
                continue
            row["human_label"], row["human_note"], row["review_timestamp"] = saved
            migrated_pairs.add(row["pair_id"])
    temporary = amended_path.with_suffix(amended_path.suffix + f".{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(amended)
        temporary.replace(amended_path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "source_labeled_unique_pairs": len(labels),
        "migrated_unique_pairs": len(migrated_pairs),
        "already_present_unique_pairs": len(already_present),
        "preserved_only_in_original_queue": len(
            set(labels) - migrated_pairs - already_present
        ),
    }


def analyze_amended_set(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    report = root / REPORT_DIRECTORY
    base_report = root / BASE_REPORT
    supplement_report = root / SUPPLEMENT_RUN_DIRECTORY
    manifest, manifest_sha = verify_frozen_manifest(
        report / "representative_manifest.json"
    )
    selected, selected_sha = verify_selected_sources(report / "selected_sources.json")
    amendment = _json(report / "amendment_manifest.json")
    for name, expected_sha in amendment["original_frozen_artifacts"].items():
        if file_sha256(base_report / name) != expected_sha:
            raise Stage5B1AValidationError(
                f"original frozen Stage 5C.2 artifact changed: {name}"
            )
    base_rows = _load_dataset(root / BASE_ARTIFACT_DIRECTORY / "representations")
    supplement_rows = _load_dataset(
        root / SUPPLEMENT_ARTIFACT_DIRECTORY / "representations"
    )
    overlap = set(base_rows) & set(supplement_rows)
    if overlap:
        raise Stage5B1AValidationError("base and supplement representation IDs overlap")
    dataset_rows = base_rows | supplement_rows
    tracks = [
        row for row in manifest["tracks"] if row["spotify_track_id"] in dataset_rows
    ]
    if len(tracks) != 100:
        raise Stage5B1AValidationError("amended representation set must contain 100 tracks")
    materialized = [dataset_rows[row["spotify_track_id"]] for row in tracks]
    vectors = {
        "clap": np.asarray(
            [row["clap_embedding"] for row in materialized], dtype=np.float32
        ),
        "muq": np.asarray(
            [row["muq_embedding"] for row in materialized], dtype=np.float32
        ),
    }
    matrices = {name: _matrix(vector) for name, vector in vectors.items()}
    contract = load_contract(
        root / "reports/holistic_stage4a_dual/audio_representation_v1.json"
    )
    matrices["combined"] = (
        contract.clap_weight * matrices["clap"]
        + contract.muq_weight * matrices["muq"]
    )
    ids = [row["stage5c2_track_id"] for row in tracks]
    for encoder in ENCODERS:
        _write_matrix(report / f"{encoder}_similarity.csv", ids, matrices[encoder])
        _write_heatmap(
            report / f"{encoder}_similarity_heatmap.png",
            f"Stage 5C.2 amended 100 {encoder.upper()} similarity",
            ids,
            matrices[encoder],
        )
        off = matrices[encoder][np.triu_indices(len(tracks), k=1)]
        _write_distribution(
            report / f"{encoder}_similarity_distribution.png",
            f"Stage 5C.2 amended 100 {encoder.upper()} pairwise similarity",
            off,
        )
    selected_by_id = {row["spotify_track_id"]: row for row in selected["tracks"]}
    neighbors = _nearest(tracks, matrices, selected_by_id)
    neighbors["experiment_id"] = EXPERIMENT_ID
    diagnostics = _diagnostics(
        tracks, materialized, vectors, matrices, neighbors, selected
    )
    diagnostics["experiment_id"] = EXPERIMENT_ID
    weights = {"clap": contract.clap_weight, "muq": contract.muq_weight}
    disagreements = _disagreements(tracks, matrices, weights)
    disagreements["experiment_id"] = EXPERIMENT_ID
    review_existed = (report / "human_similarity_review.csv").exists()
    queue = _write_review_artifacts(
        report, tracks, neighbors, matrices, manifest_sha
    )
    queue["experiment_id"] = EXPERIMENT_ID
    atomic_json(report / "review_queue.json", queue)
    migration = (
        {"existing_amended_review_preserved": True}
        if review_existed
        else migrate_review_labels(
            base_report / "human_similarity_review.csv",
            report / "human_similarity_review.csv",
        )
    )
    atomic_json(report / "nearest_neighbors.json", neighbors)
    atomic_json(report / "representation_diagnostics.json", diagnostics)
    atomic_json(report / "encoder_disagreement_analysis.json", disagreements)
    supplement_materialization = _json(
        supplement_report / "materialization_results.json"
    )
    supplement_rerun = _json(supplement_report / "cache_rerun_results.json")
    supplement_rate = _json(supplement_report / "rate_limit_metrics.json")
    supplement_cleanup = _json(supplement_report / "cleanup_audit.json")
    supplement_cache = _json(supplement_report / "cache_audit.json")
    summary = {
        "schema_version": "stage5c2-amended-100-analysis-v1",
        "experiment_id": EXPERIMENT_ID,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "representative_manifest_sha256": manifest_sha,
        "selected_sources_sha256": selected_sha,
        "successful_track_count": len(tracks),
        "base_representation_count": len(base_rows),
        "supplement_representation_count": len(supplement_rows),
        "weights": weights,
        "matrix_symmetry_max_error": {
            name: float(np.max(np.abs(matrix - matrix.T)))
            for name, matrix in matrices.items()
        },
        "matrix_diagonal_max_error": {
            name: float(np.max(np.abs(np.diag(matrix) - 1)))
            for name, matrix in matrices.items()
        },
        "representation_pathology_detected": diagnostics[
            "representation_pathology_detected"
        ],
        "review_query_count": queue["query_track_count"],
        "raw_top5_judgment_count": queue["raw_top5_judgment_count"],
        "unique_unordered_pair_count": queue["unique_unordered_pair_count"],
        "review_label_migration": migration,
        "supplement_reliability": {
            "full_materialization_successes": supplement_materialization[
                "full_materialization_successes"
            ],
            "full_materialization_failures": supplement_materialization[
                "full_materialization_failures"
            ],
            "live_acquisition_attempts": supplement_rate[
                "total_live_download_attempts"
            ],
            "minimum_start_spacing_seconds": supplement_rate[
                "minimum_start_to_start_spacing_seconds"
            ],
            "rate_limit_passed": supplement_rate["passed"],
            "cache_audit_passed": supplement_cache["passed"],
            "cleanup_passed": supplement_cleanup["directory_level_audit"]["passed"],
            "cache_rerun_network_attempts": supplement_rerun[
                "cache_rerun_validation"
            ]["network_acquisition_attempts"],
            "cache_rerun_encoder_segments_inferred": supplement_rerun[
                "cache_rerun_validation"
            ]["encoder_segments_inferred"],
        },
    }
    atomic_json(report / "amended_analysis_summary.json", summary)
    _write_report(report / "stage5c2_amended_report.md", summary)
    _write_artifact_manifest(root, report)
    return summary


def _write_report(path: Path, summary: dict[str, Any]) -> None:
    reliability = summary["supplement_reliability"]
    lines = [
        "# Stage 5C.2 Representative 100 — Selector-Aware Amendment V2",
        "",
        "This versioned amendment adds the two owner-confirmed manual-tail "
        "recoveries without rewriting the original frozen 98-materialization "
        "execution.",
        "",
        f"- Review tracks: {summary['review_query_count']}",
        f"- Base representations reused: {summary['base_representation_count']}",
        f"- New representations materialized: {summary['supplement_representation_count']}",
        f"- Supplemental exact-ID materialization: "
        f"{reliability['full_materialization_successes']}/2",
        f"- Supplemental minimum live-start spacing: "
        f"{reliability['minimum_start_spacing_seconds']:.6f} seconds",
        f"- Supplemental cache rerun network/inference: "
        f"{reliability['cache_rerun_network_attempts']}/"
        f"{reliability['cache_rerun_encoder_segments_inferred']}",
        f"- Supplemental cleanup passed: `{reliability['cleanup_passed']}`",
        f"- Representation pathology detected: `{summary['representation_pathology_detected']}`",
        f"- Raw Top-5 rows: {summary['raw_top5_judgment_count']}",
        f"- Unique unordered review pairs: {summary['unique_unordered_pair_count']}",
        f"- Label migration: `{json.dumps(summary['review_label_migration'], sort_keys=True)}`",
        "",
        "The original `stage5c2_representative_100` report remains the immutable "
        "execution record. This amended dataset is the default human-review surface.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_artifact_manifest(root: Path, report: Path) -> None:
    names = (
        "representative_manifest.json",
        "representative_manifest.sha256",
        "amendment_manifest.json",
        "selected_sources.json",
        "selected_sources.sha256",
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
        "clap_similarity_distribution.png",
        "muq_similarity_distribution.png",
        "combined_similarity_distribution.png",
        "amended_analysis_summary.json",
        "stage5c2_amended_report.md",
    )
    supplement = root / SUPPLEMENT_RUN_DIRECTORY
    supplemental_names = (
        "selected_sources.json",
        "selected_sources.sha256",
        "acquisition_attempts.json",
        "acquisition_metrics.json",
        "rate_limit_metrics.json",
        "materialization_results.json",
        "cache_rerun_results.json",
        "cleanup_audit.json",
        "cache_audit.json",
    )
    artifacts = {
        name: {
            "path": str((report / name).relative_to(root)),
            "sha256": file_sha256(report / name),
            "size_bytes": (report / name).stat().st_size,
        }
        for name in names
    }
    artifacts["human_similarity_review.csv"]["mutable_human_evidence"] = True
    artifacts["human_similarity_review.csv"]["hash_scope"] = "INITIAL_QUEUE_STATE"
    atomic_json(
        report / "artifact_manifest.json",
        {
            "schema_version": "stage5c2-amended-100-artifact-manifest-v1",
            "experiment_id": EXPERIMENT_ID,
            "artifacts": artifacts,
            "supplemental_materialization_artifacts": {
                name: {
                    "path": str((supplement / name).relative_to(root)),
                    "sha256": file_sha256(supplement / name),
                    "size_bytes": (supplement / name).stat().st_size,
                }
                for name in supplemental_names
            },
        },
    )


def run_amendment(project_root: str | Path) -> dict[str, Any]:
    prepare = prepare_amendment(project_root)
    materialization = materialize_recoveries(project_root)
    analysis = analyze_amended_set(project_root)
    return {
        "experiment_id": EXPERIMENT_ID,
        "amendment_manifest": prepare,
        "materialization": {
            "successes": materialization["first"]["full_materialization_successes"],
            "rate_limit": materialization["rate_limit_metrics"],
            "cache_audit": materialization["cache_audit"],
            "cache_rerun": materialization["cache_rerun"][
                "cache_rerun_validation"
            ],
        },
        "analysis": analysis,
    }
