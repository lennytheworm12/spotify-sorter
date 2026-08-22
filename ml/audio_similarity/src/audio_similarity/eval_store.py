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
        return pd.read_csv(self.sheets_dir / name, dtype={"rating": str, "choice": str})

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

    def rate_factor_cell(self, cell_id: str, rating: str) -> None:
        rating = str(rating).strip().upper()
        if rating not in self.VALID_RATINGS:
            raise ValueError(f"invalid rating '{rating}'")
        with self._lock:
            frame = self._read("judgments_factor.csv")
            mask = frame["cell_id"] == cell_id
            if not mask.any():
                raise KeyError(f"unknown cell '{cell_id}'")
            frame.loc[mask, "rating"] = rating
            self._write_atomic("judgments_factor.csv", frame)

    def rate_ab_trial(self, ab_id: str, choice: str) -> None:
        choice = str(choice).strip().capitalize()
        if choice not in self.VALID_CHOICES:
            raise ValueError(f"invalid choice '{choice}'")
        with self._lock:
            frame = self._read("judgments_ab.csv")
            mask = frame["ab_id"] == ab_id
            if not mask.any():
                raise KeyError(f"unknown trial '{ab_id}'")
            frame.loc[mask, "choice"] = choice
            self._write_atomic("judgments_ab.csv", frame)

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
