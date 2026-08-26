"""Validate and canonicalize the approved Stage 2B single-reviewer labels."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from .stage2b_contract import ContractError, load_contract, sha256_file, validate_input_hashes
from .stage2b_store import CHOICES, RATING_COLUMNS, normalize_rater_id

CANONICAL_COLUMNS = ["trial_id", "rater_id", "choice", "event_id", "submitted_at"]


def canonicalize_single_reviewer(events: pd.DataFrame, trial_keys: dict[str, dict[str, Any]]) -> pd.DataFrame:
    if list(events.columns) != RATING_COLUMNS:
        raise ContractError("raw rating columns do not match the append-only schema")
    if events["event_id"].duplicated().any():
        raise ContractError("duplicate rating event ID")
    if not set(events["trial_id"]).issubset(trial_keys):
        raise ContractError("raw ratings contain an unknown trial")
    if any(normalize_rater_id(value) != str(value) or not str(value) for value in events["rater_id"]):
        raise ContractError("rating contains an invalid/non-normalized rater ID")
    if not set(events["choice"]).issubset(CHOICES):
        raise ContractError("rating contains an invalid choice")

    prior_by_event: dict[str, dict[str, str]] = {}
    latest: dict[tuple[str, str], dict[str, str]] = {}
    for row in events.fillna("").astype(str).to_dict("records"):
        supersedes = row["supersedes_event_id"]
        if supersedes:
            prior = prior_by_event.get(supersedes)
            if prior is None:
                raise ContractError(f"event {row['event_id']} supersedes an unknown/later event")
            if (prior["trial_id"], prior["rater_id"]) != (row["trial_id"], row["rater_id"]):
                raise ContractError("self-correction may only supersede the same reviewer/trial")
            if latest.get((row["trial_id"], row["rater_id"]), {}).get("event_id") != supersedes:
                raise ContractError("self-correction does not supersede the latest own event")
        elif (row["trial_id"], row["rater_id"]) in latest:
            raise ContractError("repeated reviewer event must identify the superseded event")
        prior_by_event[row["event_id"]] = row
        latest[(row["trial_id"], row["rater_id"])] = row

    by_trial: dict[str, list[dict[str, str]]] = defaultdict(list)
    for (trial_id, _), row in latest.items():
        by_trial[trial_id].append(row)
    expected = set(trial_keys)
    if set(by_trial) != expected:
        missing = sorted(expected - set(by_trial))
        raise ContractError(f"single-reviewer coverage incomplete: {len(missing)} missing trials")
    if any(len(rows) != 1 for rows in by_trial.values()):
        raise ContractError("single_reviewer_v2 requires exactly one canonical reviewer per trial")
    reviewers = {rows[0]["rater_id"] for rows in by_trial.values()}
    if len(reviewers) != 1:
        raise ContractError(f"single_reviewer_v2 requires one designated reviewer, found {sorted(reviewers)}")

    canonical = pd.DataFrame([
        {
            "trial_id": trial_id,
            "rater_id": by_trial[trial_id][0]["rater_id"],
            "choice": by_trial[trial_id][0]["choice"],
            "event_id": by_trial[trial_id][0]["event_id"],
            "submitted_at": by_trial[trial_id][0]["submitted_at"],
        }
        for trial_id in sorted(expected)
    ], columns=CANONICAL_COLUMNS)
    return canonical


def validate_and_freeze_ratings(config_path: str | Path, root: str | Path = ".") -> dict[str, Any]:
    root = Path(root)
    config_path = Path(config_path)
    config = load_contract(config_path)
    if config.get("protocol_version") != "single_reviewer_v2":
        raise ContractError("rating closeout requires approved single_reviewer_v2 config")
    validate_input_hashes(config, root)
    report_dir = root / config["paths"]["report_dir"]
    keys_payload = json.loads((report_dir / "trial_keys.json").read_text(encoding="utf-8"))
    trial_keys = keys_payload["trials"]
    balance = json.loads((report_dir / "trial_balance.json").read_text(encoding="utf-8"))
    if not balance.get("gate_passed"):
        raise ContractError("frozen source-balance gate failed")

    raw_paths = {
        "all": report_dir / "human_ratings.csv",
        "train_validation": report_dir / "human_ratings_train_validation.csv",
        "test": report_dir / "human_ratings_test.csv",
    }
    events = pd.read_csv(raw_paths["all"], dtype=str).fillna("")
    canonical = canonicalize_single_reviewer(events, trial_keys)

    expected_tv = set(canonical[canonical["trial_id"].map(lambda value: trial_keys[value]["split"] in {"TRAIN", "VALIDATION"})]["event_id"])
    expected_test = set(canonical[canonical["trial_id"].map(lambda value: trial_keys[value]["split"] == "TEST")]["event_id"])
    raw_tv = pd.read_csv(raw_paths["train_validation"], dtype=str).fillna("")
    raw_test = pd.read_csv(raw_paths["test"], dtype=str).fillna("")
    latest_tv = canonicalize_single_reviewer(raw_tv, {key: value for key, value in trial_keys.items() if value["split"] in {"TRAIN", "VALIDATION"}})
    latest_test = canonicalize_single_reviewer(raw_test, {key: value for key, value in trial_keys.items() if value["split"] == "TEST"})
    if set(latest_tv["event_id"]) != expected_tv or set(latest_test["event_id"]) != expected_test:
        raise ContractError("split-safe rating exports do not match authoritative latest events")

    labels_all = report_dir / "canonical_labels.csv"
    labels_tv = report_dir / "canonical_labels_train_validation.csv"
    labels_test = report_dir / "canonical_labels_test.csv"
    canonical.to_csv(labels_all, index=False)
    latest_tv.to_csv(labels_tv, index=False)
    latest_test.to_csv(labels_test, index=False)

    split_counts: dict[str, Counter] = defaultdict(Counter)
    query_counts: dict[str, Counter] = defaultdict(Counter)
    source_counts: dict[str, Counter] = defaultdict(Counter)
    test_ab_queries: set[int] = set()
    for row in canonical.to_dict("records"):
        key = trial_keys[row["trial_id"]]
        split, choice = key["split"], row["choice"]
        split_counts[split][choice] += 1
        query_counts[str(key["query_id"])][choice] += 1
        source_counts[key["source_pair"]][choice] += 1
        if split == "TEST" and choice in {"A", "B"}:
            test_ab_queries.add(int(key["query_id"]))
    test_queries = {int(value["query_id"]) for value in trial_keys.values() if value["split"] == "TEST"}
    missing_test_ab = sorted(test_queries - test_ab_queries)
    if missing_test_ab:
        raise ContractError(f"TEST queries without an A/B choice: {missing_test_ab}")

    outputs = {
        "canonical_labels": sha256_file(labels_all),
        "canonical_labels_train_validation": sha256_file(labels_tv),
        "canonical_labels_test": sha256_file(labels_test),
    }
    summary = {
        "experiment_id": config["experiment_id"],
        "protocol_version": config["protocol_version"],
        "claim_scope": config["verdict"]["claim_scope"],
        "config_sha256": sha256_file(config_path),
        "raw_rating_sha256": {name: sha256_file(path) for name, path in raw_paths.items()},
        "trial_keys_sha256": sha256_file(report_dir / "trial_keys.json"),
        "trial_balance_sha256": sha256_file(report_dir / "trial_balance.json"),
        "canonical_output_sha256": outputs,
        "raw_event_count": len(events),
        "canonical_trial_count": len(canonical),
        "distinct_reviewers": int(canonical["rater_id"].nunique()),
        "self_correction_event_count": len(events) - len(canonical),
        "choice_counts_by_split": {key: dict(value) for key, value in sorted(split_counts.items())},
        "choice_counts_by_query": {key: dict(value) for key, value in sorted(query_counts.items(), key=lambda item: int(item[0]))},
        "choice_counts_by_source_pair": {key: dict(value) for key, value in sorted(source_counts.items())},
        "test_queries_with_ab_choice": len(test_ab_queries),
        "test_query_count": len(test_queries),
        "protocol_passed": True,
        "population_claim_permitted": False,
    }
    (report_dir / "rating_validation.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
