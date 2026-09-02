"""Atomic browser-review state for the blinded Stage 5B.1B fresh challenge."""
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
from .stage5b1b_challenge_audit import (
    QUEUE_SCHEMA_VERSION,
    REVIEW_COLUMNS,
    REVIEW_LABELS,
    REVIEW_SCHEMA_VERSION,
)


MAX_NOTE_LENGTH = 2_000
UI_LABELS = ("IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN")


class Stage5B1BChallengeReviewStore:
    """Expose only blinded raw metadata and persist reviewer-owned CSV fields."""

    def __init__(
        self,
        manifest: ChallengeManifest,
        queue_path: str | Path,
        review_path: str | Path,
        *,
        session_mode: str = "stage5b1b_fresh_challenge_human_audit",
        export_filename: str = "stage5b1b-fresh-challenge-human-review.csv",
        shuffle_salt: str = "fresh-human-review-v1",
    ) -> None:
        self.manifest = manifest
        self.queue_path = Path(queue_path)
        self.review_path = Path(review_path)
        self.session_mode = session_mode
        self.export_filename = export_filename
        self.shuffle_salt = shuffle_salt
        self._lock = threading.RLock()
        self._manifest_by_id = {
            item.track.stable_track_id: item.track for item in manifest.tracks
        }
        self._queue_cases = self._read_queue()
        self._read_rows()

    def _read_queue(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        try:
            value = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise Stage5B1AValidationError(
                f"cannot load fresh-challenge audit queue: {self.queue_path}"
            ) from exc
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != QUEUE_SCHEMA_VERSION
        ):
            raise Stage5B1AValidationError("unexpected fresh-challenge audit queue schema")
        if value.get("manifest_sha256") != self.manifest.sha256:
            raise Stage5B1AValidationError("fresh-challenge audit queue manifest changed")
        rows = value.get("cases")
        if not isinstance(rows, list) or not rows:
            raise Stage5B1AValidationError("fresh-challenge audit queue contains no cases")
        output: list[tuple[str, tuple[str, ...]]] = []
        identities: set[tuple[str, str]] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise Stage5B1AValidationError("invalid fresh-challenge audit case")
            stable_id = row.get("stable_track_id")
            video_ids = row.get("candidate_video_ids")
            if (
                stable_id not in self._manifest_by_id
                or not isinstance(video_ids, list)
                or not video_ids
            ):
                raise Stage5B1AValidationError("invalid fresh-challenge audit identity")
            normalized = tuple(str(video_id).strip() for video_id in video_ids)
            if len(normalized) != len(set(normalized)) or any(
                not YOUTUBE_VIDEO_ID.fullmatch(video_id) for video_id in normalized
            ):
                raise Stage5B1AValidationError("invalid fresh-challenge audit candidate IDs")
            if any((stable_id, video_id) in identities for video_id in normalized):
                raise Stage5B1AValidationError("duplicate fresh-challenge audit identity")
            identities.update((stable_id, video_id) for video_id in normalized)
            output.append((stable_id, normalized))
        if len(output) != len({stable_id for stable_id, _ in output}):
            raise Stage5B1AValidationError("duplicate fresh-challenge audit track")
        if value.get("track_count") != len(output) or value.get(
            "candidate_count"
        ) != len(identities):
            raise Stage5B1AValidationError("fresh-challenge audit queue accounting changed")
        return tuple(output)

    def _read_rows(self) -> list[dict[str, str]]:
        if not self.review_path.exists():
            raise Stage5B1AValidationError(
                f"fresh-challenge review artifact does not exist: {self.review_path}"
            )
        with self.review_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != REVIEW_COLUMNS:
                raise Stage5B1AValidationError("unexpected fresh-challenge review CSV columns")
            rows = list(reader)
        expected = [
            (stable_id, video_id)
            for stable_id, video_ids in self._queue_cases
            for video_id in video_ids
        ]
        actual: list[tuple[str, str]] = []
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            stable_id = row["stable_track_id"].strip()
            video_id = row["candidate_video_id"].strip()
            if row["review_schema_version"] != REVIEW_SCHEMA_VERSION:
                raise Stage5B1AValidationError("unexpected fresh-challenge review row schema")
            label = row["candidate_review_label"].strip().upper()
            if label not in REVIEW_LABELS:
                raise Stage5B1AValidationError(
                    f"invalid fresh-challenge review label: {label}"
                )
            if not YOUTUBE_VIDEO_ID.fullmatch(video_id):
                raise Stage5B1AValidationError("invalid fresh-challenge candidate video ID")
            if (
                len(row["candidate_note"]) > MAX_NOTE_LENGTH
                or len(row["track_note"]) > MAX_NOTE_LENGTH
            ):
                raise Stage5B1AValidationError("fresh-challenge review note exceeds maximum length")
            row["candidate_review_label"] = label
            actual.append((stable_id, video_id))
            grouped[stable_id].append(row)
        if actual != expected:
            raise Stage5B1AValidationError("fresh-challenge review rows do not match audit queue order")

        for stable_id, candidate_rows in grouped.items():
            target = self._manifest_by_id[stable_id]
            expected_artists = " | ".join(target.artists)
            expected_duration = str(target.duration_ms / 1000.0)
            if any(
                row["expected_title"] != target.title
                or row["expected_artists"] != expected_artists
                or row["expected_album"] != (target.album or "")
                or row["expected_duration_seconds"] != expected_duration
                or row["expected_release_year"] != str(target.release_year or "")
                for row in candidate_rows
            ):
                raise Stage5B1AValidationError("fresh-challenge target metadata changed")
            if len({row["track_note"] for row in candidate_rows}) != 1:
                raise Stage5B1AValidationError(
                    f"track note is inconsistent across candidates for {stable_id}"
                )
        return rows

    @staticmethod
    def _number(
        row: dict[str, str],
        name: str,
        converter: type[int] | type[float],
    ) -> int | float | None:
        value = row[name].strip()
        return converter(value) if value else None

    def session(self) -> dict[str, Any]:
        with self._lock:
            rows = self._read_rows()
            grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in rows:
                grouped[row["stable_track_id"]].append(row)
            cases = []
            for stable_id, _ in self._queue_cases:
                target = self._manifest_by_id[stable_id]
                candidate_rows = grouped[stable_id]
                display_rows = sorted(
                    candidate_rows,
                    key=lambda row: hashlib.sha256(
                        (
                            f"{self.manifest.sha256}|{self.shuffle_salt}|"
                            f"{stable_id}|{row['candidate_video_id']}"
                        ).encode()
                    ).hexdigest(),
                )
                cases.append(
                    {
                        "stable_track_id": stable_id,
                        "track": {
                            "title": target.title,
                            "artists": list(target.artists),
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
                                "view_count": self._number(
                                    row, "candidate_view_count", int
                                ),
                                "description": row["candidate_description"] or None,
                                "review": {
                                    "label": row["candidate_review_label"],
                                    "note": row["candidate_note"],
                                },
                            }
                            for index, row in enumerate(display_rows, start=1)
                        ],
                    }
                )
            reviewed = sum(
                bool(candidate["review"]["label"])
                for case in cases
                for candidate in case["candidates"]
            )
            completed_tracks = sum(
                all(candidate["review"]["label"] for candidate in case["candidates"])
                for case in cases
            )
            total = sum(len(case["candidates"]) for case in cases)
            return {
                "schema_version": "stage5b1b-fresh-challenge-review-session-v1",
                "mode": self.session_mode,
                "manifest_sha256": self.manifest.sha256,
                "labels": list(UI_LABELS),
                "export_filename": self.export_filename,
                "progress": {
                    "reviewed_candidates": reviewed,
                    "remaining_candidates": total - reviewed,
                    "total_candidates": total,
                    "completed_tracks": completed_tracks,
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
            raise Stage5B1AValidationError(
                "candidate label must be IDEAL, ACCEPTABLE, WRONG, UNCERTAIN, or blank"
            )
        if len(candidate_note) > MAX_NOTE_LENGTH or len(track_note) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError(
                f"review notes must not exceed {MAX_NOTE_LENGTH} characters"
            )

        with self._lock:
            rows = self._read_rows()
            target = next(
                (
                    row
                    for row in rows
                    if row["stable_track_id"] == stable_track_id
                    and row["candidate_video_id"] == video_id
                ),
                None,
            )
            if target is None:
                raise Stage5B1AValidationError("unknown fresh-challenge candidate identity")
            target["candidate_review_label"] = label
            target["candidate_note"] = candidate_note
            for row in rows:
                if row["stable_track_id"] == stable_track_id:
                    row["track_note"] = track_note
            temporary = self.review_path.with_suffix(
                self.review_path.suffix
                + f".{os.getpid()}.{threading.get_ident()}.tmp"
            )
            try:
                with temporary.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(
                        handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n"
                    )
                    writer.writeheader()
                    writer.writerows(rows)
                temporary.replace(self.review_path)
            finally:
                if temporary.exists():
                    temporary.unlink()
        return {
            "ok": True,
            "stable_track_id": stable_track_id,
            "video_id": video_id,
            "review": {"label": label, "note": candidate_note},
            "track_note": track_note,
        }
