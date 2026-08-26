"""Policy-aware, append-only multi-rater store for the Stage 2B evaluator."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

from .stage2b_audio import canonical_pcm, float32_le_bytes

CHOICES = {"A", "B", "Tie", "Neither"}
RATING_COLUMNS = ["event_id", "trial_id", "rater_id", "choice", "note", "submitted_at", "supersedes_event_id"]


class RatingPolicyError(ValueError):
    """A submission violates the frozen distinct-rater policy."""


def normalize_rater_id(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"\s+", " ", text, flags=re.UNICODE).strip()[:80]


class Stage2BStore:
    def __init__(self, report_dir: str | Path, manifest_path: str | Path, audio_root: str | Path):
        self.report_dir = Path(report_dir)
        self.audio_root = Path(audio_root)
        self.manifest = pd.read_parquet(manifest_path).set_index("track_id")
        self.keys = json.loads((self.report_dir / "trial_keys.json").read_text(encoding="utf-8"))["trials"]
        self.ratings_path = self.report_dir / "human_ratings.csv"
        self.train_validation_path = self.report_dir / "human_ratings_train_validation.csv"
        self.test_path = self.report_dir / "human_ratings_test.csv"
        self._lock = threading.RLock()
        self._audio_cache: dict[tuple[str, str], tuple[bytes, str]] = {}
        self._ensure_exports()

    def _read_events(self) -> pd.DataFrame:
        if not self.ratings_path.exists() or self.ratings_path.stat().st_size == 0:
            return pd.DataFrame(columns=RATING_COLUMNS)
        frame = pd.read_csv(self.ratings_path, dtype=str).fillna("")
        missing = set(RATING_COLUMNS) - set(frame.columns)
        if missing:
            raise RatingPolicyError(f"ratings export missing columns: {sorted(missing)}")
        return frame[RATING_COLUMNS]

    @staticmethod
    def _latest_by_rater(frame: pd.DataFrame) -> dict[str, dict[str, str]]:
        latest: dict[str, dict[str, str]] = {}
        for row in frame.to_dict("records"):
            latest[str(row["rater_id"])] = {key: str(value) for key, value in row.items()}
        return latest

    def _trial_state(self, trial_id: str, events: pd.DataFrame | None = None) -> dict[str, Any]:
        events = self._read_events() if events is None else events
        rows = events[events["trial_id"] == trial_id]
        latest = self._latest_by_rater(rows)
        choices = [row["choice"] for row in latest.values()]
        split = self.keys[trial_id]["split"]
        if split == "TEST":
            required_count = 3
            requires_more = len(latest) < 3
        elif len(latest) < 2:
            required_count = 2
            requires_more = True
        elif len(latest) == 2 and len(set(choices)) > 1:
            required_count = 3
            requires_more = True
        else:
            required_count = len(latest)
            requires_more = False
        return {
            "latest": latest,
            "aggregate_count": len(latest),
            "required_count": required_count,
            "requires_more": requires_more,
        }

    def build_session(self, rater_id: object) -> dict[str, Any]:
        rater = normalize_rater_id(rater_id)
        if not rater:
            raise RatingPolicyError("a non-empty rater ID is required")
        with self._lock:
            events = self._read_events()
            trials = []
            for trial_id in sorted(self.keys):
                state = self._trial_state(trial_id, events)
                own = state["latest"].get(rater)
                trials.append({
                    "trial_id": trial_id,
                    "question": "Which candidate sounds more like the query overall?",
                    "query_audio": f"/trial/{trial_id}/query",
                    "a_audio": f"/trial/{trial_id}/a",
                    "b_audio": f"/trial/{trial_id}/b",
                    "current_reviewer": {
                        "choice": own["choice"] if own else "",
                        "note": own["note"] if own else "",
                    },
                    "aggregate_count": state["aggregate_count"],
                    "another_judgment_required": state["requires_more"],
                    "needs_rating_by_current_reviewer": state["requires_more"] and own is None,
                })
        return {
            "rater_id": rater,
            "choices": ["A", "B", "Tie", "Neither"],
            "trials": trials,
            "progress": {
                "needs_rating": sum(item["needs_rating_by_current_reviewer"] for item in trials),
                "trials_total": len(trials),
            },
        }

    def submit(self, trial_id: str, rater_id: object, choice: object, note: object = "", submitted_at: int | None = None) -> dict[str, Any]:
        rater = normalize_rater_id(rater_id)
        if not rater:
            raise RatingPolicyError("a non-empty rater ID is required")
        normalized_choice = str(choice or "").strip().capitalize()
        if normalized_choice not in CHOICES:
            raise RatingPolicyError(f"invalid choice '{normalized_choice}'")
        if trial_id not in self.keys:
            raise KeyError(f"unknown trial '{trial_id}'")
        clean_note = str(note or "").strip()[:2000]
        with self._lock:
            events = self._read_events()
            state = self._trial_state(trial_id, events)
            prior = state["latest"].get(rater)
            if prior is None and not state["requires_more"]:
                raise RatingPolicyError("trial is closed to additional distinct raters")
            timestamp = int(time.time()) if submitted_at is None else int(submitted_at)
            sequence = len(events)
            event_material = f"{trial_id}|{rater}|{timestamp}|{sequence}|{normalized_choice}|{clean_note}"
            event_id = "vote_" + hashlib.sha256(event_material.encode()).hexdigest()[:24]
            row = {
                "event_id": event_id,
                "trial_id": trial_id,
                "rater_id": rater,
                "choice": normalized_choice,
                "note": clean_note,
                "submitted_at": str(timestamp),
                "supersedes_event_id": prior["event_id"] if prior else "",
            }
            updated = pd.concat([events, pd.DataFrame([row], columns=RATING_COLUMNS)], ignore_index=True)
            self._write_exports(updated)
            new_state = self._trial_state(trial_id, updated)
        return {
            "ok": True,
            "event_id": event_id,
            "aggregate_count": new_state["aggregate_count"],
            "another_judgment_required": new_state["requires_more"],
        }

    def import_rows(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        applied = 0
        for row in rows:
            self.submit(
                str(row.get("trial_id", "")), row.get("rater_id", ""), row.get("choice", ""),
                row.get("note", ""), int(row["submitted_at"]) if row.get("submitted_at") else None,
            )
            applied += 1
        return {"applied": applied}

    def _ensure_exports(self) -> None:
        with self._lock:
            self._write_exports(self._read_events())

    @staticmethod
    def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        frame.to_csv(tmp, index=False, columns=RATING_COLUMNS, quoting=csv.QUOTE_MINIMAL)
        tmp.replace(path)

    def _write_exports(self, events: pd.DataFrame) -> None:
        self._atomic_csv(self.ratings_path, events)
        splits = events["trial_id"].map(lambda trial_id: self.keys.get(str(trial_id), {}).get("split", ""))
        self._atomic_csv(self.train_validation_path, events[splits.isin(["TRAIN", "VALIDATION"])])
        self._atomic_csv(self.test_path, events[splits == "TEST"])

    def export_bytes(self, kind: str) -> bytes:
        path = {
            "all": self.ratings_path,
            "train-validation": self.train_validation_path,
            "test": self.test_path,
        }.get(kind)
        if path is None:
            raise KeyError(kind)
        with self._lock:
            return path.read_bytes()

    def audio_bytes(self, trial_id: str, role: str) -> tuple[bytes, str]:
        if trial_id not in self.keys or role not in {"query", "a", "b"}:
            raise KeyError("unknown trial audio role")
        cache_key = (trial_id, role)
        with self._lock:
            if cache_key in self._audio_cache:
                return self._audio_cache[cache_key]
        key = self.keys[trial_id]
        track_id = int({"query": key["query_id"], "a": key["candidate_a"], "b": key["candidate_b"]}[role])
        identity_key = {"query": "query_identity", "a": "candidate_a_identity", "b": "candidate_b_identity"}[role]
        row = self.manifest.loc[track_id]
        _, excerpt, _, _ = canonical_pcm(self.audio_root / str(row["relative_audio_path"]))
        body = float32_le_bytes(excerpt)
        content_hash = hashlib.sha256(body).hexdigest()
        expected_hash = key[identity_key]["center5_v1_pcm_sha256"]
        if content_hash != expected_hash:
            raise RatingPolicyError(f"center5_v1 content hash mismatch for trial {trial_id} role {role}")
        with self._lock:
            self._audio_cache[cache_key] = (body, content_hash)
        return body, content_hash
