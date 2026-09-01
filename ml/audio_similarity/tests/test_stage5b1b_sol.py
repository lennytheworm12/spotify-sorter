from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError
from audio_similarity.stage5b1b_sol import (
    CodexCliSolBackend,
    build_blinded_prompt,
    load_blind_inputs,
    run_sol_evaluation,
    validate_sol_response,
)
from audio_similarity.stage5b1b_sol_comparison import (
    load_audit_queue,
    propose_track_resolution,
    write_comparison_artifacts,
)
from audio_similarity.stage5b1b_sol_config import load_sol_audit_config


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "stage5b1b_sol.json"


def _response(rows: list[dict], *, uncertain: bool = False) -> dict:
    tracks = []
    for row in rows:
        candidates = []
        for index, candidate in enumerate(row["candidates"]):
            label = (
                "UNCERTAIN"
                if uncertain and index == 0
                else "IDEAL"
                if index == 0
                else "WRONG"
            )
            candidates.append(
                {
                    "video_id": candidate["video_id"],
                    "label": label,
                    "recording_identity_reason": "raw metadata judgment",
                    "source_quality_reason": "raw provenance judgment",
                    "uncertainty_reason": (
                        "metadata incomplete" if label == "UNCERTAIN" else None
                    ),
                }
            )
        tracks.append(
            {
                "stable_track_id": row["stable_track_id"],
                "selection_status": "UNCERTAIN" if uncertain else "SELECTED",
                "selected_video_id": (
                    None if uncertain else row["candidates"][0]["video_id"]
                ),
                "selection_rationale": "fixture selection",
                "candidates": candidates,
            }
        )
    return {
        "schema_version": "stage5b1b-sol-batch-response-v1",
        "tracks": tracks,
    }


class FakeBackend:
    model = "gpt-5.6-sol"
    version = "codex-cli fixture"

    def __init__(self, rows_by_id: dict[str, dict]) -> None:
        self.rows_by_id = rows_by_id
        self.calls: list[str] = []

    def evaluate(self, prompt: str, batch_id: str):
        self.calls.append(batch_id)
        ids = [stable_id for stable_id in self.rows_by_id if stable_id in batch_id]
        return _response([self.rows_by_id[stable_id] for stable_id in ids]), {
            "batch_id": batch_id,
            "elapsed_wall_seconds": 0.01,
            "event_type_counts": {"turn.completed": 1},
            "forbidden_tool_event_count": 0,
            "stdout_sha256": "a" * 64,
            "stderr_sha256": "b" * 64,
            "response_sha256": "c" * 64,
        }


def _temp_config(tmp_path: Path):
    config = load_sol_audit_config(CONFIG)
    artifacts = {key: tmp_path / path.name for key, path in config.artifacts.items()}
    return replace(config, artifacts=artifacts)


def test_config_and_blind_inputs_are_frozen_and_feature_free() -> None:
    config = load_sol_audit_config(CONFIG)
    manifest, rows = load_blind_inputs(config)
    assert manifest.sha256 == (
        "39557ede8f07bde129ad23d2bc64a0faf0fff755356cd87f2054e14f91d81e5a"
    )
    assert len(rows) == 50
    assert sum(len(row["candidates"]) for row in rows) == 248
    prompt, _ = build_blinded_prompt(
        rows[:1],
        prompt_version=config.evaluator.prompt_version,
        description_limit=config.evaluator.description_max_characters,
    )
    assert "gpt-5.6-sol" not in prompt
    assert '"recording_eligible"' not in prompt
    assert '"title_similarity"' not in prompt
    assert '"source_type"' not in prompt
    assert '"candidate_review_label"' not in prompt
    assert '"case_tags"' not in prompt
    assert '"case_rationale"' not in prompt
    assert "Do not browse the web, call tools" in prompt

    schema = json.loads(config.evaluator.output_schema_path.read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"] == {
        "type": "string",
        "const": "stage5b1b-sol-batch-response-v1",
    }


def test_response_validation_rejects_missing_candidate() -> None:
    config = load_sol_audit_config(CONFIG)
    _, rows = load_blind_inputs(config)
    response = _response(rows[:1])
    response["tracks"][0]["candidates"].pop()
    with pytest.raises(Stage5B1AValidationError, match="coverage/order"):
        validate_sol_response(response, rows[:1])


