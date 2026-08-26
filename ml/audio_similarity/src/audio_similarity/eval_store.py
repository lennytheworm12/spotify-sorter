"""Session store for the listening-test evaluator UI.

Reads the blinded judgment sheets produced by cli/build_eval_sheets.py,
exposes rater-safe session payloads (representation names stay in the
separate key files), and persists ratings back to the CSVs atomically.

Pure persistence/joining logic lives here so it can be unit-tested without
starting the HTTP server.
"""

from __future__ import annotations

import json
import threading
import time
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
        # migrate sheets created before note/rated_by/log columns existed,
        # and normalize NaN to "" so truthiness checks behave predictably
        for col in ("note", "rated_by", "rating_log", "choice_log"):
            if col not in frame.columns:
                frame[col] = ""
        for col in ("rating_log", "choice_log"):
            if col in frame.columns:
                frame[col] = frame[col].fillna("")
        for col in ("rating", "choice", "note", "rated_by", "rating_log", "choice_log"):
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
            n_ratings = len(self._parse_log(row.get("rating_log"))) or (1 if str(row["rating"] or "").strip() else 0)
            factor_cells.append(
                {
                    "cell_id": row["cell_id"],
                    "target_factor": row["target_factor"],
                    "neighbor_rank": int(row["neighbor_rank"]),
                    "rating": str(row["rating"]),
                    "n_ratings": int(n_ratings),
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
                    "n_ratings": len(self._parse_log(row.get("choice_log"))) or (1 if str(row["choice"] or "").strip() else 0),
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

    @staticmethod
    def _parse_log(raw) -> list[dict]:
        """Parse a serialized judgment log; [] when absent/legacy."""
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            return []
        try:
            parsed = json.loads(str(raw))
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    @staticmethod
    def _serialize_log(log: list[dict]) -> str:
        return json.dumps(log[-50:], ensure_ascii=False)  # bound cell size

    def _apply_judgment(
        self,
        frame: pd.DataFrame,
        mask,
        value_col: str,
        log_col: str,
        value: str,
        reviewer: str,
    ) -> None:
        """Multi-reviewer semantics: first judgment stays primary; later
        reviewers append to the log; the same reviewer may self-correct."""
        row_idx = frame.index[mask][0]
        reviewer = self._clean_reviewer(reviewer)
        log = self._parse_log(frame.at[row_idx, log_col])
        current = str(frame.at[row_idx, value_col] or "").strip()

        # Lazily migrate judgments saved before append-only logs existed. Without
        # this seed, the next reviewer would be mistaken for the first reviewer
        # and overwrite both the primary value and its attribution.
        if current and not log:
            recorded_by = str(frame.at[row_idx, "rated_by"] or "").strip()
            primary_reviewer = recorded_by.split(",", 1)[0].strip()
            log.append({"v": current, "by": primary_reviewer, "at": 0, "migrated": True})

        prior_own = next((e for e in log if e.get("by") == reviewer), None)
        if prior_own is not None:
            prior_own["v"] = value
            prior_own["at"] = int(time.time())
        else:
            log.append({"v": value, "by": reviewer, "at": int(time.time())})

        frame.at[row_idx, log_col] = self._serialize_log(log)

        is_first_rater = bool(log) and log[0].get("by") == reviewer
        if not current or is_first_rater:
            # empty cell or the original rater self-correcting -> primary updates
            frame.at[row_idx, value_col] = value

        names = []
        for entry in log:
            who = str(entry.get("by") or "")
            if who and who not in names:
                names.append(who)
        if names:
            frame.at[row_idx, "rated_by"] = ", ".join(names)[:200]

    def rate_factor_cell(self, cell_id: str, rating: str, reviewer: str = "") -> None:
        rating = str(rating).strip().upper()
        if rating not in self.VALID_RATINGS:
            raise ValueError(f"invalid rating '{rating}'")
        with self._lock:
            frame = self._read("judgments_factor.csv")
            mask = frame["cell_id"] == cell_id
            if not mask.any():
                raise KeyError(f"unknown cell '{cell_id}'")
            self._apply_judgment(frame, mask, "rating", "rating_log", rating, reviewer)
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
            self._apply_judgment(frame, mask, "choice", "choice_log", choice, reviewer)
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
        applied = {"factor": 0, "factor_logged": 0, "factor_notes": 0, "ab": 0, "ab_logged": 0, "ab_notes": 0}
        with self._lock:
            factor = self._read("judgments_factor.csv").set_index("cell_id")
            for row in factor_rows:
                cid = str(row.get("cell_id", ""))
                if cid not in factor.index:
                    continue
                rating = str(row.get("rating") or "").strip().upper()
                note = str(row.get("note") or "").strip()
                if rating and rating in self.VALID_RATINGS:
                    existing = str(factor.at[cid, "rating"] or "").strip()
                    who = self._clean_reviewer(row.get("rated_by"))
                    if not existing or overwrite_existing:
                        factor.at[cid, "rating"] = rating
                        applied["factor"] += 1
                        if who:
                            factor.at[cid, "rated_by"] = who
                    elif existing != rating:
                        # second opinion: preserve in log; never overrides primary
                        log = self._parse_log(factor.at[cid, "rating_log"])
                        log.append({"v": rating, "by": who or "imported", "at": int(time.time())})
                        factor.at[cid, "rating_log"] = self._serialize_log(log)
                        applied["factor_logged"] += 1
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
                if choice and choice in self.VALID_CHOICES:
                    existing_choice = str(ab.at[aid, "choice"] or "").strip()
                    who = self._clean_reviewer(row.get("rated_by"))
                    if not existing_choice or overwrite_existing:
                        ab.at[aid, "choice"] = choice
                        applied["ab"] += 1
                        if who:
                            ab.at[aid, "rated_by"] = who
                    elif existing_choice != choice:
                        choice_log = self._parse_log(ab.at[aid, "choice_log"])
                        choice_log.append({"v": choice, "by": who or "imported", "at": int(time.time())})
                        ab.at[aid, "choice_log"] = self._serialize_log(choice_log)
                        applied["ab_logged"] += 1
                if note and (overwrite_existing or not str(ab.at[aid, "note"] or "").strip()):
                    ab.at[aid, "note"] = note[:2000]
                    applied["ab_notes"] += 1
            self._write_atomic("judgments_ab.csv", ab.reset_index())
        return applied

    # -------------------------------------------------------- holistic

    def _read_holistic(self) -> pd.DataFrame:
        frame = pd.read_csv(self.sheets_dir / "holistic_trials.csv", dtype=str)
        # ``rating_log`` was accidentally added by the generic sheet reader in
        # older server versions. Holistic trials only have pairwise choices.
        frame = frame.drop(columns=["rating_log"], errors="ignore")
        for col in ("note", "rated_by", "choice_log"):
            if col not in frame.columns:
                frame[col] = ""
        for col in ("choice", "note", "rated_by", "choice_log"):
            frame[col] = frame[col].fillna("")
        return frame

    def build_holistic_session(self) -> dict:
        frame = self._read_holistic()
        key_path = Path(self.sheets_dir) / "holistic_trial_keys.json"
        known_ids = set()
        if key_path.exists():
            try:
                import json as _json

                known_ids = set(json.loads(key_path.read_text()).get("trials", {}))
            except Exception:
                known_ids = set()
        frame = frame[frame["trial_id"].isin(known_ids)]
        trials = []
        for _, row in frame.iterrows():
            qid = int(row["query_track_id"])
            q_meta = self.manifest.loc[qid]
            trials.append({
                "trial_id": row["trial_id"],
                "question": row["question"],
                "a_title": row["a_title"], "a_artist": row["a_artist"],
                "b_title": row["b_title"], "b_artist": row["b_artist"],
                "choice": str(row["choice"]),
                "note": str(row["note"]),
                "rated_by": str(row["rated_by"]),
                "n_ratings": len(self._parse_log(row.get("choice_log")))
                or (1 if str(row["choice"] or "").strip() else 0),
                "query_title": str(q_meta["title"]),
                "query_artist": str(q_meta["artist"]),
                "query_audio": f"/audio/track/{qid}",
                "a_audio": f"/audio/track/{self._holistic_candidate(row['trial_id'], 'A')}",
                "b_audio": f"/audio/track/{self._holistic_candidate(row['trial_id'], 'B')}",
            })
        trials.sort(key=lambda t: (int(t["trial_id"].split(":")[0]), t["trial_id"]))
        judgments_recorded = sum(int(t["n_ratings"]) for t in trials)
        return {
            "trials": trials,
            "progress": {
                # Legacy keys remain for older evaluator clients.
                "ab_rated": sum(1 for t in trials if t["choice"]),
                "ab_total": len(trials),
                "factor_rated": 0,
                "factor_total": 0,
                # Current constrained pilot gate: cover every available trial
                # once. Additional independent judgments remain useful and are
                # counted, but are not required to complete this pilot pass.
                "judgments_recorded": judgments_recorded,
                "judgments_target": len(trials),
                "trials_started": sum(1 for t in trials if t["n_ratings"]),
                "trials_total": len(trials),
            },
        }

    def _holistic_candidate(self, trial_id: str, side: str) -> int | None:
        try:
            keys = json.loads((Path(self.sheets_dir) / "holistic_trial_keys.json").read_text())
            info = keys["trials"][trial_id]
            key = "candidate_a" if side == "A" else "candidate_b"
            return int(info[key])
        except Exception:
            return None

    def rate_holistic_trial(self, trial_id: str, choice: str, reviewer: str = "", note: str | None = None) -> None:
        choice = str(choice).strip().capitalize()
        if choice not in {"A", "B", "Tie", "Neither"}:
            raise ValueError(f"invalid choice '{choice}'")
        with self._lock:
            frame = self._read_holistic()
            mask = frame["trial_id"] == trial_id
            if not mask.any():
                raise KeyError(f"unknown trial '{trial_id}'")
            self._apply_judgment(frame, mask, "choice", "choice_log", choice, reviewer)
            if note is not None:
                frame.loc[mask, "note"] = str(note)[:2000]
            self._write_atomic("holistic_trials.csv", frame)

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
