from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256
from audio_similarity.stage5b3_minimal_selector import DURATION_ANOMALY_SECONDS
from audio_similarity.stage5b4_representative_v3 import (
    BENCHMARK_ID,
    FROZEN_STAGE5B3_COMMIT,
    SAMPLE_SIZE,
    freeze_v3_manifest,
    historical_manifest_paths,
    load_v3_config,
    run_frozen_selector,
    run_v3_discovery,
)
from audio_similarity.stage5b4_review import (
    LABELS,
    REVIEW_COLUMNS,
    Stage5B4ReviewStore,
    compute_v3_metrics,
    first_safe_rank,
    next_review_requirement,
    oracle_next_rank,
    validate_complete_review,
    write_closeout_artifacts,
    write_human_review_artifacts,
)


def _track(index: int) -> dict:
    return {
        "id": f"{index:022d}",
        "name": f"Fresh Song {index}",
        "artists": [{"name": f"Artist {index}"}],
        "album": {"name": f"Album {index}", "release_date": "2026-01-01"},
        "duration_ms": 180_000,
        "external_ids": {"isrc": f"USABC26{index:05d}"},
        "is_local": False,
    }


def _project(tmp_path: Path) -> tuple[Path, Path]:
    historical = (
        "reports/stage5b1a/frozen_tracks.json",
        "reports/stage5b1b/heldout_tracks.json",
        "reports/stage5b1b_fresh_challenge/challenge_tracks.json",
        "reports/stage5b_representative_library_v1/benchmark_manifest.json",
        "reports/stage5b_youtube_prior_v1/benchmark_manifest.json",
    )
    old = _track(1)
    for relative in historical:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "tracks": [{
                "spotify_track_id": old["id"],
                "title": old["name"],
                "artists": [old["artists"][0]["name"]],
            }]
        }))
    review_paths = (
        "reports/stage5b_representative_library_v1/human_review.csv",
        "reports/stage5b_youtube_prior_v1/human_review.csv",
        "reports/stage5b3_minimal_selector/human_review.csv",
    )
    for relative in review_paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"spotify_track_id\n{old['id']}\n")
    selector_source = tmp_path / "src/audio_similarity/stage5b3_minimal_selector.py"
    selector_source.parent.mkdir(parents=True, exist_ok=True)
    selector_source.write_text("# frozen test selector source\n")
    query_source = tmp_path / "src/audio_similarity/stage5b2_youtube_prior.py"
    query_source.write_text("# frozen test natural-query source\n")
    selector_artifact = tmp_path / "reports/stage5b3_minimal_selector/minimal_selector_decisions.json"
    selector_artifact.write_text(json.dumps({
        "experiment_id": "STAGE5B3_MINIMAL_YOUTUBE_SELECTOR_V1",
        "policy": {
            "duration_boundary_seconds": 20.0,
            "vetoes": [
                "UNREQUESTED_LIVE_OR_PERFORMANCE",
                "DURATION_ANOMALY_GT_20_SECONDS",
            ],
        },
        "summary": {
            "auto_select_count": 99,
            "match_uncertain_count": 1,
            "human_safe_count": 97,
            "human_wrong_count": 0,
            "human_uncertain_count": 2,
            "success_gate_passed": True,
        },
    }))
    snapshot = tmp_path / "library.private.json"
    snapshot.write_text(json.dumps({
        "schema_version": "stage5b-owner-library-snapshot-v1",
        "sources": [{"source_key": "LIKED", "tracks": [_track(i) for i in range(1, 121)]}],
    }))
    return tmp_path, snapshot


class _FakeAdapter:
    def discover_query(self, track, query, *, limit):
        assert query == f"{track.title} {track.artists[0]}"
        assert '"' not in query and " official" not in query.casefold()
        assert limit == 3
        number = int(track.stable_track_id.rsplit("_", 1)[1])
        candidates = []
        for rank in (1, 2, 3):
            title = f"Candidate {rank}"
            duration = 180.0
            if number == 2 and rank == 1:
                title = "Candidate 1 Live Stage"
            if number == 3 and rank == 1:
                duration = 220.001
            if number == 4:
                duration = 220.001 + rank
            candidates.append({
                "rank": rank,
                "provider_rank": rank,
                "youtube_video_id": f"v{number:07d}{rank:03d}",
                "canonical_url": f"https://www.youtube.com/watch?v=v{number:07d}{rank:03d}",
                "title": title,
                "uploader": "Uploader",
                "channel": "Channel",
                "duration_seconds": duration,
                "view_count": 100,
                "description": "Raw candidate metadata",
            })
        return SimpleNamespace(to_dict=lambda: {
            "track": track.to_dict(),
            "query": query,
            "provider": {"name": "yt_dlp", "version": "test"},
            "candidates": candidates,
            "candidate_video_ids": [row["youtube_video_id"] for row in candidates],
            "warnings": [],
            "error": None,
        })


