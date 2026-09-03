"""Gate, freeze, and construct Stage 5B representative benchmark artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b_representative_library import (
    DEFAULT_SAMPLE_SEED,
    DEFAULT_SAMPLE_SIZE,
    build_benchmark_manifest,
    canonical_json_bytes,
    historical_exclusion_identities,
    load_library_snapshot,
)
from .stage5b1j_artifacts import evaluate_and_write
from .stage5b1j_representation_rediscovery import (
    STATUS_PART_A_PASSED,
    Stage5B1JConfig,
    load_stage5b1j_config,
)


STACK_SCHEMA_VERSION = "stage5b-resolver-candidate-stack-v1"
STACK_ID = "STAGE5B_RESOLVER_CANDIDATE_V1"
BENCHMARK_CONFIG_SCHEMA_VERSION = "stage5b-representative-library-config-v1"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _write_immutable_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        if _json(path) != value:
            raise Stage5B1AValidationError(f"refusing to replace frozen artifact: {path}")
        return
    atomic_json(path, value)


def _relative(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def freeze_resolver_stack(
    config: Stage5B1JConfig,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Freeze only after the human gate has passed with all-safe selections."""

    manifest = evaluate_and_write(config)
    gate = manifest["human_validation_gate"]
    if (
        manifest["status"] != STATUS_PART_A_PASSED
        or not manifest["part_b_authorized"]
        or not gate["all_new_selections_human_safe"]
        or gate["completed"] != gate["required"]
        or gate["label_counts"].get("WRONG", 0)
        or gate["label_counts"].get("UNCERTAIN", 0)
    ):
        raise Stage5B1AValidationError(
            "Part A human-safe gate has not passed; resolver stack cannot be frozen"
        )
    output = Path(output_path) if output_path else (
        config.artifacts["manifest"].parent / "resolver_stack_candidate_v1.json"
    )
    source_files = (
        "stage5b1a2_ytdlp.py",
        "stage5b1c_normalization.py",
        "stage5b1c_tier2.py",
        "stage5b1c_source_neutral.py",
        "stage5b1c_strong_metadata.py",
        "stage5b1g_global_preference.py",
        "stage5b1h_source_semantics.py",
        "stage5b1i_live_fallback.py",
        "stage5b1j_representation_rediscovery.py",
    )
    source_root = config.project_root / "src/audio_similarity"
    stack = {
        "schema_version": STACK_SCHEMA_VERSION,
        "stack_id": STACK_ID,
        "status": "FROZEN_CANDIDATE_STACK_NOT_PRODUCTION_ACTIVATED",
        "part_a_manifest": {
            "path": _relative(config.project_root, config.artifacts["manifest"]),
            "sha256": file_sha256(config.artifacts["manifest"]),
        },
        "human_review": {
            "path": _relative(config.project_root, config.artifacts["human_review"]),
            "sha256": file_sha256(config.artifacts["human_review"]),
            "required": gate["required"],
            "completed": gate["completed"],
            "label_counts": gate["label_counts"],
            "all_safe": True,
        },
        "discovery": {
            "primary_query": '"{primary_artist}" "{normalized_title}" official',
            "fallback_query": '"{primary_artist}" "{base_title}" official',
            "mode": "ytsearch5",
            "metadata_only": True,
            "sequential": True,
        },
        "resolver_hierarchy": [
            "POLICY_BALANCED_V1",
            "STAGE5B1C_A_NORMALIZATION_EVIDENCE_FUSION_V1",
            "STAGE5B1C_B_SOURCE_NEUTRAL_V1",
            "STAGE5B1C_C_STRONG_METADATA_V1",
            "GLOBAL_CANDIDATE_PREFERENCE_V1",
            "CANONICAL_SOURCE_SEMANTICS_V1",
            "REPRESENTATION_EQUIVALENT_REDISCOVERY_V1",
        ],
        "match_modes": [
            "EXACT_RECORDING",
            "REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK",
            "REPRESENTATION_EQUIVALENT_MASTER_FALLBACK",
            "MATCH_UNCERTAIN",
        ],
        "fallback_precedence": [
            "EXACT_RECORDING",
            "REPRESENTATION_EQUIVALENT",
            "MATCH_UNCERTAIN",
        ],
        "exact_only_version_families": [
            "remix", "mix", "rerecording", "acoustic", "instrumental",
            "karaoke", "slowed", "sped_up", "reverb", "nightcore",
            "bass_boosted", "radio_edit", "extended",
            "arrangement_changing_live",
        ],
        "source_files": {
            name: {
                "path": _relative(config.project_root, source_root / name),
                "sha256": file_sha256(source_root / name),
            }
            for name in source_files
        },
        "challenge_measurement": manifest["summary"],
        "scope_guards": {
            "production_activated": False,
            "audio_downloads": 0,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
            "benchmark_tuning_permitted": False,
        },
    }
    _write_immutable_json(output, stack)
    return stack


def default_historical_paths(project_root: Path) -> tuple[Path, ...]:
    return (
        project_root / "reports/stage5b1a/frozen_tracks.json",
        project_root / "reports/stage5b1b/heldout_tracks.json",
        project_root / "reports/stage5b1b_fresh_challenge/challenge_tracks.json",
    )


def freeze_benchmark_manifest(
    config: Stage5B1JConfig,
    snapshot_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    seed: str = DEFAULT_SAMPLE_SEED,
) -> dict[str, Any]:
    stack_path = config.artifacts["manifest"].parent / "resolver_stack_candidate_v1.json"
    stack = freeze_resolver_stack(config, stack_path)
    output = Path(output_dir) if output_dir else (
        config.project_root / "reports/stage5b_representative_library_v1"
    )
    snapshot = Path(snapshot_path).resolve()
    library = load_library_snapshot(snapshot)
    excluded, provenance = historical_exclusion_identities(
        default_historical_paths(config.project_root)
    )
    manifest = build_benchmark_manifest(
        library,
        excluded,
        sample_size=sample_size,
        seed=seed,
        snapshot_sha256=file_sha256(snapshot),
        exclusion_provenance=provenance,
    )
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "benchmark_manifest.json"
    _write_immutable_json(manifest_path, manifest)
    digest_path = output / "benchmark_manifest.sha256"
    actual = file_sha256(manifest_path)
    if digest_path.exists() and digest_path.read_text(encoding="utf-8").strip() != actual:
        raise Stage5B1AValidationError("benchmark manifest digest lock changed")
    if not digest_path.exists():
        digest_path.write_text(actual + "\n", encoding="utf-8")
    benchmark_config = {
        "schema_version": BENCHMARK_CONFIG_SCHEMA_VERSION,
        "benchmark_id": "STAGE5B_REPRESENTATIVE_LIBRARY_V1",
        "resolver_stack": {
            "path": _relative(config.project_root, stack_path),
            "sha256": file_sha256(stack_path),
            "stack_id": stack["stack_id"],
        },
        "benchmark_manifest": {
            "path": _relative(config.project_root, manifest_path),
            "sha256": actual,
        },
        "private_snapshot_sha256": file_sha256(snapshot),
        "sample_seed": seed,
        "requested_sample_size": sample_size,
        "query_strategy": "Q0_FROZEN",
        "resolver_mutation_permitted": False,
        "post_freeze_substitution_permitted": False,
    }
    _write_immutable_json(output / "benchmark_config.json", benchmark_config)
    return {
        "resolver_stack": stack,
        "benchmark_manifest": manifest,
        "benchmark_manifest_sha256": actual,
        "benchmark_config": benchmark_config,
    }


def load_part_a_config(path: str | Path) -> Stage5B1JConfig:
    return load_stage5b1j_config(path)
