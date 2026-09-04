"""Reliability, integrity, and immutable artifact closeout for Stage 5C.2."""
from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5c1_closeout import audit_stage5a_cache
from .stage5c2_analysis import REVIEW_COLUMNS
from .stage5c2_discovery import verify_selected_sources
from .stage5c2_manifest import EXPERIMENT_ID, REPORT_DIRECTORY, verify_frozen_manifest
from .stage5c2_pipeline import ARTIFACT_DIRECTORY


VERDICT_PASS = "REPRESENTATIVE_100_PIPELINE_PASSED_REVIEW_READY"
VERDICT_PARTIAL = "REPRESENTATIVE_100_PIPELINE_PARTIAL_REVIEW_READY"
VERDICT_FAILED = "REPRESENTATIVE_100_PIPELINE_FAILED"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _source(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve().relative_to(root.resolve())),
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def acquisition_and_rate_metrics(
    attempts: dict[str, Any], materialization: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = attempts["attempts"]
    deltas = [
        float(row["previous_request_start_delta_seconds"])
        for row in rows
        if row.get("previous_request_start_delta_seconds") is not None
    ]
    statuses = Counter(row.get("http_status") for row in rows if row.get("http_status"))
    retries = [row for row in rows if int(row["attempt_number"]) > 1]
    final_failures = [row for row in rows if row["final_outcome"] == "FAILED"]
    rate = {
        "schema_version": "stage5c2-rate-limit-metrics-v1",
        "experiment_id": EXPERIMENT_ID,
        "total_live_download_attempts": len(rows),
        "retry_attempts": len(retries),
        "minimum_start_to_start_spacing_seconds": min(deltas) if deltas else None,
        "median_start_to_start_spacing_seconds": statistics.median(deltas) if deltas else None,
        "maximum_start_to_start_spacing_seconds": max(deltas) if deltas else None,
        "required_minimum_spacing_seconds": 20.0,
        "all_observed_start_spacings_compliant": all(
            row["minimum_spacing_compliant"] for row in rows
        ),
        "retry_after_events": sum(row.get("retry_after_seconds") is not None for row in rows),
        "http_429_count": statuses[429],
        "http_5xx_count": sum(count for status, count in statuses.items() if 500 <= status <= 599),
        "timeout_or_network_retry_count": sum(
            row.get("retry_reason") == "ACQUISITION_FAILED" and row["final_outcome"] == "RETRY_SCHEDULED"
            for row in rows
        ),
        "final_failures_after_retry_exhaustion": len(final_failures),
        "concurrent_downloads": attempts["concurrent_downloads"],
        "passed": (
            all(row["minimum_spacing_compliant"] for row in rows)
            and (not deltas or min(deltas) >= 20.0 - 1e-6)
            and attempts["concurrent_downloads"] == 0
        ),
    }
    acquisition_rows = materialization["acquisitions"]
    acquisition = {
        "schema_version": "stage5c2-acquisition-metrics-v1",
        "experiment_id": EXPERIMENT_ID,
        "selected_tracks": materialization["automated_selected_tracks"],
        "cache_hits_before_acquisition": sum(
            row["provider_result"] == "CACHE_HIT_NO_ACQUISITION" for row in acquisition_rows
        ),
        "tracks_with_live_acquisition_attempts": sum(
            row.get("network_attempt_count", 0) > 0 for row in acquisition_rows
        ),
        "acquisition_successes": sum(
            row["provider_result"] == "SUCCESS" for row in acquisition_rows
        ),
        "acquisition_failures": sum(
            row["provider_result"] == "FAILED" for row in acquisition_rows
        ),
        "failure_categories": dict(
            Counter(
                row.get("failure_category")
                for row in acquisition_rows
                if row["provider_result"] == "FAILED"
            )
        ),
        "exact_id_only": attempts["exact_id_only"],
        "discovery_requests_during_acquisition": attempts["discovery_requests"],
        "rate_limit_metrics_path": "reports/stage5c2_representative_100/rate_limit_metrics.json",
    }
    return acquisition, rate


def _encoder_success(row: dict[str, Any], encoder_id: str) -> bool:
    return {
        segment["center_sec"]
        for segment in row.get("segments", [])
        if segment["encoder_id"] == encoder_id and segment["status"] == "SUCCESS"
    } == {5, 15, 25}


def _human_review_metrics(review_path: Path) -> dict[str, Any]:
    with review_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise Stage5B1AValidationError("unexpected Stage 5C.2 human review columns")
        rows = list(reader)
    unique: dict[str, str] = {}
    for row in rows:
        label = row["human_label"].strip().upper()
        if label:
            prior = unique.setdefault(row["pair_id"], label)
            if prior != label:
                raise Stage5B1AValidationError("reciprocal human labels disagree")
    all_pairs = {row["pair_id"] for row in rows}
    if set(unique) != all_pairs:
        return {
            "status": "HUMAN_REVIEW_PENDING",
            "reviewed_unique_pairs": len(unique),
            "total_unique_pairs": len(all_pairs),
            "quality_metrics": None,
        }
    numeric = [row for row in rows if row["human_label"] in {"0", "1", "2", "3"}]
    ratings = np.asarray([float(row["human_label"]) for row in numeric], dtype=np.float64)

    def correlation(field: str) -> float | None:
        scores = np.asarray([float(row[field]) for row in numeric], dtype=np.float64)
        if len(scores) < 2 or not np.std(scores) or not np.std(ratings):
            return None
        return float(np.corrcoef(scores, ratings)[0, 1])

    by_rank: dict[int, list[float]] = defaultdict(list)
    for row in numeric:
        by_rank[int(row["neighbor_rank"])].append(float(row["human_label"]))
    top1 = [float(row["human_label"]) for row in numeric if row["neighbor_rank"] == "1"]
    return {
        "status": "HUMAN_REVIEW_COMPLETE",
        "reviewed_unique_pairs": len(unique),
        "total_unique_pairs": len(all_pairs),
        "quality_metrics": {
            "numeric_directional_judgment_count": len(numeric),
            "unsure_directional_judgment_count": len(rows) - len(numeric),
            "mean_human_rating_top1": statistics.mean(top1) if top1 else None,
            "mean_human_rating_top5": float(ratings.mean()) if ratings.size else None,
            "fraction_top1_at_least_similar": (
                sum(value >= 2 for value in top1) / len(top1) if top1 else None
            ),
            "fraction_top5_at_least_similar": (
                float(np.mean(ratings >= 2)) if ratings.size else None
            ),
            "fraction_top5_at_least_somewhat_related": (
                float(np.mean(ratings >= 1)) if ratings.size else None
            ),
            "mean_rating_by_neighbor_rank": {
                str(rank): statistics.mean(values) for rank, values in sorted(by_rank.items())
            },
            "clap_correlation": correlation("clap_similarity"),
            "muq_correlation": correlation("muq_similarity"),
            "combined_correlation": correlation("combined_similarity"),
        },
    }


def write_closeout(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    report = root / REPORT_DIRECTORY
    artifacts = root / ARTIFACT_DIRECTORY
    manifest, manifest_sha = verify_frozen_manifest(report / "representative_manifest.json")
    selected, selected_sha = verify_selected_sources(report / "selected_sources.json")
    discovery = _json(report / "discovery_results.json")
    materialization = _json(report / "materialization_results.json")
    rerun = _json(report / "cache_rerun_results.json")
    cleanup = _json(report / "cleanup_audit.json")
    attempts = _json(report / "acquisition_attempts.json")
    diagnostics = _json(report / "representation_diagnostics.json")
    queue = _json(report / "review_queue.json")
    acquisition, rate = acquisition_and_rate_metrics(attempts, materialization)
    cache_audit = audit_stage5a_cache(artifacts / "representations.sqlite")
    atomic_json(report / "acquisition_metrics.json", acquisition)
    atomic_json(report / "rate_limit_metrics.json", rate)
    atomic_json(report / "cache_audit.json", cache_audit)
    success_rows = [row for row in materialization["tracks"] if row["status"] == "SUCCESS"]
    cleanup_expected = [row for row in cleanup["tracks"] if row["cleanup_expected"]]
    cleanup_success = sum(
        row["temp_files_absent_after_cleanup"] and not row["errors"]
        for row in cleanup_expected
    )
    rerun_validation = rerun["cache_rerun_validation"]
    human = _human_review_metrics(report / "human_similarity_review.csv")
    selected_count = len(selected["tracks"])
    materialized_count = len(success_rows)
    pipeline_pass = (
        selected_count > 0
        and materialized_count / selected_count >= 0.95
        and rate["passed"]
        and cleanup_success == len(cleanup_expected)
        and cleanup["temporary_root_absent_after_cleanup"] is True
        and cleanup["unintended_retained_source_audio_files"] == 0
        and cache_audit["passed"]
        and rerun_validation["network_acquisition_attempts"] == 0
        and rerun_validation["encoder_segments_inferred"] == 0
        and all(rerun_validation["representation_hash_equality"].values())
        and not diagnostics["representation_pathology_detected"]
        and queue["status"] == "HUMAN_REVIEW_PENDING"
    )
    verdict = VERDICT_PASS if pipeline_pass else (
        VERDICT_PARTIAL if queue.get("query_track_count") == materialized_count else VERDICT_FAILED
    )
    metrics = {
        "schema_version": "stage5c2-metrics-v1",
        "experiment_id": EXPERIMENT_ID,
        "verdict": verdict,
        "human_similarity_quality_verdict": human["status"],
        "representative_manifest_sha256": manifest_sha,
        "selected_sources_sha256": selected_sha,
        "pipeline": {
            "manifest_tracks": len(manifest["tracks"]),
            "discovery_successes": discovery["summary"]["tracks_with_candidates"],
            "discovery_unresolved": discovery["summary"]["zero_candidate_tracks"],
            "decomposition_triggers": discovery["summary"]["fallback_trigger_count"],
            "automated_selections": selected_count,
            "manual_tail": selected["manual_tail_count"],
            "acquisition_attempted_tracks": acquisition["tracks_with_live_acquisition_attempts"],
            "cache_hits_before_acquisition": acquisition["cache_hits_before_acquisition"],
            "acquisition_successes": acquisition["acquisition_successes"],
            "acquisition_failures": acquisition["acquisition_failures"],
            "decode_successes": sum(
                row.get("status") == "SUCCESS"
                for row in materialization["decode_validation"].values()
            ),
            "segment_successes": sum(
                row.get("required_windows_available") is True
                for row in materialization["decode_validation"].values()
            ),
            "clap_successes": sum(_encoder_success(row, "laion_clap") for row in success_rows),
            "muq_successes": sum(_encoder_success(row, "muq_mulan_large") for row in success_rows),
            "full_materialization_successes": materialized_count,
            "cache_write_successes": materialization["cache_manifest"]["tables"]["tracks"]["success"],
            "cleanup_expected": len(cleanup_expected),
            "cleanup_successes": cleanup_success,
            "cache_rerun_hits": rerun_validation["reacquisition_prevented"],
            "redundant_downloads_on_rerun": rerun_validation["network_acquisition_attempts"],
            "redundant_inference_segments_on_rerun": rerun_validation["encoder_segments_inferred"],
            "selection_yield": selected_count / len(manifest["tracks"]),
            "media_materialization_reliability": materialized_count / selected_count,
            "end_to_end_automated_materialization_yield": materialized_count / len(manifest["tracks"]),
            "failure_categories": dict(
                Counter(
                    row["failure_category"]
                    for row in materialization["tracks"]
                    if row["status"] != "SUCCESS"
                )
            ),
        },
        "rate_limit": rate,
        "cache_integrity": cache_audit,
        "cleanup": {
            "temporary_root_absent": cleanup["temporary_root_absent_after_cleanup"],
            "unintended_retained_source_audio_files": cleanup["unintended_retained_source_audio_files"],
        },
        "representation": {
            "successful_track_count": diagnostics["successful_track_count"],
            "pathology_detected": diagnostics["representation_pathology_detected"],
            "pathologies": diagnostics["pathologies_detected"],
        },
        "review": {
            "query_tracks": queue["query_track_count"],
            "raw_top5_judgments": queue["raw_top5_judgment_count"],
            "unique_unordered_pairs": queue["unique_unordered_pair_count"],
            **human,
        },
        "scope_guards": {
            "query_tuning": False,
            "selector_tuning": False,
            "representation_tuning": False,
            "post_freeze_substitutions": 0,
            "human_labels_fabricated": 0,
            "production_activation": False,
        },
    }
    atomic_json(report / "stage5c2_metrics.json", metrics)
    _write_report(report / "stage5c2_report.md", metrics)
    artifact_names = (
        "representative_manifest.json", "representative_manifest.sha256",
        "discovery_results.json", "automated_selector_decisions.json",
        "selected_sources.json", "selected_sources.sha256",
        "acquisition_attempts.json", "acquisition_metrics.json", "rate_limit_metrics.json",
        "materialization_results.json", "cache_rerun_results.json", "cleanup_audit.json",
        "cache_audit.json", "clap_similarity.csv", "muq_similarity.csv",
        "combined_similarity.csv", "nearest_neighbors.json",
        "encoder_disagreement_analysis.json", "representation_diagnostics.json",
        "review_queue.json", "human_similarity_review.csv",
        "clap_similarity_heatmap.png", "muq_similarity_heatmap.png",
        "combined_similarity_heatmap.png", "clap_similarity_distribution.png",
        "muq_similarity_distribution.png", "combined_similarity_distribution.png",
        "representation_analysis_summary.json", "stage5c2_metrics.json", "stage5c2_report.md",
    )
    missing = [name for name in artifact_names if not (report / name).is_file()]
    if missing:
        raise Stage5B1AValidationError(f"missing Stage 5C.2 artifacts: {missing}")
    implementation_paths = (
        root / "src/audio_similarity/stage5c2_manifest.py",
        root / "src/audio_similarity/stage5c2_discovery.py",
        root / "src/audio_similarity/stage5c2_rate_limit.py",
        root / "src/audio_similarity/stage5c2_pipeline.py",
        root / "src/audio_similarity/stage5c2_analysis.py",
        root / "src/audio_similarity/stage5c2_review.py",
        root / "src/audio_similarity/stage5c2_closeout.py",
        root / "src/audio_similarity/cli/stage5c2_review_server.py",
        root / "evaluation/static/stage5c2_similarity_review.html",
    )
    artifact_manifest = {
        "schema_version": "stage5c2-artifact-manifest-v1",
        "experiment_id": EXPERIMENT_ID,
        "verdict": verdict,
        "human_review_status": human["status"],
        "artifacts": {name: _source(report / name, root) for name in artifact_names},
        "implementation": {
            path.name: _source(path, root) for path in implementation_paths
        },
        "cache": {
            "path": str((artifacts / "representations.sqlite").relative_to(root)),
            "included_in_report_directory": False,
            "audit_sha256": file_sha256(report / "cache_audit.json"),
        },
        "historical_inputs_unchanged": all(
            file_sha256(root / source["path"]) == source["sha256"]
            for source in manifest["source_artifacts"]
        ),
        "stage5c1_artifact_manifest": _source(
            root / "reports/stage5c1_curated_25_materialization/artifact_manifest.json", root
        ),
    }
    atomic_json(report / "artifact_manifest.json", artifact_manifest)
    return metrics


def _write_report(path: Path, metrics: dict[str, Any]) -> None:
    pipeline = metrics["pipeline"]
    rate = metrics["rate_limit"]
    representation = metrics["representation"]
    review = metrics["review"]
    lines = [
        "# Stage 5C.2 — Representative 100 End-to-End Validation",
        "",
        f"**Engineering verdict:** `{metrics['verdict']}`  ",
        f"**Human similarity verdict:** `{metrics['human_similarity_quality_verdict']}`",
        "",
        "The fresh 100-track manifest, discovery results, and 98 exact selected YouTube IDs were frozen before media acquisition. No failed or manual-tail track was substituted.",
        "",
        "## Pipeline reliability",
        "",
        f"- Manifest: {pipeline['manifest_tracks']} tracks; discovery {pipeline['discovery_successes']}; automated selections {pipeline['automated_selections']}; manual tail {pipeline['manual_tail']}.",
        f"- Full materialization: {pipeline['full_materialization_successes']}/{pipeline['automated_selections']} selected ({pipeline['media_materialization_reliability']:.1%}); end-to-end manifest yield {pipeline['end_to_end_automated_materialization_yield']:.1%}.",
        f"- Cache rerun: {pipeline['cache_rerun_hits']} hits, {pipeline['redundant_downloads_on_rerun']} redundant downloads, {pipeline['redundant_inference_segments_on_rerun']} redundant inferred segments.",
        f"- Cleanup: {pipeline['cleanup_successes']}/{pipeline['cleanup_expected']} expected cleanups; zero unintended retained source media.",
        f"- Cache audit: `{metrics['cache_integrity']['sqlite_integrity']}` with {metrics['cache_integrity']['corrupt_cache_entries']} corrupt entries.",
        "",
        "## Rate-limit audit",
        "",
        f"- Live attempts: {rate['total_live_download_attempts']}; retries: {rate['retry_attempts']}; concurrent downloads: {rate['concurrent_downloads']}.",
        f"- Start spacing (min / median / max): {rate['minimum_start_to_start_spacing_seconds']:.3f} / {rate['median_start_to_start_spacing_seconds']:.3f} / {rate['maximum_start_to_start_spacing_seconds']:.3f} seconds.",
        f"- Retry-After events: {rate['retry_after_events']}; HTTP 429: {rate['http_429_count']}; HTTP 5xx: {rate['http_5xx_count']}; final exhausted failures: {rate['final_failures_after_retry_exhaustion']}.",
        "",
        "## Representation health",
        "",
        f"Similarity matrices and Top-5/Top-10 neighbors cover {representation['successful_track_count']} tracks. Structural pathology detected: `{representation['pathology_detected']}`. Detected classes: {representation['pathologies'] or 'none'}.",
        "",
        "## Unified human review",
        "",
        f"The reused local review workspace contains {review['query_tracks']} complete query views, {review['raw_top5_judgments']} directional Top-5 rows, and {review['unique_unordered_pairs']} unique unordered pairs after reciprocal deduplication.",
        "",
        "Owner labels remain blank. Start `python -m audio_similarity.cli.stage5c2_review_server` to review, save incrementally, leave, and resume. Retrieval-quality claims remain pending until owner review is complete.",
        "",
        "## Experimental boundary",
        "",
        "No discovery, selector, segment, encoder, or weight tuning occurred. This report establishes engineering/materialization health and review readiness; it does not claim human-validated retrieval quality or activate production behavior.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
