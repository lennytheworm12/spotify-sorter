"""Persistent human-review state for the Stage 5B.1A2 yt-dlp experiment."""

from __future__ import annotations

import csv
import os
import threading
from pathlib import Path
from typing import Any

from .stage5b1a2_review import REVIEW_COLUMNS
from .stage5b1a_models import FrozenTrackManifest, Stage5B1AValidationError
from .stage5b1a_review import NOT_IN_TOP_5, UNCERTAIN


UI_LABELS = ("1", "2", "3", "4", "5", NOT_IN_TOP_5, UNCERTAIN)
MAX_NOTE_LENGTH = 2_000


class Stage5B1A2ReviewStore:
    """Expose rich discovery cases while persisting only reviewer-owned fields."""

    def __init__(
        self,
        manifest: FrozenTrackManifest,
        results: dict[str, Any],
        review_path: str | Path,
    ) -> None:
        self.manifest = manifest
        self.results = results
        self.review_path = Path(review_path)
        self._lock = threading.RLock()
        self._tracks = self._validate_results()
        self._read_review_rows()

    def _validate_results(self) -> tuple[dict[str, Any], ...]:
        tracks = self.results.get("tracks")
        if not isinstance(tracks, list):
            raise Stage5B1AValidationError("yt-dlp results tracks must be an array")
        identities = []
        for row in tracks:
            if not isinstance(row, dict) or not isinstance(row.get("track"), dict):
                raise Stage5B1AValidationError("invalid yt-dlp result track row")
            stable_id = row["track"].get("stable_track_id")
            candidates = row.get("candidates")
            if not isinstance(stable_id, str) or not isinstance(candidates, list):
                raise Stage5B1AValidationError("invalid yt-dlp review case")
            identities.append(stable_id)
        if tuple(identities) != self.manifest.stable_track_ids:
            raise Stage5B1AValidationError("yt-dlp results do not match frozen manifest order")
        return tuple(tracks)

    def _read_review_rows(self) -> list[dict[str, str]]:
        if not self.review_path.exists():
            raise Stage5B1AValidationError(f"review artifact does not exist: {self.review_path}")
        with self.review_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != REVIEW_COLUMNS:
                raise Stage5B1AValidationError("unexpected yt-dlp human-review CSV columns")
            rows = list(reader)
        identities = tuple((row.get("stable_track_id") or "").strip() for row in rows)
        if identities != self.manifest.stable_track_ids:
            raise Stage5B1AValidationError("review CSV does not match frozen manifest order")
        for row in rows:
            label = (row.get("review_label") or "").strip().upper()
            if label and label not in UI_LABELS:
                raise Stage5B1AValidationError(
                    f"invalid review label for {row['stable_track_id']}: {label}"
                )
        return rows

    @staticmethod
    def _candidate(candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "rank": candidate.get("rank"),
            "youtube_video_id": candidate.get("youtube_video_id"),
            "url": candidate.get("canonical_url") or candidate.get("url"),
            "title": candidate.get("title"),
            "uploader": candidate.get("uploader"),
            "channel": candidate.get("channel"),
            "duration_seconds": candidate.get("duration_seconds"),
            "description": candidate.get("description"),
            "availability": candidate.get("availability"),
            "live_status": candidate.get("live_status"),
        }

    def session(self) -> dict[str, Any]:
        with self._lock:
            review_by_id = {row["stable_track_id"]: row for row in self._read_review_rows()}
            cases = []
            for discovered in self._tracks:
                track = discovered["track"]
                stable_id = track["stable_track_id"]
                review = review_by_id[stable_id]
                cases.append(
                    {
                        "stable_track_id": stable_id,
                        "track": {
                            "title": track.get("title"),
                            "artists": track.get("artists", []),
                            "album": track.get("album"),
                            "release_year": track.get("release_year"),
                            "duration_ms": track.get("duration_ms"),
                        },
                        "case_tags": discovered.get("case_tags", []),
                        "case_rationale": discovered.get("case_rationale"),
                        "query": discovered.get("query"),
                        "candidates": [self._candidate(value) for value in discovered["candidates"]],
                        "error": discovered.get("error"),
                        "warnings": discovered.get("warnings", []),
                        "review": {
                            "label": (review.get("review_label") or "").strip().upper(),
                            "note": review.get("optional_note") or "",
                        },
                    }
                )
            reviewed = sum(bool(case["review"]["label"]) for case in cases)
            return {
                "schema_version": "stage5b1a2-review-session-v1",
                "mode": "stage5b1a2_ytdlp_human_review",
                "experiment_status": self.results.get("status"),
                "manifest_sha256": self.manifest.sha256,
                "labels": list(UI_LABELS),
                "progress": {
                    "reviewed": reviewed,
                    "remaining": len(cases) - reviewed,
                    "total": len(cases),
                },
                "cases": cases,
            }

    def submit(self, stable_track_id: str, label: str, note: str = "") -> dict[str, Any]:
        stable_track_id = str(stable_track_id or "").strip()
        label = str(label or "").strip().upper()
        note = str(note or "").strip()
        if stable_track_id not in self.manifest.stable_track_ids:
            raise Stage5B1AValidationError("unknown stable_track_id")
        if label not in UI_LABELS:
            raise Stage5B1AValidationError("review label must be 1-5, NOT_IN_TOP_5, or UNCERTAIN")
        if len(note) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError(f"optional note exceeds {MAX_NOTE_LENGTH} characters")
        track_index = self.manifest.stable_track_ids.index(stable_track_id)
        if label.isdigit() and int(label) > len(self._tracks[track_index]["candidates"]):
            raise Stage5B1AValidationError("review rank exceeds available candidates")

        with self._lock:
            rows = self._read_review_rows()
            row = rows[track_index]
            row["review_label"] = label
            row["optional_note"] = note
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
            "ok": True,
            "stable_track_id": stable_track_id,
            "review": {"label": label, "note": note},
        }
