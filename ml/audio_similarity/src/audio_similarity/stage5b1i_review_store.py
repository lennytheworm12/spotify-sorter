"""Atomic local-review state for the Stage 5B.1I all-candidate oracle audit."""
from __future__ import annotations

import csv
import json
import os
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

from .stage5b1a_discovery import YOUTUBE_VIDEO_ID
from .stage5b1a_models import Stage5B1AValidationError
from .stage5b1i_human_oracle import QUEUE_SCHEMA_VERSION
from .stage5b1i_review import (
    REVIEW_COLUMNS,
    REVIEW_LABELS,
    load_human_review,
)


MAX_NOTE_LENGTH = 2_000
UI_LABELS = ("IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN")


class Stage5B1IReviewStore:
    """Serve blinded candidates and atomically persist reviewer-owned CSV fields."""

    def __init__(
        self, queue_path: Path, review_path: Path, universe: dict[str, Any]
    ) -> None:
        self.queue_path = Path(queue_path)
        self.review_path = Path(review_path)
        self._lock = threading.RLock()
        self.queue = self._load_queue()
        self._evidence = {
            (track["track"]["stable_track_id"], row["candidate"]["video_id"]):
            row["resolver_evidence"]
            for track in universe["tracks"] for row in track["candidates"]
        }
        expected_evidence = {
            (case["stable_track_id"], video_id)
            for case in self.queue["cases"] for video_id in case["candidate_video_ids"]
        }
        if set(self._evidence) != expected_evidence:
            raise Stage5B1AValidationError(
                "Stage 5B.1I resolver evidence does not match the review queue"
            )
        self._validate_rows(load_human_review(self.review_path))

    def _load_queue(self) -> dict[str, Any]:
        try:
            value = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise Stage5B1AValidationError(
                f"cannot load Stage 5B.1I review queue: {self.queue_path}"
            ) from exc
        if not isinstance(value, dict) or value.get("schema_version") != QUEUE_SCHEMA_VERSION:
            raise Stage5B1AValidationError("unexpected Stage 5B.1I review queue schema")
        cases = value.get("cases")
        if not isinstance(cases, list) or len(cases) != 8:
            raise Stage5B1AValidationError("Stage 5B.1I queue must contain eight tracks")
        stable_ids = [row.get("stable_track_id") for row in cases]
        if len(stable_ids) != len(set(stable_ids)):
            raise Stage5B1AValidationError("duplicate Stage 5B.1I review track")
        identities = [
            (row["stable_track_id"], video_id)
            for row in cases
            for video_id in row.get("candidate_video_ids", [])
        ]
        if (
            len(identities) != value.get("candidate_count")
            or len(identities) != len(set(identities))
            or any(not YOUTUBE_VIDEO_ID.fullmatch(video_id) for _, video_id in identities)
        ):
            raise Stage5B1AValidationError("invalid Stage 5B.1I queue candidate accounting")
        for row in cases:
            video_ids = row.get("candidate_video_ids")
            if not isinstance(video_ids, list) or len(video_ids) > 5:
                raise Stage5B1AValidationError("invalid Stage 5B.1I candidate list")
            expected = "AVAILABLE" if video_ids else "NO_Q0_CANDIDATES"
            if row.get("candidate_availability") != expected:
                raise Stage5B1AValidationError("inconsistent Stage 5B.1I availability")
        return value

    def _validate_rows(self, rows: list[dict[str, str]]) -> None:
        expected = [
            (case["stable_track_id"], video_id)
            for case in self.queue["cases"]
            for video_id in case["candidate_video_ids"]
        ]
        actual = [(row["stable_track_id"], row["candidate_video_id"]) for row in rows]
        if actual != expected:
            raise Stage5B1AValidationError("review rows do not match frozen Stage 5B.1I queue")
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            if (
                len(row["candidate_note"]) > MAX_NOTE_LENGTH
                or len(row["track_note"]) > MAX_NOTE_LENGTH
            ):
                raise Stage5B1AValidationError("Stage 5B.1I review note is too long")
            grouped[row["stable_track_id"]].append(row)
        for stable_id, candidate_rows in grouped.items():
            ranks = [int(row["candidate_rank"]) for row in candidate_rows]
            if ranks != list(range(1, len(candidate_rows) + 1)):
                raise Stage5B1AValidationError(f"invalid Stage 5B.1I ranks: {stable_id}")
            if len({row["track_note"] for row in candidate_rows}) != 1:
                raise Stage5B1AValidationError(f"inconsistent track note: {stable_id}")

    @staticmethod
    def _number(row: dict[str, str], name: str, converter: type[int] | type[float]):
        value = row[name].strip()
        return converter(value) if value else None

    def session(self) -> dict[str, Any]:
        with self._lock:
            rows = load_human_review(self.review_path)
            self._validate_rows(rows)
            grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in rows:
                grouped[row["stable_track_id"]].append(row)
            cases = []
            for case in self.queue["cases"]:
                stable_id = case["stable_track_id"]
                target = case["track"]
                candidate_rows = grouped.get(stable_id, [])
                cases.append({
                    "stable_track_id": stable_id,
                    "candidate_availability": case["candidate_availability"],
                    "availability_note": (
                        None if candidate_rows else
                        "The frozen Q0 ytsearch5 result contained no candidates. This track is documented as unavailable and requires no fabricated judgment."
                    ),
                    "track": {
                        "title": target["title"],
                        "artists": list(target["artists"]),
                        "album": target.get("album"),
                        "duration_seconds": (
                            target["duration_ms"] / 1000.0
                            if target.get("duration_ms") is not None else None
                        ),
                        "release_year": target.get("release_year"),
                        "version_descriptors": case["target_version_descriptors"],
                    },
                    "track_note": candidate_rows[0]["track_note"] if candidate_rows else "",
                    "candidates": [
                        {
                            "rank": int(row["candidate_rank"]),
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
                            "resolver_evidence": self._evidence[(
                                stable_id, row["candidate_video_id"]
                            )],
                            "review": {
                                "label": row["candidate_review_label"],
                                "note": row["candidate_note"],
                            },
                        }
                        for row in candidate_rows
                    ],
                })
            reviewed = sum(
                bool(candidate["review"]["label"])
                for case in cases for candidate in case["candidates"]
            )
            completed_reviewable = sum(
                bool(case["candidates"])
                and all(candidate["review"]["label"] for candidate in case["candidates"])
                for case in cases
            )
            return {
                "schema_version": "stage5b1i-review-session-v1",
                "mode": "stage5b1i_human_oracle_tail",
                "labels": list(UI_LABELS),
                "export_filename": "stage5b1i-human-oracle-tail-review.csv",
                "progress": {
                    "reviewed_candidates": reviewed,
                    "remaining_candidates": self.queue["candidate_count"] - reviewed,
                    "total_candidates": self.queue["candidate_count"],
                    "completed_tracks": completed_reviewable,
                    "reviewable_tracks": self.queue["tracks_with_candidates"],
                    "unavailable_tracks": self.queue["tracks_without_candidates"],
                    "total_tracks": self.queue["track_count"],
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
        candidate_note = str(candidate_note or "")
        track_note = str(track_note or "")
        if label not in REVIEW_LABELS:
            raise Stage5B1AValidationError(
                "candidate label must be IDEAL, ACCEPTABLE, WRONG, UNCERTAIN, or blank"
            )
        if len(candidate_note) > MAX_NOTE_LENGTH or len(track_note) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError(
                f"review notes must not exceed {MAX_NOTE_LENGTH} characters"
            )
        with self._lock:
            rows = load_human_review(self.review_path)
            self._validate_rows(rows)
            target = next(
                (
                    row for row in rows
                    if row["stable_track_id"] == stable_track_id
                    and row["candidate_video_id"] == video_id
                ),
                None,
            )
            if target is None:
                raise Stage5B1AValidationError("unknown Stage 5B.1I candidate identity")
            target["candidate_review_label"] = label
            target["candidate_note"] = candidate_note
            for row in rows:
                if row["stable_track_id"] == stable_track_id:
                    row["track_note"] = track_note
            temporary = self.review_path.with_suffix(
                self.review_path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp"
            )
            try:
                with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
                    writer = csv.DictWriter(
                        handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n"
                    )
                    writer.writeheader()
                    writer.writerows(rows)
                os.replace(temporary, self.review_path)
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
