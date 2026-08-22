"""Aggregate human judgments and produce the Phase 1 decision report inputs.

    python -m audio_similarity.cli.summarize_human_eval \
        --sheets reports/human_eval \
        --output reports/human_eval_summary.json

Reads judgments_factor.csv (0/1/2/3/X ratings) and judgments_ab.csv
(A/B/Tie/Neither), joins reveal keys, and computes the predeclared gates:
- per factor: median rating, share of pairs rated >= 2
- A/B: MERIT preference rate excluding Tie/Neither
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

VALID_RATINGS = {"0", "1", "2", "3", "X"}


def summarize(sheets_dir: str | Path) -> dict:
    sheets = Path(sheets_dir)
    report: dict = {}

    factor_path = sheets / "judgments_factor.csv"
    if factor_path.exists() and factor_path.stat().st_size > 0:
        frame = pd.read_csv(factor_path)
        rated = frame[frame["rating"].astype(str).str.strip() != ""]
        invalid = set(rated["rating"].astype(str)) - VALID_RATINGS
        if invalid:
            raise ValueError(f"invalid ratings present: {invalid}")
        numeric = rated[rated["rating"].astype(str) != "X"].copy()
        numeric["rating"] = numeric["rating"].astype(float)

        per_factor = {}
        for factor, group in numeric.groupby("target_factor"):
            per_factor[factor] = {
                "n_rated": int(len(group)),
                "n_excluded_x": int(len(rated) - len(numeric)),
                "median_rating": float(group["rating"].median()),
                "share_rating_ge_2": float((group["rating"] >= 2).mean()),
                "gate_median_ge_2": bool(group["rating"].median() >= 2),
                "gate_share_ge_2_pct60": bool((group["rating"] >= 2).mean() >= 0.60),
            }
        report["factor_utility"] = per_factor
        report["factor_gate_pass"] = {
            f: v["gate_median_ge_2"] and v["gate_share_ge_2_pct60"] for f, v in per_factor.items()
        }

    ab_path = sheets / "judgments_ab.csv"
    key_path = sheets / "key_ab.csv"
    if (
        ab_path.exists()
        and key_path.exists()
        and ab_path.stat().st_size > 0
        and key_path.stat().st_size > 0
    ):
        ab = pd.read_csv(ab_path)
        keys = pd.read_csv(key_path)
        answered = ab[ab["choice"].astype(str).isin(["A", "B", "Tie", "Neither"])].merge(keys, on="ab_id")
        decisive = answered[answered["choice"].isin(["A", "B"])].copy()
        decisive["merit_side"] = np.where(
            decisive["a_representation"].str.startswith("merit"), "A", "B"
        )
        decisive["merit_won"] = decisive["merit_side"] == decisive["choice"]
        per_factor_ab = {}
        for factor, group in decisive.groupby(decisive["ab_id"].str.split(":").str[1]):
            wins = int(group["merit_won"].sum())
            losses = int((~group["merit_won"]).sum())
            total = wins + losses
            per_factor_ab[factor] = {
                "merit_wins": wins,
                "mert_wins": losses,
                "preference_rate": (wins / total) if total else None,
                "gate_wins_more_than_losses": bool(wins > losses),
                "strong_result_ge_60pct": bool(total and wins / total >= 0.60),
            }
        report["ab_factor_control"] = per_factor_ab

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheets", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    report = summarize(args.sheets)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as fh:
        json.dump(report, fh, indent=2)
    print(json.dumps(report, indent=2))
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
