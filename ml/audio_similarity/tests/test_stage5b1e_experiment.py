from __future__ import annotations

import csv
import json
import shutil
from dataclasses import replace
from pathlib import Path

from audio_similarity.stage5b1a2_ytdlp import YtDlpBackendResponse, YtDlpDiscoveryAdapter
from audio_similarity.stage5b1a_config import QueryConfig
from audio_similarity.stage5b1b_challenge import load_challenge_config, load_challenge_manifest
from audio_similarity.stage5b1e_experiment import (
    DISCOVERY_SCHEMA_VERSION,
    _replay_candidate_pool,
    evaluate,
    expected_strategy_artifact,
    run_discovery,
    select_query_strategy,
    write_evaluation,
)
from audio_similarity.stage5b1e_queries import STRATEGY_IDS, load_stage5b1e_config


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1e_natural_query_evaluation.json"
FROZEN_DISCOVERY = ROOT / "reports/stage5b1b_fresh_challenge/challenge_ytdlp_discovery.json"
STAGE5B1E_DISCOVERY = ROOT / "reports/stage5b1e_natural_query_evaluation/query_discovery_results.json"


class FakeBackend:
    version = "test-yt-dlp"

    def __init__(self):
        self.expressions: list[str] = []

    def search(self, expression: str) -> YtDlpBackendResponse:
        self.expressions.append(expression)
        video_id = f"Q{len(self.expressions):010d}"
        return YtDlpBackendResponse(
            info={
                "entries": [{
                    "id": video_id,
                    "ie_key": "Youtube",
                    "title": f"Candidate {len(self.expressions)}",
                    "duration": 200,
                    "uploader": "Fixture",
                }]
            },
            warnings=(),
            version=self.version,
        )


def test_discovery_runner_is_sequential_metadata_only_and_checkpointed(tmp_path):
    config = load_stage5b1e_config(CONFIG)
    config = replace(config, artifacts=config.artifacts | {"discovery": tmp_path / "discovery.json"})
    strategies = expected_strategy_artifact(config)
    backend = FakeBackend()
    adapter = YtDlpDiscoveryAdapter(
        config.provider,
        QueryConfig("unused", "{normalized_title}", False),
        backend,
        sleep=lambda _: None,
    )
    sleeps: list[float] = []
    checkpoints: list[dict] = []
    result = run_discovery(
        config,
        strategies,
        adapter,
        sleep=sleeps.append,
        now=lambda: "2026-09-02T00:00:00+00:00",
        checkpoint=lambda value: checkpoints.append(value),
    )
    assert result["schema_version"] == DISCOVERY_SCHEMA_VERSION
    assert result["status"] == "DISCOVERY_COMPLETE"
    assert len(backend.expressions) == 200
    assert len(checkpoints) == 201
    assert len(sleeps) == 199
    assert all(expression.startswith("ytsearch5:") for expression in backend.expressions)
    assert result["media_activity"]["audio_downloads"] == 0
    assert result["media_activity"]["video_downloads"] == 0

    config.artifacts["discovery"].write_text(json.dumps(result))
    resumed_backend = FakeBackend()
    resumed_adapter = YtDlpDiscoveryAdapter(
        config.provider,
        QueryConfig("unused", "{normalized_title}", False),
        resumed_backend,
        sleep=lambda _: None,
    )
    resumed_sleeps: list[float] = []
    resumed = run_discovery(
        config,
        strategies,
        resumed_adapter,
        sleep=resumed_sleeps.append,
        now=lambda: "2026-09-02T00:00:01+00:00",
        checkpoint=lambda _value: None,
    )
    assert resumed["status"] == "DISCOVERY_COMPLETE"
    assert resumed_backend.expressions == []
    assert resumed_sleeps == []


def _control_repeated_discovery(config, tmp_path):
    frozen = json.loads(FROZEN_DISCOVERY.read_text())
    tracks = []
    for row in frozen["tracks"]:
        tracks.append({
            "track": row["track"],
            "strategies": [
                {
                    "strategy_id": strategy_id,
                    "query": f"fixture {strategy_id}",
                    "requested_at_utc": "2026-09-02T00:00:00Z",
                    "completed_at_utc": "2026-09-02T00:00:00Z",
                    "request": {"download": False},
                    "provider": {"name": "yt_dlp", "version": "fixture"},
                    "candidates": row["candidates"],
                    "candidate_video_ids": row["candidate_video_ids"],
                    "warnings": [],
                    "error": None,
                }
                for strategy_id in STRATEGY_IDS
            ],
        })
    discovery = {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "experiment_id": "stage5b1e_natural_query_evaluation_v1",
        "config_sha256": config.sha256,
        "strategies_sha256": "fixture",
        "status": "DISCOVERY_COMPLETE",
        "started_at_utc": "2026-09-02T00:00:00Z",
        "completed_at_utc": "2026-09-02T00:00:01Z",
        "provider_mode": {"metadata_only": True},
        "summary": {},
        "tracks": tracks,
        "media_activity": {
            "audio_downloads": 0, "video_downloads": 0, "stage5a_calls": 0,
            "clap_calls": 0, "muq_calls": 0,
        },
    }
    path = tmp_path / "discovery.json"
    path.write_text(json.dumps(discovery))
    return replace(config, artifacts=config.artifacts | {"discovery": path}), discovery


