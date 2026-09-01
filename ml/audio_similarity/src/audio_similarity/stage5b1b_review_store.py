"""Atomic autosave state for the Stage 5B.1B held-out candidate reviewer."""
from __future__ import annotations

import csv
import os
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

from .stage5b1a_discovery import YOUTUBE_VIDEO_ID
from .stage5b1a_models import Stage5B1AValidationError
from .stage5b1b_artifacts import REVIEW_COLUMNS, REVIEW_LABELS, REVIEW_SCHEMA_VERSION
from .stage5b1b_manifest import HeldoutManifest


MAX_NOTE_LENGTH = 2_000
UI_LABELS = ("IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN")


class Stage5B1BReviewStore:
    """Read frozen candidate evidence and atomically persist reviewer-owned fields."""

    def __init__(
        self,
        manifest: HeldoutManifest,
        review_path: str | Path,
        *,
        case_filter: tuple[str, ...] | None = None,
        candidate_filter: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.manifest = manifest
        self.review_path = Path(review_path)
        self._lock = threading.RLock()
        self._manifest_by_id = {
            item.track.stable_track_id: item for item in self.manifest.tracks
        }
        if case_filter is not None:
            unknown = set(case_filter) - set(self._manifest_by_id)
            if unknown or not case_filter or len(case_filter) != len(set(case_filter)):
                raise Stage5B1AValidationError("invalid manual audit case filter")
        if candidate_filter is not None and (
            case_filter is None or tuple(candidate_filter) != case_filter
        ):
            raise Stage5B1AValidationError("candidate filter must match case filter order")
        self.case_filter = case_filter
        self.candidate_filter = candidate_filter
        rows = self._read_rows()
        if self.candidate_filter is not None:
            known = {
                (row["stable_track_id"], row["candidate_video_id"]) for row in rows
            }
            requested = {
                (stable_id, video_id)
                for stable_id, video_ids in self.candidate_filter.items()
                for video_id in video_ids
            }
            if not requested or not requested <= known:
                raise Stage5B1AValidationError("candidate filter contains unknown candidates")

    def _read_rows(self) -> list[dict[str, str]]:
        if not self.review_path.exists():
            raise Stage5B1AValidationError(
                f"held-out review artifact does not exist: {self.review_path}"
            )
        with self.review_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != REVIEW_COLUMNS:
                raise Stage5B1AValidationError("unexpected held-out review CSV columns")
            rows = list(reader)
        if not rows:
            raise Stage5B1AValidationError("held-out review CSV contains no candidates")

        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        identities: set[tuple[str, str]] = set()
        for row in rows:
            stable_id = row["stable_track_id"].strip()
            video_id = row["candidate_video_id"].strip()
            identity = (stable_id, video_id)
            if (
                stable_id not in self._manifest_by_id
                or not YOUTUBE_VIDEO_ID.fullmatch(video_id)
                or identity in identities
            ):
                raise Stage5B1AValidationError("invalid or duplicate held-out review identity")
            if row["review_schema_version"] != REVIEW_SCHEMA_VERSION:
                raise Stage5B1AValidationError("unexpected held-out review row schema")
            label = row["candidate_review_label"].strip().upper()
            if label not in REVIEW_LABELS:
                raise Stage5B1AValidationError(f"invalid held-out review label: {label}")
            if len(row["candidate_note"]) > MAX_NOTE_LENGTH:
                raise Stage5B1AValidationError("candidate note exceeds maximum length")
            if len(row["track_note"]) > MAX_NOTE_LENGTH:
                raise Stage5B1AValidationError("track note exceeds maximum length")
            identities.add(identity)
            grouped[stable_id].append(row)

        ordered_ids = tuple(grouped)
        if ordered_ids != self.manifest.stable_track_ids:
            raise Stage5B1AValidationError("review tracks do not match frozen manifest order")
        for stable_id, candidates in grouped.items():
            ranks = [int(row["candidate_rank"]) for row in candidates]
            if ranks != list(range(1, len(candidates) + 1)) or len(candidates) > 5:
                raise Stage5B1AValidationError(
                    f"candidate ranks are not contiguous for {stable_id}"
                )
            notes = {row["track_note"] for row in candidates}
            if len(notes) != 1:
                raise Stage5B1AValidationError(
                    f"track note is inconsistent across candidates for {stable_id}"
                )
        return rows

    @staticmethod
    def _candidate(row: dict[str, str]) -> dict[str, Any]:
        def number(name: str, converter: type[int] | type[float]) -> int | float | None:
            value = row[name].strip()
            return converter(value) if value else None

        return {
            "rank": int(row["candidate_rank"]),
            "video_id": row["candidate_video_id"],
            "title": row["candidate_title"],
            "uploader": row["candidate_uploader"] or None,
            "channel": row["candidate_channel"] or None,
            "duration_seconds": number("candidate_duration_seconds", float),
            "view_count": number("candidate_view_count", int),
            "review": {
                "label": row["candidate_review_label"].strip().upper(),
                "note": row["candidate_note"],
            },
        }

    def session(self) -> dict[str, Any]:
        with self._lock:
            rows = self._read_rows()
            grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in rows:
                grouped[row["stable_track_id"]].append(row)
            cases = []
            displayed_ids = self.case_filter or self.manifest.stable_track_ids
            for stable_id in displayed_ids:
                item = self._manifest_by_id[stable_id]
                candidate_rows = grouped[stable_id]
                if self.candidate_filter is not None:
                    included = set(self.candidate_filter[stable_id])
                    candidate_rows = [
                        row
                        for row in candidate_rows
                        if row["candidate_video_id"] in included
                    ]
                track = item.track
                cases.append(
                    {
                        "stable_track_id": stable_id,
                        "track": {
                            "title": track.title,
                            "artists": list(track.artists),
                            "album": track.album,
                            "duration_seconds": (
                                track.duration_ms / 1000.0
                                if track.duration_ms is not None else None
                            ),
                            "release_year": track.release_year,
                        },
                        "case_tags": list(item.case_tags),
                        "case_rationale": item.case_rationale,
                        "query": candidate_rows[0]["query"],
                        "track_note": candidate_rows[0]["track_note"],
                        "candidates": [self._candidate(row) for row in candidate_rows],
                    }
                )
            reviewed = sum(
                bool(candidate["review"]["label"])
                for case in cases for candidate in case["candidates"]
            )
            completed_tracks = sum(
                all(candidate["review"]["label"] for candidate in case["candidates"])
                for case in cases
            )
            total = sum(len(case["candidates"]) for case in cases)
            return {
                "schema_version": "stage5b1b-review-session-v1",
                "mode": (
                    "stage5b1b_targeted_sol_audit"
                    if self.case_filter is not None
                    else "stage5b1b_heldout_candidate_review"
                ),
                "manifest_sha256": self.manifest.sha256,
                "labels": list(UI_LABELS),
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
        if stable_track_id not in self._manifest_by_id:
            raise Stage5B1AValidationError("unknown stable_track_id")
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
                    row for row in rows
                    if row["stable_track_id"] == stable_track_id
                    and row["candidate_video_id"] == video_id
                ),
                None,
            )
            if target is None:
                raise Stage5B1AValidationError("unknown candidate identity")
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