def test_response_validation_rejects_wrong_selected_label() -> None:
    config = load_sol_audit_config(CONFIG)
    _, rows = load_blind_inputs(config)
    response = _response(rows[:1])
    response["tracks"][0]["candidates"][0]["label"] = "WRONG"
    with pytest.raises(Stage5B1AValidationError, match="safe-labeled"):
        validate_sol_response(response, rows[:1])


def test_resumable_fake_sol_evaluation_and_comparison(tmp_path: Path) -> None:
    config = _temp_config(tmp_path)
    _, rows = load_blind_inputs(config)
    backend = FakeBackend({row["stable_track_id"]: row for row in rows})
    partial = run_sol_evaluation(config, backend, max_batches=1)
    assert partial["status"] == "PARTIAL"
    assert partial["completed_track_count"] == 5
    assert len(backend.calls) == 1

    result = run_sol_evaluation(config, backend)
    assert result["status"] == "COMPLETE"
    assert result["completed_track_count"] == 50
    assert result["completed_candidate_count"] == 248
    assert len(backend.calls) == 10

    rerun = FakeBackend({row["stable_track_id"]: row for row in rows})
    resumed = run_sol_evaluation(config, rerun)
    assert resumed["status"] == "COMPLETE"
    assert rerun.calls == []

    summary = write_comparison_artifacts(config)
    assert summary["track_count"] == 50
    assert config.artifacts["comparison"].is_file()
    queue = load_audit_queue(
        config.artifacts["manual_audit_queue"], config.manifest_sha256
    )
    assert len(queue) == summary["manual_audit_track_count"]
    assert len(queue) == len(set(queue))
    assert sum(map(len, queue.values())) == summary["manual_audit_candidate_count"]


def test_tool_event_detection_is_fail_closed() -> None:
    stdout = "\n".join(
        [
            json.dumps({"type": "thread.started"}),
            json.dumps(
                {"type": "item.completed", "item": {"type": "web_search"}}
            ),
        ]
    )
    counts, tools = CodexCliSolBackend._event_summary(stdout)
    assert counts == {"item.completed": 1, "thread.started": 1}
    assert tools == ["web_search"]


def test_codex_backend_uses_metadata_only_isolated_invocation() -> None:
    config = load_sol_audit_config(CONFIG)
    calls: list[list[str]] = []

    def runner(command, **kwargs):
        calls.append(command)
        if command[1:] == ["--version"]:
            return subprocess.CompletedProcess(command, 0, "codex-cli test\n", "")
        output = Path(command[command.index("--output-last-message") + 1])
        _, rows = load_blind_inputs(config)
        output.write_text(json.dumps(_response(rows[:1])), encoding="utf-8")
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started"}),
                json.dumps(
                    {"type": "item.completed", "item": {"type": "agent_message"}}
                ),
            ]
        )
        return subprocess.CompletedProcess(command, 0, stdout, "")

    backend = CodexCliSolBackend(config, executable="codex", runner=runner)
    _, rows = load_blind_inputs(config)
    response, operational = backend.evaluate("fixture prompt", "fixture-batch")
    validate_sol_response(response, rows[:1])
    command = calls[-1]
    assert command[command.index("--model") + 1] == "gpt-5.6-sol"
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert "--ignore-rules" in command
    assert "--json" in command
    assert operational["forbidden_tool_event_count"] == 0


def test_uncalibrated_proposal_abstains_without_exact_identity() -> None:
    feature = {
        "recording_eligible": True,
        "ineligible_auto_match_reasons": [],
        "identity": {
            "title_exact_normalized_match": False,
            "primary_artist_match": True,
            "title_similarity": 0.8,
            "artist_similarity": 1.0,
        },
        "versions": {"version_absent_count": 0, "version_conflict_count": 0},
        "duration": {"absolute_duration_delta_seconds": 1.0},
        "source": {
            "source_type": "OFFICIAL_AUDIO",
            "source_preference_tier": 4,
        },
        "description_evidence": {
            "album_evidence_match": None,
            "release_year_evidence_match": None,
        },
        "weak_evidence": {
            "view_rank_among_plausible_candidates": 1,
            "search_rank": 1,
        },
    }
    track_row = {
        "candidates": [
            {
                "candidate": {
                    "youtube_video_id": "abcdefghijk",
                    "rank": 1,
                    "title": "near title",
                },
                "features": feature,
            }
        ]
    }
    result = propose_track_resolution(track_row, resolver_version="fixture-v1")
    assert result["status"] == "MATCH_UNCERTAIN"
    assert result["selected_video_id"] is None
    assert result["production_auto_match_enabled"] is False
