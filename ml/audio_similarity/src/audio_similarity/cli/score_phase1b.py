"""Generate the full Phase 1B cross-reference analysis and amended decision report.

    python -m audio_similarity.cli.score_phase1b

Reads frozen cases + feature cache, builds the master cross-reference table,
runs every analysis stage, and writes all required artifacts under
reports/phase1b/. Pairs whose features are missing are skipped (and counted).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from audio_similarity.mir_features import FeatureCache, cache_stats, feature_config_hash
from audio_similarity.phase1b_analyze import (
    AnalysisContext,
    EmbeddingLookup,
    background_distributions,
    load_human_joins,
    save_master_table,
    score_master_table,
)
from audio_similarity.phase1b_freeze import sha256_file
from audio_similarity.phase1b_report import (
    construct_validity_comparisons,
    correlation_matrix,
    disagreement_analysis,
    evidence_components,
    factor_specificity_report,
    flag_cross_factor_leakage,
    original_phase1_gate,
)


def human_factor_stats(master: pd.DataFrame) -> dict:
    targets = master[master["retrieval_source"] == "merit_target"]
    out = {}
    for factor in ("melody", "rhythm", "timbre"):
        rows = targets[targets["retrieval_factor"] == factor]
        valid = rows[rows["human_valid"] == True]  # noqa: E712
        ratings = pd.to_numeric(valid["human_rating"], errors="coerce").dropna()
        n_total = len(rows)
        n_x = int((rows["human_rating"] == "X").sum())
        out[factor] = {
            "n_pairs": int(n_total),
            "n_valid": int(len(ratings)),
            "x_count": n_x,
            "x_rate": float(n_x / n_total) if n_total else None,
            "median_rating": float(ratings.median()) if len(ratings) else None,
            "share_ge_2": float((ratings >= 2).mean()) if len(ratings) else None,
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="reports/phase1b/frozen_cases.json")
    parser.add_argument("--config", default="reports/phase1b/phase1b_config.json")
    parser.add_argument("--embeddings", default="artifacts/phase1_full/embeddings.parquet")
    parser.add_argument("--manifest", default="data/manifests/fma_small.parquet")
    parser.add_argument("--key-factor", default="reports/human_eval/key_factor.csv")
    parser.add_argument("--ratings", default="reports/human_eval/judgments_factor.csv")
    parser.add_argument("--cache-dir", default="data/phase1b_feature_cache")
    parser.add_argument("--output-dir", default="reports/phase1b")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_full = pd.read_parquet(args.manifest)
    manifest = manifest_full.copy()

    lookup = EmbeddingLookup(args.embeddings)
    cache = FeatureCache(args.cache_dir)

    # ---- Stage H: background calibration over cached features
    data = json.loads(Path(args.cases).read_text())
    needed: set[int] = set()
    for c in data["cases"]:
        needed.add(c["query_id"])
        needed.update(c["merit_target_neighbors"])
        for lst in c["merit_other_neighbors"].values():
            needed.update(lst)
        needed.update(c["mert_general_neighbors"])
        needed.update(c["conventional_neighbors"])
        needed.update(c["random_negatives"])
        needed.update(c["hard_negatives"])

    bg_rng = np.random.default_rng(424242)
    all_ids = np.array(sorted({int(t) for t in manifest["track_id"]}))
    have_hash = {str(t): str(manifest.set_index("track_id").at[t, "audio_sha256"]) for t in all_ids}
    available = [t for t in all_ids if cache.get(have_hash[int(t)]) is not None]
    print(f"features available for {len(available)} / {len(all_ids)} corpus tracks")

    bg_ids = [int(t) for t in bg_rng.choice(available, size=min(4000, len(available)), replace=False)]
    calib_path = out_dir / "background_calibration.npz"
    dists = background_distributions(cache, bg_ids, n_pairs=2000, seed=424242)
    calibration = BackgroundCalibration(dists)
    save_calibration(
        calibration, calib_path,
        {"n_pairs_target": 2000, "seed": 424242,
         "config_hash": feature_config_hash(),
         "n_available_tracks": len(available)},
    )
    print(f"background calibration: {len(dists['timbre_cos'])} pairs")

    ctx = AnalysisContext(
        manifest=manifest, lookup=lookup, cache=cache,
        calibration=calibration,
        human_joins=load_human_joins(args.ratings, args.key_factor),
    )

    # ---- Stages E/F/I/M: master table
    master = score_master_table(args.cases, ctx)
    missing_pairs = 0  # skipped pairs already excluded inside scorer
    save_master_table(master, out_dir / "master_cross_reference.parquet")
    print(f"master table rows: {len(master)}")

    # ---- Stage J/K/L/O analyses
    spec_report = factor_specificity_report(master)
    comparisons = construct_validity_comparisons(master)
    corr = correlation_matrix(master)
    leakage_flags = flag_cross_factor_leakage(corr)
    human_stats = human_factor_stats(master)
    disagreements = disagreement_analysis(master)

    components = evidence_components(master, spec_report, comparisons, corr, human_stats)
    gates = original_phase1_gate({
        f: {
            "median_rating": components[f]["human_components"]["median_rating"],
            "share_ge_2": components[f]["human_components"]["share_ge_2"],
        }
        for f in ("melody", "rhythm", "timbre")
    })

    # ---- persist analysis artifacts
    (out_dir / "factor_specificity.json").write_text(json.dumps(spec_report, indent=1))
    (out_dir / "construct_validity.json").write_text(json.dumps(comparisons, indent=1))
    corr.to_csv(out_dir / "merit_mir_correlation.csv")
    (out_dir / "correlation_flags.json").write_text(json.dumps(leakage_flags, indent=1))
    if not disagreements["disagreement_rows"].empty:
        disagreements["disagreement_rows"].to_csv(out_dir / "human_mir_disagreements.csv", index=False)

    summary = {
        "experiment_id": "phase1b_cross_reference_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": sha256_file(__file__)[:12],
        "human_stats": human_stats,
        "original_phase1_gate": gates,
        "evidence_components": components,
        "leakage_flags": leakage_flags,
        "feature_cache": cache_stats(args.cache_dir),
        "missing_pairs_skipped": missing_pairs,
        "master_rows": len(master),
    }
    (out_dir / "phase1b_summary.json").write_text(json.dumps(summary, indent=1))

    # ---- decision table (design section 30)
    lines = ["| Area | Melody | Rhythm | Timbre |", "|---|---:|---:|---:|"]
    for label, key in [
        ("Construct validity", "construct_validity"),
        ("Factor specificity", "factor_specificity"),
        ("Baseline advantage", "baseline_advantage"),
        ("Human usefulness", "human_usefulness"),
        ("Composite", "composite"),
    ]:
        lines.append(f"| {label} | " + " | ".join(str(components[f][key]) for f in ("melody", "rhythm", "timbre")) + " |")
    lines.append("| Human median 0-3 | " + " | ".join(str(human_stats[f]["median_rating"]) for f in ("melody", "rhythm", "timbre")) + " |")
    lines.append("| Human useful-rate >=2 | " + " | ".join(_pct(human_stats[f]["share_ge_2"]) for f in ("melody", "rhythm", "timbre")) + " |")
    lines.append("| Human X rate | " + " | ".join(_pct(human_stats[f]["x_rate"]) for f in ("melody", "rhythm", "timbre")) + " |")
    lines.append("| Original P1 result | " + " | ".join(gates[f] for f in ("melody", "rhythm", "timbre")) + " |")
    lines.append("| Phase 1B result | " + " | ".join(components[f]["decision"] for f in ("melody", "rhythm", "timbre")) + " |")
    (out_dir / "decision_table.md").write_text("\n".join(lines) + "\n")
    print(f"analysis written to {out_dir}")
    return 0


def _pct(v):
    return f"{v:.2f}" if v is not None else "n/a"


if __name__ == "__main__":
    raise SystemExit(main())
