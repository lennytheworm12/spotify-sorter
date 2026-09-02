"""Atomic local-browser review state for the Stage 5B.1E targeted audit."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

from .stage5b1a_discovery import YOUTUBE_VIDEO_ID
from .stage5b1a_models import Stage5B1AValidationError
from .stage5b1b_challenge import ChallengeManifest
from .stage5b1e_experiment import AUDIT_SCHEMA_VERSION, REVIEW_COLUMNS, REVIEW_LABELS


MAX_NOTE_LENGTH = 2_000
UI_LABELS = ("IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN")
SESSION_SCHEMA_VERSION = "stage5b1e-review-session-v1"


class Stage5B1EReviewStore:
    """Expose raw metadata only and persist reviewer-owned fields atomically."""

    def __init__(
        self,
        manifest: ChallengeManifest,
        queue_path: str | Path,
        review_path: str | Path,
        *,
        export_filename: str = "stage5b1e-natural-query-human-review.csv",
        shuffle_salt: str = "stage5b1e-natural-query-review-v1",
    ) -> None:
        self.manifest = manifest
        self.queue_path = Path(queue_path)
        self.review_path = Path(review_path)
        self.export_filename = export_filename
        self.shuffle_salt = shuffle_salt
        self._lock = threading.RLock()
        self._manifest_by_id = {
            item.track.stable_track_id: item.track for item in manifest.tracks
        }
        self._identities = self._read_queue()
        self._read_rows()

    def _read_queue(self) -> tuple[tuple[str, str], ...]:
        try:
            value = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise Stage5B1AValidationError(
                f"cannot load Stage 5B.1E audit queue: {self.queue_path}"
            ) from exc
        if not isinstance(value, dict) or value.get("schema_version") != AUDIT_SCHEMA_VERSION:
            raise Stage5B1AValidationError("unexpected Stage 5B.1E audit queue schema")
        cases = value.get("cases")
        if not isinstance(cases, list) or not cases:
            raise Stage5B1AValidationError("Stage 5B.1E audit queue contains no cases")
        identities = []
        for case in cases:
            if not isinstance(case, dict):
                raise Stage5B1AValidationError("invalid Stage 5B.1E audit case")
            stable_id = case.get("stable_track_id")
            video_id = case.get("candidate_video_id")
            if (
                stable_id not in self._manifest_by_id
                or not isinstance(video_id, str)
                or not YOUTUBE_VIDEO_ID.fullmatch(video_id)
            ):
                raise Stage5B1AValidationError("invalid Stage 5B.1E audit identity")
            identities.append((stable_id, video_id))
        if len(identities) != len(set(identities)):
            raise Stage5B1AValidationError("duplicate Stage 5B.1E audit identity")
        if value.get("required_judgments") != len(identities):
            raise Stage5B1AValidationError("Stage 5B.1E audit accounting changed")
        return tuple(identities)

    def _read_rows(self) -> list[dict[str, str]]:
        try:
            handle = self.review_path.open(encoding="utf-8-sig", newline="")
        except FileNotFoundError as exc:
            raise Stage5B1AValidationError(
                f"Stage 5B.1E review artifact does not exist: {self.review_path}"
            ) from exc
        with handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != REVIEW_COLUMNS:
                raise Stage5B1AValidationError("unexpected Stage 5B.1E review columns")
            rows = list(reader)
        actual = []
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            stable_id = row["stable_track_id"].strip()
            video_id = row["candidate_video_id"].strip()
            label = row["candidate_review_label"].strip().upper()
            if row["review_schema_version"] != AUDIT_SCHEMA_VERSION:
                raise Stage5B1AValidationError("unexpected Stage 5B.1E review row schema")
            if label not in REVIEW_LABELS:
                raise Stage5B1AValidationError(f"invalid Stage 5B.1E review label: {label}")
            if (
                len(row["candidate_note"]) > MAX_NOTE_LENGTH
                or len(row["track_note"]) > MAX_NOTE_LENGTH
            ):
                raise Stage5B1AValidationError("Stage 5B.1E review note is too long")
            row["candidate_review_label"] = label
            actual.append((stable_id, video_id))
            grouped[stable_id].append(row)
        if tuple(actual) != self._identities:
            raise Stage5B1AValidationError("Stage 5B.1E review rows changed identity or order")
        for stable_id, candidate_rows in grouped.items():
            target = self._manifest_by_id[stable_id]
            if any(
                row["expected_title"] != target.title
                or row["expected_artists"] != " | ".join(target.artists)
                or row["expected_album"] != (target.album or "")
                or row["expected_duration_seconds"] != str(target.duration_ms / 1000.0)
                or row["expected_release_year"] != str(target.release_year or "")
                for row in candidate_rows
            ):
                raise Stage5B1AValidationError("Stage 5B.1E target metadata changed")
            if len({row["track_note"] for row in candidate_rows}) != 1:
                raise Stage5B1AValidationError("Stage 5B.1E track note is inconsistent")
        return rows

    @staticmethod
    def _number(row: dict[str, str], name: str, converter):
        value = row[name].strip()
        return converter(value) if value else None

    def session(self) -> dict[str, Any]:
        with self._lock:
            rows = self._read_rows()
            grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
            order = []
            for row in rows:
                stable_id = row["stable_track_id"]
                if stable_id not in grouped:
                    order.append(stable_id)
                grouped[stable_id].append(row)
            cases = []
            for stable_id in order:
                target = self._manifest_by_id[stable_id]
                candidate_rows = sorted(
                    grouped[stable_id],
                    key=lambda row: hashlib.sha256(
                        f"{self.shuffle_salt}|{stable_id}|{row['candidate_video_id']}".encode()
                    ).hexdigest(),
                )
                cases.append({
                    "stable_track_id": stable_id,
                    "track": {
                        "title": target.title, "artists": list(target.artists),
                        "album": target.album,
                        "duration_seconds": target.duration_ms / 1000.0,
                        "release_year": target.release_year,
                    },
                    "track_note": candidate_rows[0]["track_note"],
                    "candidates": [
                        {
                            "display_index": index,
                            "video_id": row["candidate_video_id"],
                            "url": row["candidate_url"],
                            "title": row["candidate_title"],
                            "uploader": row["candidate_uploader"] or None,
                            "channel": row["candidate_channel"] or None,
                            "duration_seconds": self._number(
                                row, "candidate_duration_seconds", float
                            ),
                            "view_count": self._number(row, "candidate_view_count", int),
                            "description": row["candidate_description"] or None,
                            "review": {
                                "label": row["candidate_review_label"],
                                "note": row["candidate_note"],
                            },
                        }
                        for index, row in enumerate(candidate_rows, start=1)
                    ],
                })
            total = sum(len(case["candidates"]) for case in cases)
            reviewed = sum(
                bool(candidate["review"]["label"])
                for case in cases for candidate in case["candidates"]
            )
            return {
                "schema_version": SESSION_SCHEMA_VERSION,
                "mode": "stage5b1e_natural_query_human_audit",
                "labels": list(UI_LABELS),
                "export_filename": self.export_filename,
                "progress": {
                    "reviewed_candidates": reviewed,
                    "remaining_candidates": total - reviewed,
                    "total_candidates": total,
                    "completed_tracks": sum(
                        all(candidate["review"]["label"] for candidate in case["candidates"])
                        for case in cases
                    ),
                    "total_tracks": len(cases),
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
        stable_track_id = str(stable_track_id or "").strip()
        video_id = str(video_id or "").strip()
        label = str(label or "").strip().upper()
        candidate_note = "" if candidate_note is None else str(candidate_note)
        track_note = "" if track_note is None else str(track_note)
        if label not in REVIEW_LABELS:
            raise Stage5B1AValidationError("invalid Stage 5B.1E review label")
        if len(candidate_note) > MAX_NOTE_LENGTH or len(track_note) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError("review notes must not exceed 2000 characters")
        with self._lock:
            rows = self._read_rows()
            target = next(
                (
                    row for row in rows
                    if row["stable_track_id"] == stable_track_id
                    and row["candidate_video_id"] == video_id
                ),
                None,
            )
            if target is None:
                raise Stage5B1AValidationError("unknown Stage 5B.1E review identity")
            target["candidate_review_label"] = label
            target["candidate_note"] = candidate_note
            for row in rows:
                if row["stable_track_id"] == stable_track_id:
                    row["track_note"] = track_note
            temporary = self.review_path.with_suffix(
                self.review_path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp"
            )
            try:
                with temporary.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
                    writer.writeheader()
                    writer.writerows(rows)
                temporary.replace(self.review_path)
            finally:
                if temporary.exists():
                    temporary.unlink()
        return {
            "ok": True, "stable_track_id": stable_track_id, "video_id": video_id,
            "review": {"label": label, "note": candidate_note},
            "track_note": track_note,
        }
