from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256
from audio_similarity.stage5b1b_artifacts import atomic_json
from audio_similarity.stage5b1b_challenge import (
    DISCOVERY_SCHEMA_VERSION,
    POLICY_IDS,
    load_challenge_config,
    load_challenge_manifest,
    load_frozen_policies,
    materialize_and_resolve,
    verify_non_overlap,
)
from audio_similarity.stage5b1b_challenge_audit import (
    REVIEW_COLUMNS,
    build_comparison_and_queue,
    evaluate_review,
    write_review,
)
from audio_similarity.stage5b1b_challenge_sol import build_blinded_payload


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1b_fresh_challenge.json"
MANIFEST_SHA = "e2e9a1ab43f568dd9de853c2964f341ee0d0e2631ca87f732d0d4326ab990f79"
POLICY_SHA = "bbc527aa9a734b0aebbfafcb2775b479541a5e0248503627c14b8f429f708d5a"


def inputs():
    config = load_challenge_config(CONFIG)
    manifest = load_challenge_manifest(config.manifest_path, expected_sha256=config.manifest_sha256)
    return config, manifest


def fake_discovery(config, manifest):
    tracks = []
    for index, item in enumerate(manifest.tracks, start=1):
        track = item.track.to_dict()
        delta = 5.0 if index == 1 else 1.0
        video_id = f"C{index:010d}"
        candidate = {
            "rank": 1,
            "provider_rank": 1,
            "youtube_video_id": video_id,
            "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "title": f"{track['artists'][0]} - {track['title']} (Official Audio)",
            "uploader": track["artists"][0],
            "channel": track["artists"][0],
            "duration_seconds": track["duration_ms"] / 1000.0 + delta,
            "view_count": 1000 + index,
            "description": f"Official audio from {track.get('album') or 'the release'}",
            "availability": "public",
            "live_status": "not_live",
            "provider": "yt_dlp",
            "query": "frozen query",
            "stable_track_id": track["stable_track_id"],
            "duplicate_occurrences": [],
        }
        tracks.append({
            "track": track, "query": "frozen query", "request": {"download": False},
            "provider": {"name": "yt_dlp", "version": "test", "attempts": 1},
            "normalized_results": [], "candidates": [candidate],
            "candidate_video_ids": [video_id], "warnings": [], "error": None,
            "case_tags": list(item.case_tags), "case_rationale": item.case_rationale,
        })
    return {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "experiment_id": "stage5b1b_fresh_challenge_validation_v1",
        "manifest_sha256": manifest.sha256,
        "media_activity": {"audio_downloads": 0, "video_downloads": 0, "stage5a_calls": 0, "clap_calls": 0, "muq_calls": 0},
        "tracks": tracks,
    }


def temp_config(tmp_path):
    config, manifest = inputs()
    artifacts = {key: tmp_path / path.name for key, path in config.artifacts.items()}
    config = replace(config, artifacts=artifacts)
    atomic_json(artifacts["discovery"], fake_discovery(config, manifest))
    return config, manifest


def test_frozen_manifest_is_hash_locked_and_disjoint_from_both_prior_sets():
    config, manifest = inputs()
    assert manifest.sha256 == MANIFEST_SHA
    assert len(manifest.tracks) == 50
    assert verify_non_overlap(config, manifest) == {
        "fresh_track_count": 50,
        "dev_track_count": 25,
        "calibration_track_count": 50,
        "dev_overlap": [],
        "calibration_overlap": [],
    }


def test_frozen_policy_bundle_is_exactly_the_part_b_implementation():
    config, _ = inputs()
    assert config.policy_bundle_sha256 == POLICY_SHA
    boundaries, policies = load_frozen_policies(config)
    assert (boundaries.very_close_seconds, boundaries.close_seconds, boundaries.moderate_seconds) == (2, 7, 48)
    assert policies[POLICY_IDS[0]].canonical_or_official_only is True
    assert policies[POLICY_IDS[1]].allow_lyric_fallback is True
    assert policies[POLICY_IDS[1]].maximum_duration_band == "DURATION_CLOSE"


def test_policy_hash_tampering_fails_closed(tmp_path):
    config, _ = inputs()
    changed = tmp_path / "policies.json"
    changed.write_bytes(config.policy_bundle_path.read_bytes() + b"\n")
    with pytest.raises(Stage5B1AValidationError, match="policy bundle hash changed"):
        load_frozen_policies(replace(config, policy_bundle_path=changed))
    assert file_sha256(changed) != POLICY_SHA


def test_unchanged_features_and_dual_policy_create_balanced_incremental_coverage(tmp_path):
    config, manifest = temp_config(tmp_path)
    output = materialize_and_resolve(config, manifest)
    assert output["comparison"]["conservative_auto_match_count"] == 49
    assert output["comparison"]["balanced_auto_match_count"] == 50
    assert output["comparison"]["balanced_incremental_auto_match_count"] == 1
    assert output["comparison"]["balanced_incremental_track_ids"] == ["s5b1c_001"]
    assert output["production_auto_match_activated"] is False


