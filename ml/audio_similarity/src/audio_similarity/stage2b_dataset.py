"""Immutable feature dataset builder for the Stage 2B fusion benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .stage2b_contract import ContractError, load_contract, sha256_file, validate_input_hashes
from .stage2b_trials import load_validated_embeddings

ENCODER_COLUMNS = {
    "laion_clap": "clap",
    "mert_5120": "mert",
    "muq_mulan_large": "muq",
}


def delta_features(similarities_a: list[float] | np.ndarray, similarities_b: list[float] | np.ndarray) -> np.ndarray:
    first = np.asarray(similarities_a, dtype=np.float64)
    second = np.asarray(similarities_b, dtype=np.float64)
    if first.shape != (3,) or second.shape != (3,):
        raise ContractError("Stage 2B requires exactly three encoder similarities")
    result = first - second
    if not np.isfinite(result).all():
        raise ContractError("non-finite Stage 2B delta")
    return result


def swap_features(delta: list[float] | np.ndarray) -> np.ndarray:
    return -np.asarray(delta, dtype=np.float64)


def build_fusion_dataset(config_path: str | Path, root: str | Path = ".") -> dict[str, Any]:
    root = Path(root)
    config_path = Path(config_path)
    config = load_contract(config_path)
    if config.get("protocol_version") != "single_reviewer_v2":
        raise ContractError("fusion dataset requires approved single_reviewer_v2")
    validate_input_hashes(config, root)
    report_dir = root / config["paths"]["report_dir"]
    rating_validation = json.loads((report_dir / "rating_validation.json").read_text(encoding="utf-8"))
    if not rating_validation.get("protocol_passed"):
        raise ContractError("rating protocol did not pass")
    labels_path = report_dir / "canonical_labels.csv"
    if sha256_file(labels_path) != rating_validation["canonical_output_sha256"]["canonical_labels"]:
        raise ContractError("canonical label hash mismatch")
    labels = pd.read_csv(labels_path, dtype=str).fillna("").set_index("trial_id")
    keys = json.loads((report_dir / "trial_keys.json").read_text(encoding="utf-8"))["trials"]
    if set(labels.index) != set(keys):
        raise ContractError("label/key trial coverage mismatch")

    vectors: dict[str, dict[int, np.ndarray]] = {}
    for encoder, spec in config["inputs"]["embeddings"].items():
        vectors[encoder] = load_validated_embeddings(
            root / spec["path"], spec["sha256"], spec["analysis_key"], int(spec["dimensions"])
        )

    config_hash = sha256_file(config_path)
    key_hash = sha256_file(report_dir / "trial_keys.json")
    label_hash = sha256_file(labels_path)
    rows = []
    for trial_id in sorted(keys):
        key = keys[trial_id]
        query, candidate_a, candidate_b = int(key["query_id"]), int(key["candidate_a"]), int(key["candidate_b"])
        sims_a, sims_b = [], []
        for encoder in ENCODER_COLUMNS:
            try:
                sims_a.append(float(np.dot(vectors[encoder][query], vectors[encoder][candidate_a])))
                sims_b.append(float(np.dot(vectors[encoder][query], vectors[encoder][candidate_b])))
            except KeyError as exc:
                raise ContractError(f"missing embedding coverage for trial {trial_id}: {exc}") from exc
        delta = delta_features(sims_a, sims_b)
        if not np.array_equal(swap_features(delta), delta_features(sims_b, sims_a)):
            raise ContractError(f"A/B anti-symmetry failed for {trial_id}")
        choice = labels.at[trial_id, "choice"]
        included = choice in {"A", "B"}
        exclusion = "" if included else "tie" if choice == "Tie" else "neither" if choice == "Neither" else "invalid_label"
        row = {
            "trial_id": trial_id,
            "query_id": query,
            "split": key["split"],
            "source_pair": key["source_pair"],
            "choice": choice,
            "binary_label_a_wins": 1 if choice == "A" else 0 if choice == "B" else "",
            "included_binary": included,
            "exclusion_reason": exclusion,
            "same_artist_candidate_flag": bool(key["same_artist_candidate_flag"]),
            "config_sha256": config_hash,
            "trial_keys_sha256": key_hash,
            "canonical_labels_sha256": label_hash,
        }
        for index, encoder in enumerate(ENCODER_COLUMNS):
            short = ENCODER_COLUMNS[encoder]
            row[f"{short}_cosine_a"] = sims_a[index]
            row[f"{short}_cosine_b"] = sims_b[index]
            row[f"delta_{short}"] = delta[index]
            row[f"{short}_embedding_sha256"] = config["inputs"]["embeddings"][encoder]["sha256"]
        rows.append(row)

    output = report_dir / "fusion_dataset.csv"
    frame = pd.DataFrame(rows)
    frame.to_csv(output, index=False, float_format="%.17g")
    exclusions = {
        str(reason): int(count)
        for reason, count in frame.loc[~frame["included_binary"], "exclusion_reason"].value_counts().items()
    }
    summary = {
        "experiment_id": config["experiment_id"],
        "protocol_version": config["protocol_version"],
        "config_sha256": config_hash,
        "trial_keys_sha256": key_hash,
        "canonical_labels_sha256": label_hash,
        "embedding_sha256": {encoder: spec["sha256"] for encoder, spec in config["inputs"]["embeddings"].items()},
        "fusion_dataset_sha256": sha256_file(output),
        "row_count": len(frame),
        "binary_row_count": int(frame["included_binary"].sum()),
        "excluded_row_count": int((~frame["included_binary"]).sum()),
        "exclusion_counts": exclusions,
        "binary_rows_by_split": {
            split: int(((frame["split"] == split) & frame["included_binary"]).sum())
            for split in ("TRAIN", "VALIDATION", "TEST")
        },
        "feature_orientation": "sim(query,A)-sim(query,B)",
        "anti_symmetry_validated": True,
    }
    (report_dir / "fusion_dataset_manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
