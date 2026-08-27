"""Stage 4 config validation and immutable contract hashing."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from .stage4_corpus import CorpusReadinessError, readiness, sha256_file
from .stage4_scoring import METHODS

IMPLEMENTATION_FILES = [
    "src/audio_similarity/holistic_encoders.py",
    "src/audio_similarity/stage4_sampling.py",
    "src/audio_similarity/stage4_scoring.py",
    "src/audio_similarity/stage4_cache.py",
    "src/audio_similarity/stage4_corpus.py",
    "src/audio_similarity/stage4_contract.py",
]


class Stage4ContractError(ValueError):
    pass


def load_config(path: str | Path) -> dict:
    path = Path(path)
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("experiment_id") != "holistic_stage4_full_song_benchmark":
        raise Stage4ContractError("wrong Stage 4 experiment_id")
    if tuple(config.get("architectures", ())) != METHODS:
        raise Stage4ContractError("primary architectures differ from frozen three-method contract")
    if config["sampling"] != {"version": "five5_fractional_v1", "centers": [0.1, 0.3, 0.5, 0.7, 0.9], "window_samples": 120000}:
        raise Stage4ContractError("sampling contract changed")
    if config["encoder"]["checkpoint_sha256"] != "8053c9775516af2f4902e1e8281e356cc1bf7a85e8b761908170767b77c3f037":
        raise Stage4ContractError("Stage 2B checkpoint identity changed")
    if config["metrics"]["bootstrap_draws"] != 50_000:
        raise Stage4ContractError("bootstrap draw count changed")
    if set(config["verdict"]["allowed"]) != {"UNIFORM_MEAN_WINS", "RECURRENCE_WEIGHTING_WINS", "LATE_INTERACTION_WINS", "INSUFFICIENT_EVIDENCE_PICK_SIMPLER"}:
        raise Stage4ContractError("verdict set changed")
    return config


def verify_static_inputs(root: str | Path, config: dict) -> None:
    root = Path(root)
    checkpoint = root / config["encoder"]["checkpoint"]
    adapter = root / config["encoder"]["adapter"]
    for path, expected in ((checkpoint, config["encoder"]["checkpoint_sha256"]), (adapter, config["encoder"]["adapter_sha256"])):
        if not path.is_file() or sha256_file(path) != expected:
            raise Stage4ContractError(f"frozen source hash mismatch: {path}")


def freeze_readiness_contract(root: str | Path, config_path: str | Path, output: str | Path) -> dict:
    root, config_path, output = Path(root), Path(config_path), Path(output)
    config = load_config(config_path)
    verify_static_inputs(root, config)
    medley = config["corpus"]["medleydb"]
    corpus = readiness(
        root / config["corpus"]["musdb18"]["archive"],
        root / medley["audio_root"],
        root / medley["metadata_root"],
        medley["metadata_git_revision"],
    )
    implementation = {name: sha256_file(root / name) for name in IMPLEMENTATION_FILES}
    duplicate_file = root / config["corpus"]["manual_duplicate_aliases"]
    payload = {
        "experiment_id": config["experiment_id"],
        "config_sha256": sha256_file(config_path),
        "corpus": corpus,
        "duplicate_aliases_sha256": sha256_file(duplicate_file),
        "implementation_sha256": implementation,
        "claim_boundary": config["claim_boundary"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["contract_sha256"] = hashlib.sha256(canonical).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def validate_frozen_contract(root: str | Path, config_path: str | Path, frozen_path: str | Path) -> dict:
    frozen = json.loads(Path(frozen_path).read_text(encoding="utf-8"))
    current = freeze_readiness_contract(root, config_path, Path(frozen_path).with_suffix(".validation.tmp"))
    Path(frozen_path).with_suffix(".validation.tmp").unlink(missing_ok=True)
    if frozen != current:
        raise Stage4ContractError("frozen contract does not match current sources/assets")
    return current
