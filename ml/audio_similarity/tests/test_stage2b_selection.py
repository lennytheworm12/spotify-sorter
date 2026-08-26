from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from audio_similarity.stage2b_contract import ContractError
from audio_similarity.stage2b_metrics import accuracy_contributions, query_macro_accuracy
from audio_similarity.stage2b_selection import (
    FUSIONS,
    SINGLES,
    load_train_validation_rows,
    run_model_selection,
)

ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/holistic_stage2b_fusion_single_reviewer.yaml"
REPORT = ROOT / "reports/holistic_stage2b"


def test_zero_margin_gets_half_credit_and_query_macro_weights_queries_equally():
    margins = np.array([1.0, 0.0, -1.0, 1.0])
    labels = np.array([1, 0, 1, 0])
    queries = np.array([1, 1, 1, 2])
    np.testing.assert_array_equal(accuracy_contributions(margins, labels), [1.0, 0.5, 0.0, 0.0])
    result = query_macro_accuracy(margins, labels, queries)
    assert result["per_query_accuracy"] == {"1": 0.5, "2": 0.0}
    assert result["query_macro_accuracy"] == 0.25


def test_selection_rejects_test_labels():
    with pytest.raises(ContractError, match="TRAIN/VALIDATION"):
        load_train_validation_rows(
            REPORT / "fusion_dataset.csv", REPORT / "canonical_labels_test.csv",
            REPORT / "trial_keys.json", REPORT / "rating_validation.json",
        )


def test_test_feature_and_label_columns_have_zero_selection_influence(tmp_path):
    original = REPORT / "fusion_dataset.csv"
    changed = pd.read_csv(original)
    mask = changed["split"] == "TEST"
    changed.loc[mask, ["delta_clap", "delta_mert", "delta_muq"]] = 1e12
    changed.loc[mask, "choice"] = "B"
    changed.loc[mask, "binary_label_a_wins"] = 0
    modified = tmp_path / "dataset.csv"
    changed.to_csv(modified, index=False)
    args = (
        REPORT / "canonical_labels_train_validation.csv",
        REPORT / "trial_keys.json",
        REPORT / "rating_validation.json",
    )
    train_a, validation_a, _ = load_train_validation_rows(original, *args)
    train_b, validation_b, _ = load_train_validation_rows(modified, *args)
    np.testing.assert_array_equal(train_a.feature_matrix, train_b.feature_matrix)
    np.testing.assert_array_equal(validation_a.feature_matrix, validation_b.feature_matrix)
    np.testing.assert_array_equal(train_a.labels, train_b.labels)
    np.testing.assert_array_equal(validation_a.labels, validation_b.labels)


def test_real_selection_is_deterministic_train_scaled_no_intercept_and_exact_ablations():
    first = run_model_selection(CONFIG, ROOT)
    first_bytes = (REPORT / "model_selection.json").read_bytes()
    second = run_model_selection(CONFIG, ROOT)
    assert first == second
    assert (REPORT / "model_selection.json").read_bytes() == first_bytes
    assert first["test_labels_accessed"] is False
    assert set(first["single_results"]) == {"+".join(value) for value in SINGLES}
    assert set(first["fusion_results"]) == {"+".join(value) for value in FUSIONS}
    expected_grid = [0.01, 0.1, 1.0, 10.0, 100.0]
    dataset = pd.read_csv(REPORT / "fusion_dataset.csv")
    tv_labels = pd.read_csv(REPORT / "canonical_labels_train_validation.csv")
    binary_ids = set(tv_labels[tv_labels["choice"].isin(["A", "B"])]["trial_id"])
    train = dataset[(dataset["trial_id"].isin(binary_ids)) & (dataset["split"] == "TRAIN")]
    mapping = {"laion_clap": "delta_clap", "mert_5120": "delta_mert", "muq_mulan_large": "delta_muq"}
    for result in first["fusion_results"].values():
        assert [row["C"] for row in result["C_candidates"]] == expected_grid
        columns = [mapping[name] for name in result["representation_set"]]
        np.testing.assert_allclose(result["scaler_mean"], train[columns].mean(axis=0), rtol=0, atol=1e-15)
        np.testing.assert_allclose(result["scaler_scale"], train[columns].std(axis=0, ddof=0), rtol=0, atol=1e-15)
        assert len(result["coefficients"]) == len(columns)
        assert all(np.isfinite(result["coefficients"]))
    payload = json.loads(first_bytes)
    assert "test_metrics" not in payload
    assert payload["equal_weight_three_encoder_diagnostic"]["diagnostic_only"] is True
