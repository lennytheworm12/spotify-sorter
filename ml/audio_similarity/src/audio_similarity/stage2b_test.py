"""One-time git-locked Stage 2B held-out TEST evaluation and verdict."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from .stage2b_contract import ContractError, load_contract, sha256_file
from .stage2b_metrics import accuracy_contributions, binary_log_loss, query_macro_accuracy
from .stage2b_selection import FEATURES, _sigmoid, load_train_validation_rows


class TestLockError(ContractError):
    """The pushed model-selection checkpoint is not safe to reveal TEST."""


def _git(root: Path, *args: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=False,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode:
        message = result.stderr.strip() if result.stderr else "git checkpoint check failed"
        raise TestLockError(message)
    return result.stdout.strip() if capture else ""


def verify_test_lock(config_path: str | Path, root: str | Path = ".", allow_existing: bool = False) -> dict[str, Any]:
    root, config_path = Path(root).resolve(), Path(config_path).resolve()
    config = load_contract(config_path)
    report_dir = root / config["paths"]["report_dir"]
    selection_path = report_dir / "model_selection.json"
    git_root = Path(_git(root, "rev-parse", "--show-toplevel", capture=True))
    selection_rel = str(selection_path.relative_to(git_root))
    _git(git_root, "ls-files", "--error-unmatch", selection_rel)
    _git(git_root, "diff", "--quiet", "--", selection_rel)
    _git(git_root, "diff", "--cached", "--quiet", "--", selection_rel)
    _git(git_root, "cat-file", "-e", f"HEAD:{selection_rel}")
    upstream = _git(git_root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", capture=True)
    _git(git_root, "merge-base", "--is-ancestor", "HEAD", upstream)
    if (report_dir / "test_metrics.json").exists() and not allow_existing:
        raise TestLockError("test_metrics.json already exists; refusing to reveal or overwrite TEST")

    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    expected = selection["source_hashes"]
    actual = {
        "ratings_sha256": sha256_file(report_dir / "canonical_labels_train_validation.csv"),
        "dataset_sha256": sha256_file(report_dir / "fusion_dataset.csv"),
        "trial_keys_sha256": sha256_file(report_dir / "trial_keys.json"),
        "rating_validation_sha256": sha256_file(report_dir / "rating_validation.json"),
    }
    if actual != expected:
        raise TestLockError(f"model-selection source hash mismatch: {actual}")
    if selection["config_sha256"] != sha256_file(config_path):
        raise TestLockError("model-selection config hash mismatch")
    selection_code = root / "src/audio_similarity/stage2b_selection.py"
    if selection["selection_code_sha256"] != sha256_file(selection_code):
        raise TestLockError("model-selection code hash mismatch")
    keys = json.loads((report_dir / "trial_keys.json").read_text(encoding="utf-8"))["trials"]
    identities = "\n".join(sorted(key for key, value in keys.items() if value["split"] == "TEST"))
    identity_hash = hashlib.sha256(identities.encode()).hexdigest()
    if identity_hash != selection["frozen_test_trial_identities_sha256"]:
        raise TestLockError("frozen TEST trial identity hash mismatch")
    return {
        "selection": selection,
        "selection_sha256": sha256_file(selection_path),
        "upstream": upstream,
        "head": _git(git_root, "rev-parse", "HEAD", capture=True),
    }


def paired_query_bootstrap(
    per_query_first: dict[str, float], per_query_second: dict[str, float] | None,
    draws: int, seed: int,
) -> dict[str, Any]:
    query_ids = sorted(per_query_first, key=int)
    if per_query_second is not None and set(per_query_second) != set(query_ids):
        raise ContractError("paired bootstrap query sets differ")
    first = np.asarray([per_query_first[key] for key in query_ids], dtype=np.float64)
    second = None if per_query_second is None else np.asarray([per_query_second[key] for key in query_ids], dtype=np.float64)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(query_ids), size=(draws, len(query_ids)))
    sampled_first = first[indices].mean(axis=1)
    values = sampled_first if second is None else (first - second)[indices].mean(axis=1)
    return {
        "draws": draws,
        "seed": seed,
        "estimate": float(first.mean() if second is None else (first - second).mean()),
        "ci_95": [float(value) for value in np.quantile(values, [0.025, 0.975])],
    }


def _model_metrics(margins: np.ndarray, labels: np.ndarray, queries: np.ndarray, sources: np.ndarray, fitted: bool) -> dict[str, Any]:
    metrics = query_macro_accuracy(margins, labels, queries)
    contributions = accuracy_contributions(margins, labels)
    metrics["per_source_pair_accuracy"] = {
        str(source): float(contributions[sources == source].mean()) for source in sorted(set(sources.tolist()))
    }
    metrics["binary_row_count"] = len(labels)
    metrics["query_count"] = len(set(queries.tolist()))
    if fitted:
        metrics["log_loss"] = binary_log_loss(_sigmoid(margins), labels)
    return metrics


def _coefficient_stability(
    train_matrix: np.ndarray, labels: np.ndarray, queries: np.ndarray,
    indices: list[int], selection: dict[str, Any], draws: int, seed: int,
) -> dict[str, Any]:
    selected = selection["fusion_results"][selection["selected_fusion"]]
    mean = np.asarray(selected["scaler_mean"], dtype=np.float64)
    scale = np.asarray(selected["scaler_scale"], dtype=np.float64)
    frozen = np.asarray(selected["coefficients"], dtype=np.float64)
    matrix = (train_matrix[:, indices] - mean) / scale
    unique_queries = np.asarray(sorted(set(queries.tolist())), dtype=np.int64)
    rng = np.random.default_rng(seed)
    coefficients = []
    attempts = 0
    while len(coefficients) < draws and attempts < draws * 10:
        attempts += 1
        sampled = rng.choice(unique_queries, size=len(unique_queries), replace=True)
        row_indices = np.concatenate([np.flatnonzero(queries == query) for query in sampled])
        sampled_labels = labels[row_indices]
        if len(set(sampled_labels.tolist())) < 2:
            continue
        model = LogisticRegression(
            C=float(selected["selected_C"]), penalty="l2", solver="lbfgs", fit_intercept=False,
            random_state=seed, max_iter=10000, tol=1e-8,
        ).fit(matrix[row_indices], sampled_labels)
        coefficients.append(model.coef_[0])
    if len(coefficients) != draws:
        raise ContractError(f"only {len(coefficients)}/{draws} coefficient bootstrap refits succeeded")
    array = np.asarray(coefficients)
    sign = np.sign(frozen)
    corr = np.corrcoef(array, rowvar=False) if array.shape[1] > 1 else np.asarray([[1.0]])
    feature_corr = np.corrcoef(matrix, rowvar=False) if matrix.shape[1] > 1 else np.asarray([[1.0]])
    return {
        "draws": draws,
        "attempts": attempts,
        "seed": seed,
        "frozen_coefficients": frozen.tolist(),
        "percentile_interval_95": np.quantile(array, [0.025, 0.975], axis=0).T.tolist(),
        "sign_retention_frequency": (np.sign(array) == sign).mean(axis=0).tolist(),
        "near_zero_frequency_abs_lt_0_05": (np.abs(array) < 0.05).mean(axis=0).tolist(),
        "coefficient_correlation": np.nan_to_num(corr, nan=0.0).tolist(),
        "standardized_train_feature_correlation": np.nan_to_num(feature_corr, nan=0.0).tolist(),
    }


def _complementarity(margins: dict[str, np.ndarray], labels: np.ndarray, selected_individual: str, selected_fusion: str) -> dict[str, Any]:
    singles = ["laion_clap", "mert_5120", "muq_mulan_large"]
    predictions = {name: np.sign(margins[name]) for name in singles}
    correctness = {name: accuracy_contributions(margins[name], labels) for name in singles}
    pairwise = {}
    for index, first in enumerate(singles):
        for second in singles[index + 1:]:
            pairwise[f"{first}__vs__{second}"] = int(np.sum(predictions[first] != predictions[second]))
    unique_correct = {
        name: int(np.sum((correctness[name] == 1) & np.logical_and.reduce([
            correctness[other] == 0 for other in singles if other != name
        ]))) for name in singles
    }
    unanimous = np.logical_and.reduce([predictions[name] == predictions[singles[0]] for name in singles[1:]])
    muq_minority = (correctness["muq_mulan_large"] == 1) & (correctness["laion_clap"] == 0) & (correctness["mert_5120"] == 0)
    individual_correct = accuracy_contributions(margins[selected_individual], labels)
    fusion_correct = accuracy_contributions(margins[selected_fusion], labels)
    return {
        "binary_trial_count": len(labels),
        "pairwise_encoder_prediction_disagreement_count": pairwise,
        "unique_correct_count": unique_correct,
        "muq_correct_minority_count": int(muq_minority.sum()),
        "unanimous_prediction_count": int(unanimous.sum()),
        "all_encoders_correct_count": int(np.logical_and.reduce([correctness[name] == 1 for name in singles]).sum()),
        "all_encoders_wrong_count": int(np.logical_and.reduce([correctness[name] == 0 for name in singles]).sum()),
        "selected_fusion_rescues": int(((individual_correct == 0) & (fusion_correct == 1)).sum()),
        "selected_fusion_created_errors": int(((individual_correct == 1) & (fusion_correct == 0)).sum()),
    }


def _engineering_diagnostics(root: Path) -> dict[str, Any]:
    report = root / "reports/holistic_stage1a"
    details = {}
    dimensions = {"laion_clap": 512, "mert_5120": 5120, "muq_mulan_large": 512}
    licenses = {
        "laion_clap": "checkpoint license not recorded in frozen config; verify before distribution",
        "mert_5120": "model license not recorded in frozen config; verify before distribution",
        "muq_mulan_large": "code MIT; frozen Stage 1 contract records weights CC-BY-NC-4.0",
    }
    for name in dimensions:
        summary = json.loads((report / f"{name}_batch_summary.json").read_text(encoding="utf-8"))
        details[name] = {
            "embedding_dimensions": dimensions[name],
            "float32_storage_bytes_per_track": dimensions[name] * 4,
            "clips_per_hour_observed": summary["clips_per_hour"],
            "failed_encodes": summary["failed"],
            "attempted_encodes": summary["attempted"],
            "license_note": licenses[name],
        }
    details["complexity_tiebreak_order"] = [
        "validation-preselected individual", "fewer encoders", "smaller storage", "higher throughput", "canonical encoder order"
    ]
    return details


def choose_verdict(
    protocol_passed: bool,
    test_query_count: int,
    fusion_minus_individual: dict[str, Any],
    individual_minus_fusions: dict[str, dict[str, Any]],
    threshold: float,
) -> str:
    if not protocol_passed or test_query_count != 16:
        return "INSUFFICIENT_HUMAN_EVIDENCE"
    if fusion_minus_individual["estimate"] >= threshold and fusion_minus_individual["ci_95"][0] > 0:
        return "FUSION_WINS"
    every_material = all(
        result["estimate"] >= threshold and result["ci_95"][0] > 0
        for result in individual_minus_fusions.values()
    )
    every_degrades = all(result["estimate"] > 0 for result in individual_minus_fusions.values())
    if every_material or every_degrades:
        return "SINGLE_ENCODER_WINS"
    return "STATISTICALLY_EQUIVALENT_PICK_SIMPLER"


def ensure_outputs_absent(paths: list[Path]) -> None:
    existing = [path.name for path in paths if path.exists()]
    if existing:
        raise TestLockError(f"final TEST output already exists ({', '.join(existing)}); refusing overwrite")


def run_locked_test(config_path: str | Path, root: str | Path = ".") -> dict[str, Any]:
    root, config_path = Path(root).resolve(), Path(config_path).resolve()
    lock = verify_test_lock(config_path, root, allow_existing=False)
    config, selection = load_contract(config_path), lock["selection"]
    report_dir = root / config["paths"]["report_dir"]
    validation = json.loads((report_dir / "rating_validation.json").read_text(encoding="utf-8"))
    test_labels_path = report_dir / "canonical_labels_test.csv"
    if sha256_file(test_labels_path) != validation["canonical_output_sha256"]["canonical_labels_test"]:
        raise TestLockError("TEST canonical-label hash mismatch")
    labels_frame = pd.read_csv(test_labels_path, dtype=str).fillna("")
    keys = json.loads((report_dir / "trial_keys.json").read_text(encoding="utf-8"))["trials"]
    if any(keys.get(trial_id, {}).get("split") != "TEST" for trial_id in labels_frame["trial_id"]):
        raise TestLockError("non-TEST label entered TEST reveal")
    binary_labels = labels_frame[labels_frame["choice"].isin(["A", "B"])].set_index("trial_id")["choice"].map({"A": 1, "B": 0})
    dataset = pd.read_csv(report_dir / "fusion_dataset.csv")
    test = dataset[dataset["trial_id"].isin(binary_labels.index)].copy()
    if set(test["trial_id"]) != set(binary_labels.index):
        raise ContractError("TEST feature/label coverage mismatch")
    test["label"] = test["trial_id"].map(binary_labels).astype(int)
    feature_order = tuple(FEATURES)
    matrix = test[[FEATURES[name] for name in feature_order]].to_numpy(dtype=np.float64)
    labels = test["label"].to_numpy(dtype=np.int64)
    queries = test["query_id"].to_numpy(dtype=np.int64)
    sources = test["source_pair"].to_numpy(dtype=str)
    index_by_name = {name: index for index, name in enumerate(feature_order)}

    margins: dict[str, np.ndarray] = {}
    fitted_names: set[str] = set()
    for name in feature_order:
        margins[name] = matrix[:, index_by_name[name]]
    for name, result in selection["fusion_results"].items():
        indices = [index_by_name[value] for value in result["representation_set"]]
        standardized = (matrix[:, indices] - np.asarray(result["scaler_mean"])) / np.asarray(result["scaler_scale"])
        margins[name] = standardized @ np.asarray(result["coefficients"])
        fitted_names.add(name)
    equal = selection["equal_weight_three_encoder_diagnostic"]
    margins["equal_weight_three_encoder"] = (
        (matrix - np.asarray(equal["scaler_mean"])) / np.asarray(equal["scaler_scale"])
    ).mean(axis=1)

    model_metrics = {
        name: _model_metrics(value, labels, queries, sources, name in fitted_names)
        for name, value in margins.items()
    }
    draws = int(config["uncertainty"]["paired_query_bootstrap_draws"])
    model_bootstrap = {
        name: paired_query_bootstrap(metrics["per_query_accuracy"], None, draws, int(config["seed"]) + index)
        for index, (name, metrics) in enumerate(model_metrics.items())
    }
    selected_individual, selected_fusion = selection["selected_individual"], selection["selected_fusion"]
    headline_difference = paired_query_bootstrap(
        model_metrics[selected_fusion]["per_query_accuracy"],
        model_metrics[selected_individual]["per_query_accuracy"], draws, int(config["seed"]) + 100,
    )
    individual_vs_fusions = {}
    for index, fusion_name in enumerate(selection["fusion_results"]):
        individual_vs_fusions[fusion_name] = paired_query_bootstrap(
            model_metrics[selected_individual]["per_query_accuracy"],
            model_metrics[fusion_name]["per_query_accuracy"], draws, int(config["seed"]) + 200 + index,
        )

    selected_subset = selection["fusion_results"][selected_fusion]["representation_set"]
    subset_indices = [index_by_name[name] for name in selected_subset]
    train, _, _ = load_train_validation_rows(
        report_dir / "fusion_dataset.csv", report_dir / "canonical_labels_train_validation.csv",
        report_dir / "trial_keys.json", report_dir / "rating_validation.json",
    )
    stability = _coefficient_stability(
        train.feature_matrix, train.labels, train.query_ids, subset_indices, selection,
        int(config["uncertainty"]["coefficient_query_bootstrap_refits"]), int(config["seed"]) + 300,
    )
    complementarity = _complementarity(margins, labels, selected_individual, selected_fusion)

    all_canonical = pd.read_csv(report_dir / "canonical_labels.csv", dtype=str)
    coverage = {
        "primary_trials": len(all_canonical),
        "binary_trials": int(all_canonical["choice"].isin(["A", "B"]).sum()),
        "tie_trials": int((all_canonical["choice"] == "Tie").sum()),
        "neither_trials": int((all_canonical["choice"] == "Neither").sum()),
        "tie_rate": float((all_canonical["choice"] == "Tie").mean()),
        "neither_rate": float((all_canonical["choice"] == "Neither").mean()),
        "no_majority_rate": 0.0,
        "test_binary_trials": len(test),
        "test_queries_with_binary_trials": len(set(queries.tolist())),
        "designated_reviewer_count": int(all_canonical["rater_id"].nunique()),
        "inter_rater_agreement": "not applicable under single_reviewer_v2",
    }

    verdict = choose_verdict(
        bool(validation.get("protocol_passed")), coverage["test_queries_with_binary_trials"],
        headline_difference, individual_vs_fusions,
        float(config["verdict"]["fusion_min_improvement"]),
    )
    selected_representation = (
        None if verdict == "INSUFFICIENT_HUMAN_EVIDENCE"
        else selected_fusion if verdict == "FUSION_WINS"
        else selected_individual
    )

    result = {
        "experiment_id": config["experiment_id"],
        "protocol_version": config["protocol_version"],
        "claim_scope": config["verdict"]["claim_scope"],
        "population_claim_permitted": False,
        "selection_checkpoint": {
            "commit": lock["head"], "upstream": lock["upstream"], "model_selection_sha256": lock["selection_sha256"]
        },
        "test_label_sha256": sha256_file(test_labels_path),
        "test_evaluation_code_sha256": sha256_file(Path(__file__)),
        "preselected_individual": selected_individual,
        "preselected_fusion": selected_fusion,
        "model_metrics": model_metrics,
        "model_query_bootstrap": model_bootstrap,
        "headline_fusion_minus_individual": headline_difference,
        "individual_minus_each_fusion": individual_vs_fusions,
        "coefficient_stability_diagnostic": stability,
        "complementarity": complementarity,
        "coverage_and_ambiguity": coverage,
        "engineering_diagnostics": _engineering_diagnostics(root),
        "verdict": verdict,
        "selected_representation": selected_representation,
    }

    metrics_path = report_dir / "test_metrics.json"
    report_path = report_dir / "decision_report.md"
    receipt_path = report_dir / "test_reveal_receipt.json"
    ensure_outputs_absent([metrics_path, report_path, receipt_path])
    metrics_tmp = metrics_path.with_suffix(".json.tmp")
    report_tmp = report_path.with_suffix(".md.tmp")
    receipt_tmp = receipt_path.with_suffix(".json.tmp")
    metrics_tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_tmp.write_text(_decision_report(result), encoding="utf-8")
    receipt = {
        "revealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_commit": lock["head"],
        "selection_artifact_sha256": lock["selection_sha256"],
        "test_labels_sha256": result["test_label_sha256"],
        "test_metrics_sha256": sha256_file(metrics_tmp),
        "test_evaluation_code_sha256": result["test_evaluation_code_sha256"],
        "one_time_reveal": True,
    }
    receipt_tmp.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    metrics_tmp.replace(metrics_path)
    report_tmp.replace(report_path)
    receipt_tmp.replace(receipt_path)
    return result


def _decision_report(result: dict[str, Any]) -> str:
    individual = result["preselected_individual"]
    fusion = result["preselected_fusion"]
    individual_metrics = result["model_metrics"][individual]
    fusion_metrics = result["model_metrics"][fusion]
    difference = result["headline_fusion_minus_individual"]
    stability = result["coefficient_stability_diagnostic"]
    complementarity = result["complementarity"]
    coverage = result["coverage_and_ambiguity"]
    return f"""# Stage 2B Balanced Holistic Encoder Fusion Decision\n\n## Claim boundary\n\n**This is a single-reviewer personal perceptual-alignment benchmark.** It does not establish general human consensus, population-level superiority, or inter-rater reliability. Bootstrap intervals describe variation across frozen queries for the designated reviewer's judgments.\n\n## Frozen comparison\n\n- Validation-preselected individual: `{individual}`\n- Validation-preselected fusion: `{fusion}`\n- TEST query-macro accuracy, individual: {individual_metrics['query_macro_accuracy']:.4f}\n- TEST query-macro accuracy, fusion: {fusion_metrics['query_macro_accuracy']:.4f}\n- Fusion minus individual: {difference['estimate']:.4f}\n- Paired 95% query-bootstrap CI: [{difference['ci_95'][0]:.4f}, {difference['ci_95'][1]:.4f}] ({difference['draws']:,} draws)\n\n## Evidence quality\n\n- Primary trials: {coverage['primary_trials']}\n- Binary A/B trials: {coverage['binary_trials']}\n- TEST binary trials / represented queries: {coverage['test_binary_trials']} / {coverage['test_queries_with_binary_trials']}\n- Tie rate: {coverage['tie_rate']:.3f}\n- Neither rate: {coverage['neither_rate']:.3f}\n- Inter-rater agreement: not applicable under `single_reviewer_v2`\n\n## Coefficient stability and complementarity\n\n- Coefficient 95% intervals: `{stability['percentile_interval_95']}`\n- Coefficient sign retention: `{stability['sign_retention_frequency']}`\n- Fusion rescues: {complementarity['selected_fusion_rescues']}\n- Fusion-created errors: {complementarity['selected_fusion_created_errors']}\n- MuQ correct-minority cases: {complementarity['muq_correct_minority_count']}\n\nFull per-model, per-query, per-source, bootstrap, redundancy, engineering, and complementarity diagnostics are frozen in `test_metrics.json`.\n\n## Final verdict\n\n`{result['verdict']}`\n\nSelected Stage 2B representation: `{result['selected_representation']}`. This is the only Stage 2B verdict. No MIR/MERIT fusion, full-song sampling, Spotify acquisition, or application integration was started.\n"""
