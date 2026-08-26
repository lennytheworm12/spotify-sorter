"""TRAIN/VALIDATION-only Stage 2B fusion model selection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from .stage2b_contract import ContractError, load_contract, sha256_file
from .stage2b_metrics import binary_log_loss, query_macro_accuracy

FEATURES = {
    "laion_clap": "delta_clap",
    "mert_5120": "delta_mert",
    "muq_mulan_large": "delta_muq",
}
SINGLES = (("laion_clap",), ("mert_5120",), ("muq_mulan_large",))
FUSIONS = (
    ("laion_clap", "mert_5120"),
    ("laion_clap", "muq_mulan_large"),
    ("mert_5120", "muq_mulan_large"),
    ("laion_clap", "mert_5120", "muq_mulan_large"),
)


@dataclass(frozen=True)
class SelectionRows:
    frame: pd.DataFrame
    feature_matrix: np.ndarray
    labels: np.ndarray
    query_ids: np.ndarray


def _subset_name(subset: tuple[str, ...]) -> str:
    return "+".join(subset)


def _split_rows(frame: pd.DataFrame, split: str) -> SelectionRows:
    selected = frame[frame["split"] == split].copy()
    if selected.empty:
        raise ContractError(f"no binary rows for {split}")
    matrix = selected[[FEATURES[name] for name in FEATURES]].to_numpy(dtype=np.float64)
    labels = selected["selection_label"].to_numpy(dtype=np.int64)
    queries = selected["query_id"].to_numpy(dtype=np.int64)
    if not np.isfinite(matrix).all():
        raise ContractError("non-finite selection features")
    return SelectionRows(selected, matrix, labels, queries)


def load_train_validation_rows(
    dataset_path: str | Path,
    ratings_path: str | Path,
    trial_keys_path: str | Path,
    rating_validation_path: str | Path,
) -> tuple[SelectionRows, SelectionRows, dict[str, Any]]:
    dataset_path, ratings_path = Path(dataset_path), Path(ratings_path)
    keys = json.loads(Path(trial_keys_path).read_text(encoding="utf-8"))["trials"]
    validation = json.loads(Path(rating_validation_path).read_text(encoding="utf-8"))
    expected_hash = validation["canonical_output_sha256"]["canonical_labels_train_validation"]
    if sha256_file(ratings_path) != expected_hash:
        raise ContractError("selection accepts only the frozen TRAIN/VALIDATION canonical-label export")
    ratings = pd.read_csv(ratings_path, dtype=str).fillna("")
    if ratings["trial_id"].duplicated().any():
        raise ContractError("duplicate canonical selection trial")
    if any(keys.get(trial_id, {}).get("split") == "TEST" for trial_id in ratings["trial_id"]):
        raise ContractError("TEST trial/label supplied to model selection")
    if any(keys.get(trial_id, {}).get("split") not in {"TRAIN", "VALIDATION"} for trial_id in ratings["trial_id"]):
        raise ContractError("unknown/non-selection trial supplied")

    binary = ratings[ratings["choice"].isin(["A", "B"])].copy()
    labels = binary.set_index("trial_id")["choice"].map({"A": 1, "B": 0})
    dataset = pd.read_csv(dataset_path)
    # Label and choice columns in the full provenance dataset are deliberately
    # ignored. Only the hash-locked split-safe ratings export supplies targets.
    selected = dataset[dataset["trial_id"].isin(labels.index)].copy()
    if set(selected["trial_id"]) != set(labels.index):
        raise ContractError("selection feature/label coverage mismatch")
    selected["selection_label"] = selected["trial_id"].map(labels).astype(int)
    selected["split"] = selected["trial_id"].map(lambda trial_id: keys[trial_id]["split"])
    if set(selected["split"]) - {"TRAIN", "VALIDATION"}:
        raise ContractError("TEST feature row entered model selection")
    train, validation_rows = _split_rows(selected, "TRAIN"), _split_rows(selected, "VALIDATION")
    provenance = {
        "ratings_sha256": sha256_file(ratings_path),
        "dataset_sha256": sha256_file(dataset_path),
        "trial_keys_sha256": sha256_file(trial_keys_path),
        "rating_validation_sha256": sha256_file(rating_validation_path),
    }
    return train, validation_rows, provenance


def _scaler(train_matrix: np.ndarray, indices: list[int]) -> tuple[np.ndarray, np.ndarray]:
    subset = train_matrix[:, indices]
    mean = subset.mean(axis=0)
    scale = subset.std(axis=0, ddof=0)
    if not np.isfinite(mean).all() or not np.isfinite(scale).all() or np.any(scale <= 0):
        raise ContractError("zero-variance/non-finite TRAIN feature")
    return mean, scale


def _sigmoid(margins: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(margins, dtype=np.float64), -700, 700)
    return 1.0 / (1.0 + np.exp(-clipped))


def _metrics(margins: np.ndarray, rows: SelectionRows, fitted: bool) -> dict[str, Any]:
    result = query_macro_accuracy(margins, rows.labels, rows.query_ids)
    if fitted:
        result["log_loss"] = binary_log_loss(_sigmoid(margins), rows.labels)
    result["binary_row_count"] = len(rows.labels)
    result["query_count"] = len(set(rows.query_ids.tolist()))
    return result


def run_model_selection(config_path: str | Path, root: str | Path = ".", ratings_path: str | Path | None = None) -> dict[str, Any]:
    root, config_path = Path(root), Path(config_path)
    config = load_contract(config_path)
    if config.get("protocol_version") != "single_reviewer_v2":
        raise ContractError("selection requires approved single_reviewer_v2")
    report_dir = root / config["paths"]["report_dir"]
    ratings_path = Path(ratings_path) if ratings_path else report_dir / "canonical_labels_train_validation.csv"
    train, validation_rows, provenance = load_train_validation_rows(
        report_dir / "fusion_dataset.csv", ratings_path,
        report_dir / "trial_keys.json", report_dir / "rating_validation.json",
    )
    feature_names = tuple(FEATURES)
    index_by_name = {name: index for index, name in enumerate(feature_names)}
    single_results: dict[str, Any] = {}
    for subset in SINGLES:
        index = index_by_name[subset[0]]
        single_results[_subset_name(subset)] = {
            "representation_set": list(subset),
            "model": "native_cosine_margin_unscaled_unsupervised",
            "train_metrics": _metrics(train.feature_matrix[:, index], train, False),
            "validation_metrics": _metrics(validation_rows.feature_matrix[:, index], validation_rows, False),
        }
    selected_individual_name = sorted(
        single_results,
        key=lambda name: (-single_results[name]["validation_metrics"]["query_macro_accuracy"], list(single_results).index(name)),
    )[0]

    c_grid = [float(value) for value in config["selection"]["fusion_model"]["C_grid"]]
    c_tie = float(config["selection"]["C_practical_tie"])
    fusion_results: dict[str, Any] = {}
    for subset in FUSIONS:
        indices = [index_by_name[name] for name in subset]
        mean, scale = _scaler(train.feature_matrix, indices)
        x_train = (train.feature_matrix[:, indices] - mean) / scale
        x_validation = (validation_rows.feature_matrix[:, indices] - mean) / scale
        candidates = []
        for c_value in c_grid:
            model = LogisticRegression(
                C=c_value, penalty="l2", solver="lbfgs", fit_intercept=False,
                random_state=int(config["seed"]), max_iter=10000, tol=1e-8,
            )
            model.fit(x_train, train.labels)
            if model.intercept_.shape != (1,) or float(model.intercept_[0]) != 0.0:
                raise ContractError("fusion model unexpectedly fitted an intercept")
            coefficients = model.coef_[0].astype(np.float64)
            train_margin = x_train @ coefficients
            validation_margin = x_validation @ coefficients
            candidates.append({
                "C": c_value,
                "coefficients": coefficients.tolist(),
                "train_metrics": _metrics(train_margin, train, True),
                "validation_metrics": _metrics(validation_margin, validation_rows, True),
                "n_iter": int(model.n_iter_[0]),
            })
        best_accuracy = max(row["validation_metrics"]["query_macro_accuracy"] for row in candidates)
        practically_tied = [
            row for row in candidates
            if row["validation_metrics"]["query_macro_accuracy"] >= best_accuracy - c_tie
        ]
        selected = min(practically_tied, key=lambda row: (row["validation_metrics"]["log_loss"], row["C"]))
        fusion_results[_subset_name(subset)] = {
            "representation_set": list(subset),
            "scaler_mean": mean.tolist(),
            "scaler_scale": scale.tolist(),
            "C_candidates": candidates,
            "selected_C": selected["C"],
            "coefficients": selected["coefficients"],
            "train_metrics": selected["train_metrics"],
            "validation_metrics": selected["validation_metrics"],
        }

    top_fusion_accuracy = max(row["validation_metrics"]["query_macro_accuracy"] for row in fusion_results.values())
    subset_tie = float(config["selection"]["fusion_subset_practical_tie"])
    equivalent_names = [
        name for name, row in fusion_results.items()
        if row["validation_metrics"]["query_macro_accuracy"] >= top_fusion_accuracy - subset_tie
    ]
    canonical_order = list(fusion_results)
    selected_fusion_name = min(equivalent_names, key=lambda name: (
        len(fusion_results[name]["representation_set"]),
        fusion_results[name]["validation_metrics"]["log_loss"],
        canonical_order.index(name),
    ))

    all_indices = [0, 1, 2]
    eq_mean, eq_scale = _scaler(train.feature_matrix, all_indices)
    equal_train = ((train.feature_matrix - eq_mean) / eq_scale).mean(axis=1)
    equal_validation = ((validation_rows.feature_matrix - eq_mean) / eq_scale).mean(axis=1)
    equal_weight = {
        "diagnostic_only": True,
        "scaler_mean": eq_mean.tolist(),
        "scaler_scale": eq_scale.tolist(),
        "train_metrics": _metrics(equal_train, train, False),
        "validation_metrics": _metrics(equal_validation, validation_rows, False),
    }

    trial_keys = json.loads((report_dir / "trial_keys.json").read_text(encoding="utf-8"))["trials"]
    test_identities = "\n".join(sorted(trial_id for trial_id, row in trial_keys.items() if row["split"] == "TEST"))
    selected_fusion = fusion_results[selected_fusion_name]
    artifact = {
        "experiment_id": config["experiment_id"],
        "protocol_version": config["protocol_version"],
        "claim_scope": config["verdict"]["claim_scope"],
        "selection_splits": ["TRAIN", "VALIDATION"],
        "test_labels_accessed": False,
        "config_sha256": sha256_file(config_path),
        "source_hashes": provenance,
        "selection_code_sha256": sha256_file(Path(__file__)),
        "frozen_test_trial_identities_sha256": hashlib.sha256(test_identities.encode()).hexdigest(),
        "frozen_test_trial_count": sum(row["split"] == "TEST" for row in trial_keys.values()),
        "selected_individual": selected_individual_name,
        "selected_fusion": selected_fusion_name,
        "selected_fusion_C": selected_fusion["selected_C"],
        "selected_fusion_scaler_mean": selected_fusion["scaler_mean"],
        "selected_fusion_scaler_scale": selected_fusion["scaler_scale"],
        "selected_fusion_coefficients": selected_fusion["coefficients"],
        "single_results": single_results,
        "fusion_results": fusion_results,
        "equal_weight_three_encoder_diagnostic": equal_weight,
    }
    output = report_dir / "model_selection.json"
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact
