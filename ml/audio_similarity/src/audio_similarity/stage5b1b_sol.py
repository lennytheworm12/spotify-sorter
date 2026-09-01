"""Blinded, resumable Sol evaluation over frozen raw Stage 5B.1B evidence."""
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
from typing import Any, Callable, Protocol, Sequence

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b1b_manifest import HeldoutManifest, load_heldout_manifest
from .stage5b1b_sol_config import SolAuditConfig


RESPONSE_SCHEMA_VERSION = "stage5b1b-sol-batch-response-v1"
EVALUATION_SCHEMA_VERSION = "stage5b1b-sol-evaluations-v1"
SOL_LABELS = {"IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"}
SELECTION_STATUSES = {"SELECTED", "NO_SAFE_CANDIDATE", "UNCERTAIN"}
_TOOL_ITEM_TYPES = {
    "command_execution",
    "file_change",
    "mcp_tool_call",
    "tool_call",
    "web_search",
    "web_search_call",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def value_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def load_blind_inputs(config: SolAuditConfig) -> tuple[HeldoutManifest, list[dict[str, Any]]]:
    """Read only manifest + raw yt-dlp results; resolver artifacts are forbidden here."""
    if file_sha256(config.discovery_path) != config.discovery_sha256:
        raise Stage5B1AValidationError("frozen discovery hash changed before Sol evaluation")
    manifest = load_heldout_manifest(
        config.manifest_path, expected_sha256=config.manifest_sha256
    )
    discovery = _load_json(config.discovery_path)
    rows = discovery.get("tracks")
    if not isinstance(rows, list):
        raise Stage5B1AValidationError("held-out discovery tracks must be an array")
    expected_ids = list(manifest.stable_track_ids)
    actual_ids = [
        row.get("track", {}).get("stable_track_id")
        if isinstance(row, dict) and isinstance(row.get("track"), dict)
        else None
        for row in rows
    ]
    if actual_ids != expected_ids:
        raise Stage5B1AValidationError("discovery tracks do not match frozen manifest order")

    manifest_by_id = {item.track.stable_track_id: item for item in manifest.tracks}
    blind_rows: list[dict[str, Any]] = []
    for row in rows:
        track = row["track"]
        stable_id = track["stable_track_id"]
        item = manifest_by_id[stable_id]
        frozen_track = item.track.to_dict()
        if track != frozen_track:
            raise Stage5B1AValidationError(
                f"discovery target metadata diverges from frozen manifest for {stable_id}"
            )
        candidates = row.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise Stage5B1AValidationError(f"no candidates for blinded track {stable_id}")
        normalized_candidates = []
        seen: set[str] = set()
        for expected_rank, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, dict):
                raise Stage5B1AValidationError("candidate must be an object")
            video_id = str(candidate.get("youtube_video_id") or "")
            if not video_id or video_id in seen or candidate.get("rank") != expected_rank:
                raise Stage5B1AValidationError(
                    f"invalid blinded candidate identity/order for {stable_id}"
                )
            seen.add(video_id)
            normalized_candidates.append(
                {
                    "rank": expected_rank,
                    "video_id": video_id,
                    "url": candidate.get("canonical_url") or candidate.get("url"),
                    "title": candidate.get("title"),
                    "uploader": candidate.get("uploader"),
                    "channel": candidate.get("channel"),
                    "duration_seconds": candidate.get("duration_seconds"),
                    "description": candidate.get("description"),
                    "view_count": candidate.get("view_count"),
                    "availability": candidate.get("availability"),
                    "live_status": candidate.get("live_status"),
                }
            )
        blind_rows.append(
            {
                "stable_track_id": stable_id,
                "target": {
                    "spotify_track_id": frozen_track.get("spotify_track_id"),
                    "title": frozen_track.get("title"),
                    "artists": list(frozen_track.get("artists") or []),
                    "album": frozen_track.get("album"),
                    "duration_ms": frozen_track.get("duration_ms"),
                    "release_year": frozen_track.get("release_year"),
                    "isrc": frozen_track.get("isrc"),
                },
                "case_tags": list(item.case_tags),
                "case_rationale": item.case_rationale,
                "query": row.get("query"),
                "candidates": normalized_candidates,
            }
        )
    return manifest, blind_rows


def _prompt_payload(rows: Sequence[dict[str, Any]], description_limit: int) -> list[dict[str, Any]]:
    payload = [
        {
            "stable_track_id": row["stable_track_id"],
            "target": row["target"],
            "query": row["query"],
            "candidates": row["candidates"],
        }
        for row in json.loads(json.dumps(list(rows), ensure_ascii=False))
    ]
    for row in payload:
        for candidate in row["candidates"]:
            description = candidate.get("description")
            if isinstance(description, str) and len(description) > description_limit:
                candidate["description"] = description[:description_limit]
                candidate["description_truncated"] = True
            else:
                candidate["description_truncated"] = False
    return payload


