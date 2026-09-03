from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5b1i_live_fallback import (
    ARRANGEMENT_CHANGING_LIVE,
    AUTO_MATCH,
    EXACT_RECORDING,
    MATCH_UNCERTAIN,
    ORDINARY_LIVE,
    REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK,
    build_fallback_candidate_evidence,
    classify_live_target,
    evaluate_stage5b1i,
    load_stage5b1i_config,
    resolve_representation_equivalence,
    verify_frozen_inputs,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1i_live_representation_fallback.json"


def _track(title: str = "Song - Live at the Ryman") -> dict:
    return {
        "stable_track_id": "track",
        "spotify_track_id": None,
        "title": title,
        "artists": ["Artist"],
        "album": "Live Album",
        "duration_ms": 260_000,
        "release_year": 2024,
        "isrc": None,
    }


def _candidate(
    video_id: str = "studio",
    *,
    rank: int = 1,
    title: str = "Artist - Song (Official Audio)",
    description: str = "",
    title_match: bool = True,
    performer_match: bool = True,
    performer_conflict: bool = False,
    cover: bool = False,
    candidate_families: list[str] | None = None,
    hard_conflicts: list[str] | None = None,
    artist_channel: bool = True,
    release: bool = False,
    source_type: str = "OFFICIAL_AUDIO",
    explicit_official: bool = True,
    duration: float = 210.0,
    views: int = 1_000_000,
) -> tuple[dict, dict]:
    families = list(candidate_families or [])
    conflicts = list(hard_conflicts or [])
    if performer_conflict or cover:
        conflicts.append("EXPLICIT_PERFORMER_OR_COVER_CONFLICT")
    relationships = [{
        "family": "live",
        "relationship": "ABSENT" if "live" not in families else "CONFLICT",
        "target_qualifier": "the Ryman",
        "candidate_qualifier": None,
        "target_raw": "Live at the Ryman",
        "candidate_raw": None,
    }]
    for family in families:
        if family != "live":
            relationships.append({
                "family": family,
                "relationship": "CONFLICT",
                "target_qualifier": None,
                "candidate_qualifier": None,
                "target_raw": None,
                "candidate_raw": family,
            })
    record = {
        "snapshot": {
            "track_id": "track",
            "video_id": video_id,
            "search_rank": rank,
            "title": title,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "uploader": "Artist" if artist_channel else "Unknown",
            "channel": "Artist" if artist_channel else "Unknown",
            "duration_seconds": duration,
            "view_count": views,
            "description": description,
            "human_evidence": None,
            "sol_evidence": None,
        },
        "global_features": {
            "track_id": "track",
            "candidate_video_id": video_id,
            "identity": {
                "strong_structural_title_identity": title_match,
                "strong_primary_performer_identity": performer_match,
                "performer_evidence": {
                    "primary_performer_match": performer_match,
                    "explicit_cover_signal": cover,
                    "explicit_performer_conflict": performer_conflict,
                    "explicit_title_performer_conflict": performer_conflict,
                    "credited_performer_matches": ["Artist"] if performer_match else [],
                    "normalized_target_performers": ["artist"],
                    "evidence": [],
                },
            },
            "versions": {
                "relationships": relationships,
                "target_is_versioned": True,
                "complete_and_compatible": False,
                "explicit_complete_match": False,
                "match_count": 0,
                "absent_count": 1,
                "conflict_count": len(families),
            },
            "modifications": {
                "target_families": ["live"],
                "candidate_families": families,
                "unrequested_candidate_families": families,
                "explicit_conflict": bool(families),
            },
            "hard_conflicts": conflicts,
            "provenance": {
                "channel_or_uploader_performer_match": artist_channel,
                "art_track_internally_consistent": release,
                "release_metadata_corroborated": release,
            },
            "duration": {
                "target_seconds": 260.0,
                "candidate_seconds": duration,
                "absolute_duration_delta_seconds": abs(260.0 - duration),
            },
        },
    }
    semantics = {
        "source_presentation": {
            "normalized_source_type": source_type,
            "normalized_presentation_signal": source_type,
            "explicit_official_source_signal": explicit_official,
        }
    }
    return record, semantics


def _evidence(**kwargs) -> dict:
    record, semantics = _candidate(**kwargs)
    return build_fallback_candidate_evidence(
        record, semantics, classify_live_target(_track())
    )


def _uncertain() -> dict:
    return {
        "status": MATCH_UNCERTAIN,
        "policy_rule_id": "CANONICAL_SOURCE_SEMANTICS_V1",
        "selected_video_id": None,
        "selected_candidate_rank": None,
        "uncertainty_reason": "no exact candidate",
        "ranked_plausible_candidates": [],
    }


def test_ordinary_live_target_allows_studio_fallback() -> None:
    classification = classify_live_target(_track())
    assert classification["classification"] == ORDINARY_LIVE
    assert classification["studio_fallback_allowed"]
    decision = resolve_representation_equivalence(
        _uncertain(), classification, [_evidence()]
    )
    assert decision["status"] == AUTO_MATCH
    assert decision["match_mode"] == REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK


def test_exact_live_match_always_precedes_studio_fallback() -> None:
    baseline = {
        "status": AUTO_MATCH,
        "selected_video_id": "exact-live",
        "selected_candidate_rank": 2,
        "policy_rule_id": "CANONICAL_SOURCE_SEMANTICS_V1",
    }
    decision = resolve_representation_equivalence(
        baseline, classify_live_target(_track()), [_evidence()]
    )
    assert decision["selected_video_id"] == "exact-live"
    assert decision["match_mode"] == EXACT_RECORDING


@pytest.mark.parametrize(
    "suffix",
    [
        "Live Acoustic",
        "Live Orchestral",
        "Live Remix",
        "Live Instrumental",
        "Live Slowed + Reverb",
    ],
)
def test_arrangement_changing_live_target_rejects_studio_fallback(suffix: str) -> None:
    classification = classify_live_target(_track(f"Song - {suffix}"))
    assert classification["classification"] == ARRANGEMENT_CHANGING_LIVE
    assert not classification["studio_fallback_allowed"]
    assert resolve_representation_equivalence(
        _uncertain(), classification, [_evidence()]
    )["status"] == MATCH_UNCERTAIN


@pytest.mark.parametrize(
    "kwargs",
    [
        {"performer_conflict": True},
        {"cover": True},
        {"candidate_families": ["remix"]},
        {"candidate_families": ["acoustic"]},
        {"candidate_families": ["instrumental"]},
        {"candidate_families": ["karaoke"]},
        {"candidate_families": ["slowed"]},
        {"candidate_families": ["sped_up"]},
        {"candidate_families": ["reverb"]},
        {"candidate_families": ["live"]},
    ],
)
def test_recording_conflicts_and_nonstudio_versions_remain_rejected(kwargs: dict) -> None:
    evidence = _evidence(**kwargs)
    assert not evidence["eligibility"]["eligible"]


def test_explicit_live_presentation_is_not_misclassified_as_studio() -> None:
    evidence = _evidence(
        title="Artist - Song",
        description="Recorded live on the 2024 concert tour",
    )
    assert evidence["explicit_live_presentation_evidence"]
    assert not evidence["eligibility"]["eligible"]


def test_wrong_performer_without_explicit_conflict_remains_insufficient() -> None:
    evidence = _evidence(performer_match=False)
    assert not evidence["eligibility"]["eligible"]
    assert "strong_primary_performer_identity" in evidence["eligibility"][
        "failed_conditions"
    ]


def test_unknown_source_is_weaker_and_cannot_establish_equivalence() -> None:
    evidence = _evidence(
        artist_channel=False,
        release=False,
        explicit_official=False,
        source_type="OTHER",
    )
    assert evidence["canonicality"]["level"] == "CANONICAL_UNKNOWN"
    assert not evidence["eligibility"]["eligible"]


def test_canonical_release_source_is_preferred_over_artist_channel() -> None:
    release = _evidence(video_id="release", rank=5, release=True, views=10)
    artist = _evidence(video_id="artist", rank=1, release=False, views=10_000)
    decision = resolve_representation_equivalence(
        _uncertain(), classify_live_target(_track()), [artist, release]
    )
    assert decision["selected_video_id"] == "release"


def test_artist_backed_bare_audio_is_treated_as_canonical_audio() -> None:
    evidence = _evidence(source_type="AUDIO_PRESENTATION")
    assert evidence["source"]["fallback_normalized_source_type"] == "OFFICIAL_AUDIO"
    assert evidence["eligibility"]["eligible"]


def test_live_to_studio_duration_delta_does_not_reject_fallback() -> None:
    evidence = _evidence(duration=120.0)
    assert evidence["duration"]["live_to_studio_delta_seconds"] == 140.0
    assert not evidence["duration"]["used_for_fallback_eligibility"]
    assert evidence["eligibility"]["eligible"]


def test_non_live_target_semantics_remain_unchanged() -> None:
    classification = classify_live_target(_track("Song - 2024 Remaster"))
    decision = resolve_representation_equivalence(
        _uncertain(), classification, [_evidence()]
    )
    assert decision["status"] == MATCH_UNCERTAIN
    assert decision["match_mode"] is None


def test_frozen_stage5b1h_replay_and_live_fallback_measurement() -> None:
    config = load_stage5b1i_config(CONFIG)
    assert len(verify_frozen_inputs(config)) == 6
    classifications, features, decisions, queue = evaluate_stage5b1i(config)
    assert classifications["summary"] == {
        "live_target_count": 4,
        "ordinary_live_target_count": 4,
        "arrangement_changing_live_target_count": 0,
        "exact_live_auto_match_count": 3,
        "ordinary_live_exact_failures": 1,
        "studio_fallback_opportunity_count": 0,
    }
    assert features["attempted_track_count"] == 1
    assert features["candidate_count"] == 5
    assert decisions["summary"]["stage5b1h_auto_match_count"] == 42
    assert decisions["summary"]["stage5b1h_match_uncertain_count"] == 8
    assert decisions["summary"]["stage5b1i_auto_match_count"] == 42
    assert decisions["summary"]["stage5b1i_match_uncertain_count"] == 8
    assert decisions["summary"]["representation_equivalent_fallback_count"] == 0
    assert decisions["summary"]["coverage_after"] == 0.84
    assert queue["status"] == "NO_REVIEW_REQUIRED"
    assert queue["candidate_count"] == 0

    live_ids = {row["stable_track_id"] for row in classifications["tracks"]}
    assert live_ids == {"s5b1c_026", "s5b1c_027", "s5b1c_028", "s5b1c_029"}
    unresolved = next(
        row for row in classifications["tracks"] if row["stable_track_id"] == "s5b1c_029"
    )
    assert not unresolved["exact_live_candidate_available"]
    assert unresolved["studio_fallback_candidate_ids"] == []

    baseline_selected = {
        row["stage5b1h_decision"].get("selected_video_id")
        for row in decisions["tracks"]
        if row["stage5b1h_decision"]["status"] == AUTO_MATCH
    }
    final_selected = {
        row["stage5b1i_decision"].get("selected_video_id")
        for row in decisions["tracks"]
        if row["stage5b1i_decision"]["status"] == AUTO_MATCH
    }
    assert final_selected == baseline_selected


def test_committed_stage5b1i_artifacts_match_manifest() -> None:
    config = load_stage5b1i_config(CONFIG)
    if not config.artifacts["manifest"].exists():
        pytest.skip("Stage 5B.1I closeout artifacts not generated yet")
    manifest = json.loads(config.artifacts["manifest"].read_text(encoding="utf-8"))
    assert manifest["status"] == "STAGE5B1I_LIVE_REPRESENTATION_FALLBACK_EVALUATED"
    assert manifest["config"]["sha256"] == file_sha256(CONFIG)
    for row in manifest["artifacts"].values():
        path = ROOT / row["path"]
        assert path.stat().st_size == row["size_bytes"]
        assert file_sha256(path) == row["sha256"]
