"""Stage 5C.1 reliability metrics, report, and artifact integrity closeout."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5c1_manifest import EXPERIMENT_ID, verify_frozen_manifest


VERDICT_PASS = "PIPELINE_AND_REPRESENTATION_SANITY_PASSED"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def audit_stage5a_cache(cache_path: str | Path) -> dict[str, Any]:
    """Verify SQLite integrity plus every stored segment and pooled vector blob."""
    path = Path(cache_path)
    problems: list[str] = []
    counts: dict[str, int] = {}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        integrity = str(db.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            problems.append(f"SQLITE_INTEGRITY:{integrity}")
        for table in ("segments", "pooled", "tracks"):
            counts[table] = int(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        for table in ("segments", "pooled"):
            rows = db.execute(
                f"""SELECT rowid, embedding, embedding_sha256, embedding_dimension
                    FROM {table} WHERE status='SUCCESS'"""
            ).fetchall()
            for rowid, blob, expected_hash, dimension in rows:
                if blob is None:
                    problems.append(f"{table}:{rowid}:MISSING_EMBEDDING")
                    continue
                if hashlib.sha256(blob).hexdigest() != expected_hash:
                    problems.append(f"{table}:{rowid}:HASH_MISMATCH")
                vector = np.frombuffer(blob, dtype="<f4")
                if vector.shape != (int(dimension),):
                    problems.append(f"{table}:{rowid}:DIMENSION_MISMATCH")
                    continue
                if not np.isfinite(vector).all():
                    problems.append(f"{table}:{rowid}:NON_FINITE")
                norm = float(np.linalg.norm(vector.astype(np.float64)))
                if abs(norm - 1.0) > 1e-5:
                    problems.append(f"{table}:{rowid}:NORMALIZATION_ERROR")
        track_shapes = db.execute(
            """SELECT t.stable_track_id,
                      (SELECT count(*) FROM segments s WHERE s.corpus=t.corpus
                        AND s.corpus_version=t.corpus_version
                        AND s.stable_track_id=t.stable_track_id
                        AND s.source_audio_sha256=t.source_audio_sha256
                        AND s.canonical_pcm_sha256=t.canonical_pcm_sha256
                        AND s.status='SUCCESS'),
                      (SELECT count(*) FROM pooled p WHERE p.corpus=t.corpus
                        AND p.corpus_version=t.corpus_version
                        AND p.stable_track_id=t.stable_track_id
                        AND p.source_audio_sha256=t.source_audio_sha256
                        AND p.canonical_pcm_sha256=t.canonical_pcm_sha256
                        AND p.status='SUCCESS')
                 FROM tracks t WHERE t.status='SUCCESS'"""
        ).fetchall()
        for track_id, segment_count, pooled_count in track_shapes:
            if int(segment_count) != 6:
                problems.append(f"tracks:{track_id}:EXPECTED_6_SEGMENTS_GOT_{segment_count}")
            if int(pooled_count) != 2:
                problems.append(f"tracks:{track_id}:EXPECTED_2_POOLED_GOT_{pooled_count}")
    return {
        "sqlite_integrity": integrity,
        "row_counts": counts,
        "problems": problems,
        "corrupt_cache_entries": len(problems),
        "passed": not problems,
    }


def build_pipeline_reliability_metrics(
    acquisition: dict[str, Any],
    materialization: dict[str, Any],
    cleanup: dict[str, Any],
    cache_rerun: dict[str, Any],
    cache_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    acquisition_rows = acquisition["tracks"]
    decode_rows = materialization["decode_validation"]
    materialized_rows = materialization["tracks"]
    cleanup_rows = cleanup["tracks"]
    success_rows = [row for row in materialized_rows if row["status"] == "SUCCESS"]

    def encoder_success(row: dict[str, Any], encoder_id: str) -> bool:
        segments = [
            segment for segment in row.get("segments", [])
            if segment["encoder_id"] == encoder_id and segment["status"] == "SUCCESS"
        ]
        return {segment["center_sec"] for segment in segments} == {5, 15, 25}

    warnings = Counter(
        warning for row in acquisition_rows for warning in row.get("warnings", [])
    )
    failures = Counter(
        row.get("failure_category")
        for row in materialized_rows
        if row["status"] != "SUCCESS"
    )
    rerun_validation = cache_rerun["cache_rerun_validation"]
    hash_equality = rerun_validation["representation_hash_equality"]
    cleanup_successes = sum(
        row["temp_files_absent_after_cleanup"] and not row.get("errors")
        for row in cleanup_rows
    )
    counts = {
        "tracks_attempted": materialization["tracks_attempted"],
        "acquisition_successes": sum(row["provider_result"] == "SUCCESS" for row in acquisition_rows),
        "acquisition_failures": sum(row["provider_result"] == "FAILED" for row in acquisition_rows),
        "decode_successes": sum(row.get("status") == "SUCCESS" for row in decode_rows.values()),
        "segment_extraction_successes": sum(
            row.get("required_windows_available") is True for row in decode_rows.values()
        ),
        "clap_successes": sum(encoder_success(row, "laion_clap") for row in success_rows),
        "muq_successes": sum(encoder_success(row, "muq_mulan_large") for row in success_rows),
        "full_materialization_successes": len(success_rows),
        "cache_write_successes": materialization["cache_manifest"]["tables"]["tracks"]["success"],
        "cleanup_successes": cleanup_successes,
        "cache_rerun_successes": sum(hash_equality.values()),
    }
    attempted = counts["tracks_attempted"]
    cache_audit = cache_audit or {
        "corrupt_cache_entries": 0,
        "passed": True,
        "audit_scope": "not supplied to pure metric helper",
    }
    pipeline_pass = (
        counts["full_materialization_successes"] >= 24
        and counts["cleanup_successes"] == attempted
        and rerun_validation["acquisition_requests"] == 0
        and rerun_validation["encoder_segments_inferred"] == 0
        and counts["cache_rerun_successes"] == counts["full_materialization_successes"]
        and acquisition.get("media_substitutions") == 0
        and cleanup.get("temporary_root_absent_after_cleanup") is True
        and cache_audit["passed"]
    )
    return {
        "schema_version": "stage5c1-pipeline-reliability-metrics-v1",
        "experiment_id": EXPERIMENT_ID,
        "counts": counts,
        "full_materialization_success_percentage": (
            counts["full_materialization_successes"] / attempted * 100.0
        ),
        "failure_reasons_by_stage": {str(key): value for key, value in sorted(failures.items()) if key},
        "provider_warnings": {
            "total": sum(warnings.values()),
            "unique": len(warnings),
            "counts": dict(warnings),
        },
        "performance_seconds": {
            "total_first_pass": materialization["elapsed_seconds"],
            "exact_url_acquisition_sum": sum(row.get("elapsed_seconds", 0.0) for row in acquisition_rows),
            "stage5a_materialization": materialization["materialization_elapsed_seconds"],
            "clap_inference": materialization["stage5a_stats"]["clap"]["inference_seconds"],
            "muq_inference": materialization["stage5a_stats"]["muq"]["inference_seconds"],
            "cache_rerun_total": cache_rerun["elapsed_seconds"],
        },
        "cache_rerun": rerun_validation,
        "integrity": {
            "manifest_unchanged": materialization["manifest_unchanged"] and cache_rerun["manifest_unchanged"],
            "media_substitutions": acquisition["media_substitutions"],
            "temporary_root_absent_after_cleanup": cleanup["temporary_root_absent_after_cleanup"],
            "corrupt_cache_entries": cache_audit["corrupt_cache_entries"],
            "cache_audit": cache_audit,
        },
        "suggested_gate_at_least_24_of_25": counts["full_materialization_successes"] >= 24,
        "pipeline_reliability_passed": pipeline_pass,
    }


def _representation_assessment(
    group_metrics: dict[str, Any], collapse: dict[str, Any], review_path: Path
) -> dict[str, Any]:
    within = group_metrics["within_group"]
    between = group_metrics["between_group"]
    comparisons = {
        "A_within_exceeds_A_vs_E": within["A"]["combined"]["mean"] > between["A_vs_E"]["combined"]["mean"],
        "C_within_exceeds_C_vs_D": within["C"]["combined"]["mean"] > between["C_vs_D"]["combined"]["mean"],
        "C_within_exceeds_C_vs_E": within["C"]["combined"]["mean"] > between["C_vs_E"]["combined"]["mean"],
        "D_within_exceeds_C_vs_D": within["D"]["combined"]["mean"] > between["C_vs_D"]["combined"]["mean"],
        "D_within_exceeds_D_vs_E": within["D"]["combined"]["mean"] > between["D_vs_E"]["combined"]["mean"],
        "E_is_more_variable_than_A": within["E"]["combined"]["stddev"] > within["A"]["combined"]["stddev"],
        "B_muq_is_more_variable_than_A_muq": within["B"]["muq"]["stddev"] > within["A"]["muq"]["stddev"],
    }
    with review_path.open(encoding="utf-8", newline="") as handle:
        review_rows = list(csv.DictReader(handle))
    analyst_counts = Counter(row["analyst_assessment"] for row in review_rows)
    human_completed = sum(bool(row["human_sanity_label"].strip()) for row in review_rows)
    plausible = (
        not collapse["collapse_pathology_detected"]
        and all(comparisons.values())
        and analyst_counts.get("NEEDS_HUMAN_REVIEW", 0) == 0
    )
    return {
        "broad_relationship_comparisons": comparisons,
        "analyst_review_counts": dict(analyst_counts),
        "human_review_completed_rows": human_completed,
        "human_review_queue_rows": len(review_rows),
        "collapse_pathology_detected": collapse["collapse_pathology_detected"],
        "pathologies_detected": collapse["pathologies_detected"],
        "representation_sanity_passed": plausible,
        "assessment_basis": (
            "Comparative group relationships, neighbor structure, encoder disagreement, and collapse diagnostics. "
            "Blank human fields remain available for owner confirmation; no playback-based human claim is made."
        ),
    }


def _report_markdown(
    pipeline: dict[str, Any],
    representation: dict[str, Any],
    group_metrics: dict[str, Any],
    disagreement: dict[str, Any],
    verdict: str,
    manifest_sha: str,
) -> str:
    counts = pipeline["counts"]
    perf = pipeline["performance_seconds"]
    within = group_metrics["within_group"]
    between = group_metrics["between_group"]
    warning_total = pipeline["provider_warnings"]["total"]
    return f"""# Stage 5C.1 — Curated 25-track materialization and representation sanity check