def build_blinded_prompt(
    rows: Sequence[dict[str, Any]], *, prompt_version: str, description_limit: int
) -> tuple[str, str]:
    """Build the complete model input without importing or naming resolver features."""
    payload = _prompt_payload(rows, description_limit)
    prompt = f"""You are the blinded semantic evaluator for a YouTube music-source validation set.

Protocol version: {prompt_version}

Judge ONLY the Spotify-style target metadata and raw yt-dlp candidate metadata in the JSON payload below. Do not browse the web, call tools, inspect files, or use any resolver-derived features. Do not infer that rank 1 is correct. Uploader/channel is provenance and may legitimately be a label, distributor, Topic channel, VEVO channel, or entertainment company rather than the performer.

For every candidate, assign exactly one label:
- IDEAL: the intended recording and a preferred clean source for audio representation (often the correct Art Track/Topic or Official Audio).
- ACCEPTABLE: the intended recording and safe enough, but not the preferred clean source (for example a clean lyric upload or compatible music video).
- WRONG: wrong song, performer, recording, or target-relative version (cover, wrong remix, live/studio mismatch, sped/slowed variant, different rerecording, and similar explicit conflicts).
- UNCERTAIN: the supplied metadata is insufficient to decide safely.

Recording identity comes before source preference. A canonical upload of the wrong version is WRONG; a less canonical upload of the correct named version can be acceptable. Missing evidence is weak; explicit contradictory evidence is strong. Duration, descriptions, album/year, and provenance are evidence, not infallible truth. Popularity and search rank are only weak tie-breakers and never override an identity conflict.

Then make one track-level source decision:
- SELECTED with selected_video_id only when at least one candidate is IDEAL or ACCEPTABLE; choose the cleanest reasonable source among compatible candidates.
- NO_SAFE_CANDIDATE when every candidate is confidently WRONG.
- UNCERTAIN when the metadata does not support a safe source decision.

Multiple candidates may be IDEAL or ACCEPTABLE. Keep reasons concise and evidence-specific. Return only the response matching the required JSON schema.

BLINDED_INPUT_JSON:
{json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))}
"""
    return prompt, value_sha256(payload)


