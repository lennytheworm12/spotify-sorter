"""Freeze and validate the immutable Stage 2B collection bundle."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .stage2b_contract import ContractError, sha256_file
from .stage2b_store import RATING_COLUMNS

IMMUTABLE_FILES = (
    "configs/holistic_stage2b_fusion.yaml",
    "reports/holistic_stage2b/query_split_manifest.json",
    "reports/holistic_stage2b/trial_balance.json",
    "reports/holistic_stage2b/holistic_trials.csv",
    "reports/holistic_stage2b/trial_keys.json",
    "reports/holistic_stage2b/pcm_identity_manifest.json",
    "src/audio_similarity/stage2b_audio.py",
    "src/audio_similarity/stage2b_store.py",
    "src/audio_similarity/cli/stage2b_eval_server.py",
    "evaluation/static/stage2b.html",
)
RATING_FILES = (
    "reports/holistic_stage2b/human_ratings.csv",
    "reports/holistic_stage2b/human_ratings_train_validation.csv",
    "reports/holistic_stage2b/human_ratings_test.csv",
)


def freeze_collection_bundle(root: str | Path = ".") -> dict:
    root = Path(root)
    for relative in RATING_FILES:
        frame = pd.read_csv(root / relative, dtype=str)
        if list(frame.columns) != RATING_COLUMNS or len(frame):
            raise ContractError(f"collection bundle can only freeze empty rating schema: {relative}")
    payload = {
        "schema_version": 1,
        "stage": "pre_collection",
        "immutable_sha256": {relative: sha256_file(root / relative) for relative in IMMUTABLE_FILES},
        "initial_empty_rating_sha256": {relative: sha256_file(root / relative) for relative in RATING_FILES},
        "rating_columns": RATING_COLUMNS,
        "human_payload_blinding": [
            "no model identity", "no score", "no split", "no track ID", "no title", "no artist", "no album", "no genre"
        ],
    }
    output = root / "reports/holistic_stage2b/collection_bundle_manifest.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def validate_collection_bundle(root: str | Path = ".") -> None:
    root = Path(root)
    path = root / "reports/holistic_stage2b/collection_bundle_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    for relative, expected in payload["immutable_sha256"].items():
        if sha256_file(root / relative) != expected:
            raise ContractError(f"collection bundle drift: {relative}")
