"""Versioned CSV boundary for Stage 5B.1I reviewer-owned evidence."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError


REVIEW_SCHEMA_VERSION = "stage5b1i-human-review-v1"
REVIEW_LABELS = frozenset({"", "IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"})
REVIEW_COLUMNS = [
    "review_schema_version", "stable_track_id", "expected_title",
    "expected_artists", "expected_album", "expected_version_descriptors_json",
    "expected_duration_seconds", "expected_release_year", "candidate_rank",
    "candidate_video_id", "candidate_url", "candidate_title",
    "candidate_uploader", "candidate_channel", "candidate_duration_seconds",
    "candidate_view_count", "candidate_description",
    "candidate_review_label", "candidate_note", "track_note",
]


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_review_rows(universe: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for track_row in universe["tracks"]:
        target = track_row["track"]
        for wrapped in track_row["candidates"]:
            candidate = wrapped["candidate"]
            evidence = wrapped["resolver_evidence"]
            rows.append({
                "review_schema_version": REVIEW_SCHEMA_VERSION,
                "stable_track_id": target["stable_track_id"],
                "expected_title": target["title"],
                "expected_artists": " | ".join(target["artists"]),
                "expected_album": target.get("album") or "",
                "expected_version_descriptors_json": _json_cell(
                    track_row["target_version_descriptors"]
                ),
                "expected_duration_seconds": (
                    target["duration_ms"] / 1000.0
                    if target.get("duration_ms") is not None else ""
                ),
                "expected_release_year": target.get("release_year") or "",
                "candidate_rank": candidate["rank"],
                "candidate_video_id": candidate["video_id"],
                "candidate_url": candidate["url"],
                "candidate_title": candidate.get("title") or "",
                "candidate_uploader": candidate.get("uploader") or "",
                "candidate_channel": candidate.get("channel") or "",
                "candidate_duration_seconds": (
                    candidate["duration_seconds"]
                    if candidate.get("duration_seconds") is not None else ""
                ),
                "candidate_view_count": (
                    candidate["view_count"] if candidate.get("view_count") is not None else ""
                ),
                "candidate_description": candidate.get("description") or "",
                "candidate_review_label": "",
                "candidate_note": "",
                "track_note": "",
            })
    return rows


def load_human_review(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != REVIEW_COLUMNS:
            raise Stage5B1AValidationError("unexpected Stage 5B.1I review CSV columns")
        rows = list(reader)
    identities: set[tuple[str, str]] = set()
    for row in rows:
        if row["review_schema_version"] != REVIEW_SCHEMA_VERSION:
            raise Stage5B1AValidationError("unexpected Stage 5B.1I review row schema")
        label = row["candidate_review_label"].strip().upper()
        if label not in REVIEW_LABELS:
            raise Stage5B1AValidationError(f"invalid Stage 5B.1I review label: {label}")
        row["candidate_review_label"] = label
        identity = (row["stable_track_id"], row["candidate_video_id"])
        if identity in identities:
            raise Stage5B1AValidationError(f"duplicate Stage 5B.1I review identity: {identity}")
        identities.add(identity)
    return rows


def write_human_review(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            existing = list(reader)
        reviewer_fields = {"candidate_review_label", "candidate_note", "track_note"}
        has_review_evidence = any(
            str(row.get(name) or "").strip()
            for row in existing for name in reviewer_fields
        )
        if reader.fieldnames != REVIEW_COLUMNS:
            if has_review_evidence:
                raise Stage5B1AValidationError(
                    "refusing to migrate labeled Stage 5B.1I review evidence"
                )
            existing = []
        immutable = [
            name for name in REVIEW_COLUMNS
            if name not in reviewer_fields
        ]
        if existing and (len(existing) != len(rows) or any(
            old[name] != str(new[name])
            for old, new in zip(existing, rows)
            for name in immutable
        )):
            raise Stage5B1AValidationError(
                "refusing to overwrite changed Stage 5B.1I review evidence"
            )
        if existing:
            return
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
