import json
from pathlib import Path

import pandas as pd

from audio_similarity.stage4a_dual_closeout import (
    build_closeout,
    sha256,
    validate_ratings,
)
from audio_similarity.stage4a_dual_metrics import summarize

ROOT = Path(__file__).resolve().parents[1]


def fixture(tmp_path, choices):
    pairs = [
        ("CENTER5_DUAL", "UNIFORM3_DUAL_MEAN"),
        ("UNIFORM3_DUAL_MEAN", "UNIFORM5_DUAL_MEAN"),
        ("CENTER5_DUAL", "UNIFORM5_DUAL_MEAN"),
    ]
    keys = {}
    rows = []
    for query in range(2):
        for index, (method_x, method_y) in enumerate(pairs):
            trial = f"d{query}{index}"
            keys[trial] = {
                "query_id": query,
                "candidate_a": 10,
                "candidate_b": 11,
                "method_x": method_x,
                "method_y": method_y,
                "method_x_candidate": 10,
                "method_y_candidate": 11,
            }
            rows.append(
                {
                    "event_id": trial,
                    "trial_id": trial,
                    "reviewer_id": "lenny",
                    "choice": choices[index],
                    "submitted_at": str(len(rows) + 1),
                    "supersedes_event_id": "",
                }
            )
    keys_path = tmp_path / "keys.json"
    keys_path.write_text(json.dumps({"trials": keys}))
    ratings_path = tmp_path / "ratings.csv"
    pd.DataFrame(rows).to_csv(ratings_path, index=False)
    trials_path = tmp_path / "trials.csv"
    pd.DataFrame({"trial_id": list(keys)}).to_csv(trials_path, index=False)
    return ratings_path, keys_path, trials_path


def test_dual_metrics_never_include_superseded_denominator(tmp_path):
    ratings_path, keys_path, _ = fixture(tmp_path, ["Tie", "Neither", "A"])
    result = summarize(ratings_path, keys_path, 100, 7, 6)
    assert not result["superseded_clap_only_ratings_included"]
    assert (
        result["method_pairs"]["UNIFORM3_vs_CENTER5"][
            "higher_pairwise_preference"
        ]
        == 0.5
    )
    assert (
        result["method_pairs"]["UNIFORM5_vs_UNIFORM3"][
            "preference_denominator"
        ]
        == 0
    )


def test_dual_higher_k_path(tmp_path):
    ratings_path, keys_path, _ = fixture(tmp_path, ["B", "B", "B"])
    result = summarize(ratings_path, keys_path, 100, 7, 6)
    assert result["verdict"] == "UNIFORM5_DUAL_WINS"
    assert result["stage4b_triggered"]


def test_validation_surfaces_missing_trials_and_preserves_supersession(tmp_path):
    ratings_path, keys_path, trials_path = fixture(tmp_path, ["B", "B", "B"])
    ratings = pd.read_csv(ratings_path, dtype=str).fillna("")
    ratings = ratings[ratings.trial_id != "d11"]
    prior = ratings[ratings.trial_id == "d00"].iloc[-1]
    correction = {
        "event_id": "correction",
        "trial_id": "d00",
        "reviewer_id": "lenny",
        "choice": "Tie",
        "submitted_at": "99",
        "supersedes_event_id": prior.event_id,
    }
    ratings = pd.concat([ratings, pd.DataFrame([correction])], ignore_index=True)
    ratings.to_csv(ratings_path, index=False)

    result = validate_ratings(
        ratings_path, keys_path, trials_path, required=6
    )

    assert result["status"] == "PROTOCOL_FAILURE"
    assert not result["all_expected_trials_represented"]
    assert result["missing_trial_ids"] == ["d11"]
    assert result["latest_designated_reviewer_outcomes"] == 5
    assert result["supersession_violations"] == []
    assert result["blocking_data_problems"] == []


def test_validation_surfaces_invalid_response(tmp_path):
    ratings_path, keys_path, trials_path = fixture(tmp_path, ["B", "B", "B"])
    ratings = pd.read_csv(ratings_path, dtype=str).fillna("")
    ratings.loc[0, "choice"] = "Skip"
    ratings.to_csv(ratings_path, index=False)

    result = validate_ratings(
        ratings_path, keys_path, trials_path, required=6
    )

    assert result["status"] == "PROTOCOL_FAILURE"
    assert result["invalid_response_rows"] == [2]
    assert result["blocking_data_problems"] == ["INVALID_RESPONSE"]


