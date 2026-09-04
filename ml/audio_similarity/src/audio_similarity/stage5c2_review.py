"""Resumable pairwise similarity-review state for Stage 5C.2."""
from __future__ import annotations

import csv
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError
from .stage5c2_analysis import REVIEW_COLUMNS, canonical_pair_id
from .stage5c2_discovery import _json


LABELS = ("3", "2", "1", "0", "UNSURE")
MAX_NOTE_LENGTH = 2_000


class Stage5C2ReviewStore:
    """Persist one unordered sonic-similarity label across reciprocal ranks."""

    def __init__(self, queue_path: str | Path, review_path: str | Path) -> None:
        self.queue_path = Path(queue_path).resolve()
        self.review_path = Path(review_path).resolve()
        self._queue = _json(self.queue_path)
        if self._queue.get("schema_version") != "stage5c2-similarity-review-queue-v1":
            raise Stage5B1AValidationError("invalid Stage 5C.2 review queue")
        self._lock = threading.RLock()
        self._read_rows()

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
