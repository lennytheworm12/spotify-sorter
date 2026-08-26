"""Unfitted, query-grouped residual-signal screen for Stage 2A."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _prediction(margin: float) -> int:
    return 1 if margin > 0 else (-1 if margin < 0 else 0)


def _truth(label: str) -> int:
    if label == "A": return 1
    if label == "B": return -1
    raise ValueError(f"directional metric requires A/B, got {label}")


def _credit(pred: int, truth: int) -> float:
    return 0.5 if pred == 0 else float(pred == truth)


def query_macro_accuracy(frame: pd.DataFrame, margin_col: str) -> float:
    if frame.empty: return float("nan")
    values = frame.apply(lambda r: _credit(_prediction(float(r[margin_col])), _truth(r.canonical_label)), axis=1)
    return float(values.groupby(frame.query_track_id).mean().mean())


def rescue_stats(frame: pd.DataFrame, baseline_col: str, residual_col: str) -> dict:
    rescues = conflicts = disagreements = 0
    per_query: dict[int, list[float]] = {}
    for _, r in frame.iterrows():
        bp, rp, truth = _prediction(float(r[baseline_col])), _prediction(float(r[residual_col])), _truth(r["canonical_label"])
        if bp != rp:
            disagreements += 1
            bc, rc = _credit(bp, truth), _credit(rp, truth)
            rescues += int(rc > bc); conflicts += int(rc < bc)
        per_query.setdefault(int(r["query_track_id"]), []).append(_credit(rp, truth) - _credit(bp, truth))
    n = len(frame)
    return {"n_trials": n, "n_queries": len(per_query), "disagreement_count": disagreements,
            "rescue_count": rescues, "rescue_rate": rescues / disagreements if disagreements else 0.0,
            "conflict_count": conflicts, "conflict_rate": conflicts / disagreements if disagreements else 0.0,
            "net_rescue": rescues - conflicts, "net_rescue_rate": (rescues - conflicts) / n if n else float("nan"),
            "query_effects": {str(k): float(np.mean(v)) for k, v in per_query.items()}}


def query_bootstrap(effects: dict[str, float], count: int, seed: int) -> dict:
    vals = np.asarray([effects[k] for k in sorted(effects, key=lambda x: int(x))], float)
    if vals.size == 0: return {"low": None, "high": None, "probability_positive": None}
    rng = np.random.default_rng(seed)
    draws = vals[rng.integers(0, len(vals), size=(count, len(vals)))].mean(axis=1)
    return {"low": float(np.quantile(draws, .025)), "high": float(np.quantile(draws, .975)),
            "probability_positive": float(np.mean(draws > 0))}


def component_metrics(frame: pd.DataFrame, baseline: str, component: str, bootstrap_count: int, seed: int) -> dict:
    work = frame.copy()
    bcol, rcol = "_baseline_margin", "_residual_margin"
    work[bcol] = work[f"{baseline}_sim_a"] - work[f"{baseline}_sim_b"]
    work[rcol] = work[f"{component}_sim_a"] - work[f"{component}_sim_b"]
    stats = rescue_stats(work, bcol, rcol)
    boot = query_bootstrap(stats.pop("query_effects"), bootstrap_count, seed)
    return {"baseline_accuracy": query_macro_accuracy(work, bcol),
            "residual_accuracy": query_macro_accuracy(work, rcol), **stats,
            "paired_query_effect_ci95": [boot["low"], boot["high"]],
            "bootstrap_probability_net_rescue_positive": boot["probability_positive"]}


def family_decisions(metrics: dict, cfg: dict) -> dict[str, dict]:
    threshold = cfg["decision"]
    out = {}
    for family, components in cfg["components"].items():
        promising_components = []
        every_component_no_signal = True
        for comp in components:
            vals = [metrics[comp][b]["primary"] for b in cfg["active_baselines"]]
            direct = [metrics[comp][b]["direct_disagreement"] for b in cfg["active_baselines"]]
            promising = (all(v["disagreement_count"] >= threshold["min_disagreements_each_baseline"] for v in vals)
                          and all(v["net_rescue"] > 0 for v in vals)
                          and all(v["bootstrap_probability_net_rescue_positive"] >= threshold["min_positive_probability"] for v in vals)
                          and all(v["net_rescue"] >= 0 for v in direct))
            if promising: promising_components.append(comp)
            if not all(v["net_rescue"] <= 0 for v in vals): every_component_no_signal = False
        status = "PROMISING_FOR_STAGE_2B" if promising_components else ("NO_SIGNAL" if every_component_no_signal else "INCONCLUSIVE")
        out[family] = {"status": status, "qualifying_components": promising_components}
    return out


def score_table(table: pd.DataFrame, cfg: dict) -> dict:
    eligible = table[(table.primary_eligible == True) & table.canonical_label.isin(["A", "B"])]  # noqa: E712
    primary = eligible[eligible.slice.isin(["direct_disagreement", "competitive_rank2"])]
    direct = eligible[eligible.slice == "direct_disagreement"]
    anchor = table[(table.slice == "anchor_negative") & table.canonical_label.isin(["A", "B"]) & (table.label_status == "CANONICAL")]
    components = [c for values in cfg["components"].values() for c in values]
    metrics = {}
    for ci, component in enumerate(components + cfg.get("diagnostics", [])):
        metrics[component] = {}
        for bi, baseline in enumerate(cfg["active_baselines"]):
            component_seed = int(cfg["seed"]) + ci * 101 + bi
            metrics[component][baseline] = {
                "primary": component_metrics(primary, baseline, component, cfg["bootstrap"]["count"], component_seed),
                "direct_disagreement": component_metrics(direct, baseline, component, cfg["bootstrap"]["count"], component_seed),
                "anchor_diagnostic": component_metrics(anchor, baseline, component, cfg["bootstrap"]["count"], component_seed),
            }
    return {"experiment_id": cfg["experiment_id"], "seed": cfg["seed"],
            "denominators": {"canonical_trials": int(len(table)), "raw_judgments": int(table.raw_judgment_count.sum()),
                             "primary_ab": int(len(primary)), "direct_disagreement_ab": int(len(direct)),
                             "anchor_ab": int(len(anchor)), "tie": int((table.canonical_label == "Tie").sum()),
                             "neither": int((table.canonical_label == "Neither").sum()),
                             "rater_conflict": int((table.label_status == "RATER_CONFLICT").sum())},
            "metrics": metrics, "family_decisions": family_decisions(metrics, cfg)}


def stable_json(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n"


def render_report(result: dict) -> str:
    d = result["denominators"]
    lines = ["# Stage 2A Residual Signal Screen", "", "**Exploratory decision screen; no model was fitted and no fusion weight was selected.**", "",
             "## Denominators", "", f"- Frozen canonical trials: {d['canonical_trials']} from {d['raw_judgments']} append-only judgments",
             f"- Primary A/B trials (direct disagreement + competitive rank-2; anchors excluded): {d['primary_ab']}",
             f"- Direct-disagreement A/B sensitivity: {d['direct_disagreement_ab']}", f"- Anchor A/B diagnostic: {d['anchor_ab']}",
             f"- Ambiguity: {d['tie']} Tie, {d['neither']} Neither; rater conflicts: {d['rater_conflict']}", "", "## Family decisions", ""]
    for family, decision in result["family_decisions"].items():
        suffix = f" ({', '.join(decision['qualifying_components'])})" if decision["qualifying_components"] else ""
        lines.append(f"- **{family}: {decision['status']}**{suffix}")
    lines += ["", "## Component results", "", "| Component | Baseline | N | Disagreements | Rescue | Conflict | Net | P(net > 0) | 95% paired query-effect CI | Direct net |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for comp, by_base in result["metrics"].items():
        for base, slices in by_base.items():
            p, s = slices["primary"], slices["direct_disagreement"]
            ci = p["paired_query_effect_ci95"]
            lines.append(f"| {comp} | {base} | {p['n_trials']} | {p['disagreement_count']} | {p['rescue_count']} | {p['conflict_count']} | {p['net_rescue']} | {p['bootstrap_probability_net_rescue_positive']:.3f} | [{ci[0]:.3f}, {ci[1]:.3f}] | {s['net_rescue']} |")
    lines += ["", "## Limitations and failure cases", "", "- Almost all labels came from one listener; this cannot support population or inter-rater claims.",
              "- Listeners heard each full FMA clip, while all baseline and residual inputs are the deterministic centered five-second `center5_v1` excerpt at 24 kHz mono. Stimulus/input mismatch may hide or create apparent signal.",
              "- The frozen label budget is small and adaptively generated by Stage 1 encoder disagreements; confidence intervals describe this pilot only.",
              "- Exact score ties receive 0.5 directional credit. Tie and Neither labels remain ambiguity diagnostics and are never coerced to A/B.",
              "- Anchor negatives are excluded from the primary screen and shown only diagnostically in `metrics.json`.",
              "- The conflict counts in the component table are the observed residual failure counts; trial-level scores and exclusions are retained in `canonical_trial_features.csv` for case inspection.",
              "- `log_tempo_ratio` is reported in `metrics.json` as a diagnostic only and cannot qualify the rhythm family.",
              "- These decisions only screen whether a separately designed, nested query-grouped Stage 2B fitted ablation might be worth running. They do not select an encoder, feature, production model, or application behavior.", ""]
    return "\n".join(lines)


def write_outputs(table: pd.DataFrame, raw: list[dict], result: dict, cfg: dict, root: Path, checked_hashes: dict) -> dict:
    out = root / cfg["paths"]["report_dir"]; out.mkdir(parents=True, exist_ok=True)
    table_path = out / "canonical_trial_features.csv"; table.to_csv(table_path, index=False, lineterminator="\n", float_format="%.10g")
    (out / "metrics.json").write_text(stable_json(result)); (out / "decision_report.md").write_text(render_report(result))
    manifest = {"experiment_id": cfg["experiment_id"], "input_sha256": checked_hashes,
                "raw_judgment_count": len(raw), "canonical_trial_count": len(table),
                "table_sha256": hashlib.sha256(table_path.read_bytes()).hexdigest(),
                "metrics_sha256": hashlib.sha256((out / "metrics.json").read_bytes()).hexdigest(),
                "report_sha256": hashlib.sha256((out / "decision_report.md").read_bytes()).hexdigest(),
                "excerpt": cfg["excerpt"], "network_used_for_scoring": False}
    (out / "input_provenance_manifest.json").write_text(stable_json(manifest))
    return manifest
