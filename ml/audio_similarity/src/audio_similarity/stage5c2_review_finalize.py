"""Validate and freeze completed Stage 5C.2 owner similarity judgments."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5c2_analysis import REVIEW_COLUMNS, canonical_pair_id
from .stage5c2_closeout import _human_review_metrics
from .stage5c2_review import (
    LABELS,
    MAX_NOTE_LENGTH,
    REVIEW_ROW_SCHEMA_V2,
    _atomic_write_review_rows,
)


REPORT_DIRECTORY = "reports/stage5c2_representative_100_amended_v2"
OUTPUT_NAMES = (
    "human_similarity_metrics.json",
    "human_similarity_review_report.md",
    "human_similarity_review_manifest.json",
)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise Stage5B1AValidationError("unexpected Stage 5C.2 review columns")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise Stage5B1AValidationError("malformed Stage 5C.2 review row")
    return rows


def _display(value: float | None, *, percent: bool = False) -> str:
    if value is None:
        return "unavailable"
    return f"{value:.1%}" if percent else f"{value:.3f}"


def validate_completed_review(queue: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, Any]:
    if queue.get("schema_version") != "stage5c2-similarity-review-queue-v1":
        raise Stage5B1AValidationError("invalid Stage 5C.2 review queue")
    expected: dict[tuple[str, str], dict[str, Any]] = {}
    for case in queue.get("cases", []):
        query_id = str(case.get("spotify_track_id", ""))
        for neighbor in case.get("neighbors", []):
            neighbor_id = str(neighbor.get("spotify_track_id", ""))
            identity = (query_id, neighbor_id)
            if not all(identity) or identity in expected:
                raise Stage5B1AValidationError("invalid directional identity in review queue")
            expected[identity] = neighbor
    actual: dict[tuple[str, str], dict[str, str]] = {}
    pair_evidence: dict[str, tuple[str, str]] = {}
    for row in rows:
        identity = (row["query_spotify_id"], row["neighbor_spotify_id"])
        if identity in actual:
            raise Stage5B1AValidationError("duplicate directional review identity")
        actual[identity] = row
        neighbor = expected.get(identity)
        if neighbor is None:
            raise Stage5B1AValidationError("review contains a relationship outside the frozen queue")
        if row["review_schema_version"] != REVIEW_ROW_SCHEMA_V2:
            raise Stage5B1AValidationError("completed review must use the five-point schema")
        label = row["human_label"].strip().upper()
        if label not in LABELS:
            raise Stage5B1AValidationError("completed review contains a blank or invalid label")
        pair_id = canonical_pair_id(*identity)
        if row["pair_id"] != pair_id or neighbor.get("pair_id") != pair_id:
            raise Stage5B1AValidationError("review pair identity differs from frozen queue")
        if int(row["neighbor_rank"]) != int(neighbor["rank"]):
            raise Stage5B1AValidationError("review rank differs from frozen queue")
        for field in ("clap_similarity", "muq_similarity", "combined_similarity"):
            actual_score = float(row[field])
            expected_score = float(neighbor[field])
            if not math.isfinite(actual_score) or not math.isclose(
                actual_score, expected_score, abs_tol=5e-10
            ):
                raise Stage5B1AValidationError(f"review {field} differs from frozen queue")
        if not row["review_timestamp"].strip():
            raise Stage5B1AValidationError("completed review is missing a timestamp")
        try:
            timestamp = datetime.fromisoformat(row["review_timestamp"])
        except ValueError as error:
            raise Stage5B1AValidationError("completed review has an invalid timestamp") from error
        if timestamp.tzinfo is None:
            raise Stage5B1AValidationError("completed review timestamp must include a timezone")
        if len(row["human_note"]) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError("completed review note is too long")
        evidence = (label, row["human_note"])
        prior = pair_evidence.setdefault(pair_id, evidence)
        if prior != evidence:
            raise Stage5B1AValidationError("reciprocal review evidence disagrees")
    if actual.keys() != expected.keys():
        raise Stage5B1AValidationError("completed review does not exactly cover the frozen queue")
    if len(rows) != queue.get("raw_top5_judgment_count"):
        raise Stage5B1AValidationError("completed review row count differs from queue")
    if len(pair_evidence) != queue.get("unique_unordered_pair_count"):
        raise Stage5B1AValidationError("completed review pair count differs from queue")
    return {"directional_rows": len(rows), "unique_unordered_pairs": len(pair_evidence)}


def finalize_review(project_root: str | Path, export_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_root).resolve()
    report = root / REPORT_DIRECTORY
    queue_path = report / "review_queue.json"
    review_path = report / "human_similarity_review.csv"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    incoming = Path(export_path).resolve() if export_path else review_path
    incoming_rows = _rows(incoming)
    coverage = validate_completed_review(queue, incoming_rows)
    canonical_before_sha256 = file_sha256(review_path)
    if incoming != review_path and file_sha256(incoming) != canonical_before_sha256:
        _atomic_write_review_rows(review_path, incoming_rows)
    canonical_rows = _rows(review_path)
    validate_completed_review(queue, canonical_rows)
    human = _human_review_metrics(review_path)
    if human["status"] != "HUMAN_REVIEW_COMPLETE":
        raise Stage5B1AValidationError("human review did not finalize")
    directional_counts = Counter(row["human_label"].strip().upper() for row in canonical_rows)
    unique_rows = {row["pair_id"]: row for row in canonical_rows}
    pair_counts = Counter(row["human_label"].strip().upper() for row in unique_rows.values())
    metrics = {
        "schema_version": "stage5c2-human-similarity-final-metrics-v1",
        "experiment_id": "STAGE5C2_REPRESENTATIVE_100_SELECTOR_AWARE_AMENDMENT_V2",
        "status": "HUMAN_REVIEW_COMPLETE",
        "review_scale": "1–5; 5 extremely similar, 1 not similar; UNSURE nonnumeric",
        "single_owner_review": True,
        "review_file_sha256": file_sha256(review_path),
        "review_queue_sha256": file_sha256(queue_path),
        **coverage,
        "directional_label_counts": dict(sorted(directional_counts.items())),
        "unique_pair_label_counts": dict(sorted(pair_counts.items())),
        "quality_metrics": human["quality_metrics"],
        "scope": {
            "embeddings_changed": False,
            "rankings_changed": False,
            "weights_changed": False,
            "human_labels_inferred": False,
            "production_activation": False,
        },
    }
    atomic_json(report / OUTPUT_NAMES[0], metrics)
    quality = metrics["quality_metrics"]
    lines = [
        "# Stage 5C.2 amended 100 — completed human similarity review", "",
        "**Status:** `HUMAN_REVIEW_COMPLETE`", "",
        f"The owner reviewed all {coverage['unique_unordered_pairs']} unique unordered pairs "
        f"covering {coverage['directional_rows']} directional Top-5 relationships across 100 queries. "
        "No labels were inferred and no embeddings or rankings changed.", "",
        "## Results", "",
        f"- Mean Top-1 rating: **{_display(quality['mean_human_rating_top1'])} / 5**.",
        f"- Mean Top-5 rating: **{_display(quality['mean_human_rating_top5'])} / 5**.",
        f"- Top-1 rated at least moderately similar (3–5): **{_display(quality['fraction_top1_at_least_similar'], percent=True)}**.",
        f"- Top-5 rated at least moderately similar (3–5): **{_display(quality['fraction_top5_at_least_similar'], percent=True)}**.",
        f"- Top-5 rated at least somewhat related (2–5): **{_display(quality['fraction_top5_at_least_somewhat_related'], percent=True)}**.",
        f"- Directional labels: `{dict(sorted(directional_counts.items()))}`.", "",
        "Mean rating by rank: " + ", ".join(
            f"#{rank} {value:.3f}" for rank, value in quality["mean_rating_by_neighbor_rank"].items()
        ) + ".", "",
        "## Alignment diagnostics", "",
        f"Pearson correlation with owner ratings: CLAP **{_display(quality['clap_correlation'])}**, "
        f"MuQ **{_display(quality['muq_correlation'])}**, combined **{_display(quality['combined_correlation'])}**. "
        "These are descriptive single-owner results on the frozen reviewed relationships, not a new weight-tuning set.", "",
        "## Boundary", "",
        "This completes human review of the amended representative corpus. It does not establish population-level agreement, "
        "authorize model tuning, or activate the pipeline in production.", "",
    ]
    (report / OUTPUT_NAMES[1]).write_text("\n".join(lines), encoding="utf-8")
    manifest = {
        "schema_version": "stage5c2-human-similarity-final-manifest-v1",
        "status": "HUMAN_REVIEW_COMPLETE",
        "canonical_review_before_import_sha256": canonical_before_sha256,
        "provided_export_sha256": file_sha256(incoming),
        "provided_export_already_matched_canonical": canonical_before_sha256 == file_sha256(incoming),
        "artifacts": {
            name: {"sha256": file_sha256(report / name), "size_bytes": (report / name).stat().st_size}
            for name in OUTPUT_NAMES[:2]
        },
    }
    atomic_json(report / OUTPUT_NAMES[2], manifest)
    return metrics
