"""Hash-bound Stage 5B.1B Part A configuration."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .stage5b1a2_config import Stage5B1A2Config, load_ytdlp_config
from .stage5b1a_models import Stage5B1AValidationError, file_sha256


CONFIG_SCHEMA_VERSION = "stage5b1b-config-v1"
EXPERIMENT_ID = "stage5b1b_candidate_resolution_heldout"


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Stage5B1AValidationError(f"{name} must be a non-empty string")
    return value.strip()


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"{name} must be an object")
    return value


def _path(root: Path, value: Any, name: str) -> Path:
    path = (root / _text(value, name)).resolve()
    if not path.is_relative_to(root):
        raise Stage5B1AValidationError(f"{name} must remain inside the project root")
    return path


@dataclass(frozen=True)
class Stage5B1BConfig:
    path: Path
    sha256: str
    project_root: Path
    checkpoint_commit: str
    discovery: Stage5B1A2Config
    dev_manifest_path: Path
    dev_manifest_sha256: str
    dev_discovery_path: Path
    dev_review_path: Path
    heldout_manifest_path: Path
    heldout_manifest_sha256: str
    artifacts: dict[str, Path]


def load_stage5b1b_config(path: str | Path) -> Stage5B1BConfig:
    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.1B config schema")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise Stage5B1AValidationError("unexpected Stage 5B.1B experiment ID")
    root = config_path.parent.parent
    discovery_value = _object(payload.get("discovery_configuration"), "discovery_configuration")
    discovery_path = _path(root, discovery_value.get("path"), "discovery_configuration.path")
    expected_discovery_hash = _text(
        discovery_value.get("expected_sha256"), "discovery_configuration.expected_sha256"
    )
    if file_sha256(discovery_path) != expected_discovery_hash:
        raise Stage5B1AValidationError("frozen yt-dlp discovery configuration hash changed")
    discovery = load_ytdlp_config(discovery_path)

    dev = _object(payload.get("dev"), "dev")
    heldout = _object(payload.get("heldout"), "heldout")
    raw_artifacts = _object(payload.get("artifacts"), "artifacts")
    expected_artifacts = {
        "dev_features", "dev_diagnostics", "heldout_discovery", "heldout_features",
        "heldout_review", "run_status", "implementation_report",
    }
    if set(raw_artifacts) != expected_artifacts:
        raise Stage5B1AValidationError("Stage 5B.1B artifact paths are incomplete")
    return Stage5B1BConfig(
        path=config_path,
        sha256=file_sha256(config_path),
        project_root=root,
        checkpoint_commit=_text(payload.get("stage5b1a2_evidence_checkpoint"), "checkpoint"),
        discovery=discovery,
        dev_manifest_path=_path(root, dev.get("manifest_path"), "dev.manifest_path"),
        dev_manifest_sha256=_text(dev.get("manifest_expected_sha256"), "dev.manifest_expected_sha256"),
        dev_discovery_path=_path(root, dev.get("discovery_results_path"), "dev.discovery_results_path"),
        dev_review_path=_path(root, dev.get("review_path"), "dev.review_path"),
        heldout_manifest_path=_path(root, heldout.get("manifest_path"), "heldout.manifest_path"),
        heldout_manifest_sha256=_text(
            heldout.get("manifest_expected_sha256"), "heldout.manifest_expected_sha256"
        ),
        artifacts={key: _path(root, value, f"artifacts.{key}") for key, value in raw_artifacts.items()},
    )