class _UnavailableAdapter(_FakeAdapter):
    def discover_query(self, track, query, *, limit):
        outcome = super().discover_query(track, query, limit=limit).to_dict()
        if track.stable_track_id.endswith("_001"):
            outcome["candidates"] = []
            outcome["candidate_video_ids"] = []
        return SimpleNamespace(to_dict=lambda: outcome)


def test_manifest_is_fresh_deterministic_immutable_and_pins_selector(tmp_path) -> None:
    project, snapshot = _project(tmp_path)
    output = project / "reports/stage5b4_representative_v3"
    first = freeze_v3_manifest(project, snapshot, output)
    second = freeze_v3_manifest(project, snapshot, output)

    assert first == second
    assert first["manifest"]["benchmark_id"] == BENCHMARK_ID
    assert first["manifest"]["sampled_track_count"] == SAMPLE_SIZE
    assert first["manifest"]["historically_excluded_track_count"] == 1
    assert first["manifest"]["prior_review_exclusion_audit"][
        "uncovered_reviewed_spotify_track_count"
    ] == 0
    assert _track(1)["id"] not in {
        row["spotify_track_id"] for row in first["manifest"]["tracks"]
    }
    assert first["config"]["selector"]["source_commit"] == FROZEN_STAGE5B3_COMMIT
    assert first["config"]["selector"]["contract"]["duration_boundary_seconds"] == 20.0
    assert first["config"]["scope_guards"]["production_activation"] is False
    assert first["config"]["query"]["template"] == "{spotify_title} {primary_artist}"
    query_source = project / first["config"]["query"]["implementation"]["path"]
    assert first["config"]["query"]["implementation"]["sha256"] == file_sha256(query_source)

    value = json.loads((output / "benchmark_manifest.json").read_text())
    value["post_freeze_substitutions"] = 1
    (output / "benchmark_manifest.json").write_text(json.dumps(value))
    with pytest.raises(Stage5B1AValidationError, match="refusing to replace"):
        freeze_v3_manifest(project, snapshot, output)


def test_config_rejects_query_or_selector_contract_mutation(tmp_path) -> None:
    project, snapshot = _project(tmp_path)
    output = project / "reports/stage5b4_representative_v3"
    freeze_v3_manifest(project, snapshot, output)
    config_path = output / "benchmark_config.json"
    value = json.loads(config_path.read_text())
    value["query"]["forced_official_token"] = True
    config_path.write_text(json.dumps(value))
    with pytest.raises(Stage5B1AValidationError, match="natural-query contract"):
        load_v3_config(config_path)


def test_all_historical_track_universes_are_explicit() -> None:
    assert [path.name for path in historical_manifest_paths(Path("/project"))] == [
        "frozen_tracks.json",
        "heldout_tracks.json",
        "challenge_tracks.json",
        "benchmark_manifest.json",
        "benchmark_manifest.json",
    ]


def test_discovery_preserves_top3_and_frozen_selector_is_label_independent(tmp_path) -> None:
    project, snapshot = _project(tmp_path)
    output = project / "reports/stage5b4_representative_v3"
    freeze_v3_manifest(project, snapshot, output)
    config = load_v3_config(output / "benchmark_config.json")
    discovery = run_v3_discovery(config, _FakeAdapter(), sleep=lambda _seconds: None)
    decisions, metrics = run_frozen_selector(config)

    assert discovery["summary"]["candidate_count"] == 300
    assert discovery["scope_guards"]["candidate_reranking"] is False
    assert [row["rank"] for row in discovery["tracks"][0]["outcome"]["candidates"]] == [1, 2, 3]
    assert decisions["human_labels_visible"] is False
    assert decisions["selector"]["modified_for_v3"] is False
    assert decisions["selector"]["duration_boundary_seconds"] == DURATION_ANOMALY_SECONDS
    assert metrics["auto_select_count"] == 99
    assert metrics["match_uncertain_count"] == 1
    assert metrics["selected_rank_distribution"] == {
        "rank_1": 97, "rank_2": 2, "rank_3": 0, "none": 1
    }
    assert metrics["human_labels_used_in_decisions"] is False
    before = file_sha256(output / "automated_selector_decisions.json")
    run_frozen_selector(config)
    assert file_sha256(output / "automated_selector_decisions.json") == before


