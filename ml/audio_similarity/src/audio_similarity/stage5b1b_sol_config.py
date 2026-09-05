"""Hash-bound configuration for blinded Sol-assisted Stage 5B.1B review."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError, file_sha256


CONFIG_SCHEMA_VERSION = "stage5b1b-sol-evaluator-config-v1"
EXPERIMENT_ID = "stage5b1b_candidate_resolution_sol_audit"


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Stage5B1AValidationError(f"{name} must be a non-empty string")
    return value.strip()


def _integer(value: Any, name: str, *, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise Stage5B1AValidationError(f"{name} must be an integer >= {minimum}")
    return value


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
class SolEvaluatorSettings:
    provider: str
    model: str
    reasoning_effort: str
    prompt_version: str
    output_schema_path: Path
    output_schema_sha256: str
    batch_track_count: int
    max_attempts: int
    timeout_seconds: int
    description_max_characters: int
    tools_allowed: bool
    isolated_working_directory: bool
    ignore_user_config: bool
    ignore_rules: bool


@dataclass(frozen=True)
class SolAuditConfig:
    path: Path
    sha256: str
    project_root: Path
    manifest_path: Path
    manifest_sha256: str
    discovery_path: Path
    discovery_sha256: str
    resolver_features_path: Path
    resolver_features_sha256: str
    evaluator: SolEvaluatorSettings
    resolver_version: str
    production_auto_match_enabled: bool
    random_seed: str
    random_agreement_track_count: int
    artifacts: dict[str, Path]


def load_sol_audit_config(path: str | Path) -> SolAuditConfig:
    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected blinded Sol evaluator config schema")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise Stage5B1AValidationError("unexpected blinded Sol evaluator experiment ID")
    root = config_path.parent.parent.resolve()
    inputs = _object(payload.get("inputs"), "inputs")
    evaluator = _object(payload.get("evaluator"), "evaluator")
    resolver = _object(payload.get("resolver_proposal"), "resolver_proposal")
    audit = _object(payload.get("audit"), "audit")
    raw_artifacts = _object(payload.get("artifacts"), "artifacts")
    expected_artifacts = {
        "sol_evaluations", "comparison", "manual_audit", "manual_audit_queue"
    }
    if set(raw_artifacts) != expected_artifacts:
        raise Stage5B1AValidationError("blinded Sol evaluator artifact paths are incomplete")

    manifest_path = _path(root, inputs.get("manifest_path"), "inputs.manifest_path")
    discovery_path = _path(root, inputs.get("discovery_path"), "inputs.discovery_path")
    feature_path = _path(
        root, inputs.get("resolver_features_path"), "inputs.resolver_features_path"
    )
    manifest_sha = _text(
        inputs.get("manifest_expected_sha256"), "inputs.manifest_expected_sha256"
    )
    discovery_sha = _text(
        inputs.get("discovery_expected_sha256"), "inputs.discovery_expected_sha256"
    )
    feature_sha = _text(
        inputs.get("resolver_features_expected_sha256"),
        "inputs.resolver_features_expected_sha256",
    )
    for name, artifact, expected in (
        ("manifest", manifest_path, manifest_sha),
        ("discovery", discovery_path, discovery_sha),
        ("resolver features", feature_path, feature_sha),
    ):
        if file_sha256(artifact) != expected:
            raise Stage5B1AValidationError(f"frozen {name} artifact hash changed")

    if evaluator.get("provider") != "codex_cli":
        raise Stage5B1AValidationError("only the frozen codex_cli evaluator is supported")
    model = _text(evaluator.get("model"), "evaluator.model")
    if model != "gpt-5.6-sol":
        raise Stage5B1AValidationError("the evaluator model must remain gpt-5.6-sol")
    tools_allowed = evaluator.get("tools_allowed")
    isolated = evaluator.get("isolated_working_directory")
    ignore_user = evaluator.get("ignore_user_config")
    ignore_rules = evaluator.get("ignore_rules")
    if tools_allowed is not False or isolated is not True or ignore_user is not True or ignore_rules is not True:
        raise Stage5B1AValidationError("blinded evaluator isolation settings changed")
    production = resolver.get("production_auto_match_enabled")
    if production is not False:
        raise Stage5B1AValidationError("Sol audit must not enable production AUTO_MATCH")

    schema_path = _path(
        root, evaluator.get("output_schema_path"), "evaluator.output_schema_path"
    )
    schema_sha = _text(
        evaluator.get("output_schema_expected_sha256"),
        "evaluator.output_schema_expected_sha256",
    )
    if not schema_path.is_file() or file_sha256(schema_path) != schema_sha:
        raise Stage5B1AValidationError("frozen Sol output schema hash changed")
    settings = SolEvaluatorSettings(
        provider="codex_cli",
        model=model,
        reasoning_effort=_text(evaluator.get("reasoning_effort"), "evaluator.reasoning_effort"),
        prompt_version=_text(evaluator.get("prompt_version"), "evaluator.prompt_version"),
        output_schema_path=schema_path,
        output_schema_sha256=schema_sha,
        batch_track_count=_integer(
            evaluator.get("batch_track_count"), "evaluator.batch_track_count"
        ),
        max_attempts=_integer(evaluator.get("max_attempts"), "evaluator.max_attempts"),
        timeout_seconds=_integer(
            evaluator.get("timeout_seconds"), "evaluator.timeout_seconds"
        ),
        description_max_characters=_integer(
            evaluator.get("description_max_characters"),
            "evaluator.description_max_characters",
        ),
        tools_allowed=False,
        isolated_working_directory=True,
        ignore_user_config=True,
        ignore_rules=True,
    )
    return SolAuditConfig(
        path=config_path,
        sha256=file_sha256(config_path),
        project_root=root,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha,
        discovery_path=discovery_path,
        discovery_sha256=discovery_sha,
        resolver_features_path=feature_path,
        resolver_features_sha256=feature_sha,
        evaluator=settings,
        resolver_version=_text(resolver.get("version"), "resolver_proposal.version"),
        production_auto_match_enabled=False,
        random_seed=_text(audit.get("random_seed"), "audit.random_seed"),
        random_agreement_track_count=_integer(
            audit.get("random_agreement_track_count"),
            "audit.random_agreement_track_count",
            minimum=0,
        ),
        artifacts={
            key: _path(root, value, f"artifacts.{key}")
            for key, value in raw_artifacts.items()
        },
    )