def test_identical_candidate_pools_replay_identically_without_resolver_changes(tmp_path):
    config, discovery = _control_repeated_discovery(load_stage5b1e_config(CONFIG), tmp_path)
    replays, comparison = evaluate(config, discovery)
    assert replays["frozen_original_pool_regression"]["combined_auto_match_count"] == 42
    assert replays["resolver_layers_unchanged"] is True
    assert replays["track_strategy_replay_count"] == 200
    assert {
        comparison["strategies"][strategy]["resolver_auto_match_count"]
        for strategy in STRATEGY_IDS
    } == {42}
    assert all(
        comparison["strategies"][strategy]["resolver_coverage"] == 0.84
        for strategy in STRATEGY_IDS
    )


def test_audit_queue_is_deterministic_and_provider_separated(tmp_path):
    config, discovery = _control_repeated_discovery(load_stage5b1e_config(CONFIG), tmp_path)
    outputs = {
        name: tmp_path / path.name for name, path in config.artifacts.items()
    }
    config = replace(config, artifacts=outputs | {"discovery": config.artifacts["discovery"]})
    first = write_evaluation(config, discovery)
    second = write_evaluation(config, discovery)
    assert first[2] == second[2]
    assert first[2]["remaining_judgments"] == 0
    assert first[1]["production_query_activated"] is False
    assert first[1]["selection_status"] == "ADOPT_NATURAL_TITLE"


def test_completed_experiment_review_does_not_remove_its_frozen_queue_rows(tmp_path):
    config = load_stage5b1e_config(CONFIG)
    outputs = {name: tmp_path / path.name for name, path in config.artifacts.items()}
    shutil.copyfile(STAGE5B1E_DISCOVERY, outputs["discovery"])
    config = replace(config, artifacts=outputs)
    discovery = json.loads(outputs["discovery"].read_text())

    first = write_evaluation(config, discovery)
    assert first[2]["required_judgments"] == 10
    with outputs["human_review"].open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["candidate_review_label"] = "ACCEPTABLE"
    with outputs["human_review"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    second = write_evaluation(config, discovery)
    assert second[2]["cases"] == first[2]["cases"]
    assert second[2]["required_judgments"] == 10
    assert second[2]["completed_judgments"] == 10
    assert second[2]["remaining_judgments"] == 0


def test_frozen_manifest_still_has_exactly_50_tracks():
    config = load_stage5b1e_config(CONFIG)
    challenge = load_challenge_config(config.challenge_config_path)
    manifest = load_challenge_manifest(
        challenge.manifest_path, expected_sha256=challenge.manifest_sha256
    )
    assert len(manifest.tracks) == 50


def test_empty_candidate_pool_becomes_uncertain_without_entering_frozen_fallbacks():
    track = load_challenge_manifest(
        load_challenge_config(load_stage5b1e_config(CONFIG).challenge_config_path).manifest_path,
        expected_sha256=load_challenge_config(
            load_stage5b1e_config(CONFIG).challenge_config_path
        ).manifest_sha256,
    ).tracks[0].track
    decision = _replay_candidate_pool(track, [], policy=None, boundaries=None)
    assert decision["selected_stage"] == "MATCH_UNCERTAIN"
    assert decision["final_decision"]["uncertainty_reason"] == "NO_CANDIDATES"


def test_query_selection_waits_for_audit_then_uses_predeclared_metric_priority():
    strategies = {}
    for index, strategy_id in enumerate(STRATEGY_IDS):
        strategies[strategy_id] = {
            "known_human_safe_recall": {"recall_at_5": 0.8 + index * 0.01},
            "resolver_coverage": 0.8,
            "selected_human_label_counts": {},
            "candidate_set_failure_count": 3,
        }
    comparison = {"strategies": strategies}
    assert select_query_strategy(
        comparison, human_audit_complete=False
    ) == "NO_CLEAR_WINNER_PENDING_TARGETED_HUMAN_REVIEW"
    assert select_query_strategy(
        comparison, human_audit_complete=True
    ) == "ADOPT_CORE_TITLE_ARTIST_VERSION"
    strategies["Q3_CORE_TITLE_ARTIST_VERSION"]["selected_human_label_counts"] = {
        "WRONG": 1
    }
    assert select_query_strategy(
        comparison, human_audit_complete=True
    ) == "ADOPT_NATURAL_TITLE_PLUS_ARTIST"