def test_sequential_oracle_then_hidden_selector_supplement(tmp_path) -> None:
    project, snapshot = _project(tmp_path)
    output = project / "reports/stage5b4_representative_v3"
    freeze_v3_manifest(project, snapshot, output)
    config = load_v3_config(output / "benchmark_config.json")
    run_v3_discovery(config, _FakeAdapter(), sleep=lambda _seconds: None)
    decisions, _ = run_frozen_selector(config)
    _, review_path = write_human_review_artifacts(config)
    store = Stage5B4ReviewStore(review_path, output / "automated_selector_decisions.json")

    supplemented = next(row for row in decisions["tracks"] if row["selected_rank"] == 2)
    case_id = supplemented["benchmark_id"]
    case = next(row for row in store.session()["cases"] if row["stable_track_id"] == case_id)
    assert case["review_phase"] == "TOP3_ORACLE"
    assert [row["rank"] for row in case["candidates"]] == [1]
    rank1_id = case["candidates"][0]["video_id"]
    store.submit(case_id, rank1_id, "IDEAL")

    case = next(row for row in store.session()["cases"] if row["stable_track_id"] == case_id)
    assert case["review_phase"] == "SELECTOR_VALIDATION"
    assert case["next_required_rank"] == 2
    assert [row["rank"] for row in case["candidates"]] == [1, 2]
    rank2_id = next(row["video_id"] for row in case["candidates"] if row["rank"] == 2)
    store.submit(case_id, rank2_id, "ACCEPTABLE")
    case = next(row for row in store.session()["cases"] if row["stable_track_id"] == case_id)
    assert case["review_complete"] is True
    assert first_safe_rank(_rows_for(review_path, case_id)) == 1


def _rows_for(path: Path, benchmark_id: str) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row["benchmark_id"] == benchmark_id]


def test_oracle_reveals_rank2_and_rank3_only_after_non_safe() -> None:
    rows = [
        {"youtube_rank": str(rank), "candidate_review_label": ""}
        for rank in (1, 2, 3)
    ]
    assert oracle_next_rank(rows) == 1
    rows[0]["candidate_review_label"] = "WRONG"
    assert oracle_next_rank(rows) == 2
    rows[1]["candidate_review_label"] = "UNCERTAIN"
    assert oracle_next_rank(rows) == 3
    rows[2]["candidate_review_label"] = "IDEAL"
    assert oracle_next_rank(rows) is None
    assert next_review_requirement(rows, 1) is None


def test_rank1_failure_requires_reason_at_closeout(tmp_path) -> None:
    project, snapshot = _project(tmp_path)
    output = project / "reports/stage5b4_representative_v3"
    freeze_v3_manifest(project, snapshot, output)
    config = load_v3_config(output / "benchmark_config.json")
    run_v3_discovery(config, _FakeAdapter(), sleep=lambda _seconds: None)
    run_frozen_selector(config)
    _, review_path = write_human_review_artifacts(config)
    with review_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for index, row in enumerate(rows):
        row["candidate_review_label"] = "WRONG" if index % 3 == 0 else "IDEAL"
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(Stage5B1AValidationError, match="failure reason missing"):
        validate_complete_review(review_path, output / "automated_selector_decisions.json")


def test_unavailable_candidate_pool_remains_in_denominator(tmp_path) -> None:
    project, snapshot = _project(tmp_path)
    output = project / "reports/stage5b4_representative_v3"
    freeze_v3_manifest(project, snapshot, output)
    config = load_v3_config(output / "benchmark_config.json")
    discovery = run_v3_discovery(config, _UnavailableAdapter(), sleep=lambda _seconds: None)
    decisions, metrics = run_frozen_selector(config)
    queue, review_path = write_human_review_artifacts(config)
    store = Stage5B4ReviewStore(review_path, output / "automated_selector_decisions.json")

    assert discovery["summary"]["zero_candidate_tracks"] == 1
    assert metrics["match_uncertain_count"] == 2
    assert queue["track_count"] == SAMPLE_SIZE
    assert queue["candidate_count"] == 297
    unavailable = next(
        row for row in store.session()["cases"] if row["stable_track_id"].endswith("_001")
    )
    assert unavailable["candidate_unavailable"] is True
    assert unavailable["review_complete"] is True
    assert unavailable["candidates"] == []