def validate_sol_response(
    response: dict[str, Any], rows: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    if response.get("schema_version") != RESPONSE_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Sol response schema")
    outputs = response.get("tracks")
    if not isinstance(outputs, list) or len(outputs) != len(rows):
        raise Stage5B1AValidationError("Sol response track count mismatch")
    expected_by_id = {row["stable_track_id"]: row for row in rows}
    if [item.get("stable_track_id") for item in outputs if isinstance(item, dict)] != list(expected_by_id):
        raise Stage5B1AValidationError("Sol response track order/identity mismatch")

    for output in outputs:
        stable_id = output["stable_track_id"]
        expected = expected_by_id[stable_id]
        status = output.get("selection_status")
        selected = output.get("selected_video_id")
        if status not in SELECTION_STATUSES:
            raise Stage5B1AValidationError("invalid Sol selection status")
        expected_ids = [candidate["video_id"] for candidate in expected["candidates"]]
        candidates = output.get("candidates")
        if not isinstance(candidates, list):
            raise Stage5B1AValidationError("Sol candidates must be an array")
        actual_ids = [candidate.get("video_id") for candidate in candidates if isinstance(candidate, dict)]
        if actual_ids != expected_ids:
            raise Stage5B1AValidationError("Sol candidate coverage/order mismatch")
        labels: dict[str, str] = {}
        for candidate in candidates:
            label = candidate.get("label")
            if label not in SOL_LABELS:
                raise Stage5B1AValidationError("invalid Sol candidate label")
            labels[candidate["video_id"]] = label
            for key in ("recording_identity_reason", "source_quality_reason"):
                if not isinstance(candidate.get(key), str) or not candidate[key].strip():
                    raise Stage5B1AValidationError(f"Sol candidate {key} is required")
            uncertainty = candidate.get("uncertainty_reason")
            if uncertainty is not None and not isinstance(uncertainty, str):
                raise Stage5B1AValidationError("invalid Sol uncertainty reason")
        if status == "SELECTED":
            if selected not in labels or labels[selected] not in {"IDEAL", "ACCEPTABLE"}:
                raise Stage5B1AValidationError("Sol selected candidate must be safe-labeled")
        elif selected is not None:
            raise Stage5B1AValidationError("non-selected Sol status must use null video ID")
        if status == "NO_SAFE_CANDIDATE" and any(
            label in {"IDEAL", "ACCEPTABLE"} for label in labels.values()
        ):
            raise Stage5B1AValidationError("NO_SAFE_CANDIDATE contradicts safe labels")
        if not isinstance(output.get("selection_rationale"), str) or not output["selection_rationale"].strip():
            raise Stage5B1AValidationError("Sol selection rationale is required")
    return response


class SolBackend(Protocol):
    model: str
    version: str

    def evaluate(self, prompt: str, batch_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return structured output plus non-semantic operational provenance."""


@dataclass
class CodexCliSolBackend:
    config: SolAuditConfig
    executable: str = "codex"
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run

    def __post_init__(self) -> None:
        self.model = self.config.evaluator.model
        version = self.runner(
            [self.executable, "--version"],
            text=True,
            capture_output=True,
            check=False,
        )
        if version.returncode != 0:
            raise Stage5B1AValidationError("unable to execute Codex CLI")
        self.version = (version.stdout or version.stderr).strip()

    @staticmethod
    def _event_summary(stdout: str) -> tuple[dict[str, int], list[str]]:
        event_counts: dict[str, int] = {}
        tool_events: list[str] = []
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = str(event.get("type") or "unknown")
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
            item = event.get("item")
            if isinstance(item, dict):
                item_type = str(item.get("type") or "")
                if item_type in _TOOL_ITEM_TYPES:
                    tool_events.append(item_type)
        return dict(sorted(event_counts.items())), tool_events

    def evaluate(self, prompt: str, batch_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        settings = self.config.evaluator
        with tempfile.TemporaryDirectory(prefix="stage5b1b-sol-") as directory:
            working = Path(directory)
            output = working / "response.json"
            command = [
                self.executable,
                "exec",
                "--model",
                settings.model,
                "-c",
                f'model_reasoning_effort="{settings.reasoning_effort}"',
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--output-schema",
                str(settings.output_schema_path),
                "--json",
                "--output-last-message",
                str(output),
                "--cd",
                str(working),
                "-",
            ]
            started = time.monotonic()
            completed = self.runner(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                check=False,
                timeout=settings.timeout_seconds,
                env={**os.environ, "NO_COLOR": "1"},
            )
            elapsed = time.monotonic() - started
            counts, tool_events = self._event_summary(completed.stdout)
            if completed.returncode != 0:
                tail = (completed.stderr or completed.stdout)[-1000:]
                raise Stage5B1AValidationError(
                    f"Codex CLI batch {batch_id} failed ({completed.returncode}): {tail}"
                )
            if tool_events:
                raise Stage5B1AValidationError(
                    f"blinded Sol batch attempted forbidden tool use: {sorted(set(tool_events))}"
                )
            if not output.is_file():
                raise Stage5B1AValidationError("Codex CLI did not write structured output")
            raw = output.read_text(encoding="utf-8")
            try:
                response = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise Stage5B1AValidationError("Codex CLI output is not JSON") from exc
            return response, {
                "batch_id": batch_id,
                "elapsed_wall_seconds": elapsed,
                "event_type_counts": counts,
                "forbidden_tool_event_count": 0,
                "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
                "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
                "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            }


def _empty_evaluation(config: SolAuditConfig, backend: SolBackend) -> dict[str, Any]:
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "status": "RUNNING",
        "experiment_id": "stage5b1b_candidate_resolution_sol_audit",
        "config_sha256": config.sha256,
        "manifest_sha256": config.manifest_sha256,
        "discovery_sha256": config.discovery_sha256,
        "prompt_version": config.evaluator.prompt_version,
        "output_schema_sha256": config.evaluator.output_schema_sha256,
        "evaluator": {
            "provider": config.evaluator.provider,
            "model": backend.model,
            "codex_cli_version": backend.version,
            "reasoning_effort": config.evaluator.reasoning_effort,
        },
        "blindness": {
            "input_artifacts": ["heldout_tracks", "heldout_ytdlp_discovery"],
            "resolver_features_supplied_to_model": False,
            "human_labels_supplied_to_model": False,
            "web_or_tool_use_allowed": False,
            "isolated_working_directory": True,
            "ignore_user_config": True,
            "ignore_rules": True,
        },
        "expected_track_count": 50,
        "expected_candidate_count": 248,
        "tracks": [],
        "errors": [],
        "started_at": _utc_now(),
        "updated_at": _utc_now(),
        "completed_at": None,
    }


def _validate_resume(value: dict[str, Any], config: SolAuditConfig) -> None:
    expected = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "config_sha256": config.sha256,
        "manifest_sha256": config.manifest_sha256,
        "discovery_sha256": config.discovery_sha256,
        "prompt_version": config.evaluator.prompt_version,
        "output_schema_sha256": config.evaluator.output_schema_sha256,
    }
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            raise Stage5B1AValidationError(f"incompatible Sol resume artifact: {key}")


def run_sol_evaluation(
    config: SolAuditConfig,
    backend: SolBackend,
    *,
    overwrite: bool = False,
    max_batches: int | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    manifest, blind_rows = load_blind_inputs(config)
    output = config.artifacts["sol_evaluations"]
    if output.exists() and not overwrite:
        state = _load_json(output)
        _validate_resume(state, config)
    else:
        state = _empty_evaluation(config, backend)
    completed_by_id = {
        item["stable_track_id"]: item
        for item in state.get("tracks", [])
        if isinstance(item, dict) and item.get("stable_track_id")
    }
    unknown = set(completed_by_id) - set(manifest.stable_track_ids)
    if unknown:
        raise Stage5B1AValidationError("Sol resume artifact contains unknown tracks")
    remaining = [row for row in blind_rows if row["stable_track_id"] not in completed_by_id]
    size = config.evaluator.batch_track_count
    errors: list[dict[str, Any]] = list(state.get("errors") or [])

    if max_batches is not None and max_batches < 1:
        raise Stage5B1AValidationError("max_batches must be at least 1")
    pending_batches = [remaining[offset : offset + size] for offset in range(0, len(remaining), size)]
    if max_batches is not None:
        pending_batches = pending_batches[:max_batches]

    for batch_number, batch in enumerate(pending_batches, start=1):
        batch_id = f"batch-{batch_number:03d}-" + "-".join(
            row["stable_track_id"] for row in batch
        )
        prompt, blind_input_sha = build_blinded_prompt(
            batch,
            prompt_version=config.evaluator.prompt_version,
            description_limit=config.evaluator.description_max_characters,
        )
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        last_error: Exception | None = None
        for attempt in range(1, config.evaluator.max_attempts + 1):
            try:
                raw_response, operational = backend.evaluate(prompt, batch_id)
                response = validate_sol_response(raw_response, batch)
                for result in response["tracks"]:
                    completed_by_id[result["stable_track_id"]] = {
                        **result,
                        "blind_input_sha256": blind_input_sha,
                        "prompt_sha256": prompt_sha,
                        "attempt": attempt,
                        "evaluated_at": _utc_now(),
                        "operational": operational,
                    }
                last_error = None
                break
            except (Stage5B1AValidationError, subprocess.TimeoutExpired) as exc:
                last_error = exc
                if attempt < config.evaluator.max_attempts:
                    sleeper(float(attempt))
        if last_error is not None:
            errors.append(
                {
                    "batch_id": batch_id,
                    "stable_track_ids": [row["stable_track_id"] for row in batch],
                    "error_type": type(last_error).__name__,
                    "message": str(last_error),
                    "attempts": config.evaluator.max_attempts,
                    "recorded_at": _utc_now(),
                }
            )
        state["tracks"] = [
            completed_by_id[stable_id]
            for stable_id in manifest.stable_track_ids
            if stable_id in completed_by_id
        ]
        state["errors"] = errors
        state["updated_at"] = _utc_now()
        atomic_json(output, state)

    candidate_count = sum(len(row["candidates"]) for row in state["tracks"])
    complete = len(state["tracks"]) == len(blind_rows) and candidate_count == 248
    state["status"] = "COMPLETE" if complete else "PARTIAL"
    state["completed_track_count"] = len(state["tracks"])
    state["completed_candidate_count"] = candidate_count
    state["completed_at"] = _utc_now() if complete else None
    state["updated_at"] = _utc_now()
    atomic_json(output, state)
    return state


def load_sol_evaluations(path: str | Path, config: SolAuditConfig) -> dict[str, Any]:
    value = _load_json(path)
    _validate_resume(value, config)
    if value.get("status") != "COMPLETE":
        raise Stage5B1AValidationError("Sol evaluation is not complete")
    manifest, blind_rows = load_blind_inputs(config)
    if [row.get("stable_track_id") for row in value.get("tracks", [])] != list(
        manifest.stable_track_ids
    ):
        raise Stage5B1AValidationError("Sol evaluation track coverage mismatch")
    by_id = {row["stable_track_id"]: row for row in blind_rows}
    for result in value["tracks"]:
        validate_sol_response(
            {"schema_version": RESPONSE_SCHEMA_VERSION, "tracks": [result]},
            [by_id[result["stable_track_id"]]],
        )
        operational = result.get("operational") or {}
        if operational.get("forbidden_tool_event_count") != 0:
            raise Stage5B1AValidationError("Sol evaluation contains forbidden tool use")
    return value