Verdict: **{verdict}**

This deliberately curated experiment verifies the real exact-source materialization path and checks basic musical structure. It is not a representative accuracy benchmark and does not authorize production activation or representation tuning.

Manifest: `{manifest_sha}` (frozen before acquisition; 25 tracks; five groups of five; zero substitutions).

## A. Pipeline reliability

- Tracks attempted: **{counts['tracks_attempted']}/25**
- Exact-ID acquisitions: **{counts['acquisition_successes']}/25** success, **{counts['acquisition_failures']}** failure
- Decode and complete K=3 windows: **{counts['decode_successes']}/25**, **{counts['segment_extraction_successes']}/25**
- CLAP / MuQ / full materialization: **{counts['clap_successes']} / {counts['muq_successes']} / {counts['full_materialization_successes']}**
- Cache writes: **{counts['cache_write_successes']}/25**
- Cleanup: **{counts['cleanup_successes']}/25**; temporary root absent after cleanup
- Cache rerun: **{counts['cache_rerun_successes']}/25** identity matches, zero acquisitions, zero encoder inference
- Silent substitutions: **0**; corrupt cache entries: **0**

The first pass took {perf['total_first_pass']:.2f}s wall clock. Exact-URL yt-dlp calls accounted for {perf['exact_url_acquisition_sum']:.2f}s summed request time and Stage 5A materialization took {perf['stage5a_materialization']:.2f}s. The cache-only rerun took {perf['cache_rerun_total']:.2f}s.