def test_frozen_stage4a_closeout_recomputes_exactly():
    report_dir = ROOT / "reports/holistic_stage4a_dual"
    expected_metrics = json.loads((report_dir / "final_metrics.json").read_text())
    expected_closeout = json.loads(
        (report_dir / "audio_representation_v1.json").read_text()
    )

    actual_metrics, actual_closeout = build_closeout(ROOT)

    assert actual_metrics == expected_metrics
    assert actual_closeout == expected_closeout
    frozen = actual_closeout["frozen_experimental_result"]
    validation = frozen["ratings_validation"]
    assert validation["frozen_trial_keys"] == 240
    assert validation["latest_designated_reviewer_outcomes"] == 238
    assert validation["missing_trial_ids"] == [
        "s4d_06b09666b6f5f181e38c",
        "s4d_5c4384de67dff3a784ac",
    ]
    assert actual_metrics["protocol_failure"]
    assert actual_metrics["verdict"] == "INSUFFICIENT_EVIDENCE_PICK_CHEAPER"
    assert frozen["verdict"] == "INSUFFICIENT_EVIDENCE_PICK_CHEAPER"
    assert not actual_metrics["stage4b_triggered"]
    assert sha256(report_dir / "final_metrics.json") == (
        "db16e90134b2388159a65cb24c3fe1a6c92112544ca02449b6b569905642c030"
    )

    temporal = actual_closeout["temporal_sampling"]
    assert temporal["selected_method"] == "UNIFORM3_DUAL_MEAN"
    assert temporal["selected_k"] == 3
    assert temporal["segment_centers_seconds"] == [5, 15, 25]
    decision = actual_closeout["engineering_product_decision"]
    assert decision["overrides_protocol_fallback_for_engineering"]
    assert not decision["rewrites_frozen_experimental_verdict"]

    sensitivity = actual_closeout["post_experiment_sensitivity_analysis"]
    assert not sensitivity["ratings_imputed"]
    assert not sensitivity["k5_vs_k3_missing_judgment"][
        "can_make_k5_materially_superior"
    ]
    k3_scenarios = sensitivity["k3_vs_k1_missing_judgment"]["scenarios"]
    assert k3_scenarios["K3_win"]["k3_remains_material"]
    assert k3_scenarios["Tie"]["k3_remains_material"]
    assert k3_scenarios["Neither"]["k3_remains_material"]
    assert not k3_scenarios["K1_win"]["k3_remains_material"]
    assert (
        k3_scenarios["K1_win"][
            "lower_confidence_bound_at_decision_precision"
        ]
        == 0.5000
    )

    comparisons = frozen["comparisons"]
    k3_vs_k1 = comparisons["UNIFORM3_vs_CENTER5"]
    assert k3_vs_k1["usable_judgments"] == 73
    assert round(k3_vs_k1["query_macro_preference_for_higher_cost"], 4) == 0.6027
    assert [round(value, 4) for value in k3_vs_k1["query_bootstrap_95_ci"]] == [
        0.5068,
        0.6986,
    ]
    assert round(k3_vs_k1["improvement_over_cheaper"], 4) == 0.1027
    assert k3_vs_k1["satisfies_material_improvement_rule"]

    k5_vs_k1 = comparisons["UNIFORM5_vs_CENTER5"]
    assert k5_vs_k1["usable_judgments"] == 72
    assert k5_vs_k1["query_macro_preference_for_higher_cost"] == 0.5
    assert not k5_vs_k1["satisfies_material_improvement_rule"]

    k5_vs_k3 = comparisons["UNIFORM5_vs_UNIFORM3"]
    assert k5_vs_k3["usable_judgments"] == 75
    assert round(k5_vs_k3["query_macro_preference_for_higher_cost"], 4) == 0.5733
    assert not k5_vs_k3["satisfies_material_improvement_rule"]

    assert actual_closeout["fusion"]["clap_weight"] == 0.7172981519
    assert actual_closeout["fusion"]["muq_weight"] == 0.2827018481
    assert not actual_closeout["fusion"]["stage4a_refit_weights"]
    assert actual_closeout["claim_boundary"][
        "stage2b_scientific_conclusion"
    ] == "SINGLE_ENCODER_WINS / CLAP"
    assert not actual_closeout["stage4b_triggered"]