def test_closeout_report_separates_metrics_and_answers_validation_questions(tmp_path) -> None:
    project, snapshot = _project(tmp_path)
    output = project / "reports/stage5b4_representative_v3"
    freeze_v3_manifest(project, snapshot, output)
    config = load_v3_config(output / "benchmark_config.json")
    run_v3_discovery(config, _FakeAdapter(), sleep=lambda _seconds: None)
    run_frozen_selector(config)
    _, review_path = write_human_review_artifacts(config)
    with review_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["candidate_review_label"] = "IDEAL"
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    result = write_closeout_artifacts(config)
    report = (output / "representative_v3_report.md").read_text()

    assert result["automated_coverage"] == 0.99
    assert "## Frozen discovery" in report
    assert "## Critical validation answers" in report
    assert "Raw YouTube and human Top-3 oracle" in report
    assert "Frozen automated selector" in report
    assert "production activation: **false**" in report


def _metric_row(rank: int, label: str) -> dict[str, str]:
    return {
        column: "" for column in REVIEW_COLUMNS
    } | {
        "youtube_rank": str(rank),
        "candidate_video_id": f"video0000{rank}",
        "candidate_title": f"Candidate {rank}",
        "candidate_description": "",
        "candidate_review_label": label,
        "candidate_note": "not safe" if rank == 1 and label in {"WRONG", "UNCERTAIN"} else "",
    }


def test_topk_selector_and_veto_metrics_remain_separate() -> None:
    grouped = {}
    decision_tracks = []
    for index in range(1, 101):
        benchmark_id = f"track_{index:03d}"
        if index <= 90:
            labels = ("IDEAL", "", "")
        elif index <= 99:
            labels = ("WRONG", "ACCEPTABLE", "")
        else:
            labels = ("UNCERTAIN", "WRONG", "IDEAL")
        grouped[benchmark_id] = [_metric_row(rank, label) for rank, label in enumerate(labels, 1)]
        selected_rank = 2 if index > 90 else 1
        veto = index > 90
        decision_tracks.append({
            "benchmark_id": benchmark_id,
            "spotify_target": {"title": f"Song {index}"},
            "decision": "AUTO_SELECT",
            "selected_rank": selected_rank,
            "selected_video_id": grouped[benchmark_id][selected_rank - 1]["candidate_video_id"],
            "candidate_evaluations": [{
                "video_id": grouped[benchmark_id][0]["candidate_video_id"],
                "title": "Candidate 1",
                "vetoed": veto,
                "veto_reasons": ["DURATION_ANOMALY_GT_20_SECONDS"] if veto else [],
                "absolute_duration_delta_seconds": 30.0 if veto else 0.0,
            }],
        })
    topk, automated, veto, failure = compute_v3_metrics(
        grouped, {"tracks": decision_tracks}
    )

    assert topk["top1_safe_rate"] == 0.90
    assert topk["top2_safe_recall"] == 0.99
    assert topk["top3_safe_recall"] == 1.0
    assert topk["first_safe_rank_distribution"] == {
        "rank_1": 90, "rank_2": 9, "rank_3": 1, "none": 0
    }
    assert automated["auto_select_coverage"] == 1.0
    assert automated["human_safe_count"] == 99
    assert automated["human_labels_used_in_decisions"] is False
    assert veto["duration_veto"]["total"] == 10
    assert veto["duration_veto"]["rank1_wrong_true_positive_count"] == 9
    assert veto["duration_veto"]["rank1_uncertain_count"] == 1
    assert failure["top1_failure_count"] == 10


def test_review_ui_has_v3_blinding_and_sequential_mode() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "evaluation/static/stage5b1b_review.html").read_text()
    assert "stage5b4_representative_v3_review" in html
    assert "Automated decisions remain hidden" in html
    assert "Additional selector-validation judgment" in html
    assert "Reason required if rank #1 is WRONG or UNCERTAIN" in html
