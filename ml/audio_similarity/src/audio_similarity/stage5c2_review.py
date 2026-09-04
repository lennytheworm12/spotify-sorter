"""Resumable pairwise similarity-review state for Stage 5C.2."""
from __future__ import annotations

import csv
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5c2_analysis import REVIEW_COLUMNS, canonical_pair_id
from .stage5c2_discovery import _json


LABELS = ("3", "2", "1", "0", "UNSURE")
MAX_NOTE_LENGTH = 2_000
YOUTUBE_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
LOCAL_AUDIO_CONTENT_TYPES = frozenset(
    {"audio/aac", "audio/flac", "audio/mp4", "audio/mpeg", "audio/ogg", "audio/webm"}
)
FROZEN_SEGMENT_WINDOWS = (
    {"index": 1, "start_seconds": 2.5, "end_seconds": 7.5},
    {"index": 2, "start_seconds": 12.5, "end_seconds": 17.5},
    {"index": 3, "start_seconds": 22.5, "end_seconds": 27.5},
)


class Stage5C2ReviewStore:
    """Persist one unordered sonic-similarity label across reciprocal ranks."""

    def __init__(
        self,
        queue_path: str | Path,
        review_path: str | Path,
        selected_sources_path: str | Path | None = None,
        local_audio_index_path: str | Path | None = None,
    ) -> None:
        self.queue_path = Path(queue_path).resolve()
        self.review_path = Path(review_path).resolve()
        self._queue = _json(self.queue_path)
        if self._queue.get("schema_version") != "stage5c2-similarity-review-queue-v1":
            raise Stage5B1AValidationError("invalid Stage 5C.2 review queue")
        self._local_audio_by_spotify_id: dict[str, tuple[Path, str]] = {}
        self._playback_by_spotify_id = self._load_playback(
            selected_sources_path, local_audio_index_path
        )
        self._lock = threading.RLock()
        self._read_rows()

    def _load_playback(
        self,
        selected_sources_path: str | Path | None,
        local_audio_index_path: str | Path | None,
    ) -> dict[str, dict[str, Any]]:
        if selected_sources_path is None:
            return {}
        payload = _json(Path(selected_sources_path).resolve())
        if payload.get("schema_version") != "stage5c2-selected-sources-v1":
            raise Stage5B1AValidationError("invalid Stage 5C.2 selected sources")
        playback: dict[str, dict[str, Any]] = {}
        selected_sha = file_sha256(Path(selected_sources_path).resolve())
        for source in payload.get("tracks", []):
            spotify_id = str(source.get("spotify_track_id", ""))
            video_id = str(source.get("selected_youtube_video_id", ""))
            if not spotify_id or not YOUTUBE_VIDEO_ID.fullmatch(video_id):
                raise Stage5B1AValidationError("invalid frozen playback identity")
            if spotify_id in playback:
                raise Stage5B1AValidationError("duplicate frozen playback identity")
            playback[spotify_id] = {
                "provider": "YOUTUBE_FROZEN_SELECTED_SOURCE",
                "youtube_video_id": video_id,
                "watch_url": f"https://www.youtube.com/watch?v={video_id}",
                "segment_windows": [dict(window) for window in FROZEN_SEGMENT_WINDOWS],
            }
        queue_ids = {str(case["spotify_track_id"]) for case in self._queue["cases"]}
        if queue_ids != playback.keys():
            raise Stage5B1AValidationError(
                "frozen playback sources do not match the review queue"
            )
        if local_audio_index_path is None:
            return playback
        index_path = Path(local_audio_index_path).resolve()
        index = _json(index_path)
        if (
            index.get("schema_version")
            != "stage5c2a-local-research-audio-index-v1"
            or index.get("selected_sources_sha256") != selected_sha
            or not isinstance(index.get("tracks"), dict)
        ):
            raise Stage5B1AValidationError("invalid Stage 5C.2A local audio index")
        if queue_ids != index["tracks"].keys():
            raise Stage5B1AValidationError(
                "local audio sources do not match the amended review queue"
            )
        media_root = index_path.parent.resolve()
        local_playback: dict[str, dict[str, Any]] = {}
        selected_by_id = {
            row["spotify_track_id"]: row for row in payload["tracks"]
        }
        for spotify_id, provenance in index["tracks"].items():
            source = (media_root / provenance.get("retained_relative_path", "")).resolve()
            if (
                media_root not in source.parents
                or not source.is_file()
                or provenance.get("spotify_track_id") != spotify_id
                or provenance.get("youtube_video_id")
                != selected_by_id[spotify_id]["selected_youtube_video_id"]
                or source.stat().st_size != provenance.get("file_size_bytes")
                or file_sha256(source) != provenance.get("source_sha256")
            ):
                raise Stage5B1AValidationError(
                    f"invalid local playback source: {spotify_id}"
                )
            content_type = str(provenance.get("content_type", "application/octet-stream"))
            if content_type not in LOCAL_AUDIO_CONTENT_TYPES or source.stat().st_size <= 0:
                raise Stage5B1AValidationError(
                    f"invalid local playback media metadata: {spotify_id}"
                )
            self._local_audio_by_spotify_id[spotify_id] = (source, content_type)
            local_playback[spotify_id] = {
                "provider": "LOCAL_RESEARCH_AUDIO",
                "audio_url": f"/audio/track/{quote(spotify_id, safe='')}",
                "content_type": content_type,
                "youtube_video_id": provenance["youtube_video_id"],
                "segment_windows": [dict(window) for window in FROZEN_SEGMENT_WINDOWS],
            }
        return local_playback

    def local_audio_for_request(self, spotify_id: str) -> tuple[Path, str] | None:
        """Resolve an indexed local source without exposing arbitrary filesystem paths."""
        return self._local_audio_by_spotify_id.get(spotify_id)

    def _read_rows(self) -> list[dict[str, str]]:
        with self.review_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
                raise Stage5B1AValidationError("unexpected Stage 5C.2 review columns")
            rows = list(reader)
        identities: set[tuple[str, str]] = set()
        labels_by_pair: dict[str, str] = {}
        notes_by_pair: dict[str, str] = {}
        for row in rows:
            identity = (row["query_spotify_id"], row["neighbor_spotify_id"])
            if identity in identities:
                raise Stage5B1AValidationError("duplicate directional review identity")
            identities.add(identity)
            expected_pair = canonical_pair_id(*identity)
            if row["pair_id"] != expected_pair:
                raise Stage5B1AValidationError("review pair identity changed")
            label = row["human_label"].strip().upper()
            if label and label not in LABELS:
                raise Stage5B1AValidationError("invalid Stage 5C.2 human label")
            row["human_label"] = label
            if len(row["human_note"]) > MAX_NOTE_LENGTH:
                raise Stage5B1AValidationError("Stage 5C.2 review note is too long")
            if label:
                prior_label = labels_by_pair.setdefault(row["pair_id"], label)
                prior_note = notes_by_pair.setdefault(row["pair_id"], row["human_note"])
                if prior_label != label or prior_note != row["human_note"]:
                    raise Stage5B1AValidationError("reciprocal pair review disagrees")
        return rows

    def session(self) -> dict[str, Any]:
        with self._lock:
            rows = self._read_rows()
            by_direction = {
                (row["query_spotify_id"], row["neighbor_spotify_id"]): row
                for row in rows
            }
            cases = []
            for case in self._queue["cases"]:
                query_id = case["spotify_track_id"]
                neighbors = []
                for neighbor in case["neighbors"]:
                    row = by_direction[(query_id, neighbor["spotify_track_id"])]
                    neighbors.append(
                        neighbor
                        | {
                            "playback": self._playback_by_spotify_id.get(
                                neighbor["spotify_track_id"]
                            ),
                            "review": {
                                "label": row["human_label"],
                                "note": row["human_note"],
                                "timestamp": row["review_timestamp"],
                            }
                        }
                    )
                cases.append(
                    case
                    | {
                        "playback": self._playback_by_spotify_id.get(query_id),
                        "neighbors": neighbors,
                        "review_complete": all(
                            neighbor["review"]["label"] for neighbor in neighbors
                        ),
                    }
                )
            unique_pairs = {row["pair_id"] for row in rows}
            reviewed_pairs = {
                row["pair_id"] for row in rows if row["human_label"]
            }
            return {
                "schema_version": "stage5c2-review-session-v1",
                "mode": "stage5c2_similarity_review",
                "status": (
                    "HUMAN_REVIEW_COMPLETE"
                    if reviewed_pairs == unique_pairs
                    else "HUMAN_REVIEW_PENDING"
                ),
                "labels": {
                    "3": "VERY SIMILAR",
                    "2": "SIMILAR",
                    "1": "SOMEWHAT RELATED",
                    "0": "NOT SIMILAR",
                    "UNSURE": "UNSURE / SKIP",
                },
                "progress": {
                    "completed_query_tracks": sum(case["review_complete"] for case in cases),
                    "total_query_tracks": len(cases),
                    "reviewed_unique_pairs": len(reviewed_pairs),
                    "total_unique_pairs": len(unique_pairs),
                    "raw_top5_rows": len(rows),
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
        del track_note
        label = str(label or "").strip().upper()
        note = str(candidate_note or "")
        if label not in (*LABELS, ""):
            raise Stage5B1AValidationError("invalid Stage 5C.2 human label")
        if len(note) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError("Stage 5C.2 review note is too long")
        pair_id = canonical_pair_id(stable_track_id, video_id)
        with self._lock:
            rows = self._read_rows()
            if not any(
                row["query_spotify_id"] == stable_track_id
                and row["neighbor_spotify_id"] == video_id
                for row in rows
            ):
                raise Stage5B1AValidationError("unknown Stage 5C.2 review relationship")
            timestamp = datetime.now(timezone.utc).isoformat() if label else ""
            for row in rows:
                if row["pair_id"] == pair_id:
                    row["human_label"] = label
                    row["human_note"] = note
                    row["review_timestamp"] = timestamp
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
            "pair_id": pair_id,
            "query_spotify_id": stable_track_id,
            "neighbor_spotify_id": video_id,
            "review": {"label": label, "note": note, "timestamp": timestamp},
            "reciprocal_rows_updated": sum(row["pair_id"] == pair_id for row in rows),
        }