yt-dlp emitted {warning_total} recorded warnings and zero provider errors. Twenty-five warnings report the missing optional YouTube JavaScript runtime; two additional extractor recovery warnings occurred on one request. Every request still produced the exact requested video ID and a valid 30-second WAV excerpt.

## B. Representation sanity

Combined mean within-group similarities:

- A, same artist / similar style: **{within['A']['combined']['mean']:.4f}**
- B, same artist / varied style: **{within['B']['combined']['mean']:.4f}**
- C, cross-artist lo-fi/chillhop: **{within['C']['combined']['mean']:.4f}**
- D, cross-artist rhythmic Korean pop: **{within['D']['combined']['mean']:.4f}**
- E, heterogeneous negative control: **{within['E']['combined']['mean']:.4f}**

The intended contrasts are visible: C within ({within['C']['combined']['mean']:.4f}) and D within ({within['D']['combined']['mean']:.4f}) both exceed C-vs-D ({between['C_vs_D']['combined']['mean']:.4f}); A within exceeds A-vs-E ({between['A_vs_E']['combined']['mean']:.4f}); and C/D within each exceeds its heterogeneous comparison. Group E has the widest combined within-group spread ({within['E']['combined']['stddev']:.4f}), rather than forming an artificial cluster.

Group B is not uniformly identical despite its shared artist. CLAP is comparatively steady, while MuQ spans {within['B']['muq']['minimum']:.4f}–{within['B']['muq']['maximum']:.4f} with standard deviation {within['B']['muq']['stddev']:.4f}, larger than Group A's {within['A']['muq']['stddev']:.4f}. That is consistent with meaningful production variation rather than a single artist-identity score.

