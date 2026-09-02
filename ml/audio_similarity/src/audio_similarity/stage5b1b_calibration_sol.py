"""Fresh, candidate-shuffled and metadata-only Sol calibration review."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_manifest import load_heldout_manifest
from .stage5b1b_sol import CodexCliSolBackend, value_sha256


CONFIG_SCHEMA_VERSION = "stage5b1b-calibration-sol-config-v1"
PAYLOAD_SCHEMA_VERSION = "stage5b1b-calibration-sol-payload-v1"
MAPPING_SCHEMA_VERSION = "stage5b1b-calibration-sol-private-mapping-v1"
RESPONSE_SCHEMA_VERSION = "stage5b1b-calibration-sol-batch-response-v1"
EVALUATION_SCHEMA_VERSION = "stage5b1b-calibration-sol-evaluations-v1"
SOL_LABELS = {"IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"}
SELECTION_STATUSES = {"SELECTED", "NO_SAFE_CANDIDATE", "SOL_MATCH_UNCERTAIN"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _inside(root: Path, value: str, name: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise Stage5B1AValidationError(f"{name} must remain within project root")
    return path


@dataclass(frozen=True)
class CalibrationSolConfig:
    path: Path
    sha256: str
    root: Path
    manifest_path: Path
    manifest_sha256: str
    discovery_path: Path
    discovery_sha256: str
    human_review_path: Path
    human_review_sha256: str
    feature_v1_path: Path
    feature_v1_sha256: str
    prompt_path: Path
    prompt_sha256: str
    output_schema_path: Path
    output_schema_sha256: str
    payload_path: Path
    payload_sha256: str
    mapping_path: Path
    mapping_sha256: str
    evaluations_path: Path
    model: str
    reasoning_effort: str
    batch_track_count: int
    max_attempts: int
    timeout_seconds: int
    shuffle_seed: str
    description_max_characters: int


def load_calibration_sol_config(path: str | Path) -> CalibrationSolConfig:
    config_path = Path(path).resolve()
    raw = _json_object(config_path)
    if raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected calibration Sol config schema")
    if raw.get("experiment_id") != "stage5b1b_partb_policy_calibration":
        raise Stage5B1AValidationError("unexpected calibration Sol experiment identity")
    if raw.get("production_auto_match_activated") is not False:
        raise Stage5B1AValidationError(
            "calibration config must not activate production AUTO_MATCH"
        )
    root = config_path.parent.parent.resolve()
    inputs = raw.get("inputs")
    evaluator = raw.get("evaluator")
    artifacts = raw.get("artifacts")
    if not all(isinstance(value, dict) for value in (inputs, evaluator, artifacts)):
        raise Stage5B1AValidationError("calibration Sol config sections must be objects")

    def artifact(section: dict[str, Any], key: str) -> tuple[Path, str]:
        value = section.get(key)
        if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
            raise Stage5B1AValidationError(f"{key} must bind path and sha256")
        artifact_path = _inside(root, str(value["path"]), key)
        expected = str(value["sha256"])
        if file_sha256(artifact_path) != expected:
            raise Stage5B1AValidationError(f"frozen calibration artifact hash changed: {key}")
        return artifact_path, expected

    manifest, manifest_sha = artifact(inputs, "manifest")
    discovery, discovery_sha = artifact(inputs, "discovery")
    review, review_sha = artifact(inputs, "human_review")
    feature_v1, feature_v1_sha = artifact(inputs, "feature_v1")
    prompt, prompt_sha = artifact(evaluator, "prompt")
    schema, schema_sha = artifact(evaluator, "output_schema")
    payload, payload_sha = artifact(artifacts, "blinded_payload")
    mapping, mapping_sha = artifact(artifacts, "private_mapping")
    payload_value = _json_object(payload)
    mapping_value = _json_object(mapping)
    if mapping_value.get("payload_file_sha256") != payload_sha:
        raise Stage5B1AValidationError(
            "private mapping is not bound to blinded payload file"
        )
    if mapping_value.get("payload_sha256") != value_sha256(payload_value):
        raise Stage5B1AValidationError(
            "private mapping canonical payload identity changed"
        )
    evaluations = _inside(root, str(artifacts.get("evaluations")), "evaluations")
    if evaluator.get("model") != "gpt-5.6-sol":
        raise Stage5B1AValidationError("calibration evaluator must remain gpt-5.6-sol")
    if evaluator.get("reasoning_effort") != "high":
        raise Stage5B1AValidationError(
            "calibration evaluator reasoning effort changed"
        )
    if evaluator.get("prompt_version") != "stage5b1b-calibration-sol-blind-v1":
        raise Stage5B1AValidationError("calibration evaluator prompt version changed")
    required_true = ("isolated_working_directory", "ignore_user_config", "ignore_rules")
    if any(evaluator.get(name) is not True for name in required_true):
        raise Stage5B1AValidationError("calibration Sol isolation settings changed")
    if evaluator.get("tools_allowed") is not False:
        raise Stage5B1AValidationError("calibration Sol must not use tools")
    integer_fields = ("batch_track_count", "max_attempts", "timeout_seconds", "description_max_characters")
    if any(not isinstance(evaluator.get(name), int) or evaluator[name] < 1 for name in integer_fields):
        raise Stage5B1AValidationError("calibration evaluator integer settings are invalid")
    shuffle_seed = raw.get("shuffle_seed")
    if not isinstance(shuffle_seed, str) or not shuffle_seed:
        raise Stage5B1AValidationError("calibration shuffle seed is required")
    return CalibrationSolConfig(
        path=config_path,
        sha256=file_sha256(config_path),
        root=root,
        manifest_path=manifest,
        manifest_sha256=manifest_sha,
        discovery_path=discovery,
        discovery_sha256=discovery_sha,
        human_review_path=review,
        human_review_sha256=review_sha,
        feature_v1_path=feature_v1,
        feature_v1_sha256=feature_v1_sha,
        prompt_path=prompt,
        prompt_sha256=prompt_sha,
        output_schema_path=schema,
        output_schema_sha256=schema_sha,
        payload_path=payload,
        payload_sha256=payload_sha,
        mapping_path=mapping,
        mapping_sha256=mapping_sha,
        evaluations_path=evaluations,
        model="gpt-5.6-sol",
        reasoning_effort=str(evaluator.get("reasoning_effort")),
        batch_track_count=evaluator["batch_track_count"],
        max_attempts=evaluator["max_attempts"],
        timeout_seconds=evaluator["timeout_seconds"],
        shuffle_seed=shuffle_seed,
        description_max_characters=evaluator["description_max_characters"],
    )


def _shuffle_key(seed: str, stable_id: str, video_id: str) -> str:
    return hashlib.sha256(f"{seed}|{stable_id}|{video_id}".encode()).hexdigest()


def build_blinded_payload(
    *,
    manifest_path: str | Path,
    manifest_sha256: str,
    discovery_path: str | Path,
    discovery_sha256: str,
    shuffle_seed: str,
    description_max_characters: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if file_sha256(discovery_path) != discovery_sha256:
        raise Stage5B1AValidationError("frozen discovery changed before blinded payload build")
    manifest = load_heldout_manifest(manifest_path, expected_sha256=manifest_sha256)
    discovery = _json_object(Path(discovery_path))
    rows = discovery.get("tracks")
    if not isinstance(rows, list) or len(rows) != len(manifest.tracks):
        raise Stage5B1AValidationError("discovery coverage does not match frozen manifest")
    manifest_by_id = {item.track.stable_track_id: item.track.to_dict() for item in manifest.tracks}
    payload_tracks: list[dict[str, Any]] = []
    mapping_tracks: list[dict[str, Any]] = []
    for row in rows:
        raw_track = row.get("track")
        if not isinstance(raw_track, dict):
            raise Stage5B1AValidationError("discovery target must be an object")
        stable_id = str(raw_track.get("stable_track_id") or "")
        frozen_track = manifest_by_id.get(stable_id)
        if raw_track != frozen_track:
            raise Stage5B1AValidationError(f"target metadata mismatch for {stable_id}")
        candidates = row.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise Stage5B1AValidationError(f"missing candidates for {stable_id}")
        video_ids = [str(candidate.get("youtube_video_id") or "") for candidate in candidates]
        ranks = [candidate.get("rank") for candidate in candidates]
        if (
            any(not video_id for video_id in video_ids)
            or len(video_ids) != len(set(video_ids))
            or ranks != list(range(1, len(candidates) + 1))
            or len(candidates) > 5
        ):
            raise Stage5B1AValidationError(
                f"invalid frozen candidate identities for {stable_id}"
            )
        ordered = sorted(
            candidates,
            key=lambda candidate: _shuffle_key(
                shuffle_seed, stable_id, str(candidate.get("youtube_video_id") or "")
            ),
        )
        payload_candidates = []
        mapping_candidates = []
        for index, candidate in enumerate(ordered, start=1):
            video_id = str(candidate.get("youtube_video_id") or "")
            if not video_id:
                raise Stage5B1AValidationError("candidate video identity is missing")
            key = f"candidate_{index:02d}"
            description = candidate.get("description")
            truncated = False
            if isinstance(description, str) and len(description) > description_max_characters:
                description = description[:description_max_characters]
                truncated = True
            payload_candidates.append(
                {
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
                }
            )
            mapping_candidates.append(
                {
                    "candidate_key": key,
                    "youtube_video_id": video_id,
                    "original_search_rank": candidate.get("rank"),
                }
            )
        payload_tracks.append(
            {
                "stable_track_id": stable_id,
                "target": {
                    "title": frozen_track.get("title"),
                    "artists": frozen_track.get("artists"),
                    "album": frozen_track.get("album"),
                    "duration_ms": frozen_track.get("duration_ms"),
                    "release_year": frozen_track.get("release_year"),
                },
                "candidates": payload_candidates,
            }
        )
        mapping_tracks.append({"stable_track_id": stable_id, "candidates": mapping_candidates})
    payload = {
        "schema_version": PAYLOAD_SCHEMA_VERSION,
        "manifest_sha256": manifest_sha256,
        "discovery_sha256": discovery_sha256,
        "shuffle_seed_sha256": hashlib.sha256(shuffle_seed.encode()).hexdigest(),
        "candidate_order_is_search_rank": False,
        "tracks": payload_tracks,
    }
    mapping = {
        "schema_version": MAPPING_SCHEMA_VERSION,
        "payload_sha256": value_sha256(payload),
        "tracks": mapping_tracks,
    }
    return payload, mapping


def write_blinded_payload(
    payload_path: str | Path,
    mapping_path: str | Path,
    payload: dict[str, Any],
    mapping: dict[str, Any],
) -> None:
    atomic_json(payload_path, payload)
    mapping["payload_file_sha256"] = file_sha256(payload_path)
    atomic_json(mapping_path, mapping)


def validate_sol_response(response: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    if response.get("schema_version") != RESPONSE_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected calibration Sol response schema")
    outputs = response.get("tracks")
    if not isinstance(outputs, list) or len(outputs) != len(rows):
        raise Stage5B1AValidationError("calibration Sol track coverage mismatch")
    if [row.get("stable_track_id") for row in outputs] != [row["stable_track_id"] for row in rows]:
        raise Stage5B1AValidationError("calibration Sol track order mismatch")
    for output, expected in zip(outputs, rows):
        expected_keys = [item["candidate_key"] for item in expected["candidates"]]
        candidates = output.get("candidates")
        if not isinstance(candidates, list) or [item.get("candidate_key") for item in candidates] != expected_keys:
            raise Stage5B1AValidationError("calibration Sol candidate coverage/order mismatch")
        labels: dict[str, str] = {}
        for candidate in candidates:
            label = candidate.get("label")
            if label not in SOL_LABELS:
                raise Stage5B1AValidationError("invalid calibration Sol label")
            labels[candidate["candidate_key"]] = label
            for name in ("recording_identity_reason", "source_quality_reason"):
                if not isinstance(candidate.get(name), str) or not candidate[name].strip():
                    raise Stage5B1AValidationError(f"calibration Sol {name} is required")
            if candidate.get("uncertainty_reason") is not None and not isinstance(
                candidate["uncertainty_reason"], str
            ):
                raise Stage5B1AValidationError("invalid calibration Sol uncertainty reason")
        status = output.get("selection_status")
        selected = output.get("selected_candidate_key")
        if status not in SELECTION_STATUSES:
            raise Stage5B1AValidationError("invalid calibration Sol selection status")
        if status == "SELECTED":
            if selected not in labels or labels[selected] not in {"IDEAL", "ACCEPTABLE"}:
                raise Stage5B1AValidationError("calibration Sol selection must be safe-labeled")
        elif selected is not None:
            raise Stage5B1AValidationError("uncertain/no-safe Sol result must not select")
        if status == "NO_SAFE_CANDIDATE" and any(
            label in {"IDEAL", "ACCEPTABLE"} for label in labels.values()
        ):
            raise Stage5B1AValidationError("NO_SAFE_CANDIDATE contradicts candidate labels")
        if not isinstance(output.get("selection_rationale"), str) or not output["selection_rationale"].strip():
            raise Stage5B1AValidationError("calibration Sol selection rationale is required")
    return response


class SolBackend(Protocol):
    model: str
    version: str

    def evaluate(self, prompt: str, batch_id: str) -> tuple[dict[str, Any], dict[str, Any]]: ...


@dataclass
class CalibrationCodexBackend:
    config: CalibrationSolConfig
    executable: str = "codex"
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run

    def __post_init__(self) -> None:
        completed = self.runner([self.executable, "--version"], text=True, capture_output=True, check=False)
        if completed.returncode:
            raise Stage5B1AValidationError("unable to execute Codex CLI for calibration Sol")
        self.model = self.config.model
        self.version = (completed.stdout or completed.stderr).strip()

    def evaluate(self, prompt: str, batch_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        with tempfile.TemporaryDirectory(prefix="stage5b1b-calibration-sol-") as directory:
            output = Path(directory) / "response.json"
            command = [
                self.executable,
                "exec",
                "--model",
                self.config.model,
                "-c",
                f'model_reasoning_effort="{self.config.reasoning_effort}"',
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--output-schema",
                str(self.config.output_schema_path),
                "--json",
                "--output-last-message",
                str(output),
                "--cd",
                directory,
                "-",
            ]
            started = time.monotonic()
            completed = self.runner(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                check=False,
                timeout=self.config.timeout_seconds,
                env={**os.environ, "NO_COLOR": "1"},
            )
            elapsed = time.monotonic() - started
            event_counts, tool_events = CodexCliSolBackend._event_summary(completed.stdout)
            if completed.returncode:
                tail = (completed.stderr or completed.stdout)[-1000:]
                raise Stage5B1AValidationError(f"calibration Sol {batch_id} failed: {tail}")
            if tool_events:
                raise Stage5B1AValidationError(
                    f"calibration Sol attempted forbidden tool use: {sorted(set(tool_events))}"
                )
            if not output.is_file():
                raise Stage5B1AValidationError("calibration Sol did not produce structured output")
            raw = output.read_text(encoding="utf-8")
            return json.loads(raw), {
                "batch_id": batch_id,
                "elapsed_wall_seconds": elapsed,
                "event_type_counts": event_counts,
                "forbidden_tool_event_count": 0,
                "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
                "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
                "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            }


def _prompt(template: str, rows: list[dict[str, Any]]) -> str:
    return template.rstrip() + "\n\nBLINDED_INPUT_JSON:\n" + json.dumps(
        rows, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _empty_state(config: CalibrationSolConfig, backend: SolBackend) -> dict[str, Any]:
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "status": "RUNNING",
        "config_sha256": config.sha256,
        "manifest_sha256": config.manifest_sha256,
        "discovery_sha256": config.discovery_sha256,
        "blinded_payload_sha256": config.payload_sha256,
        "private_mapping_sha256": config.mapping_sha256,
        "prompt_template_sha256": config.prompt_sha256,
        "output_schema_sha256": config.output_schema_sha256,
        "evaluator": {
            "provider": "codex_cli",
            "model": backend.model,
            "codex_cli_version": backend.version,
            "reasoning_effort": config.reasoning_effort,
        },
        "blindness": {
            "human_labels_supplied": False,
            "resolver_features_supplied": False,
            "search_rank_supplied": False,
            "case_tags_or_rationale_supplied": False,
            "candidate_order_deterministically_shuffled": True,
            "tools_or_web_allowed": False,
            "isolated_ephemeral_working_directory": True,
        },
        "tracks": [],
        "errors": [],
        "started_at": _utc_now(),
        "updated_at": _utc_now(),
        "completed_at": None,
    }


def _validate_resume(state: dict[str, Any], config: CalibrationSolConfig) -> None:
    expected = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "config_sha256": config.sha256,
        "manifest_sha256": config.manifest_sha256,
        "discovery_sha256": config.discovery_sha256,
        "blinded_payload_sha256": config.payload_sha256,
        "private_mapping_sha256": config.mapping_sha256,
        "prompt_template_sha256": config.prompt_sha256,
        "output_schema_sha256": config.output_schema_sha256,
    }
    if any(state.get(key) != value for key, value in expected.items()):
        raise Stage5B1AValidationError("incompatible calibration Sol resume state")


def run_calibration_sol(
    config: CalibrationSolConfig,
    backend: SolBackend,
    *,
    overwrite: bool = False,
    max_batches: int | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    payload = _json_object(config.payload_path)
    rows = payload.get("tracks")
    if not isinstance(rows, list) or len(rows) != 50 or sum(len(row["candidates"]) for row in rows) != 248:
        raise Stage5B1AValidationError("blinded calibration payload must contain 50 tracks / 248 candidates")
    if config.evaluations_path.exists() and not overwrite:
        state = _json_object(config.evaluations_path)
        _validate_resume(state, config)
    else:
        state = _empty_state(config, backend)
    completed = {row["stable_track_id"]: row for row in state.get("tracks", [])}
    remaining = [row for row in rows if row["stable_track_id"] not in completed]
    batches = [remaining[i : i + config.batch_track_count] for i in range(0, len(remaining), config.batch_track_count)]
    if max_batches is not None:
        if max_batches < 1:
            raise Stage5B1AValidationError("max_batches must be positive")
        batches = batches[:max_batches]
    template = config.prompt_path.read_text(encoding="utf-8")
    for batch in batches:
        batch_id = "batch-" + "-".join(row["stable_track_id"] for row in batch)
        prompt = _prompt(template, batch)
        last_error: Exception | None = None
        for attempt in range(1, config.max_attempts + 1):
            try:
                raw, operational = backend.evaluate(prompt, batch_id)
                response = validate_sol_response(raw, batch)
                for row in response["tracks"]:
                    completed[row["stable_track_id"]] = {
                        **row,
                        "attempt": attempt,
                        "evaluated_at": _utc_now(),
                        "batch_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                        "batch_payload_sha256": value_sha256(batch),
                        "operational": operational,
                    }
                last_error = None
                break
            except (Stage5B1AValidationError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < config.max_attempts:
                    sleeper(float(attempt))
        if last_error is not None:
            state["errors"].append(
                {
                    "batch_id": batch_id,
                    "stable_track_ids": [row["stable_track_id"] for row in batch],
                    "error_type": type(last_error).__name__,
                    "message": str(last_error),
                    "attempts": config.max_attempts,
                }
            )
        state["tracks"] = [row for row in (completed.get(item["stable_track_id"]) for item in rows) if row]
        state["updated_at"] = _utc_now()
        atomic_json(config.evaluations_path, state)
    candidate_count = sum(len(row["candidates"]) for row in state["tracks"])
    complete = len(state["tracks"]) == 50 and candidate_count == 248
    state["status"] = "COMPLETE" if complete else "PARTIAL"
    state["completed_track_count"] = len(state["tracks"])
    state["completed_candidate_count"] = candidate_count
    state["completed_at"] = _utc_now() if complete else None
    state["updated_at"] = _utc_now()
    atomic_json(config.evaluations_path, state)
    return state


def mapped_sol_judgments(config: CalibrationSolConfig) -> dict[str, Any]:
    state = _json_object(config.evaluations_path)
    _validate_resume(state, config)
    if state.get("status") != "COMPLETE":
        raise Stage5B1AValidationError("calibration Sol evaluation is incomplete")
    payload = _json_object(config.payload_path)
    payload_by_id = {row["stable_track_id"]: row for row in payload["tracks"]}
    if [row.get("stable_track_id") for row in state.get("tracks", [])] != list(
        payload_by_id
    ):
        raise Stage5B1AValidationError(
            "saved calibration Sol track coverage/order changed"
        )
    for result in state["tracks"]:
        validate_sol_response(
            {"schema_version": RESPONSE_SCHEMA_VERSION, "tracks": [result]},
            [payload_by_id[result["stable_track_id"]]],
        )
        if result.get("operational", {}).get("forbidden_tool_event_count") != 0:
            raise Stage5B1AValidationError(
                "saved calibration Sol output contains tool use"
            )
    mapping = _json_object(config.mapping_path)
    mappings = {
        row["stable_track_id"]: {
            candidate["candidate_key"]: candidate
            for candidate in row["candidates"]
        }
        for row in mapping["tracks"]
    }
    if set(mappings) != set(payload_by_id):
        raise Stage5B1AValidationError("private mapping track coverage changed")
    tracks = []
    for row in state["tracks"]:
        by_key = mappings[row["stable_track_id"]]
        tracks.append(
            {
                "stable_track_id": row["stable_track_id"],
                "selection_status": row["selection_status"],
                "selected_video_id": (
                    by_key[row["selected_candidate_key"]]["youtube_video_id"]
                    if row["selected_candidate_key"] else None
                ),
                "selection_rationale": row["selection_rationale"],
                "candidates": [
                    {
                        **candidate,
                        "youtube_video_id": by_key[candidate["candidate_key"]]["youtube_video_id"],
                        "original_search_rank": by_key[candidate["candidate_key"]]["original_search_rank"],
                    }
                    for candidate in row["candidates"]
                ],
            }
        )
    return {
        "schema_version": "stage5b1b-calibration-sol-mapped-v1",
        "source_evaluations_sha256": file_sha256(config.evaluations_path),
        "source_mapping_sha256": config.mapping_sha256,
        "tracks": tracks,
    }
