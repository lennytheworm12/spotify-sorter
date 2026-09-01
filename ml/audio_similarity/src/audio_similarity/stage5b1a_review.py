"""Human review artifact and deterministic Stage 5B.1A recall metrics."""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .stage5b1a_config import GateConfig
from .stage5b1a_models import FrozenTrackManifest, Stage5B1AValidationError


REVIEW_SCHEMA_VERSION = "stage5b1a-human-review-csv-v1"
METRICS_SCHEMA_VERSION = "stage5b1a-firecrawl-metrics-v1"
NOT_IN_TOP_5 = "NOT_IN_TOP_5"
UNCERTAIN = "UNCERTAIN"
ALLOWED_LABELS = {"", "1", "2", "3", "4", "5", NOT_IN_TOP_5, "NOT_IN_TOP_K", UNCERTAIN}


BASE_REVIEW_COLUMNS = [
    "stable_track_id",
    "spotify_track_id",
    "expected_title",
    "expected_artists",
    "expected_album",
    "expected_release_year",
    "case_tags",
    "case_rationale",
    "query",
]
CANDIDATE_COLUMNS = [
    f"candidate_{rank}_{field}"
    for rank in range(1, 6)
    for field in ("url", "video_id", "title", "description")
]
REVIEW_COLUMNS = BASE_REVIEW_COLUMNS + CANDIDATE_COLUMNS + ["review_label", "optional_note"]


@dataclass(frozen=True)
class ReviewLabel:
    stable_track_id: str
    label: str
    note: str

    @property
    def correct_rank(self) -> int | None:
        return int(self.label) if self.label in {"1", "2", "3", "4", "5"} else None


def _candidate_values(candidate: dict[str, Any] | None) -> list[str]:
    if candidate is None:
        return ["", "", "", ""]
    return [
        str(candidate.get("url") or ""),
        str(candidate.get("youtube_video_id") or ""),
        str(candidate.get("title") or ""),
        str(candidate.get("description") or ""),
    ]


def review_rows(
    manifest: FrozenTrackManifest,
    results: dict | None = None,
) -> list[dict[str, str]]:
    result_by_id: dict[str, dict] = {}
    if results is not None:
        rows = results.get("tracks")
        if not isinstance(rows, list):
            raise Stage5B1AValidationError("discovery results tracks must be an array")
        for row in rows:
            stable_id = row.get("track", {}).get("stable_track_id") if isinstance(row, dict) else None
            if not isinstance(stable_id, str) or stable_id in result_by_id:
                raise Stage5B1AValidationError("discovery results have invalid or duplicate track IDs")
            result_by_id[stable_id] = row
        if set(result_by_id) != set(manifest.stable_track_ids):
            raise Stage5B1AValidationError("discovery results do not match the frozen manifest")

    output = []
    for item in manifest.tracks:
        track = item.track
        discovered = result_by_id.get(track.stable_track_id)
        candidates = discovered.get("candidates", []) if discovered else []
        if not isinstance(candidates, list) or len(candidates) > 5:
            raise Stage5B1AValidationError("a discovery result has an invalid candidate array")
        row = {
            "stable_track_id": track.stable_track_id,
            "spotify_track_id": track.spotify_track_id or "",
            "expected_title": track.title,
            "expected_artists": " | ".join(track.artists),
            "expected_album": track.album or "",
            "expected_release_year": str(track.release_year or ""),
            "case_tags": " | ".join(item.case_tags),
            "case_rationale": item.case_rationale,
            "query": discovered.get("query", "") if discovered else "",
            "review_label": "",
            "optional_note": "",
        }
        for rank in range(1, 6):
            candidate = candidates[rank - 1] if rank <= len(candidates) else None
            for field, value in zip(
                ("url", "video_id", "title", "description"),
                _candidate_values(candidate),
            ):
                row[f"candidate_{rank}_{field}"] = value
        output.append(row)
    return output


def write_review_csv(
    path: str | Path,
    manifest: FrozenTrackManifest,
    results: dict | None = None,
    *,
    overwrite: bool = False,
) -> None:
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"review artifact already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(review_rows(manifest, results))
    temporary.replace(output)


