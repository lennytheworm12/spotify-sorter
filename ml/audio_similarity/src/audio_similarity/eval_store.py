"""Session store for the listening-test evaluator UI.

Reads the blinded judgment sheets produced by cli/build_eval_sheets.py,
exposes rater-safe session payloads (representation names stay in the
separate key files), and persists ratings back to the CSVs atomically.

Pure persistence/joining logic lives here so it can be unit-tested without
starting the HTTP server.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pandas as pd


class SheetStore:
    def __init__(
        self,
        sheets_dir: str | Path,
        manifest_path: str | Path,
        audio_root: str | Path,
    ):
        self.sheets_dir = Path(sheets_dir)
        self.manifest = pd.read_parquet(manifest_path).set_index("track_id")
        self.audio_root = Path(audio_root)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ io

    def _read(self, name: str) -> pd.DataFrame:
        frame = pd.read_csv(self.sheets_dir / name, dtype={"rating": str, "choice": str})
        # migrate sheets created before note/rated_by columns existed, and
        # normalize NaN to "" so truthiness checks behave predictably
        for col in ("note", "rated_by"):
            if col not in frame.columns:
                frame[col] = ""
        for col in ("rating", "choice", "note", "rated_by"):
            if col in frame.columns:
                frame[col] = frame[col].fillna("")
        return frame

    def _write_atomic(self, name: str, frame: pd.DataFrame) -> None:
        path = self.sheets_dir / name
        tmp = path.with_suffix(path.suffix + ".tmp")
        frame.to_csv(tmp, index=False)
        tmp.replace(path)

    # ------------------------------------------------------------- session

    def _audio_for_track(self, track_id: int) -> str | None:
        if track_id not in self.manifest.index:
            return None
        rel = self.manifest.at[track_id, "relative_audio_path"]
        if not (self.audio_root / rel).exists():
            return None
        return f"/audio/track/{int(track_id)}"

    def build_session(self) -> dict:
        """Rater-safe payload: no representation names, no raw track ids of neighbors."""
        with self._lock:
            factor = self._read("judgments_factor.csv").fillna({"rating": ""})
            factor_keys = self._read("key_factor.csv")
            ab = self._read("judgments_ab.csv").fillna({"choice": ""})
            ab_keys = self._read("key_ab.csv")

        key_by_cell = dict(zip(factor_keys["cell_id"], factor_keys["neighbor_track_id"]))
        factor_cells = []
        for _, row in factor.iterrows():
            neighbor_track_id = int(key_by_cell[row["cell_id"]])
            query_id = int(row["query_track_id"])
            q_meta = self.manifest.loc[query_id]
            factor_cells.append(
                {
                    "cell_id": row["cell_id"],
                    "target_factor": row["target_factor"],
                    "neighbor_rank": int(row["neighbor_rank"]),
                    "rating": str(row["rating"]),
                    "rated_by": str(row["rated_by"]) if pd.notna(row["rated_by"]) else "",
                    "note": str(row["note"]) if pd.notna(row["note"]) else "",
                    "neighbor_title": row["neighbor_title"],
                    "neighbor_artist": row["neighbor_artist"],
                    "query_title": str(q_meta["title"]),
                    "query_artist": str(q_meta["artist"]),
                    "query_top_genre": str(q_meta["top_genre"]),
                    "query_audio": f"/audio/track/{query_id}",
                    "neighbor_audio": f"/audio/track/{neighbor_track_id}",
                }
            )
        # stable ordering: query id (numeric), then factor, then neighbor rank
        factor_cells.sort(key=lambda c: (int(c["cell_id"].split(":")[0]), c["target_factor"], c["neighbor_rank"]))

        ab_key_by_id = ab_keys.set_index("ab_id")
        ab_trials = []
        for _, row in ab.iterrows():
            key = ab_key_by_id.loc[row["ab_id"]]
            query_id = int(row["ab_id"].split(":")[0])
            q_meta = self.manifest.loc[query_id]
            factor_name = row["ab_id"].split(":")[1]
            ab_trials.append(
                {
                    "ab_id": row["ab_id"],
                    "target_factor": factor_name,
                    "question": (
                        f"Which clip is MORE similar to the query specifically in {factor_name.upper()}?"
                    ),
                    "a_title": row["a_title"],
                    "a_artist": row["a_artist"],
                    "b_title": row["b_title"],
                    "b_artist": row["b_artist"],
                    "choice": str(row["choice"]),
                    "rated_by": str(row["rated_by"]) if pd.notna(row["rated_by"]) else "",
                    "note": str(row["note"]) if pd.notna(row["note"]) else "",
                    "query_title": str(q_meta["title"]),
                    "query_artist": str(q_meta["artist"]),
                    "query_top_genre": str(q_meta["top_genre"]),
                    "query_audio": f"/audio/track/{query_id}",
                    "a_audio": f"/audio/ab/{row['ab_id']}/a",
                    "b_audio": f"/audio/ab/{row['ab_id']}/b",
                }
            )
        ab_trials.sort(key=lambda t: (int(t["ab_id"].split(":")[0]), t["ab_id"]))

        return {
            "factor_cells": factor_cells,
            "ab_trials": ab_trials,
            "progress": {
                "factor_rated": sum(1 for c in factor_cells if c["rating"]),
                "factor_total": len(factor_cells),
                "ab_rated": sum(1 for t in ab_trials if t["choice"]),
                "ab_total": len(ab_trials),
            },
        }

    # ------------------------------------------------------------ mutation

    VALID_RATINGS = {"0", "1", "2", "3", "X"}
    VALID_CHOICES = {"A", "B", "Tie", "Neither"}

    @staticmethod
    def _clean_reviewer(reviewer: str | None) -> str:
        return str(reviewer or "").strip()[:80]

    def rate_factor_cell(self, cell_id: str, rating: str, reviewer: str = "") -> None:
        rating = str(rating).strip().upper()
        if rating not in self.VALID_RATINGS:
            raise ValueError(f"invalid rating '{rating}'")
        with self._lock:
            frame = self._read("judgments_factor.csv")
            mask = frame["cell_id"] == cell_id
            if not mask.any():
                raise KeyError(f"unknown cell '{cell_id}'")
            frame.loc[mask, "rating"] = rating
            clean = self._clean_reviewer(reviewer)
            if clean:
                frame.loc[mask, "rated_by"] = clean
            self._write_atomic("judgments_factor.csv", frame)

    def rate_ab_trial(self, ab_id: str, choice: str, reviewer: str = "") -> None:
        choice = str(choice).strip().capitalize()
        if choice not in self.VALID_CHOICES:
            raise ValueError(f"invalid choice '{choice}'")
        with self._lock:
            frame = self._read("judgments_ab.csv")
            mask = frame["ab_id"] == ab_id
            if not mask.any():
                raise KeyError(f"unknown trial '{ab_id}'")
            frame.loc[mask, "choice"] = choice
            clean = self._clean_reviewer(reviewer)
            if clean:
                frame.loc[mask, "rated_by"] = clean
            self._write_atomic("judgments_ab.csv", frame)

    def set_note(self, kind: str, ident: str, note: str, reviewer: str = "") -> None:
        """Attach a free-text review note to a factor cell or an A/B trial."""
        name = "judgments_factor.csv" if kind == "factor" else "judgments_ab.csv"
        id_col = "cell_id" if kind == "factor" else "ab_id"
        with self._lock:
            frame = self._read(name)
            mask = frame[id_col] == ident
            if not mask.any():
                raise KeyError(f"unknown {kind} item '{ident}'")
            frame.loc[mask, "note"] = str(note or "").strip()[:2000]
            clean = self._clean_reviewer(reviewer)
            if clean:
                frame.loc[mask, "rated_by"] = clean
            self._write_atomic(name, frame)

    def import_ratings(
        self,
        factor_rows: list[dict],
        ab_rows: list[dict],
        overwrite_existing: bool = False,
    ) -> dict:
        """Merge exported ratings (e.g., from the static Pages UI) into the CSVs.

        Rows without a value are skipped. Existing values are kept unless
        ``overwrite_existing`` is set.
        """
        applied = {"factor": 0, "factor_notes": 0, "ab": 0, "ab_notes": 0}
        with self._lock:
            factor = self._read("judgments_factor.csv").set_index("cell_id")
            for row in factor_rows:
                cid = str(row.get("cell_id", ""))
                if cid not in factor.index:
                    continue
                rating = str(row.get("rating") or "").strip().upper()
                note = str(row.get("note") or "").strip()
                if rating and (overwrite_existing or not str(factor.at[cid, "rating"] or "").strip()):
                    if rating in self.VALID_RATINGS:
                        factor.at[cid, "rating"] = rating
                        applied["factor"] += 1
                        who = self._clean_reviewer(row.get("rated_by"))
                        if who:
                            factor.at[cid, "rated_by"] = who
                if note and (overwrite_existing or not str(factor.at[cid, "note"] or "").strip()):
                    factor.at[cid, "note"] = note[:2000]
                    applied["factor_notes"] += 1
            self._write_atomic("judgments_factor.csv", factor.reset_index())

            ab = self._read("judgments_ab.csv").set_index("ab_id")
            for row in ab_rows:
                aid = str(row.get("ab_id", ""))
                if aid not in ab.index:
                    continue
                choice = str(row.get("choice") or "").strip().capitalize()
                note = str(row.get("note") or "").strip()
                if choice and (overwrite_existing or not str(ab.at[aid, "choice"] or "").strip()):
                    if choice in self.VALID_CHOICES:
                        ab.at[aid, "choice"] = choice
                        applied["ab"] += 1
                        who = self._clean_reviewer(row.get("rated_by"))
                        if who:
                            ab.at[aid, "rated_by"] = who
                if note and (overwrite_existing or not str(ab.at[aid, "note"] or "").strip()):
                    ab.at[aid, "note"] = note[:2000]
                    applied["ab_notes"] += 1
            self._write_atomic("judgments_ab.csv", ab.reset_index())
        return applied

    # --------------------------------------------------------------- audio

    def audio_path_for_request(self, kind: str, ident: str, side: str | None = None) -> Path | None:
        """Resolve an audio URL to a file path; never expose representation keys."""
        try:
            if kind == "track":
                track_id = int(ident)
                rel = self.manifest.at[track_id, "relative_audio_path"]
            elif kind == "ab":
                with self._lock:
                    keys = self._read("key_ab.csv")
                row = keys[keys["ab_id"] == ident]
                if row.empty:
                    return None
                track_id = int(row.iloc[0][f"{side}_track_id"])
                rel = self.manifest.at[track_id, "relative_audio_path"]
            else:
                return None
        except (KeyError, ValueError):
            return None
        path = self.audio_root / rel
        return path if path.exists() else None
