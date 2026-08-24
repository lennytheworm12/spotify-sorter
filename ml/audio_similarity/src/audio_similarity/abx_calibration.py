"""Inst-Sim-ABX external calibration (Phase 1B-adjacent, pivot design section 6).

Uses 281-subject human ABX judgments over 5-second Slakh excerpts
(zume06/inst-sim-abx-dataset) as FREE human ground truth:

    encoder cosine(reference, A) vs cosine(reference, B)
    compared against human majority preference

Validates our benchmark harness against published agreement rates
(MuQ-MuLan ~72%, CLAP ~72%) without collecting any new ratings.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR_NAME = "inst_sim_abx"
CONFIG_FILES = (
    "sample_configs/dict_triplet_202404.json",
    "sample_configs/dict_triplet_202407.json",
)
ANSWERS_CSV = "csvs/inst_sim_abx_answers.csv"


def load_config_index(data_dir: str | Path) -> dict[tuple[str, str], dict]:
    """Map (instrument, filename) -> leaf with ID/sr/index bounds."""
    data_dir = Path(data_dir)
    index: dict[tuple[str, str], dict] = {}
    for rel in CONFIG_FILES:
        cfg = json.loads((data_dir / rel).read_text())
        for set_key, sets in cfg.items():
            for group_key, groups in sets.items():
                for test_type, instruments in groups.items():
                    for instrument, samples in instruments.items():
                        for sample_type, leaf in samples.items():
                            key = (instrument, str(leaf.get("filename")))
                            entry = dict(leaf)
                            entry["sample_type"] = sample_type
                            entry["instrument"] = instrument
                            entry["config_set"] = set_key
                            entry["group"] = group_key
                            entry["test_type"] = test_type
                            index[key] = entry
    return index


def _parse_audio_path(path: str) -> tuple[str, str]:
    """'set2/2/piano/X_1913-28.wav' -> (instrument, filename)."""
    parts = Path(path).parts
    return parts[-2], parts[-1]


def load_triplets(
    answers_csv: str | Path,
    config_index: dict[tuple[str, str], dict],
    instrument_filter: tuple[str, ...] | None = None,
    min_majority_fraction: float = 0.0,
) -> pd.DataFrame:
    """Human-majority preferences per unique triplet.

    preference: 'A' or 'B' — which candidate humans judged more similar
    to the reference overall (answer_total A+/A- -> A, B+/B- -> B).
    """
    answers = pd.read_csv(answers_csv)
    records: dict[tuple, dict] = defaultdict(lambda: {"votes": [], "paths": None})
    for _, row in answers.iterrows():
        vote_raw = str(row["answer_total"])
        pref = "A" if vote_raw.startswith("A") else ("B" if vote_raw.startswith("B") else None)
        if pref is None:
            continue
        try:
            inst_ref, fn_ref = _parse_audio_path(str(row["reference"]))
            inst_a, fn_a = _parse_audio_path(str(row["sample_a"]))
            inst_b, fn_b = _parse_audio_path(str(row["sample_b"]))
        except Exception:
            continue
        key = (fn_ref, fn_a, fn_b)
        rec = records[key]
        rec["votes"].append(pref)
        if rec["paths"] is None:
            rec["paths"] = {
                "reference": (inst_ref, fn_ref),
                "candidate_a": (inst_a, fn_a),
                "candidate_b": (inst_b, fn_b),
            }

    rows = []
    for key, rec in records.items():
        votes = rec["votes"]
        counts = Counter(votes)
        total = len(votes)
        maj_vote, maj_count = counts.most_common(1)[0]
        fraction = maj_count / total
        if fraction < min_majority_fraction:
            continue

        paths = rec["paths"]
        leaves = {}
        skip = False
        for role in ("reference", "candidate_a", "candidate_b"):
            inst, fname = paths[role]
            leaf = config_index.get((inst, fname))
            if leaf is None:
                skip = True
                break
            leaves[role] = leaf
        if skip:
            continue

        if instrument_filter and paths["reference"][0] not in instrument_filter:
            # filter on the reference instrument category (mix/drum/...)
            pass_check = any(paths[r][0] in instrument_filter for r in paths)
            if not pass_check:
                continue

        rows.append(
            {
                "reference_fn": key[0],
                "candidate_a_fn": key[1],
                "candidate_b_fn": key[2],
                "instrument": paths["reference"][0],
                "human_preference": maj_vote,
                "majority_fraction": round(fraction, 3),
                "n_subjects": total,
                "ref_ID": leaves["reference"]["ID"],
                "a_ID": leaves["candidate_a"]["ID"],
                "b_ID": leaves["candidate_b"]["ID"],
                "ref_bounds": (leaves["reference"]["index_s"], leaves["reference"]["index_e"]),
                "a_bounds": (leaves["candidate_a"]["index_s"], leaves["candidate_a"]["index_e"]),
                "b_bounds": (leaves["candidate_b"]["index_s"], leaves["candidate_b"]["index_e"]),
                "ref_sr": leaves["reference"]["sr"],
            }
        )
    return pd.DataFrame(rows)


def abx_agreement(
    triplets: pd.DataFrame,
    embed_lookup,
    cosine_fn,
    high_agreement_threshold: float | None = 0.75,
) -> dict:
    """Fraction of triplets where the encoder's cosine preference matches
    the human majority. ``cosine_fn(ref_hash, cand_hash)`` supplied by caller."""
    frame = triplets
    if high_agreement_threshold is not None:
        frame = frame[frame["majority_fraction"] >= high_agreement_threshold]
    agreements, skipped = [], 0
    for _, row in frame.iterrows():
        ref = embed_lookup(int(row["ref_ID"]), row["ref_bounds"])
        ca = embed_lookup(int(row["a_ID"]), row["a_bounds"])
        cb = embed_lookup(int(row["b_ID"]), row["b_bounds"])
        if ref is None or ca is None or cb is None:
            skipped += 1
            continue
        sim_a, sim_b = cosine_fn(ref, ca), cosine_fn(ref, cb)
        if sim_a == sim_b:
            continue
        model_pref = "A" if sim_a > sim_b else "B"
        agreements.append(model_pref == row["human_preference"])
    n = len(agreements)
    return {
        "n_triplets_scored": n,
        "skipped_missing_features": skipped,
        "agreement_rate": float(np.mean(agreements)) if n else None,
        "se": float(np.std(agreements) / np.sqrt(n)) if n else None,
    }