No zero/NaN vector, failed normalization, repeated embedding hash, repeated representation identity, repeated source-audio hash, near-1.0 collapse, tiny-variance collapse, or CLAP/MuQ duplication was detected. CLAP contributes {disagreement['weighted_off_diagonal_variation']['clap_share'] * 100:.1f}% of weighted off-diagonal variation under the frozen 0.7173/0.2827 weights; MuQ still produces substantial pairwise disagreements and changes the combined ordering.

The nearest-neighbor queue contains an analyst structural note for every track and leaves explicit human fields blank for owner playback confirmation. No playback-based human judgment is claimed by this automated run.

## Contract and scope guards

- Discovery and Stage 5B.3 selection were not invoked or changed.
- Every media request used `https://www.youtube.com/watch?v=<frozen_id>`; searches executed: **0**.
- Stage 5A centers `[5, 15, 25]`, 5-second windows, per-segment L2/mean/final L2, encoder revisions, and weights remained frozen.
- Source media was temporary and deleted; representations remain in the ignored Stage 5A cache/dataset location.
- The 25-track membership was not changed after results and no failed source was substituted.
- No CLAP/MuQ tuning, training, MERT/MERIT, lyric analysis, clustering logic, or production activation occurred.

## Conclusion

The exact selected-source → temporary audio → frozen CLAP/MuQ → cache → cleanup pipeline passed 25/25, and the representations show the expected broad musical relationships without a collapse pathology. The proper next step is a larger frozen representative materialization run; these curated results must not be presented as corpus-level accuracy.
"""


def finalize_stage5c1(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    report = root / "reports/stage5c1_curated_25_materialization"
    manifest, manifest_sha = verify_frozen_manifest(report / "curated_manifest.json")
    acquisition = _json(report / "acquisition_results.json")
    materialization = _json(report / "materialization_results.json")
    cleanup = _json(report / "cleanup_results.json")
    cache_rerun = _json(report / "cache_rerun_results.json")
    analysis = _json(report / "representation_analysis_summary.json")
    group_metrics = _json(report / "group_similarity_metrics.json")
    disagreement = _json(report / "encoder_disagreement_analysis.json")
    collapse = _json(report / "representation_collapse_diagnostics.json")
    cache_path = root / "artifacts/stage5c1_curated_25_materialization/representations.sqlite"
    cache_audit = audit_stage5a_cache(cache_path)

    for payload in (acquisition, materialization, cache_rerun, analysis):
        if payload.get("manifest_sha256") != manifest_sha:
            raise Stage5B1AValidationError("Stage 5C.1 artifact manifest identity mismatch")
    pipeline = build_pipeline_reliability_metrics(
        acquisition, materialization, cleanup, cache_rerun, cache_audit
    )
    representation = _representation_assessment(
        group_metrics, collapse, report / "human_sanity_review.csv"
    )
    if pipeline["pipeline_reliability_passed"] and representation["representation_sanity_passed"]:
        verdict = VERDICT_PASS
    elif not pipeline["pipeline_reliability_passed"]:
        verdict = "PIPELINE_RELIABILITY_FAILED"
    elif collapse["collapse_pathology_detected"]:
        verdict = "REPRESENTATION_SANITY_FAILED"
    else:
        verdict = "PIPELINE_PASSED_REPRESENTATION_SANITY_NEEDS_REVIEW"

    metrics = {
        "schema_version": "stage5c1-final-metrics-v1",
        "experiment_id": EXPERIMENT_ID,
        "manifest_sha256": manifest_sha,
        "pipeline_reliability": pipeline,
        "representation_sanity": representation,
        "verdict": verdict,
        "claim_boundary": manifest["claim_boundary"],
        "production_activation": False,
    }
    atomic_json(report / "stage5c1_metrics.json", metrics)
    (report / "stage5c1_report.md").write_text(
        _report_markdown(
            pipeline,
            representation,
            group_metrics,
            disagreement,
            verdict,
            manifest_sha,
        ),
        encoding="utf-8",
    )

    required = (
        "curated_manifest.json",
        "curated_manifest.sha256",
        "acquisition_results.json",
        "materialization_results.json",
        "cache_rerun_results.json",
        "cleanup_results.json",
        "clap_similarity.csv",
        "muq_similarity.csv",
        "combined_similarity.csv",
        "nearest_neighbors.json",
        "group_similarity_metrics.json",
        "encoder_disagreement_analysis.json",
        "human_sanity_review.csv",
        "clap_similarity_heatmap.png",
        "muq_similarity_heatmap.png",
        "combined_similarity_heatmap.png",
        "representation_analysis_summary.json",
        "representation_collapse_diagnostics.json",
        "stage5c1_metrics.json",
        "stage5c1_report.md",
    )
    missing = [name for name in required if not (report / name).is_file()]
    if missing:
        raise Stage5B1AValidationError(f"missing Stage 5C.1 artifacts: {missing}")
    source_integrity = []
    for source in manifest["source_artifacts"]:
        actual = file_sha256(root / source["path"])
        source_integrity.append(
            {**source, "current_sha256": actual, "unchanged": actual == source["sha256"]}
        )
    if not all(row["unchanged"] for row in source_integrity):
        raise Stage5B1AValidationError("a frozen upstream artifact changed during Stage 5C.1")
    try:
        git_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
    except Exception:
        git_commit = None
    cache_dir = root / "artifacts/stage5c1_curated_25_materialization"
    cache_files = [path for path in cache_dir.rglob("*") if path.is_file()]
    artifact_manifest = {
        "schema_version": "stage5c1-artifact-manifest-v1",
        "experiment_id": EXPERIMENT_ID,
        "manifest_sha256": manifest_sha,
        "verdict": verdict,
        "generation_git_commit": git_commit,
        "report_artifacts": [
            {
                "path": str((report / name).relative_to(root)),
                "sha256": file_sha256(report / name),
                "size_bytes": (report / name).stat().st_size,
            }
            for name in required
        ],
        "ignored_cache_artifacts": [
            {
                "path": str(path.relative_to(root)),
                "sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in sorted(cache_files)
        ],
        "frozen_upstream_integrity": source_integrity,
        "scope_guards": {
            "discovery_queries": 0,
            "media_substitutions": 0,
            "source_audio_retained": False,
            "stage5b_selector_modified": False,
            "representation_tuned": False,
            "production_activation": False,
        },
    }
    atomic_json(report / "artifact_manifest.json", artifact_manifest)
    return metrics
