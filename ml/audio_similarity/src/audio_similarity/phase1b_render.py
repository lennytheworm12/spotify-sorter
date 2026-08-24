"""Render phase1b_cross_reference_report.md from computed Phase 1B artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

FACTOR_LABELS = ("melody", "rhythm", "timbre")


def render_report(
    summary: dict,
    spec_report: dict,
    comparisons: dict,
    corr: pd.DataFrame,
    leakage_flags: list[str],
    human_stats: dict,
    original_gate: dict,
    disagreements: pd.DataFrame | None,
    decision_table_md: str,
) -> str:
    lines: list[str] = []
    add = lines.append

    add("# Phase 1B — Cross-Reference Construct Validation Report")
    add("")
    add(f"Generated: {summary['generated_at']} · experiment `{summary['experiment_id']}`")
    add("")

    # ---- Q1-3 + Q4: per-factor construct validity and specificity
    add("## Independent construct validity (RQ1B-1/2/3, design section 15)")
    add("")
    for factor in FACTOR_LABELS:
        comp = comparisons.get(factor, {})
        rnd = comp.get("random_negative")
        hard = comp.get("hard_negative")
        add(f"### {factor}")
        if rnd:
            add(f"- vs random negatives: median delta **{rnd['median_delta_vs_control']:+.3f}\" "
                f"(CI {rnd['ci95_of_delta'][0]:+.3f} .. {rnd['ci95_of_delta'][1]:+.3f}\", "
                f"Cliff's δ={rnd['cliffs_delta']:+.2f})")
        if hard and hard.get("median_delta_vs_control") is not None:
            add(f"- vs matched hard negatives: median delta **{hard['median_delta_vs_control']:+.3f}\" "
                f"(CI {hard['ci95_of_delta'][0]:+.3f} .. {hard['ci95_of_delta'][1]:+.3f}\")")
        if comp.get("mert_general"):
            mg = comp["mert_general"]
            add(f"- vs general-MERT neighbors: median delta **{mg['median_delta_vs_control']:+.3f}\"** (Q5)")
        if comp.get("conventional"):
            cv = comp["conventional"]
            add(f"- vs conventional-feature neighbors: median delta **{cv['median_delta_vs_control']:+.3f}\"** (Q6)")
        sr_ = spec_report.get(factor, {})
        add(f"- specificity: median {sr_.get('median_specificity')}, "
            f"{100 * (sr_.get('pct_positive') or 0):.0f}% positive (Q4, RQ1B-4)")
        add("")

    # ---- Q5 extra note
    add("## Baseline advantage summary (RQ1B-5)")
    for factor in FACTOR_LABELS:
        bc = summary["evidence_components"][factor]["baseline_components"]
        add(f"- {factor}: vs MERT {bc['vs_general_mert_median_delta']:+.3f}, "
            f"vs conventional {bc['vs_conventional_median_delta']:+.3f}")
    add("")

    # ---- Q7: tempo collapse
    add("## Rhythm tempo-collapse diagnostic (Q7)")
    tm = summary.get("tempo_match_only_count", 0)
    rhythm_rows = summary.get("rhythm_target_rows", 0)
    add(f"TEMPO_MATCH_ONLY flagged in {tm}/{rhythm_rows} MERIT rhythm target pairs.")
    add("")

    # ---- correlation matrix
    add("## MERIT ↔ MIR correlation matrix (Stage L)")
    add("")
    add("```")
    add(corr.to_string())
    add("```")
    if leakage_flags:
        add("")
        add("**Cross-factor leakage flags:**")
        for f in leakage_flags:
            add(f"- {f}")
    else:
        add("")
        add("No cross-factor leakage: each MERIT factor correlates most strongly with its own independent metric.")
    add("")

    # ---- Q11/12 agreement/disagreement
    add("## Human ↔ MIR agreement (Q11/Q12)")
    groups = disagreements.get("groups", {}) if isinstance(disagreements, dict) else {}
    for label in ("useful", "not_useful"):
        g = groups.get(label, {"n": 0, "median_target_mir": {}})
        med = g.get("median_target_mir", {})
        add(f"- {label}: n={g['n']} " +
            ", ".join(f"{k} median={v}" for k, v in med.items() if v is not None))
    if isinstance(disagreements, pd.DataFrame) and not disagreements.empty:
        add("")
        tag_counts = disagreements["tags"].str.split(";").explode().value_counts()
        for tag, count in tag_counts.items():
            add(f"- {tag}: {count}")
    add("")

    # ---- Q8-10 failure modes
    add("## Major failure modes (Q8-Q10)")
    for factor in FACTOR_LABELS:
        hs = human_stats[factor]
        add(f"- {factor}: X-rate {hs['x_rate']}, "
            f"human median {hs['median_rating']}")

    # ---- Q13/Q14 decisions
    add("")
    add("## Original Phase 1 human-only result (preserved verbatim) (Q13)")
    add("")
    add("| Factor | Original gate |")
    add("|---|---|")
    for factor in FACTOR_LABELS:
        add(f"| {factor} | {original_gate[factor]} |")
    add("")
    add("## Phase 1B triangulated result (Q14)")
    add("")
    add(decision_table_md)
    for factor in FACTOR_LABELS:
        ec = summary["evidence_components"][factor]
        add(f"- **{factor}: {ec['decision']}** (composite {ec['composite']}) — "
            f"construct {ec['construct_validity']}, specificity {ec['factor_specificity']}, "
            f"baseline {ec['baseline_advantage']}, human {ec['human_usefulness']}"
            + (" — ANTI-COMPENSATION TRIGGERED" if ec["anti_compensation_triggered"] else ""))

    # ---- Q15 factors into Phase 2
    retained = [f for f in FACTOR_LABELS if summary["evidence_components"][f]["decision"] in ("GO", "CONDITIONAL GO")]
    add("")
    add("## Factors recommended to continue into Phase 2 (Q15)")
    add("")
    add("- " + (", ".join(retained) if retained else "NONE — see Outcome E / D logic in the design"))
    add("")

    return "\n".join(lines)
