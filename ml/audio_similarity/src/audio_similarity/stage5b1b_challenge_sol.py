"""Isolated, candidate-shuffled Sol review for the fresh Stage 5B.1B challenge."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_calibration_sol import (
    CalibrationCodexBackend,
    RESPONSE_SCHEMA_VERSION,
    validate_sol_response,
)
from .stage5b1b_challenge import ChallengeConfig, ChallengeManifest, load_discovery
from .stage5b1b_sol import value_sha256


PAYLOAD_SCHEMA_VERSION = "stage5b1b-fresh-challenge-sol-payload-v1"
MAPPING_SCHEMA_VERSION = "stage5b1b-fresh-challenge-sol-private-mapping-v1"
CONTRACT_SCHEMA_VERSION = "stage5b1b-fresh-challenge-sol-contract-v1"
EVALUATION_SCHEMA_VERSION = "stage5b1b-fresh-challenge-sol-evaluations-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _shuffle_key(seed: str, stable_id: str, video_id: str) -> str:
    return hashlib.sha256(f"{seed}|{stable_id}|{video_id}".encode()).hexdigest()


def build_blinded_payload(
    config: ChallengeConfig, manifest: ChallengeManifest
) -> tuple[dict[str, Any], dict[str, Any]]:
    discovery = load_discovery(config, manifest)
    seed = str(config.evaluator["shuffle_seed"])
    limit = int(config.evaluator["description_max_characters"])
    by_id = {row.track.stable_track_id: row.track.to_dict() for row in manifest.tracks}
    payload_tracks: list[dict[str, Any]] = []
    mapping_tracks: list[dict[str, Any]] = []
    for row in discovery["tracks"]:
        track = row["track"]
        stable_id = track["stable_track_id"]
        if track != by_id[stable_id]:
            raise Stage5B1AValidationError(f"fresh discovery target changed: {stable_id}")
        ordered = sorted(
            row["candidates"],
            key=lambda candidate: _shuffle_key(seed, stable_id, candidate["youtube_video_id"]),
        )
        blinded_candidates: list[dict[str, Any]] = []
        mapped_candidates: list[dict[str, Any]] = []
        for index, candidate in enumerate(ordered, start=1):
            key = f"candidate_{index:02d}"
            description = candidate.get("description")
            truncated = isinstance(description, str) and len(description) > limit
            if truncated:
                description = description[:limit]
            blinded_candidates.append({
                "candidate_key": key,
                "title": candidate.get("title"),
                "uploader": candidate.get("uploader"),
                "channel": candidate.get("channel"),
                "duration_seconds": candidate.get("duration_seconds"),
                "view_count": candidate.get("view_count"),
                "description": description,
                "description_truncated": truncated,
                "availability": candidate.get("availability"),
                "live_status": candidate.get("live_status"),
            })
            mapped_candidates.append({
                "candidate_key": key,
                "youtube_video_id": candidate["youtube_video_id"],
                "original_search_rank": candidate["rank"],
            })
        payload_tracks.append({
            "stable_track_id": stable_id,
            "target": {
                "title": track["title"],
                "artists": track["artists"],
                "album": track.get("album"),
                "duration_ms": track.get("duration_ms"),
                "release_year": track.get("release_year"),
            },
            "candidates": blinded_candidates,
        })
        mapping_tracks.append({"stable_track_id": stable_id, "candidates": mapped_candidates})
    payload = {
        "schema_version": PAYLOAD_SCHEMA_VERSION,
        "manifest_sha256": manifest.sha256,
        "discovery_sha256": file_sha256(config.artifacts["discovery"]),
        "shuffle_seed_sha256": hashlib.sha256(seed.encode()).hexdigest(),
        "search_rank_supplied": False,
        "candidate_ids_supplied": False,
        "resolver_features_supplied": False,
        "policy_decisions_supplied": False,
        "human_labels_supplied": False,
        "case_metadata_supplied": False,
        "tracks": payload_tracks,
    }
    mapping = {
        "schema_version": MAPPING_SCHEMA_VERSION,
        "payload_sha256": value_sha256(payload),
        "tracks": mapping_tracks,
    }
    return payload, mapping


def prepare_sol_contract(config: ChallengeConfig, manifest: ChallengeManifest) -> dict[str, Any]:
    payload, mapping = build_blinded_payload(config, manifest)
    atomic_json(config.artifacts["blinded_sol_input"], payload)
    mapping["payload_file_sha256"] = file_sha256(config.artifacts["blinded_sol_input"])
    atomic_json(config.artifacts["blinded_sol_private_mapping"], mapping)
    evaluator = config.evaluator
    contract = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "experiment_id": "stage5b1b_fresh_challenge_sol_review_v1",
        "frozen_before_sol_execution": True,
        "config_sha256": config.sha256,
        "manifest_sha256": manifest.sha256,
        "discovery_sha256": file_sha256(config.artifacts["discovery"]),
        "features_sha256": file_sha256(config.artifacts["features"]),
        "policy_decisions_sha256": file_sha256(config.artifacts["policy_decisions"]),
        "payload": {
            "path": str(config.artifacts["blinded_sol_input"].relative_to(config.root)),
            "sha256": file_sha256(config.artifacts["blinded_sol_input"]),
            "canonical_sha256": value_sha256(payload),
            "track_count": len(payload["tracks"]),
            "candidate_count": sum(len(row["candidates"]) for row in payload["tracks"]),
        },
        "private_mapping": {
            "path": str(config.artifacts["blinded_sol_private_mapping"].relative_to(config.root)),
            "sha256": file_sha256(config.artifacts["blinded_sol_private_mapping"]),
        },
        "evaluator": {
            "provider": "codex_cli",
            "model": evaluator["model"],
            "reasoning_effort": evaluator["reasoning_effort"],
            "prompt_version": evaluator["prompt_version"],
            "prompt_path": evaluator["prompt"]["path"],
            "prompt_sha256": evaluator["prompt"]["sha256"],
            "output_schema_path": evaluator["output_schema"]["path"],
            "output_schema_sha256": evaluator["output_schema"]["sha256"],
            "batch_track_count": evaluator["batch_track_count"],
            "max_attempts": evaluator["max_attempts"],
            "timeout_seconds": evaluator["timeout_seconds"],
            "tools_allowed": False,
            "isolated_working_directory": True,
            "ignore_user_config": True,
            "ignore_rules": True,
        },
        "production_auto_match_activated": False,
    }
    atomic_json(config.artifacts["sol_contract"], contract)
    return contract


@dataclass(frozen=True)
class ChallengeSolRuntime:
    path: Path
    sha256: str
    manifest_sha256: str
    discovery_sha256: str
    payload_path: Path
    payload_sha256: str
    mapping_path: Path
    mapping_sha256: str
    evaluations_path: Path
    prompt_path: Path
    prompt_sha256: str
    output_schema_path: Path
    output_schema_sha256: str
    model: str
    reasoning_effort: str
    batch_track_count: int
    max_attempts: int
    timeout_seconds: int
    expected_track_count: int
    expected_candidate_count: int


def load_sol_runtime(config: ChallengeConfig) -> ChallengeSolRuntime:
    path = config.artifacts["sol_contract"]
    raw = _json_object(path)
    if raw.get("schema_version") != CONTRACT_SCHEMA_VERSION or raw.get("frozen_before_sol_execution") is not True:
        raise Stage5B1AValidationError("invalid fresh Sol contract")
    if raw.get("config_sha256") != config.sha256 or raw.get("manifest_sha256") != config.manifest_sha256:
        raise Stage5B1AValidationError("fresh Sol contract input identity changed")
    if raw.get("discovery_sha256") != file_sha256(config.artifacts["discovery"]):
        raise Stage5B1AValidationError("fresh Sol discovery changed after contract freeze")
    payload_meta = raw["payload"]
    mapping_meta = raw["private_mapping"]
    payload_path = config.root / payload_meta["path"]
    mapping_path = config.root / mapping_meta["path"]
    for artifact_path, expected, name in (
        (payload_path, payload_meta["sha256"], "payload"),
        (mapping_path, mapping_meta["sha256"], "mapping"),
    ):
        if file_sha256(artifact_path) != expected:
            raise Stage5B1AValidationError(f"fresh Sol {name} hash changed")
    payload = _json_object(payload_path)
    mapping = _json_object(mapping_path)
    if value_sha256(payload) != payload_meta["canonical_sha256"]:
        raise Stage5B1AValidationError("fresh Sol canonical payload changed")
    if mapping.get("payload_sha256") != value_sha256(payload) or mapping.get("payload_file_sha256") != payload_meta["sha256"]:
        raise Stage5B1AValidationError("fresh Sol mapping is not bound to payload")
    evaluator = raw["evaluator"]
    if evaluator.get("model") != "gpt-5.6-sol" or evaluator.get("reasoning_effort") != "high":
        raise Stage5B1AValidationError("fresh Sol model configuration changed")
    if evaluator.get("tools_allowed") is not False or any(
        evaluator.get(key) is not True
        for key in ("isolated_working_directory", "ignore_user_config", "ignore_rules")
    ):
        raise Stage5B1AValidationError("fresh Sol isolation changed")
    prompt_path = config.root / evaluator["prompt_path"]
    schema_path = config.root / evaluator["output_schema_path"]
    if file_sha256(prompt_path) != evaluator["prompt_sha256"] or file_sha256(schema_path) != evaluator["output_schema_sha256"]:
        raise Stage5B1AValidationError("fresh Sol protocol artifact changed")
    return ChallengeSolRuntime(
        path=path,
        sha256=file_sha256(path),
        manifest_sha256=raw["manifest_sha256"],
        discovery_sha256=raw["discovery_sha256"],
        payload_path=payload_path,
        payload_sha256=payload_meta["sha256"],
        mapping_path=mapping_path,
        mapping_sha256=mapping_meta["sha256"],
        evaluations_path=config.artifacts["sol_evaluations"],
        prompt_path=prompt_path,
        prompt_sha256=evaluator["prompt_sha256"],
        output_schema_path=schema_path,
        output_schema_sha256=evaluator["output_schema_sha256"],
        model=evaluator["model"],
        reasoning_effort=evaluator["reasoning_effort"],
        batch_track_count=int(evaluator["batch_track_count"]),
        max_attempts=int(evaluator["max_attempts"]),
        timeout_seconds=int(evaluator["timeout_seconds"]),
        expected_track_count=int(payload_meta["track_count"]),
        expected_candidate_count=int(payload_meta["candidate_count"]),
    )


class SolBackend(Protocol):
    model: str
    version: str

    def evaluate(self, prompt: str, batch_id: str) -> tuple[dict[str, Any], dict[str, Any]]: ...


def _prompt(template: str, rows: list[dict[str, Any]]) -> str:
    return template.rstrip() + "\n\nBLINDED_INPUT_JSON:\n" + json.dumps(
        rows, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _empty_state(runtime: ChallengeSolRuntime, backend: SolBackend) -> dict[str, Any]:
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "status": "RUNNING",
        "contract_sha256": runtime.sha256,
        "manifest_sha256": runtime.manifest_sha256,
        "discovery_sha256": runtime.discovery_sha256,
        "payload_sha256": runtime.payload_sha256,
        "mapping_sha256": runtime.mapping_sha256,
        "prompt_sha256": runtime.prompt_sha256,
        "output_schema_sha256": runtime.output_schema_sha256,
        "expected_track_count": runtime.expected_track_count,
        "expected_candidate_count": runtime.expected_candidate_count,
        "evaluator": {
            "provider": "codex_cli", "model": backend.model,
            "codex_cli_version": backend.version, "reasoning_effort": runtime.reasoning_effort,
        },
        "blindness": {
            "human_labels_supplied": False, "search_rank_supplied": False,
            "resolver_features_supplied": False, "policy_decisions_supplied": False,
            "case_metadata_supplied": False, "candidate_order_deterministically_shuffled": True,
            "tools_or_web_allowed": False, "isolated_ephemeral_working_directory": True,
        },
        "tracks": [], "errors": [], "started_at": _utc_now(),
        "updated_at": _utc_now(), "completed_at": None,
    }


def _validate_resume(state: dict[str, Any], runtime: ChallengeSolRuntime) -> None:
    expected = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "contract_sha256": runtime.sha256,
        "manifest_sha256": runtime.manifest_sha256,
        "discovery_sha256": runtime.discovery_sha256,
        "payload_sha256": runtime.payload_sha256,
        "mapping_sha256": runtime.mapping_sha256,
        "prompt_sha256": runtime.prompt_sha256,
        "output_schema_sha256": runtime.output_schema_sha256,
        "expected_track_count": runtime.expected_track_count,
        "expected_candidate_count": runtime.expected_candidate_count,
    }
    if any(state.get(key) != value for key, value in expected.items()):
        raise Stage5B1AValidationError("incompatible fresh Sol resume state")


def run_challenge_sol(
    runtime: ChallengeSolRuntime,
    backend: SolBackend,
    *,
    overwrite: bool = False,
    max_batches: int | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    payload = _json_object(runtime.payload_path)
    rows = payload.get("tracks")
    if not isinstance(rows, list) or len(rows) != runtime.expected_track_count:
        raise Stage5B1AValidationError("fresh Sol payload track count changed")
    if sum(len(row["candidates"]) for row in rows) != runtime.expected_candidate_count:
        raise Stage5B1AValidationError("fresh Sol payload candidate count changed")
    if runtime.evaluations_path.exists() and not overwrite:
        state = _json_object(runtime.evaluations_path)
        _validate_resume(state, runtime)
    else:
        state = _empty_state(runtime, backend)
    completed = {row["stable_track_id"]: row for row in state.get("tracks", [])}
    remaining = [row for row in rows if row["stable_track_id"] not in completed]
    batches = [
        remaining[index:index + runtime.batch_track_count]
        for index in range(0, len(remaining), runtime.batch_track_count)
    ]
    if max_batches is not None:
        if max_batches < 1:
            raise Stage5B1AValidationError("max_batches must be positive")
        batches = batches[:max_batches]
    template = runtime.prompt_path.read_text(encoding="utf-8")
    for batch in batches:
        batch_id = "batch-" + "-".join(row["stable_track_id"] for row in batch)
        prompt = _prompt(template, batch)
        last_error: Exception | None = None
        for attempt in range(1, runtime.max_attempts + 1):
            try:
                raw, operational = backend.evaluate(prompt, batch_id)
                response = validate_sol_response(raw, batch)
                for row in response["tracks"]:
                    completed[row["stable_track_id"]] = {
                        **row, "attempt": attempt, "evaluated_at": _utc_now(),
                        "batch_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                        "batch_payload_sha256": value_sha256(batch), "operational": operational,
                    }
                last_error = None
                break
            except (Stage5B1AValidationError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < runtime.max_attempts:
                    sleeper(float(attempt))
        if last_error is not None:
            state["errors"].append({
                "batch_id": batch_id,
                "stable_track_ids": [row["stable_track_id"] for row in batch],
                "error_type": type(last_error).__name__, "message": str(last_error),
                "attempts": runtime.max_attempts,
            })
        state["tracks"] = [completed[row["stable_track_id"]] for row in rows if row["stable_track_id"] in completed]
        state["updated_at"] = _utc_now()
        atomic_json(runtime.evaluations_path, state)
    candidate_count = sum(len(row["candidates"]) for row in state["tracks"])
    complete = len(state["tracks"]) == runtime.expected_track_count and candidate_count == runtime.expected_candidate_count
    state.update({
        "status": "COMPLETE" if complete else "PARTIAL",
        "completed_track_count": len(state["tracks"]),
        "completed_candidate_count": candidate_count,
        "completed_at": _utc_now() if complete else None,
        "updated_at": _utc_now(),
    })
    atomic_json(runtime.evaluations_path, state)
    return state


def mapped_sol_judgments(runtime: ChallengeSolRuntime) -> dict[str, Any]:
    state = _json_object(runtime.evaluations_path)
    _validate_resume(state, runtime)
    if state.get("status") != "COMPLETE":
        raise Stage5B1AValidationError("fresh Sol evaluation is incomplete")
    payload = _json_object(runtime.payload_path)
    payload_by_id = {row["stable_track_id"]: row for row in payload["tracks"]}
    mapping = _json_object(runtime.mapping_path)
    mappings = {
        row["stable_track_id"]: {candidate["candidate_key"]: candidate for candidate in row["candidates"]}
        for row in mapping["tracks"]
    }
    tracks = []
    for result in state["tracks"]:
        expected = payload_by_id[result["stable_track_id"]]
        validate_sol_response(
            {"schema_version": RESPONSE_SCHEMA_VERSION, "tracks": [result]}, [expected]
        )
        if result.get("operational", {}).get("forbidden_tool_event_count") != 0:
            raise Stage5B1AValidationError("saved fresh Sol result contains tool use")
        by_key = mappings[result["stable_track_id"]]
        tracks.append({
            "stable_track_id": result["stable_track_id"],
            "selection_status": result["selection_status"],
            "selected_video_id": (
                by_key[result["selected_candidate_key"]]["youtube_video_id"]
                if result["selected_candidate_key"] else None
            ),
            "selection_rationale": result["selection_rationale"],
            "candidates": [
                {**candidate, "youtube_video_id": by_key[candidate["candidate_key"]]["youtube_video_id"]}
                for candidate in result["candidates"]
            ],
        })
    return {
        "schema_version": "stage5b1b-fresh-challenge-sol-mapped-v1",
        "evaluations_sha256": file_sha256(runtime.evaluations_path),
        "tracks": tracks,
    }


def codex_backend(runtime: ChallengeSolRuntime) -> CalibrationCodexBackend:
    """Construct the proven isolated backend without introducing a runtime app dependency."""
    return CalibrationCodexBackend(runtime)  # type: ignore[arg-type]
