"""Validate ratings and assemble the Stage 4A Audio Representation v1 closeout."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import yaml

from . import stage4a_dual_metrics as frozen_metrics

CHOICES = {"A", "B", "Tie", "Neither"}
COLUMNS = [
    "event_id",
    "trial_id",
    "reviewer_id",
    "choice",
    "submitted_at",
    "supersedes_event_id",
]
PAIR_LABELS = {
    "UNIFORM3_vs_CENTER5": "K=3 vs K=1",
    "UNIFORM5_vs_CENTER5": "K=5 vs K=1",
    "UNIFORM5_vs_UNIFORM3": "K=5 vs K=3",
}
VERDICT_METHODS = {
    "CENTER5_DUAL_SUFFICIENT": "CENTER5_DUAL",
    "UNIFORM3_DUAL_WINS": "UNIFORM3_DUAL_MEAN",
    "UNIFORM5_DUAL_WINS": "UNIFORM5_DUAL_MEAN",
    "INSUFFICIENT_EVIDENCE_PICK_CHEAPER": "CENTER5_DUAL",
}


class CloseoutError(ValueError):
    """Raised when corrupt inputs make the frozen metrics unsafe to run."""


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_trial_keys(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text())
    trials = payload.get("trials")
    if not isinstance(trials, dict):
        raise CloseoutError("trial-keys artifact has no trials object")
    return trials


def validate_ratings(
    ratings_path: str | Path,
    keys_path: str | Path,
    trials_path: str | Path,
    designated_reviewer: str = "lenny",
    required: int = 240,
) -> dict:
    """Validate append-only events without repairing missing trial outcomes."""
    ratings = pd.read_csv(ratings_path, dtype=str).fillna("")
    missing_columns = [name for name in COLUMNS if name not in ratings]
    if missing_columns:
        raise CloseoutError(f"ratings missing columns: {missing_columns}")
    ratings = ratings[COLUMNS]
    keys = _load_trial_keys(keys_path)
    public = pd.read_csv(trials_path, dtype=str).fillna("")
    if "trial_id" not in public:
        raise CloseoutError("public trials artifact has no trial_id column")

    frozen_ids = set(keys)
    public_ids = set(public.trial_id)
    reviewer = designated_reviewer.casefold()
    designated = ratings[ratings.reviewer_id.str.casefold() == reviewer]
    latest = designated.drop_duplicates("trial_id", keep="last")
    rated_ids = set(latest.trial_id)

    invalid_choice_rows = [
        int(index) + 2
        for index, choice in ratings.choice.items()
        if choice not in CHOICES
    ]
    unknown_trial_ids = sorted(set(ratings.trial_id) - frozen_ids)
    duplicate_event_ids = sorted(
        ratings.loc[ratings.event_id.duplicated(keep=False), "event_id"].unique()
    )
    blank_event_rows = [
        int(index) + 2 for index, value in ratings.event_id.items() if not value
    ]
    invalid_timestamp_rows = []
    for index, value in ratings.submitted_at.items():
        try:
            int(value)
        except ValueError:
            invalid_timestamp_rows.append(int(index) + 2)

    supersession_violations = []
    previous_event_by_trial: dict[str, str] = {}
    for index, row in ratings.iterrows():
        expected = previous_event_by_trial.get(row.trial_id, "")
        if row.supersedes_event_id != expected:
            supersession_violations.append(
                {
                    "row": int(index) + 2,
                    "trial_id": row.trial_id,
                    "actual": row.supersedes_event_id,
                    "expected": expected,
                }
            )
        previous_event_by_trial[row.trial_id] = row.event_id

    blocking_problems = []
    if invalid_choice_rows:
        blocking_problems.append("INVALID_RESPONSE")
    if unknown_trial_ids:
        blocking_problems.append("UNKNOWN_TRIAL_ID")
    if duplicate_event_ids or blank_event_rows:
        blocking_problems.append("INVALID_EVENT_ID")
    if invalid_timestamp_rows:
        blocking_problems.append("INVALID_SUBMISSION_TIMESTAMP")
    if supersession_violations:
        blocking_problems.append("INVALID_SUPERSESSION_CHAIN")
    if len(public) != required or public.trial_id.nunique() != required:
        blocking_problems.append("PUBLIC_TRIAL_COUNT_MISMATCH")
    if public_ids != frozen_ids:
        blocking_problems.append("PUBLIC_TRIAL_KEY_MISMATCH")

    protocol_problems = list(blocking_problems)
    if len(keys) != required:
        protocol_problems.append("FROZEN_TRIAL_COUNT_MISMATCH")
    missing_trial_ids = sorted(frozen_ids - rated_ids)
    if missing_trial_ids:
        protocol_problems.append("MISSING_DESIGNATED_REVIEWER_OUTCOMES")

    return {
        "status": "PASS" if not protocol_problems else "PROTOCOL_FAILURE",
        "all_expected_trials_represented": not missing_trial_ids
        and len(keys) == required,
        "expected_canonical_trials": required,
        "frozen_trial_keys": len(keys),
        "public_trial_rows": len(public),
        "append_only_events": len(ratings),
        "unique_event_ids": ratings.event_id.nunique(),
        "designated_reviewer": designated_reviewer,
        "designated_reviewer_events": len(designated),
        "latest_designated_reviewer_outcomes": len(latest),
        "ignored_non_designated_reviewer_events": len(ratings) - len(designated),
        "valid_responses": sorted(CHOICES),
        "all_event_responses_valid": not invalid_choice_rows,
        "invalid_response_rows": invalid_choice_rows,
        "unknown_trial_ids": unknown_trial_ids,
        "missing_trial_ids": missing_trial_ids,
        "duplicate_event_ids": duplicate_event_ids,
        "blank_event_id_rows": blank_event_rows,
        "invalid_timestamp_rows": invalid_timestamp_rows,
        "supersession_violations": supersession_violations,
        "protocol_problems": protocol_problems,
        "blocking_data_problems": blocking_problems,
        "latest_choice_counts": {
            choice: int((latest.choice == choice).sum()) for choice in sorted(CHOICES)
        },
    }


def _comparison_report(name: str, report: dict) -> dict:
    preference_ci = [value + 0.5 for value in report["improvement_95_ci"]]
    improvement = report["improvement_over_0_5"]
    improvement_ci = tuple(report["improvement_95_ci"])
    neither = int(round(report["neither_rate"] * report["trials"]))
    return {
        "comparison": PAIR_LABELS[name],
        "lower_cost_method": report["lower_method"],
        "higher_cost_method": report["higher_method"],
        "rated_trials": report["trials"],
        "usable_judgments": report["preference_denominator"],
        "excluded_neither_judgments": neither,
        "query_macro_preference_for_higher_cost": report[
            "higher_query_macro_preference"
        ],
        "query_bootstrap_95_ci": preference_ci,
        "improvement_over_cheaper": improvement,
        "improvement_95_ci": list(improvement_ci),
        "satisfies_material_improvement_rule": frozen_metrics.material(
            improvement, improvement_ci
        ),
        "tie_rate": report["tie_rate"],
        "neither_rate": report["neither_rate"],
    }


def build_closeout(root: str | Path = ".") -> tuple[dict, dict]:
    """Run frozen metrics and build the durable Audio Representation v1 record."""
    root = Path(root)
    report_dir = root / "reports/holistic_stage4a_dual"
    ratings_path = report_dir / "human_ratings.csv"
    keys_path = report_dir / "trial_keys.json"
    trials_path = report_dir / "dual_trials.csv"
    config_path = root / "configs/holistic_stage4a_dual.yaml"
    evaluator_path = root / "configs/holistic_stage4a_dual_evaluator.yaml"
    contract_path = report_dir / "experiment_contract.json"
    evaluator_bundle_path = report_dir / "evaluator_bundle.json"

    config = yaml.safe_load(config_path.read_text())
    evaluator = yaml.safe_load(evaluator_path.read_text())
    contract = json.loads(contract_path.read_text())
    validation = validate_ratings(
        ratings_path,
        keys_path,
        trials_path,
        designated_reviewer=evaluator["designated_reviewer_id"],
        required=config["trials"]["maximum_total"],
    )
    if validation["blocking_data_problems"]:
        raise CloseoutError(
            "ratings contain blocking data problems: "
            + ", ".join(validation["blocking_data_problems"])
        )

    metrics = frozen_metrics.summarize(
        ratings_path,
        keys_path,
        draws=config["metrics"]["bootstrap_draws"],
        seed=config["metrics"]["bootstrap_seed"],
        required=config["trials"]["maximum_total"],
    )
    if metrics["protocol_failure"] != (validation["status"] != "PASS"):
        raise CloseoutError("rating validation and frozen metrics disagree")

    comparisons = {
        name: _comparison_report(name, metrics["method_pairs"][name])
        for name in (
            "UNIFORM3_vs_CENTER5",
            "UNIFORM5_vs_CENTER5",
            "UNIFORM5_vs_UNIFORM3",
        )
    }
    selected_method = VERDICT_METHODS[metrics["verdict"]]
    selected = config["sampling"]["representations"][selected_method]
    encoders = contract["encoders"]
    ranking = contract["ranking"]
    missing_outcomes = len(validation["missing_trial_ids"])

    artifact = {
        "schema_version": "audio-representation-v1-stage4a-closeout-v1",
        "status": "CLOSED_WITH_PROTOCOL_FAILURE"
        if metrics["protocol_failure"]
        else "CLOSED",
        "audio_representation": "Audio Representation v1",
        "audio": {
            "excerpt_seconds": 30,
            "sample_rate_hz": config["canonical_audio"]["sample_rate"],
            "channels": config["canonical_audio"]["channels"],
            "preprocessing_version": config["canonical_audio"][
                "preprocessing_version"
            ],
        },
        "temporal_sampling": {
            "selected_method": selected_method,
            "selected_k": selected["K"],
            "segment_duration_seconds": 5,
            "segment_centers_seconds": selected["centers_sec"],
            "aggregation": (
                "Within each encoder, L2-normalize every segment embedding, "
                "take the arithmetic mean across the selected centers, then "
                "L2-normalize the aggregate; fuse encoder cosine similarities "
                "only after independent temporal aggregation."
            ),
        },
        "encoders": {
            "clap": {
                "id": encoders["clap"]["id"],
                "checkpoint": encoders["clap"]["checkpoint"],
                "checkpoint_sha256": encoders["clap"]["checkpoint_sha256"],
                "provenance": encoders["clap"]["revision"],
                "provenance_record": (
                    "reports/holistic_stage2b/checkpoint_provenance_erratum.md"
                ),
            },
            "muq": {
                "id": encoders["muq"]["id"],
                "repository": encoders["muq"]["hf_repo"],
                "revision": encoders["muq"]["revision"],
                "weights_sha256": encoders["muq"]["weights_sha256"],
                "config_sha256": encoders["muq"]["config_sha256"],
            },
        },
        "fusion": {
            "method": "weighted sum of per-encoder cosine similarities",
            "clap_weight": ranking["normalized_weights"]["clap"],
            "muq_weight": ranking["normalized_weights"]["muq"],
            "stage4a_refit_weights": ranking["refit_from_stage4_labels"],
            "statement": "Stage 4A did not refit the frozen fusion weights.",
        },
        "evidence": {
            "ratings_validation": validation,
            "final_verdict": metrics["verdict"],
            "comparisons": comparisons,
            "bootstrap": {
                **metrics["bootstrap"],
                "confidence": 0.95,
            },
            "material_improvement_threshold": config["metrics"][
                "material_improvement"
            ],
            "tie_handling": "Tie receives 0.5 credit.",
            "neither_handling": "Neither is excluded from preference estimates.",
            "protocol_failure": metrics["protocol_failure"],
            "protocol_effect": (
                "The frozen decision rule returns the cheaper K=1 configuration "
                f"because {missing_outcomes} expected designated-reviewer "
                "outcomes are missing; "
                "pairwise estimates are retained as incomplete evidence."
                if metrics["protocol_failure"]
                else "None."
            ),
            "frozen_metrics": metrics,
        },
        "human_ratings_provenance": {
            "ratings_path": "reports/holistic_stage4a_dual/human_ratings.csv",
            "ratings_sha256": sha256(ratings_path),
            "trial_keys_path": "reports/holistic_stage4a_dual/trial_keys.json",
            "trial_keys_sha256": sha256(keys_path),
            "public_trials_path": "reports/holistic_stage4a_dual/dual_trials.csv",
            "public_trials_sha256": sha256(trials_path),
            "evaluator_bundle_path": (
                "reports/holistic_stage4a_dual/evaluator_bundle.json"
            ),
            "evaluator_bundle_sha256": sha256(evaluator_bundle_path),
            "frozen_metrics_implementation_path": (
                "src/audio_similarity/stage4a_dual_metrics.py"
            ),
            "frozen_metrics_implementation_sha256": sha256(
                root / "src/audio_similarity/stage4a_dual_metrics.py"
            ),
        },
        "stage4b_triggered": metrics["stage4b_triggered"],
        "stage4b_execution": "NOT_RUN",
        "claim_boundary": {
            "stage2b_scientific_conclusion": "SINGLE_ENCODER_WINS / CLAP",
            "active_engineering_representation": "CLAP + MuQ",
            "engineering_basis": (
                "Previously frozen engineering decision; Stage 4A does not "
                "change the Stage 2B scientific conclusion."
            ),
            "population_claim": False,
        },
    }
    return metrics, artifact
