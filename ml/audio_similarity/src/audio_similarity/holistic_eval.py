"""Stage 1A: exact retrieval per encoder, candidate unions, blinded A/B sheets.

Design sections 9, 16-17 of the pivot; roadmap Stage 1.
Model identity never reaches human-facing artifacts — provenance lives in a
separate key file.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ENCODER_REPRS = ("muq_mulan_large", "mert_5120", "mert_generic", "laion_clap")
TRIALS_PER_QUERY = 8
TOP_K = 10


def load_embeddings(path: str | Path) -> tuple[dict[int, np.ndarray], str]:
    frame = pd.read_parquet(path)
    key = frame["analysis_key"].iloc[0] if not frame.empty else ""
    out: dict[int, np.ndarray] = {}
    for _, row in frame.iterrows():
        if row.get("status") == "SUCCESS":
            vec = np.asarray(row["embedding"], dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                out[int(row["track_id"])] = vec / norm
    return out, key


def top_k(matrix_ids: list[int], matrix: np.ndarray, query_id: int, k: int) -> list[tuple[int, float]]:
    qrow = matrix_ids.index(query_id)
    scores = matrix @ matrix[qrow]
    order = np.lexsort((np.asarray(matrix_ids), -scores))
    out = []
    for i in order:
        tid = int(matrix_ids[i])
        if tid == query_id:
            continue
        out.append((tid, float(scores[i])))
        if len(out) == k:
            break
    return out


@dataclass
class QueryCandidates:
    query_id: int
    per_encoder: dict[str, list[tuple[int, float]]]


def build_unions(
    embeddings_by_encoder: dict[str, tuple[dict[int, np.ndarray], str]],
    queries: list[int],
    top_k_count: int = TOP_K,
) -> dict[int, QueryCandidates]:
    unions: dict[int, QueryCandidates] = {}
    for qid in queries:
        per_encoder: dict[str, list[tuple[int, float]]] = {}
        claimed: set[int] = {qid}
        for enc, (vecs, _) in embeddings_by_encoder.items():
            ids = sorted(vecs)
            matrix = np.stack([vecs[t] for t in ids])
            tops = top_k(ids, matrix, qid, top_k_count)
            per_encoder[enc] = tops
            claimed.update(t for t, _ in tops)
        unions[qid] = QueryCandidates(qid, per_encoder)
        unions[qid].claimed = claimed  # type: ignore[attr-defined]
    return unions


def build_trials(
    unions: dict[int, QueryCandidates],
    manifest: pd.DataFrame,
    n_trials_per_query: int = TRIALS_PER_QUERY,
    seed: int = 20260823,
    anchor_pool_size: int = 300,
) -> tuple[list[dict], dict]:
    """Deterministic informative trials:

    - cross-model disagreements: each encoder's best vs another encoder's best
    - competitive pair: two candidates with near-identical pooled similarity
    - one anchor negative: low-similarity track under every encoder
    """
    rng = np.random.default_rng(seed)
    meta = manifest.set_index("track_id")

    # global anchor pool: tracks dissimilar to the query under all encoders,
    # approximated by sampling outside all union candidates
    all_candidates = {qid: uc.claimed for qid, uc in unions.items()}

    trials: list[dict] = []
    provenance: dict = {"trials": {}, "seed": seed}

    for qid in sorted(unions):
        uc = unions[qid]
        encs = sorted(uc.per_encoder)
        pool_pairs: list[tuple[int, int, str]] = []

        # cross-model best-vs-best
        for i, enc_a in enumerate(encs):
            for enc_b in encs[i + 1:]:
                a_best = uc.per_encoder[enc_a][0][0]
                b_best = uc.per_encoder[enc_b][0][0]
                if a_best != b_best:
                    pool_pairs.append((a_best, b_best, f"disagree:{enc_a}_vs_{enc_b}"))

        # competitive: rank-2 of first two encoders
        for enc_a, enc_b in zip(encs, encs[1:]):
            if len(uc.per_encoder[enc_a]) > 1 and len(uc.per_encoder[enc_b]) > 1:
                pool_pairs.append(
                    (uc.per_encoder[enc_a][1][0], uc.per_encoder[enc_b][1][0], "competitive_rank2")
                )

        # anchor negative: random non-candidate track
        non_candidates = [t for t in meta.index if int(t) not in all_candidates[qid]]
        if non_candidates:
            anchor = int(rng.choice(non_candidates))
            first_enc = encs[0]
            pool_pairs.append((uc.per_encoder[first_enc][0][0], anchor, "anchor_negative"))

        selected = pool_pairs[:n_trials_per_query]

        for trial_idx, (cand_x, cand_y, kind) in enumerate(selected, start=1):
            a_is_x = bool(rng.random() < 0.5)
            cand_a, cand_b = (cand_x, cand_y) if a_is_x else (cand_y, cand_x)
            trial_id = f"{qid}:H{trial_idx}"
            a_meta, b_meta = meta.loc[cand_a], meta.loc[cand_b]
            trials.append(
                {
                    "trial_id": trial_id,
                    "query_track_id": qid,
                    "a_title": a_meta["title"],
                    "a_artist": a_meta["artist"],
                    "b_title": b_meta["title"],
                    "b_artist": b_meta["artist"],
                    "question": "Which clip sounds MORE like the query overall?",
                    "choice": "",
                    "note": "",
                }
            )
            provenance["trials"][trial_id] = {
                "query_track_id": qid,
                "kind": kind,
                "candidate_a": int(cand_a),
                "candidate_b": int(cand_b),
                "source": (
                    f"A={'X' if a_is_x else 'Y'} ({kind})"
                ),
                "a_is_first_model_candidate": a_is_x,
            }

    return trials, provenance


def write_blinded_sheets(
    trials: list[dict],
    provenance: dict,
    output_dir: str | Path,
) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(trials).to_csv(out / "holistic_trials.csv", index=False)
    with open(out / "holistic_trial_keys.json", "w") as fh:
        json.dump(provenance, fh, indent=1)
