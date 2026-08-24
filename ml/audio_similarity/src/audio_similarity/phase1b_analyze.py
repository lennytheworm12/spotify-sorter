"""Phase 1B cross-reference scoring and analysis (design sections 15-23, 26 E-I).

Builds the master table: every frozen retrieval pair scored under MERIT,
general-MERT, and the three independent MIR metric families with background
percentiles, factor specificity, control-group labels, and human joins.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .mir_metrics import (
    BackgroundCalibration,
    melody_components,
    rhythm_components,
    timbre_components,
)
from .mir_features import FeatureCache


# ---------------------------------------------------------------------------
# embeddings access
# ---------------------------------------------------------------------------


class EmbeddingLookup:
    def __init__(self, embeddings_path: str | Path):
        table = pd.read_parquet(embeddings_path)
        rows = {int(r["track_id"]): r for r in table.to_pylist()}
        self.rows = rows

    def cosine(self, a: int, b: int, factor: str) -> float:
        ra, rb = self.rows.get(int(a)), self.rows.get(int(b))
        if ra is None or rb is None:
            return float("nan")
        va = np.asarray(ra[factor], dtype=np.float64)
        vb = np.asarray(rb[factor], dtype=np.float64)
        na, nb = np.linalg.norm(va), np.linalg.norm(vb)
        if na == 0 or nb == 0:
            return float("nan")
        return float(np.dot(va, vb) / (na * nb))


# ---------------------------------------------------------------------------
# background calibration (Stage H)
# ---------------------------------------------------------------------------


def background_distributions(
    cache: FeatureCache,
    track_ids: list[int],
    n_pairs: int,
    seed: int = 424242,
) -> dict[str, np.ndarray]:
    """Raw metric distributions over deterministic random track pairs."""
    rng = np.random.default_rng(seed)
    ids = np.array(track_ids)
    melody, rhythm, timbre = [], [], []
    for _ in range(n_pairs):
        a, b = rng.choice(ids, size=2, replace=False)
        fa, fb = cache.get(str(a)), cache.get(str(b))
        if fa is None or fb is None:
            continue
        m = melody_components(fa.chroma_sequence, fb.chroma_sequence)
        r = rhythm_components(
            fa.onset_envelope, fb.onset_envelope,
            fa.periodicity_profile, fb.periodicity_profile,
            fa.tempo_bpm, fb.tempo_bpm,
        )
        t = timbre_components(fa.timbre_vector, fb.timbre_vector)
        melody += [m.chroma_global_cos, m.chroma_dtw_sim, m.transposition_best_cos]
        rhythm += [r.onset_cos_fixed, r.onset_dtw_sim, r.tempogram_cos]
        timbre.append(t.timbre_cos)
    return {
        "chroma_global_cos": np.array(melody[0::3]),
        "chroma_dtw_sim": np.array(melody[1::3]),
        "transposition_best_cos": np.array(melody[2::3]),
        "onset_cos_fixed": np.array(rhythm[0::3]),
        "onset_dtw_sim": np.array(rhythm[1::3]),
        "tempogram_cos": np.array(rhythm[2::3]),
        "timbre_cos": np.array(timbre),
    }


def save_calibration(calib: BackgroundCalibration, path: str | Path, meta: dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **calib.to_dict())
    Path(str(out).replace(".npz", "_meta.json")).write_text(json.dumps(meta, indent=1))


def load_calibration(path: str | Path) -> BackgroundCalibration:
    data = np.load(path)
    return BackgroundCalibration({k: data[k] for k in data.files})


# ---------------------------------------------------------------------------
# master table (Stages E/F/I/M/N)
# ---------------------------------------------------------------------------


@dataclass
class AnalysisContext:
    manifest: pd.DataFrame
    lookup: EmbeddingLookup
    cache: FeatureCache
    calibration: BackgroundCalibration
    human_joins: dict[tuple[int, str, int], tuple[str, bool]]  # (qid, factor, rank) -> (rating, valid)


def load_human_joins(judgments_csv: str | Path, key_factor_csv: str | Path) -> dict[tuple[int, str, int], tuple[str, bool]]:
    keys = pd.read_csv(key_factor_csv)
    parts = keys["cell_id"].str.split(":", expand=True)
    key_map = {
        (int(p0), p1, int(p2)): int(tid)
        for p0, p1, p2, tid in zip(parts[0], parts[1], parts[2], keys["neighbor_track_id"])
    }
    judgments = pd.read_csv(judgments_csv, dtype={"rating": str})
    jparts = judgments["cell_id"].str.split(":", expand=True)
    joins: dict[tuple[int, str, int], tuple[str, bool]] = {}
    for (_, row), p0, p1, p2 in zip(
        judgments.iterrows(), jparts[0], jparts[1], jparts[2]
    ):
        rating = str(row.get("rating") or "").strip().upper()
        if not rating:
            continue
        tid = key_map.get((int(p0), p1, int(p2)))
        if tid is None:
            continue
        joins[(int(p0), p1, int(p2))] = (rating, rating != "X")
    return joins


def score_master_table(cases_path: str | Path, ctx: AnalysisContext) -> pd.DataFrame:
    data = json.loads(Path(cases_path).read_text())
    meta = ctx.manifest.set_index("track_id")

    rows: list[dict] = []
    for case in data["cases"]:
        qid = case["query_id"]
        factor = case["factor"]
        groups = {
            "merit_target": case["merit_target_neighbors"],
            **{f"merit_{k}": v for k, v in case["merit_other_neighbors"].items()},
            "mert_general": case["mert_general_neighbors"],
            "conventional": case["conventional_neighbors"],
            "random_negative": case["random_negatives"],
            "hard_negative": case["hard_negatives"],
        }
        q_hash_row = meta.loc[qid]
        for source, candidates in groups.items():
            for rank, cid in enumerate(candidates, start=1):
                fq = ctx.cache.get(str(q_hash_row["audio_sha256"]))
                fc = ctx.cache.get(str(meta.at[cid, "audio_sha256"]))
                if fq is None or fc is None:
                    continue
                m = melody_components(fq.chroma_sequence, fc.chroma_sequence)
                r = rhythm_components(
                    fq.onset_envelope, fc.onset_envelope,
                    fq.periodicity_profile, fc.periodicity_profile,
                    fq.tempo_bpm, fc.tempo_bpm,
                )
                t = timbre_components(fq.timbre_vector, fc.timbre_vector)

                raws = {
                    "chroma_global_cos": m.chroma_global_cos,
                    "chroma_dtw_sim": m.chroma_dtw_sim,
                    "transposition_best_cos": m.transposition_best_cos,
                    "onset_cos_fixed": r.onset_cos_fixed,
                    "onset_dtw_sim": r.onset_dtw_sim,
                    "tempogram_cos": r.tempogram_cos,
                    "timbre_cos": t.timbre_cos,
                }
                pcts = ctx.calibration.percentiles(raws)
                scores = factor_scores(pcts)

                merit_sims = {
                    f"merit_{f}_similarity": ctx.lookup.cosine(qid, cid, f) for f in ("melody", "rhythm", "timbre")
                }
                mert_sim = {"mert_general_similarity": ctx.lookup.cosine(qid, cid, "mert_general")}

                crow = meta.loc[cid]
                human_key = (qid, factor, rank)
                human_rating, human_valid = ctx.human_joins.get(human_key, (None, False))

                rows.append(
                    {
                        "query_id": qid,
                        "candidate_id": int(cid),
                        "retrieval_source": source,
                        "retrieval_factor": factor if source.startswith("merit") else "",
                        "group_rank": rank,
                        "merit_melody_similarity": merit_sims["merit_melody_similarity"],
                        "merit_rhythm_similarity": merit_sims["merit_rhythm_similarity"],
                        "merit_timbre_similarity": merit_sims["merit_timbre_similarity"],
                        "mert_general_similarity": mert_sim["mert_general_similarity"],
                        **{f"mir_{k}": raws[k] for k in raws},
                        **{f"pct_{k}": pcts[k] for k in pcts},
                        "independent_melody_score": scores["melody"],
                        "independent_rhythm_score": scores["rhythm"],
                        "independent_timbre_score": scores["timbre"],
                        "target_specificity": specificity(factor, scores),
                        "genre_match": str(crow["top_genre"]) == str(q_hash_row["top_genre"]),
                        "same_artist": str(crow["artist"]) == str(q_hash_row["artist"]),
                        "human_rating": human_rating,
                        "human_valid": human_valid,
                    }
                )
    frame = pd.DataFrame(rows)
    frame.attrs["n_cases"] = len(data["cases"])
    return frame


def save_master_table(frame: pd.DataFrame, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out, index=False)
