"""Vector-only paired analysis for the frozen GLAP Stage 2B challenger."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .glap_stage2b import GlapEmbeddingCache, load_evidence_tracks, load_glap_contract
from .stage2b_contract import ContractError, sha256_file
from .stage2b_metrics import accuracy_contributions, query_macro_accuracy
from .stage2b_test import paired_query_bootstrap
from .stage2b_trials import load_validated_embeddings


def _prediction(margin: float) -> str:
    return "A" if margin > 0 else "B" if margin < 0 else "TIE"


def _metric_block(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        raise ContractError("challenger metric block has no binary rows")
    margins = frame["glap_margin"].to_numpy(dtype=np.float64)
    labels = frame["binary_label_a_wins"].to_numpy(dtype=np.int64)
    queries = frame["query_id"].to_numpy(dtype=np.int64)
    query = query_macro_accuracy(margins, labels, queries)
    contribution = accuracy_contributions(margins, labels)
    return {
        "pairwise_accuracy": float(contribution.mean()),
        "query_macro_accuracy": query["query_macro_accuracy"],
        "binary_trial_count": len(frame),
        "query_count": len(query["per_query_accuracy"]),
        "tie_count": int((margins == 0).sum()),
        "tie_rate": float((margins == 0).mean()),
        "per_query_accuracy": query["per_query_accuracy"],
    }


def _correlation(first: np.ndarray, second: np.ndarray) -> dict[str, Any]:
    first, second = np.asarray(first, dtype=np.float64), np.asarray(second, dtype=np.float64)
    if first.shape != second.shape or first.size < 2:
        return {"count": int(first.size), "pearson": None, "spearman": None}
    pearson = float(np.corrcoef(first, second)[0, 1])
    spearman = float(spearmanr(first, second).statistic)
    return {"count": int(first.size), "pearson": pearson, "spearman": spearman}


def _distribution(values: pd.Series) -> dict[str, float]:
    array = values.to_numpy(dtype=np.float64)
    quantiles = np.quantile(array, [0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0])
    return {
        "min": float(quantiles[0]),
        "p05": float(quantiles[1]),
        "p25": float(quantiles[2]),
        "p50": float(quantiles[3]),
        "p75": float(quantiles[4]),
        "p95": float(quantiles[5]),
        "max": float(quantiles[6]),
        "mean": float(array.mean()),
    }


def _language_audit(root: Path, stage2b_config: dict[str, Any]) -> dict[str, Any]:
    manifest = pd.read_parquet(root / stage2b_config["inputs"]["manifest"]["path"])
    candidates = [
        str(column)
        for column in manifest.columns
        if "language" in str(column).casefold() or "vocal_lang" in str(column).casefold()
    ]
    if not candidates:
        return {
            "reliable_metadata_found": False,
            "candidate_columns": [],
            "subgroup_analysis_performed": False,
            "conclusion": "Historical Stage 2B does not support a reliable multilingual subgroup analysis.",
            "interpretation": "EXPLORATORY",
        }
    return {
        "reliable_metadata_found": False,
        "candidate_columns": candidates,
        "subgroup_analysis_performed": False,
        "conclusion": "Language-like columns exist but were not established as reliable vocal-language metadata; no subgroup claims were made.",
        "interpretation": "EXPLORATORY",
    }


def analyze_glap_challenger(
    *,
    contract_path: str | Path,
    root: str | Path,
    cache_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    root, output_dir = Path(root), Path(output_dir)
    contract = load_glap_contract(contract_path, root)
    evidence_tracks = load_evidence_tracks(contract, root)
    expected_ids = {track.track_id for track in evidence_tracks}
    cache = GlapEmbeddingCache(cache_path)
    glap = cache.all_success_embeddings()
    cache_summary = cache.summary()
    cache.close()
    if set(glap) != expected_ids:
        missing, extra = sorted(expected_ids - set(glap)), sorted(set(glap) - expected_ids)
        raise ContractError(f"GLAP cache does not exactly cover frozen evidence; missing={missing}, extra={extra}")

    historical = contract["historical_evidence"]
    clap_spec = historical["laion_clap_embeddings"]
    clap = load_validated_embeddings(
        root / clap_spec["path"],
        clap_spec["sha256"],
        clap_spec["analysis_key"],
        int(clap_spec["dimensions"]),
    )
    trials = json.loads((root / historical["trial_manifest"]["path"]).read_text(encoding="utf-8"))["trials"]
    labels = pd.read_csv(root / historical["canonical_labels"]["path"], dtype=str).fillna("").set_index("trial_id")
    rows = []
    for trial_id in sorted(trials):
        trial = trials[trial_id]
        query, candidate_a, candidate_b = map(
            int, (trial["query_id"], trial["candidate_a"], trial["candidate_b"])
        )
        glap_a = float(np.dot(glap[query], glap[candidate_a]))
        glap_b = float(np.dot(glap[query], glap[candidate_b]))
        clap_a = float(np.dot(clap[query], clap[candidate_a]))
        clap_b = float(np.dot(clap[query], clap[candidate_b]))
        choice = str(labels.at[trial_id, "choice"])
        included = choice in {"A", "B"}
        rows.append(
            {
                "trial_id": trial_id,
                "query_id": query,
                "candidate_a": candidate_a,
                "candidate_b": candidate_b,
                "split": trial["split"],
                "source_pair": trial["source_pair"],
                "human_choice": choice,
                "included_binary": included,
                "binary_label_a_wins": 1 if choice == "A" else 0 if choice == "B" else "",
                "glap_cosine_a": glap_a,
                "glap_cosine_b": glap_b,
                "glap_margin": glap_a - glap_b,
                "glap_prediction": _prediction(glap_a - glap_b),
                "clap_cosine_a": clap_a,
                "clap_cosine_b": clap_b,
                "clap_margin": clap_a - clap_b,
                "clap_prediction": _prediction(clap_a - clap_b),
            }
        )
    predictions = pd.DataFrame(rows)
    binary = predictions[predictions["included_binary"]].copy()
    binary["binary_label_a_wins"] = binary["binary_label_a_wins"].astype(int)
    labels_array = binary["binary_label_a_wins"].to_numpy(dtype=np.int64)
    binary["glap_accuracy_credit"] = accuracy_contributions(
        binary["glap_margin"].to_numpy(), labels_array
    )
    binary["clap_accuracy_credit"] = accuracy_contributions(
        binary["clap_margin"].to_numpy(), labels_array
    )

    metrics = {"ALL": _metric_block(binary)}
    for split in ("TRAIN", "VALIDATION", "TEST"):
        metrics[split] = _metric_block(binary[binary["split"] == split])
    frozen_test = historical["frozen_test_metrics"]["laion_clap_test_query_macro_accuracy"]
    clap_test_query = query_macro_accuracy(
        binary.loc[binary["split"] == "TEST", "clap_margin"].to_numpy(),
        binary.loc[binary["split"] == "TEST", "binary_label_a_wins"].to_numpy(),
        binary.loc[binary["split"] == "TEST", "query_id"].to_numpy(),
    )
    if clap_test_query["query_macro_accuracy"] != frozen_test:
        raise ContractError(
            f"LAION-CLAP baseline reproduction changed during GLAP analysis: {clap_test_query['query_macro_accuracy']}"
        )

    query_rows = []
    for (split, query_id), frame in binary.groupby(["split", "query_id"], sort=True):
        query_rows.append(
            {
                "split": split,
                "query_id": int(query_id),
                "binary_trial_count": len(frame),
                "glap_accuracy": float(frame["glap_accuracy_credit"].mean()),
                "laion_clap_accuracy": float(frame["clap_accuracy_credit"].mean()),
                "glap_minus_laion_clap": float(
                    frame["glap_accuracy_credit"].mean() - frame["clap_accuracy_credit"].mean()
                ),
                "mean_glap_margin": float(frame["glap_margin"].mean()),
                "mean_laion_clap_margin": float(frame["clap_margin"].mean()),
            }
        )
    per_query = pd.DataFrame(query_rows)
    test_queries = per_query[per_query["split"] == "TEST"]
    bootstrap = paired_query_bootstrap(
        dict(zip(test_queries["query_id"].astype(str), test_queries["glap_accuracy"])),
        dict(zip(test_queries["query_id"].astype(str), test_queries["laion_clap_accuracy"])),
        int(contract["metrics"]["bootstrap_draws"]),
        int(contract["metrics"]["bootstrap_seed"]),
    )

    test = binary[binary["split"] == "TEST"]
    glap_correct, clap_correct = test["glap_accuracy_credit"], test["clap_accuracy_credit"]
    paired_table = {
        "both_correct": int(((glap_correct == 1) & (clap_correct == 1)).sum()),
        "laion_clap_only_correct": int(((glap_correct == 0) & (clap_correct == 1)).sum()),
        "glap_only_correct": int(((glap_correct == 1) & (clap_correct == 0)).sum()),
        "both_wrong": int(((glap_correct == 0) & (clap_correct == 0)).sum()),
        "rows_with_exact_tie_credit": int(((glap_correct == 0.5) | (clap_correct == 0.5)).sum()),
    }
    diagnostics = {
        "test_paired_outcomes": paired_table,
        "test_glap_rescues": paired_table["glap_only_correct"],
        "test_glap_created_errors": paired_table["laion_clap_only_correct"],
        "margin_correlation_all_binary": _correlation(binary["glap_margin"], binary["clap_margin"]),
        "margin_correlation_test": _correlation(test["glap_margin"], test["clap_margin"]),
        "similarity_correlation_all_trials": _correlation(
            np.concatenate([predictions["glap_cosine_a"], predictions["glap_cosine_b"]]),
            np.concatenate([predictions["clap_cosine_a"], predictions["clap_cosine_b"]]),
        ),
        "absolute_margin_distributions": {
            "GLAP_ALL_BINARY": _distribution(binary["glap_margin"].abs()),
            "LAION_CLAP_ALL_BINARY": _distribution(binary["clap_margin"].abs()),
            "GLAP_TEST": _distribution(test["glap_margin"].abs()),
            "LAION_CLAP_TEST": _distribution(test["clap_margin"].abs()),
        },
        "queries_glap_strongest": test_queries.sort_values(
            ["glap_minus_laion_clap", "query_id"], ascending=[False, True]
        ).head(5)[["query_id", "glap_minus_laion_clap"]].to_dict("records"),
        "queries_laion_clap_strongest": test_queries.sort_values(
            ["glap_minus_laion_clap", "query_id"], ascending=[True, True]
        ).head(5)[["query_id", "glap_minus_laion_clap"]].to_dict("records"),
    }

    import yaml

    stage2b_config_path = root / historical["stage2b_config"]["path"]
    stage2b_config = yaml.safe_load(stage2b_config_path.read_text(encoding="utf-8"))
    language = _language_audit(root, stage2b_config)
    if bootstrap["ci_95"][1] < 0:
        verdict = "GLAP_REJECTED_AS_GLOBAL_CHALLENGER"
    elif bootstrap["ci_95"][0] > 0:
        verdict = "GLAP_PROMOTE_TO_REPRESENTATION_V2_CHALLENGER"
    else:
        verdict = "GLAP_COMPETITIVE_BUT_UNPROVEN"

    output_dir.mkdir(parents=True, exist_ok=True)
    predictions_path, per_query_path = output_dir / "predictions.csv", output_dir / "per_query_metrics.csv"
    predictions.to_csv(predictions_path, index=False, float_format="%.17g")
    per_query.to_csv(per_query_path, index=False, float_format="%.17g")
    (output_dir / "bootstrap.json").write_text(
        json.dumps(bootstrap, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "language_audit.json").write_text(
        json.dumps(language, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    result = {
        "schema_version": 1,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": sha256_file(contract_path),
        "cache_summary": cache_summary,
        "baseline_reproduction": {
            "expected_test_query_macro_accuracy": frozen_test,
            "reproduced_test_query_macro_accuracy": clap_test_query["query_macro_accuracy"],
            "exact_match": True,
        },
        "glap_metrics": metrics,
        "glap_minus_laion_clap_test_query_macro": bootstrap,
        "diagnostics": diagnostics,
        "language_audit": language,
        "provisional_statistical_verdict": verdict,
        "production_contract_changed": False,
        "artifact_hashes": {
            "predictions.csv": sha256_file(predictions_path),
            "per_query_metrics.csv": sha256_file(per_query_path),
        },
    }
    result_path = output_dir / "comparison_summary.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result["artifact_hashes"]["comparison_summary.json"] = sha256_file(result_path)
    return result
