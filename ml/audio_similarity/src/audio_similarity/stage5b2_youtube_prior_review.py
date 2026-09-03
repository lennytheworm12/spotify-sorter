"""Adaptive human review and metrics for the raw YouTube top-three prior."""
from __future__ import annotations

import csv
import json
import os
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from .stage5b1a_discovery import YOUTUBE_VIDEO_ID
from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b2_youtube_prior import (
    BENCHMARK_ID,
    H1_TOP1_SAFE_MINIMUM,
    H2_TOP3_SAFE_MINIMUM,
    SAMPLE_SIZE,
    STATUS_DISCOVERY_COMPLETE,
    YoutubePriorConfig,
    load_youtube_prior_manifest,
)


REVIEW_SCHEMA_VERSION = "stage5b2-youtube-prior-human-review-v1"
QUEUE_SCHEMA_VERSION = "stage5b2-youtube-prior-human-review-queue-v1"
SOL_SCHEMA_VERSION = "stage5b2-sol-evaluations-v1"
LABELS = ("IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN")
SAFE_LABELS = frozenset({"IDEAL", "ACCEPTABLE"})
MAX_NOTE_LENGTH = 2_000
REVIEW_COLUMNS = (
    "review_schema_version", "benchmark_id", "spotify_track_id",
    "expected_title", "expected_artists", "expected_album",
    "expected_duration_seconds", "expected_release_year", "search_query",
    "youtube_rank", "candidate_video_id", "candidate_url", "candidate_title",
    "candidate_uploader", "candidate_channel", "candidate_duration_seconds",
    "candidate_view_count", "candidate_description", "candidate_review_label",
    "candidate_note", "track_note",
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def write_human_review_artifacts(config: YoutubePriorConfig) -> tuple[dict[str, Any], Path]:
    manifest = load_youtube_prior_manifest(config)
    discovery_path = config.output_dir / "youtube_top3_discovery.json"
    discovery = _json(discovery_path)
    if discovery.get("status") != STATUS_DISCOVERY_COMPLETE:
        raise Stage5B1AValidationError("top-three discovery must be frozen before review")
    targets = {row["benchmark_id"]: row for row in manifest["tracks"]}
    queue_cases = []
    review_rows = []
    for row in discovery["tracks"]:
        benchmark_id = row["benchmark_id"]
        target = targets[benchmark_id]
        candidates = row["outcome"].get("candidates", [])
        queue_cases.append({
            "benchmark_id": benchmark_id,
            "candidate_video_ids_by_native_rank": [
                candidate["youtube_video_id"] for candidate in candidates
            ],
        })
        for candidate in candidates:
            review_rows.append({
                "review_schema_version": REVIEW_SCHEMA_VERSION,
                "benchmark_id": benchmark_id,
                "spotify_track_id": target["spotify_track_id"],
                "expected_title": target["title"],
                "expected_artists": " | ".join(target["artists"]),
                "expected_album": target.get("album") or "",
                "expected_duration_seconds": target["duration_ms"] / 1000,
                "expected_release_year": target.get("release_year") or "",
                "search_query": row["query"],
                "youtube_rank": candidate["rank"],
                "candidate_video_id": candidate["youtube_video_id"],
                "candidate_url": candidate.get("canonical_url") or candidate.get("url") or "",
                "candidate_title": candidate.get("title") or "",
                "candidate_uploader": candidate.get("uploader") or "",
                "candidate_channel": candidate.get("channel") or "",
                "candidate_duration_seconds": candidate.get("duration_seconds")
                if candidate.get("duration_seconds") is not None else "",
                "candidate_view_count": candidate.get("view_count")
                if candidate.get("view_count") is not None else "",
                "candidate_description": candidate.get("description") or "",
                "candidate_review_label": "",
                "candidate_note": "",
                "track_note": "",
            })
    queue = {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "benchmark_manifest_sha256": config.manifest_sha256,
        "discovery_sha256": file_sha256(discovery_path),
        "protocol": "REVIEW_NATIVE_RANKS_UNTIL_FIRST_SAFE",
        "safe_labels": sorted(SAFE_LABELS),
        "track_count": len(queue_cases),
        "candidate_count": len(review_rows),
        "cases": queue_cases,
    }
    queue_path = config.output_dir / "human_review_queue.json"
    atomic_json(queue_path, queue)
    review_path = config.output_dir / "human_review.csv"
    if review_path.exists():
        with review_path.open(encoding="utf-8", newline="") as handle:
            existing = list(csv.DictReader(handle))
        expected = [(row["benchmark_id"], str(row["youtube_rank"]), row["candidate_video_id"]) for row in review_rows]
        actual = [(row["benchmark_id"], row["youtube_rank"], row["candidate_video_id"]) for row in existing]
        if actual != expected:
            raise Stage5B1AValidationError("existing Stage 5B.2 review identities changed")
        return queue, review_path
    temporary = review_path.with_suffix(review_path.suffix + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(review_rows)
    temporary.replace(review_path)
    return queue, review_path


def _read_review_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise Stage5B1AValidationError("unexpected Stage 5B.2 review columns")
        rows = list(reader)
    seen = set()
    for row in rows:
        identity = (row["benchmark_id"], row["youtube_rank"], row["candidate_video_id"])
        if identity in seen or not YOUTUBE_VIDEO_ID.fullmatch(row["candidate_video_id"]):
            raise Stage5B1AValidationError("invalid Stage 5B.2 review identity")
        seen.add(identity)
        label = row["candidate_review_label"].strip().upper()
        if label and label not in LABELS:
            raise Stage5B1AValidationError("invalid Stage 5B.2 human label")
        row["candidate_review_label"] = label
        if len(row["candidate_note"]) > MAX_NOTE_LENGTH or len(row["track_note"]) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError("Stage 5B.2 review note is too long")
    return rows


def required_rank(rows: list[dict[str, str]]) -> int | None:
    """Return the next rank requiring review, or None when the track is complete."""

    ordered = sorted(rows, key=lambda row: int(row["youtube_rank"]))
    for row in ordered:
        label = row["candidate_review_label"]
        rank = int(row["youtube_rank"])
        if label in SAFE_LABELS:
            return None
        if not label:
            return rank
    return None


def first_safe_rank(rows: list[dict[str, str]]) -> int | None:
    for row in sorted(rows, key=lambda item: int(item["youtube_rank"])):
        if row["candidate_review_label"] in SAFE_LABELS:
            return int(row["youtube_rank"])
    return None


class YoutubePriorReviewStore:
    def __init__(self, review_path: str | Path) -> None:
        self.review_path = Path(review_path)
        self._lock = threading.RLock()
        self._read_grouped()

    def _read_grouped(self) -> dict[str, list[dict[str, str]]]:
        grouped: dict[str, list[dict[str, str]]] = {}
        for row in _read_review_rows(self.review_path):
            grouped.setdefault(row["benchmark_id"], []).append(row)
        if len(grouped) != SAMPLE_SIZE or any(len(rows) != 3 for rows in grouped.values()):
            raise Stage5B1AValidationError("Stage 5B.2 review must contain 100 × 3 rows")
        for rows in grouped.values():
            if sorted(int(row["youtube_rank"]) for row in rows) != [1, 2, 3]:
                raise Stage5B1AValidationError("Stage 5B.2 candidate ranks changed")
        return grouped

    @staticmethod
    def _number(value: str, converter: type[int] | type[float]) -> int | float | None:
        return converter(value) if value.strip() else None

    def session(self) -> dict[str, Any]:
        with self._lock:
            grouped = self._read_grouped()
            cases = []
            completed = 0
            reviewed = 0
            for benchmark_id, rows in grouped.items():
                ordered = sorted(rows, key=lambda row: int(row["youtube_rank"]))
                next_rank = required_rank(ordered)
                if next_rank is None:
                    completed += 1
                    visible_rank = first_safe_rank(ordered) or 3
                else:
                    visible_rank = next_rank
                reviewed += sum(bool(row["candidate_review_label"]) for row in ordered)
                first = ordered[0]
                visible = ordered[:visible_rank]
                cases.append({
                    "stable_track_id": benchmark_id,
                    "track": {
                        "title": first["expected_title"],
                        "artists": first["expected_artists"].split(" | "),
                        "album": first["expected_album"] or None,
                        "duration_seconds": self._number(first["expected_duration_seconds"], float),
                        "release_year": self._number(first["expected_release_year"], int),
                    },
                    "query": first["search_query"],
                    "track_note": first["track_note"],
                    "review_complete": next_rank is None,
                    "next_required_rank": next_rank,
                    "candidates": [{
                        "display_index": int(row["youtube_rank"]),
                        "rank": int(row["youtube_rank"]),
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
                        "is_current": next_rank == int(row["youtube_rank"]),
                    } for row in visible],
                })
            return {
                "schema_version": "stage5b2-youtube-prior-review-session-v1",
                "mode": "stage5b2_youtube_prior_review",
                "labels": list(LABELS),
                "export_filename": "stage5b2-youtube-prior-human-review.csv",
                "progress": {
                    "reviewed_candidates": reviewed,
                    "remaining_candidates": SAMPLE_SIZE - completed,
                    "total_candidates": 300,
                    "completed_tracks": completed,
                    "total_tracks": SAMPLE_SIZE,
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
        if label not in (*LABELS, ""):
            raise Stage5B1AValidationError("invalid Stage 5B.2 review label")
        if len(candidate_note) > MAX_NOTE_LENGTH or len(track_note) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError("Stage 5B.2 review note is too long")
        with self._lock:
            rows = _read_review_rows(self.review_path)
            grouped: dict[str, list[dict[str, str]]] = {}
            for row in rows:
                grouped.setdefault(row["benchmark_id"], []).append(row)
            target_rows = grouped.get(stable_track_id)
            target = next((row for row in target_rows or [] if row["candidate_video_id"] == video_id), None)
            if target is None:
                raise Stage5B1AValidationError("unknown Stage 5B.2 review identity")
            target_rank = int(target["youtube_rank"])
            next_rank = required_rank(target_rows or [])
            if label and next_rank is not None and target_rank > next_rank:
                raise Stage5B1AValidationError("review earlier YouTube ranks first")
            target["candidate_review_label"] = label
            target["candidate_note"] = candidate_note
            for row in target_rows or []:
                row["track_note"] = track_note
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
