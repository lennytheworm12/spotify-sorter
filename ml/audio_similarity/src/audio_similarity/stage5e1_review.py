"""Blinded, resumable pairwise human-review store for Stage 5E.1."""
from __future__ import annotations

import csv
import mimetypes
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5c2_analysis import canonical_pair_id
from .stage5e1_analysis import REVIEW_COLUMNS


LABELS = {
    "5": "EXTREMELY SIMILAR",
    "4": "VERY SIMILAR",
    "3": "MODERATELY SIMILAR",
    "2": "SOMEWHAT RELATED",
    "1": "NOT SIMILAR",
    "UNSURE": "UNSURE / SKIP",
}
MAX_NOTE_LENGTH = 2000


class Stage5E1ReviewStore:
    def __init__(self, queue_path: str | Path, review_path: str | Path, project_root: str | Path):
        import json

        self.queue_path = Path(queue_path).resolve()
        self.review_path = Path(review_path).resolve()
        self.root = Path(project_root).resolve()
        self._queue = json.loads(self.queue_path.read_text(encoding="utf-8"))
        if self._queue.get("schema_version") != "stage5e1-blinded-review-queue-v1":
            raise Stage5B1AValidationError("invalid Stage 5E.1 review queue")
        self._lock = threading.RLock()
        self._tracks: dict[str, dict[str, Any]] = {}
        for pair in self._queue["pairs"]:
            for side in (pair["left"], pair["right"]):
                spotify_id = side["spotify_track_id"]
                prior = self._tracks.setdefault(spotify_id, side)
                if prior != side:
                    raise Stage5B1AValidationError("review track metadata differs across pairs")
        self._local_audio: dict[str, tuple[Path, str]] = {}
        for spotify_id, track in self._tracks.items():
            source = (self.root / track["retained_source_path"]).resolve()
            media_root = (self.root / ".research_audio").resolve()
            if media_root not in source.parents or not source.is_file() or file_sha256(source) != track["source_sha256"]:
                raise Stage5B1AValidationError(f"invalid Stage 5E.1 local playback source: {spotify_id}")
            content_type = {
                ".m4a": "audio/mp4", ".webm": "audio/webm", ".opus": "audio/ogg"
            }.get(source.suffix.casefold()) or mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            if not content_type.startswith("audio/"):
                raise Stage5B1AValidationError(f"unsupported browser playback media: {source.suffix}")
            self._local_audio[spotify_id] = (source, content_type)
        self._read_rows()

    def _read_rows(self) -> list[dict[str, str]]:
        with self.review_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
                raise Stage5B1AValidationError("unexpected Stage 5E.1 review columns")
            rows = list(reader)
        expected = {pair["pair_id"] for pair in self._queue["pairs"]}
        if {row["pair_id"] for row in rows} != expected or len(rows) != len(expected):
            raise Stage5B1AValidationError("Stage 5E.1 review state does not match frozen queue")
        for row in rows:
            if row["pair_id"] != canonical_pair_id(row["left_spotify_id"], row["right_spotify_id"]):
                raise Stage5B1AValidationError("Stage 5E.1 review pair identity differs")
            if row["human_label"] and row["human_label"] not in LABELS:
                raise Stage5B1AValidationError("invalid Stage 5E.1 review label")
            if len(row["human_note"]) > MAX_NOTE_LENGTH:
                raise Stage5B1AValidationError("Stage 5E.1 review note is too long")
        return rows

    def local_audio_for_request(self, spotify_id: str) -> tuple[Path, str] | None:
        return self._local_audio.get(spotify_id)

    def _public_track(self, track: dict[str, Any]) -> dict[str, Any]:
        return {
            "spotify_track_id": track["spotify_track_id"],
            "title": track["title"],
            "artists": track["artists"],
            "album": track.get("album"),
            "playback": {
                "provider": "LOCAL_RESEARCH_AUDIO",
                "audio_url": f"/audio/track/{track['spotify_track_id']}",
            },
        }

    def session(self) -> dict[str, Any]:
        return self.session_page(
            offset=0,
            limit=min(250, max(1, len(self._queue["pairs"]))),
        )

    def session_page(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        review_filter: str = "all",
    ) -> dict[str, Any]:
        if review_filter not in {"all", "reviewed", "unreviewed"}:
            raise Stage5B1AValidationError("invalid Stage 5E.1 review filter")
        if offset < 0 or not 1 <= limit <= 250:
            raise Stage5B1AValidationError("invalid Stage 5E.1 review page")
        with self._lock:
            by_pair = {row["pair_id"]: row for row in self._read_rows()}
            all_pairs = []
            for pair in self._queue["pairs"]:
                row = by_pair[pair["pair_id"]]
                all_pairs.append(
                    {
                        "review_index": pair["review_index"],
                        "pair_id": pair["pair_id"],
                        "left": self._public_track(pair["left"]),
                        "right": self._public_track(pair["right"]),
                        "review": {
                            "label": row["human_label"],
                            "note": row["human_note"],
                            "timestamp": row["review_timestamp"],
                            "provenance": row["label_provenance"],
                        },
                    }
                )
            reviewed = sum(bool(pair["review"]["label"]) for pair in all_pairs)
            filtered = [
                pair for pair in all_pairs
                if review_filter == "all"
                or (review_filter == "reviewed") == bool(pair["review"]["label"])
            ]
            pairs = filtered[offset : offset + limit]
            return {
                "schema_version": "stage5e1-blinded-review-session-v1",
                "mode": "stage5e1_blinded_pair_review",
                "status": "HUMAN_REVIEW_COMPLETE" if reviewed == len(all_pairs) else "HUMAN_REVIEW_PENDING",
                "labels": LABELS,
                "progress": {"reviewed_pairs": reviewed, "total_pairs": len(all_pairs)},
                "page": {
                    "offset": offset,
                    "limit": limit,
                    "returned": len(pairs),
                    "filtered_total": len(filtered),
                    "filter": review_filter,
                },
                "pairs": pairs,
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
        if label not in (*LABELS, "") or len(note) > MAX_NOTE_LENGTH:
            raise Stage5B1AValidationError("invalid Stage 5E.1 human review value")
        pair_id = canonical_pair_id(stable_track_id, video_id)
        with self._lock:
            rows = self._read_rows()
            matching = [row for row in rows if row["pair_id"] == pair_id]
            if len(matching) != 1:
                raise Stage5B1AValidationError("unknown Stage 5E.1 review pair")
            row = matching[0]
            row["human_label"] = label
            row["human_note"] = note
            row["review_timestamp"] = datetime.now(timezone.utc).isoformat() if label else ""
            row["label_provenance"] = "STAGE5E1_OWNER" if label else ""
            temporary = self.review_path.with_suffix(f".{os.getpid()}.tmp")
            with temporary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            temporary.replace(self.review_path)
        return {"ok": True, "pair_id": pair_id, "review": {"label": label, "note": note}}