def load_review_labels(
    path: str | Path,
    *,
    candidate_counts: dict[str, int] | None = None,
    expected_columns: Sequence[str] | None = None,
) -> tuple[ReviewLabel, ...]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(expected_columns or REVIEW_COLUMNS):
            raise Stage5B1AValidationError("unexpected human-review CSV columns")
        labels = []
        seen = set()
        for row_number, row in enumerate(reader, start=2):
            stable_id = (row.get("stable_track_id") or "").strip()
            if not stable_id or stable_id in seen:
                raise Stage5B1AValidationError(
                    f"invalid or duplicate stable_track_id on review row {row_number}"
                )
            seen.add(stable_id)
            label = (row.get("review_label") or "").strip().upper()
            if label not in ALLOWED_LABELS:
                raise Stage5B1AValidationError(
                    f"invalid review_label {label!r} on row {row_number}"
                )
            if label == "NOT_IN_TOP_K":
                label = NOT_IN_TOP_5
            if label in {"1", "2", "3", "4", "5"} and candidate_counts is not None:
                if int(label) > candidate_counts.get(stable_id, 0):
                    raise Stage5B1AValidationError(
                        f"review rank {label} exceeds candidates for {stable_id}"
                    )
            labels.append(
                ReviewLabel(
                    stable_track_id=stable_id,
                    label=label,
                    note=(row.get("optional_note") or "").strip(),
                )
            )
    return tuple(labels)


def classify_gate(recall_at_5: float, gate: GateConfig) -> str:
    if not 0 <= recall_at_5 <= 1:
        raise Stage5B1AValidationError("Recall@5 must be between zero and one")
    if recall_at_5 >= gate.pass_min_recall_at_5:
        return "PASS"
    if recall_at_5 >= gate.conditional_min_recall_at_5:
        return "CONDITIONAL"
    return "FAIL"


def compute_metrics(
    results: dict,
    labels: tuple[ReviewLabel, ...],
    gate: GateConfig,
    *,
    metrics_schema_version: str = METRICS_SCHEMA_VERSION,
    request_failure_key: str = "firecrawl_request_failure_count",
) -> dict:
    result_rows = results.get("tracks")
    if not isinstance(result_rows, list):
        raise Stage5B1AValidationError("discovery results tracks must be an array")
    result_by_id = {}
    for row in result_rows:
        stable_id = row.get("track", {}).get("stable_track_id") if isinstance(row, dict) else None
        if not isinstance(stable_id, str) or stable_id in result_by_id:
            raise Stage5B1AValidationError("invalid or duplicate result track identity")
        result_by_id[stable_id] = row
    label_by_id = {label.stable_track_id: label for label in labels}
    if len(label_by_id) != len(labels) or set(label_by_id) != set(result_by_id):
        raise Stage5B1AValidationError("human-review identities do not match discovery results")

    labeled = [label for label in labels if label.label]
    uncertain = [label for label in labels if label.label == UNCERTAIN]
    evaluable = [label for label in labels if label.correct_rank is not None or label.label == NOT_IN_TOP_5]
    unreviewed = [label for label in labels if not label.label]
    denominator = len(evaluable)

    recalls = {}
    for k in (1, 3, 5):
        numerator = sum(
            label.correct_rank is not None and label.correct_rank <= k
            for label in evaluable
        )
        recalls[f"recall_at_{k}"] = {
            "numerator": numerator,
            "denominator": denominator,
            "value": numerator / denominator if denominator else None,
        }
    recall_at_5 = recalls["recall_at_5"]["value"]
    if unreviewed:
        verdict = "PENDING_HUMAN_REVIEW"
    elif recall_at_5 is None:
        verdict = "NO_EVALUABLE_TRACKS"
    else:
        verdict = classify_gate(recall_at_5, gate)
    return {
        "schema_version": metrics_schema_version,
        "experiment_id": results.get("experiment_id"),
        "review": {
            "total_tracks": len(labels),
            "reviewed_tracks": len(labeled),
            "evaluable_tracks": denominator,
            "unreviewed_tracks": len(unreviewed),
            "uncertain_tracks": len(uncertain),
            "not_in_top_5_tracks": sum(label.label == NOT_IN_TOP_5 for label in labels),
            "denominator_semantics": "Confirmed ranks plus NOT_IN_TOP_5; UNCERTAIN and unreviewed tracks are excluded.",
        },
        "recall_at_1": recalls["recall_at_1"],
        "recall_at_3": recalls["recall_at_3"],
        "recall_at_5": recalls["recall_at_5"],
        request_failure_key: sum(row.get("error") is not None for row in result_rows),
        "tracks_with_zero_youtube_candidates": sum(not row.get("candidates") for row in result_rows),
        "feasibility_verdict": verdict,
        "gate": {
            "pass": f">= {gate.pass_min_recall_at_5:.0%}",
            "conditional": f">= {gate.conditional_min_recall_at_5:.0%} and < {gate.pass_min_recall_at_5:.0%}",
            "fail": f"< {gate.conditional_min_recall_at_5:.0%}",
            "primary_metric": gate.primary_metric,
            "scope_note": gate.scope_note,
        },
    }