def test_blinded_sol_payload_is_shuffled_opaque_and_feature_free(tmp_path):
    config, manifest = temp_config(tmp_path)
    payload, mapping = build_blinded_payload(config, manifest)
    assert len(payload["tracks"]) == 50
    assert sum(len(row["candidates"]) for row in payload["tracks"]) == 50
    assert payload["search_rank_supplied"] is False
    serialized = json.dumps(payload)
    for forbidden in (
        "youtube_video_id", "original_search_rank", "recording_eligible", "source_type",
        "policy_id", "policy_rule_id", "case_tags", "case_rationale", '"rank"', '"query"',
    ):
        assert forbidden not in serialized
    assert "youtube_video_id" in json.dumps(mapping)
    assert "original_search_rank" in json.dumps(mapping)


def test_audit_queue_is_deterministic_and_review_is_blinded(tmp_path, monkeypatch):
    config, manifest = temp_config(tmp_path)
    materialize_and_resolve(config, manifest)
    atomic_json(config.artifacts["sol_evaluations"], {"status": "COMPLETE"})
    decisions = json.loads(config.artifacts["policy_decisions"].read_text())
    balanced = {
        row["stable_track_id"]: row["decision"]
        for row in decisions["policies"][POLICY_IDS[1]]["tracks"]
    }
    sol_tracks = []
    for stable_id, decision in balanced.items():
        label = "WRONG" if stable_id == "s5b1c_001" else "IDEAL"
        sol_tracks.append({
            "stable_track_id": stable_id,
            "selection_status": "SELECTED",
            "selected_video_id": decision["selected_video_id"],
            "selection_rationale": "raw metadata rationale",
            "candidates": [{
                "candidate_key": "candidate_01", "youtube_video_id": decision["selected_video_id"],
                "label": label, "recording_identity_reason": "identity",
                "source_quality_reason": "source", "uncertainty_reason": None,
            }],
        })
    monkeypatch.setattr(
        "audio_similarity.stage5b1b_challenge_audit.mapped_sol_judgments",
        lambda runtime: {"tracks": sol_tracks},
    )
    runtime = SimpleNamespace(evaluations_path=config.artifacts["sol_evaluations"])
    first_comparison, first = build_comparison_and_queue(config, manifest, runtime)
    second_comparison, second = build_comparison_and_queue(config, manifest, runtime)
    assert first == second and first_comparison == second_comparison
    case = next(row for row in first["cases"] if row["stable_track_id"] == "s5b1c_001")
    assert "BALANCED_SOL_WRONG" in case["selection_reasons"]
    assert first_comparison["targeted_audit"]["random_conservative_agreement_track_ids"]
    write_review(config, manifest, first)
    with config.artifacts["human_review"].open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == REVIEW_COLUMNS
        text = json.dumps(list(reader))
    for forbidden in ("selection_reasons", "sol_", "source_type", "policy", "candidate_rank", "case_rationale"):
        assert forbidden not in text


def test_final_state_waits_for_labels_then_applies_safety_priority(tmp_path, monkeypatch):
    config, manifest = temp_config(tmp_path)
    materialize_and_resolve(config, manifest)
    atomic_json(config.artifacts["sol_evaluations"], {"status": "COMPLETE"})
    decisions = json.loads(config.artifacts["policy_decisions"].read_text())
    balanced = {
        row["stable_track_id"]: row["decision"]
        for row in decisions["policies"][POLICY_IDS[1]]["tracks"]
    }
    sol_tracks = [{
        "stable_track_id": stable_id,
        "selection_status": "SOL_MATCH_UNCERTAIN" if stable_id == "s5b1c_001" else "SELECTED",
        "selected_video_id": None if stable_id == "s5b1c_001" else decision["selected_video_id"],
        "selection_rationale": "raw metadata",
        "candidates": [{
            "candidate_key": "candidate_01", "youtube_video_id": decision["selected_video_id"],
            "label": "WRONG" if stable_id == "s5b1c_001" else "IDEAL",
            "recording_identity_reason": "identity", "source_quality_reason": "source",
            "uncertainty_reason": None,
        }],
    } for stable_id, decision in balanced.items()]
    monkeypatch.setattr(
        "audio_similarity.stage5b1b_challenge_audit.mapped_sol_judgments",
        lambda runtime: {"tracks": sol_tracks},
    )
    runtime = SimpleNamespace(evaluations_path=config.artifacts["sol_evaluations"])
    _, queue = build_comparison_and_queue(config, manifest, runtime)
    write_review(config, manifest, queue)
    assert evaluate_review(config)["status"] == "STAGE5B1B_FRESH_CHALLENGE_AWAITING_HUMAN_AUDIT"
    with config.artifacts["human_review"].open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    for row in rows:
        row["candidate_review_label"] = "IDEAL"
    with config.artifacts["human_review"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    assert evaluate_review(config)["status"] == "STAGE5B1B_BALANCED_POLICY_VALIDATED"
    balanced_only = next(row for row in rows if row["stable_track_id"] == "s5b1c_001")
    balanced_only["candidate_review_label"] = "WRONG"
    with config.artifacts["human_review"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    assert evaluate_review(config)["status"] == "STAGE5B1B_CONSERVATIVE_POLICY_VALIDATED"
