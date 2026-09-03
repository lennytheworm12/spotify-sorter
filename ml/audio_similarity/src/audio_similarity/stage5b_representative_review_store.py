"""Autosaving review state for the representative owner-library benchmark."""
from __future__ import annotations

import csv
import os
import threading
from pathlib import Path
from typing import Any

from .stage5b1a_discovery import YOUTUBE_VIDEO_ID
from .stage5b1a_models import Stage5B1AValidationError
from .stage5b_representative_benchmark import (
    REVIEW_COLUMNS,
    REVIEW_LABELS,
    REVIEW_SCHEMA_VERSION,
)


MAX_NOTE_LENGTH = 2_000


class RepresentativeBenchmarkReviewStore:
    def __init__(self, review_path: str | Path) -> None:
        self.review_path = Path(review_path)
        self._lock = threading.RLock()
        self._read_rows()

    def _read_rows(self) -> list[dict[str, str]]:
        with self.review_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
                raise Stage5B1AValidationError("unexpected representative review columns")
            rows = list(reader)
        identities = set()
        for row in rows:
            identity = (row["benchmark_id"], row["candidate_video_id"])
            if identity in identities or not YOUTUBE_VIDEO_ID.fullmatch(identity[1]):
                raise Stage5B1AValidationError("invalid representative review identity")
            identities.add(identity)
            if row["review_schema_version"] != REVIEW_SCHEMA_VERSION:
                raise Stage5B1AValidationError("unexpected representative review schema")
            label = row["candidate_review_label"].strip().upper()
            if label not in REVIEW_LABELS:
                raise Stage5B1AValidationError("invalid representative review label")
            row["candidate_review_label"] = label
            if len(row["candidate_note"]) > MAX_NOTE_LENGTH or len(row["track_note"]) > MAX_NOTE_LENGTH:
                raise Stage5B1AValidationError("representative review note is too long")
        if not rows:
            raise Stage5B1AValidationError("representative review queue is empty")
        return rows

    @staticmethod
    def _number(value: str, converter: type[int] | type[float]) -> int | float | None:
        return converter(value) if value.strip() else None

    def session(self) -> dict[str, Any]:
        with self._lock:
            rows = self._read_rows()
            cases = []
            for row in rows:
                cases.append({
                    "stable_track_id": row["benchmark_id"],
                    "track": {
                        "title": row["expected_title"],
                        "artists": row["expected_artists"].split(" | "),
                        "album": row["expected_album"] or None,
                        "duration_seconds": self._number(row["expected_duration_seconds"], float),
                        "release_year": self._number(row["expected_release_year"], int),
                    },
                    "track_note": row["track_note"],
                    "fallback": {
                        "match_mode": row["match_mode"],
                        "reason": row["fallback_reason"] or "frozen exact-recording selection",
                    },
                    "candidates": [{
                        "display_index": 1,
                        "video_id": row["candidate_video_id"],
                        "url": row["candidate_url"],
                        "title": row["candidate_title"],
                        "uploader": row["candidate_uploader"] or None,
                        "channel": row["candidate_channel"] or None,
                        "duration_seconds": self._number(row["candidate_duration_seconds"], float),
                        "view_count": self._number(row["candidate_view_count"], int),
                        "description": row["candidate_description"] or None,
                        "review": {
                            "label": row["candidate_review_label"],
                            "note": row["candidate_note"],
                        },
                    }],
                })
            reviewed = sum(bool(row["candidate_review_label"]) for row in rows)
            return {
                "schema_version": "stage5b-representative-library-review-session-v1",
                "mode": "stage5b_representative_library_review",
                "labels": ["IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"],
                "export_filename": "stage5b-representative-library-v1-human-review.csv",
                "progress": {
                    "reviewed_candidates": reviewed,
                    "remaining_candidates": len(rows) - reviewed,
                    "total_candidates": len(rows),
                    "completed_tracks": reviewed,
                    "total_tracks": len(rows),
                },
                "cases": cases,
            }

    def submit(
        self,
        stable_track_id: str,
        video_id: str,
        label: str,
        candidate_note: str = "",
        track_note: str = "",
    ) -> dict[str, Any]:
        label = str(label or "").strip().upper()
        candidate_note = str(candidate_note or "")
        track_note = str(track_note or "")
        if label not in REVIEW_LABELS:
            raise Stage5B1AValidationError("invalid representative review label")
        if len(candidate_note) > MAX_NOTE_LENGTH or len(track_note) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError("representative review note is too long")
        with self._lock:
            rows = self._read_rows()
            target = next((
                row for row in rows
                if row["benchmark_id"] == stable_track_id
                and row["candidate_video_id"] == video_id
            ), None)
            if target is None:
                raise Stage5B1AValidationError("unknown representative review identity")
            target["candidate_review_label"] = label
            target["candidate_note"] = candidate_note
            target["track_note"] = track_note
            temporary = self.review_path.with_suffix(
                self.review_path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp"
            )
            with temporary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            temporary.replace(self.review_path)
        return {
            "ok": True,
            "stable_track_id": stable_track_id,
            "video_id": video_id,
            "review": {"label": label, "note": candidate_note},
            "track_note": track_note,
        }
