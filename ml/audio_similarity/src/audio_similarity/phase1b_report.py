"""Phase 1B statistical analyses: specificity, construct validity, correlations,
disagreements, and the amended evidence scoring (design sections 14-23, 30).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def bootstrap_ci(
    values: np.ndarray,
    statistic: str = "median",
    n_boot: int = 2000,
    seed: int = 424242,
    level: float = 0.95,
) -> tuple[float, tuple[float, float]]:
    vals = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=np.float64)
    if len(vals) == 0:
        return float("nan"), (float("nan"), float("nan"))
    fn = np.median if statistic == "median" else np.mean
    rng = np.random.default_rng(seed)
    boots = [fn(rng.choice(vals, size=len(vals), replace=True)) for _ in range(n_boot)]
    alpha = (1 - level) / 2 * 100
    return (
        float(fn(vals)),
        (float(np.percentile(boots, alpha)), float(np.percentile(boots, 100 - alpha))),
    )


def cliffs_delta(group_a: np.ndarray, group_b: np.ndarray) -> float:
    """Nonparametric effect size: P(a>b) - P(a<b)."""
    a = np.asarray(group_a, dtype=np.float64)
    b = np.asarray(group_b, dtype=np.float64)
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    greater = sum((a > bv).sum() for bv in b)
    less = sum((a < bv).sum() for bv in b)
    return float((greater - less) / (len(a) * len(b)))


def paired_bootstrap_diff(
    paired_a: np.ndarray, paired_b: np.ndarray, n_boot: int = 2000, seed: int = 424242
) -> tuple[float, tuple[float, float]]:
    """Median of (a-b), CI resampling queries. Inputs aligned by query."""
    diffs = np.asarray(paired_a, dtype=np.float64) - np.asarray(paired_b, dtype=np.float64)
    return bootstrap_ci(diffs, statistic="median", n_boot=n_boot, seed=seed)


# ---------------------------------------------------------------------------
# Stage J — factor specificity
# ---------------------------------------------------------------------------


def factor_specificity_report(master: pd.DataFrame) -> dict:
    out = {}
    target_rows = master[master["retrieval_source"] == "merit_target"]
    for factor in ("melody", "rhythm", "timbre"):
        specs = target_rows[target_rows["retrieval_factor"] == factor]["target_specificity"]
        specs = specs[np.isfinite(specs)]
        point, (lo, hi) = bootstrap_ci(specs.to_numpy(), statistic="median")
        out[factor] = {
            "n": int(len(specs)),
            "mean_specificity": float(specs.mean()) if len(specs) else None,
            "median_specificity": point,
            "ci95": [lo, hi],
            "pct_positive": float((specs > 0).mean()) if len(specs) else None,
            "values": [float(v) for v in specs],
        }
    return out


# ---------------------------------------------------------------------------
# Stage K — construct-validity comparisons
# ---------------------------------------------------------------------------


def construct_validity_comparisons(master: pd.DataFrame, seed: int = 424242) -> dict:
    comparisons: dict[str, dict] = {}
    control_sources = [
        "random_negative",
        "hard_negative",
        "merit_melody",
        "merit_rhythm",
        "merit_timbre",
        "mert_general",
        "conventional",
    ]
    for factor in ("melody", "rhythm", "timbre"):
        target_col = f"independent_{factor}_score"
        targets = master[
            (master["retrieval_source"] == "merit_target") & (master["retrieval_factor"] == factor)
        ]
        factor_out = {}
        for source in control_sources:
            if source == f"merit_{factor}":
                continue
            controls = master[master["retrieval_source"] == source]
            if controls.empty or targets.empty:
                continue
            # paired by query where both sides exist (valid pairing per design section 15)
            t_by_q = targets.groupby("query_id")[target_col].apply(list)
            c_by_q = controls.groupby("query_id")[target_col].apply(list)

            flat_t = np.concatenate([np.asarray(v, dtype=float) for v in t_by_q]) if len(t_by_q) else np.array([])
            flat_c = np.concatenate([np.asarray(v, dtype=float) for v in c_by_q]) if len(c_by_q) else np.array([])

            delta_point, (lo, hi) = paired_bootstrap_diff(
                np.concatenate([[np.mean(v)] for v in t_by_q]),
                np.concatenate([[np.mean(v)] for v in c_by_q]),
                seed=seed,
            )
            factor_out[source] = {
                "n_target_pairs": int(len(flat_t)),
                "n_control_pairs": int(len(flat_c)),
                "n_queries_paired": int(min(len(t_by_q), len(c_by_q))),
                "target_median": float(np.median(flat_t)) if len(flat_t) else None,
                "control_median": float(np.median(flat_c)) if len(flat_c) else None,
                "median_delta_vs_control": float(delta_point),
                "ci95_of_delta": [lo, hi],
                "cliffs_delta": cliffs_delta(flat_t, flat_c),
            }
        comparisons[factor] = factor_out
    return comparisons


# ---------------------------------------------------------------------------
# Stage L — correlation matrix
# ---------------------------------------------------------------------------


def correlation_matrix(master: pd.DataFrame) -> pd.DataFrame:
    merit_cols = {
        "merit_melody": "merit_melody_similarity",
        "merit_rhythm": "merit_rhythm_similarity",
        "merit_timbre": "merit_timbre_similarity",
        "mert_general": "mert_general_similarity",
    }
    mir_cols = {
        "mir_melody": "independent_melody_score",
        "mir_rhythm": "independent_rhythm_score",
        "mir_timbre": "independent_timbre_score",
    }
    selection = {**merit_cols, **mir_cols}
    frame = master[list(selection.values())].rename(columns={v: k for k, v in selection.items()}).dropna()
    ranked = frame.rank()
    return ranked.corr(method="spearman").round(3)


def flag_cross_factor_leakage(corr: pd.DataFrame) -> list[str]:
    flags = []
    mir_cols = ["mir_melody", "mir_rhythm", "mir_timbre"]
    for merit_factor, mir_target in (("merit_melody", "mir_melody"), ("merit_rhythm", "mir_rhythm"), ("merit_timbre", "mir_timbre")):
        row = corr.loc[merit_factor, mir_cols]
        best = row.idxmax()
        if best != mir_target:
            flags.append(
                f"{merit_factor} correlates most with {best} ({row[best]:.3f}) "
                f"instead of {mir_target} ({row[mir_target]:.3f}) — cross-factor leakage"
            )
    return flags


# ---------------------------------------------------------------------------
# Stage O — human/MIR disagreement buckets
# ---------------------------------------------------------------------------


def disagreement_analysis(master: pd.DataFrame) -> dict:
    valid = master[
        (master["human_valid"] == True)  # noqa: E712
        & (master["retrieval_source"] == "merit_target")
    ]
    useful = valid[pd.to_numeric(valid["human_rating"], errors="coerce") >= 2]
    not_useful = valid[pd.to_numeric(valid["human_rating"], errors="coerce") <= 1]

    def target_scores(frame: pd.DataFrame) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {f: [] for f in ("melody", "rhythm", "timbre")}
        for _, row in frame.iterrows():
            col = f"independent_{row['retrieval_factor']}_score"
            if col in row and np.isfinite(row[col]):
                out[str(row["retrieval_factor"])].append(float(row[col]))
        return out

    stats = {}
    for label, frame in (("useful", useful), ("not_useful", not_useful)):
        ts = target_scores(frame)
        stats[label] = {
            "n": int(len(frame)),
            "median_target_mir": {k: float(np.median(v)) if v else None for k, v in ts.items()},
        }

    # disagreement rows persisted for manual inspection
    disagree_rows = []
    for _, row in valid.iterrows():
        factor = str(row["retrieval_factor"])
        human_useful = float(row["human_rating"]) >= 2
        spec = float(row["target_specificity"])
        mir_supports = spec > 0
        merit_sim_col = f"merit_{factor}_similarity"
        merit_strong = row[merit_sim_col] > 0.5

        tags = []
        if merit_strong and mir_supports and not human_useful:
            tags.append("TECHNICALLY_SIMILAR_NOT_PERCEPTUALLY_USEFUL")
        elif merit_strong and human_useful and not mir_supports:
            tags.append("MIR_MISSES_HIGH_LEVEL_STRUCTURE")
        elif merit_strong and not human_useful and not mir_supports:
            tags.append(f"WRONG_{factor.upper()}")
            if factor == "rhythm" and row.get("mir_tempogram_cos", 1) < 0.5 and row.get("bpm_close"):
                tags.append("TEMPO_MATCH_ONLY")
        elif len(tags) == 0 and not merit_strong and not human_useful and not mir_supports:
            tags.append("AMBIGUOUS_CASE")
        if tags:
            disagree_rows.append({
                "query_id": int(row["query_id"]),
                "candidate_id": int(row["candidate_id"]),
                "factor": factor,
                "human_rating": row["human_rating"],
                "merit_similarity": float(row[merit_sim_col]),
                "target_specificity": spec,
                "tags": ";".join(tags),
            })

    disagreement = pd.DataFrame(disagree_rows)
    return {"groups": stats, "disagreement_rows": disagreement}


# ---------------------------------------------------------------------------
# Stages P/Q — evidence components + composite + decisions
# ---------------------------------------------------------------------------

WEIGHTS = {"construct_validity": 0.40, "factor_specificity": 0.25, "baseline_advantage": 0.20, "human_usefulness": 0.15}


def _norm(value: float | None, low: float, high: float) -> float:
    if value is None or not np.isfinite(value):
        return 0.0
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))


def evidence_components(
    master: pd.DataFrame,
    specificity_report: dict,
    validity_comparisons: dict,
    corr: pd.DataFrame,
    human_stats: dict,
) -> dict:
    out = {}
    target_rows = master[(master["retrieval_source"] == "merit_target")]
    mert_rows = master[master["retrieval_source"] == "mert_general"]
    rand_rows = master[master["retrieval_source"] == "random_negative"]

    for factor in ("melody", "rhythm", "timbre"):
        col = f"independent_{factor}_score"

        # --- construct validity (40%): lift over random negatives + over hard negatives
        targets = target_rows[target_rows["retrieval_factor"] == factor][col]
        random_lift = float(targets.median() - rand_rows[col].median()) \
            if not targets.empty and not rand_rows.empty else None
        hard = master[master["retrieval_source"] == "hard_negative"]
        hard_lift = float(targets.median() - hard[col].median()) \
            if not targets.empty and not hard.empty else None
        corr_val = float(corr.loc[f"merit_{factor}", f"mir_{factor}"]) if f"mir_{factor}" in corr.columns else None

        cv_random = _norm(random_lift, 0.0, 0.25)
        cv_hard = _norm(hard_lift, 0.0, 0.20)
        cv_corr = _norm(corr_val, 0.0, 0.6)
        construct_validity = round(0.45 * cv_random + 0.30 * cv_hard + 0.25 * cv_corr, 4)

        # --- factor specificity (25%)
        spec = specificity_report.get(factor, {})
        pct_pos = spec.get("pct_positive")
        median_spec = spec.get("median_specificity")
        factor_specificity = round(0.6 * _norm(pct_pos, 0.5, 0.9) + 0.4 * _norm(median_spec, 0.0, 0.25), 4)

        # --- baseline advantage (20%)
        mert_targets = mert_rows[col]
        mert_adv = float(targets.median() - mert_targets.median()) \
            if not targets.empty and not mert_rows.empty else None
        conv_rows = master[master["retrieval_source"] == "conventional"]
        conv_adv = float(targets.median() - conv_rows[col].median()) \
            if not targets.empty and not conv_rows.empty else None
        baseline_advantage = round(0.6 * _norm(mert_adv, 0.0, 0.15) + 0.4 * _norm(conv_adv, 0.0, 0.15), 4)

        # --- human usefulness (15%) from original rubric; X reported separately
        hstats = human_stats.get(factor, {})
        median_rating = hstats.get("median_rating")
        share_ge_2 = hstats.get("share_ge_2")
        x_rate = hstats.get("x_rate", 0.0)
        human_usefulness = round(0.5 * _norm(median_rating, 1.0, 3.0) + 0.5 * _norm(share_ge_2, 0.3, 0.9), 4)

        composite = round(
            WEIGHTS["construct_validity"] * construct_validity
            + WEIGHTS["factor_specificity"] * factor_specificity
            + WEIGHTS["baseline_advantage"] * baseline_advantage
            + WEIGHTS["human_usefulness"] * human_usefulness,
            4,
        )

        # anti-compensation rule (design section 22)
        construct_failed = construct_validity < 0.35
        if composite >= 0.70 and not construct_failed:
            decision = "GO"
        elif composite >= 0.55 or (construct_validity >= 0.55 and factor_specificity >= 0.5):
            decision = "CONDITIONAL GO"
        else:
            decision = "NO-GO / REPLACE FACTOR"

        out[factor] = {
            "construct_validity": construct_validity,
            "construct_components": {
                "lift_over_random": random_lift, "lift_over_hard_negatives": hard_lift,
                "merit_target_vs_target_mir_correlation": corr_val,
            },
            "factor_specificity": factor_specificity,
            "baseline_advantage": baseline_advantage,
            "baseline_components": {
                "vs_general_mert_median_delta": mert_adv,
                "vs_conventional_median_delta": conv_adv,
            },
            "human_usefulness": human_usefulness,
            "human_components": {
                "median_rating": median_rating, "share_ge_2": share_ge_2, "x_rate": x_rate,
            },
            "composite": composite,
            "decision": decision,
            "anti_compensation_triggered": bool(composite >= 0.70 and construct_failed),
        }
    return out


def original_phase1_gate(human_stats: dict) -> dict:
    """The ORIGINAL predeclared Phase 1 thresholds, preserved verbatim."""
    gates = {}
    for factor, hs in human_stats.items():
        median_ok = (hs.get("median_rating") or 0) >= 2
        share_ok = (hs.get("share_ge_2") or 0) >= 0.60
        gates[factor] = "PASS" if (median_ok and share_ok) else "FAIL"
    return gates
