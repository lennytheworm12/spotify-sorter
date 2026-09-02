from __future__ import annotations

from pathlib import Path
import json

import pytest

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5b1h_source_semantics import (
    AUDIO_PRESENTATION,
    CANONICAL_STRONG,
    CANONICAL_SUPPORTED,
    CANONICAL_UNKNOWN,
    CLEAN_AUDIO_LIKELY,
    NEGATED_VIDEO_PRESENTATION,
    OFFICIAL_AUDIO,
    OFFICIAL_LYRIC_VIDEO,
    OFFICIAL_MUSIC_VIDEO,
    OUTSIDE_EXPERIMENTAL_DURATION_LIMIT,
    RECORDING_CONFLICT,
    VIDEO_PADDING_HIGH_OR_UNKNOWN,
    VIDEO_PADDING_LOW,
    VIDEO_PADDING_POSSIBLE,
    derive_source_semantics,
    evaluate_stage5b1h,
    load_stage5b1h_config,
    recognize_source_phrases,
    source_phrase_vocabulary,
    verify_frozen_inputs,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/stage5b1h_canonical_source_semantics.json"


def _candidate(
    title: str,
    *,
    delta: float = 2.0,
    artist_channel: bool = True,
    art_track: bool = False,
    release_corroborated: bool = False,
    title_match: bool = True,
    performer_match: bool = True,
    version_complete: bool = True,
    hard_conflicts: list[str] | None = None,
    eligible: bool = True,
) -> dict:
    conflicts = list(hard_conflicts or [])
    return {
        "snapshot": {
            "track_id": "track",
            "video_id": "video",
            "title": title,
            "description": "",
        },
        "global_features": {
            "track_id": "track",
            "candidate_video_id": "video",
            "identity": {
                "strong_structural_title_identity": title_match,
                "strong_primary_performer_identity": performer_match,
            },
            "versions": {"complete_and_compatible": version_complete},
            "hard_conflicts": conflicts,
            "duration": {
                "absolute_duration_delta_seconds": delta,
                "bucket": "DURATION_CLOSE" if delta <= 7 else "DURATION_EXTENDED_3",
            },
            "provenance": {
                "channel_or_uploader_performer_match": artist_channel,
                "art_track_internally_consistent": art_track,
                "release_metadata_corroborated": release_corroborated,
            },
            "source": {"effective_preference_source_type": "OTHER"},
            "eligibility": {
                "eligible": eligible,
                "basis": "GRADUATED_DURATION_EVIDENCE" if eligible else "INELIGIBLE",
            },
        },
    }


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Artist - Song M/V", "MUSIC_VIDEO"),
        ("Artist - Song (Official M/V)", OFFICIAL_MUSIC_VIDEO),
        ("Artist - Song (Official MV)", OFFICIAL_MUSIC_VIDEO),
        ("Artist - Song (Official Music Video)", OFFICIAL_MUSIC_VIDEO),
        ("Artist - Song (Official Video)", OFFICIAL_MUSIC_VIDEO),
        ("Artist - Song (Official Lyric Video)", OFFICIAL_LYRIC_VIDEO),
        ("Artist - Song (Official Audio)", OFFICIAL_AUDIO),
        ("Artist - Song (Lyrics)", "LYRIC_VIDEO"),
        ("Artist - Song [Music Video]", "MUSIC_VIDEO"),
        ("Artist - Chanson (clip officiel)", OFFICIAL_MUSIC_VIDEO),
        ("Artist - Chanson (vidéo officielle)", OFFICIAL_MUSIC_VIDEO),
        ("Artist - Canción (video oficial)", OFFICIAL_MUSIC_VIDEO),
        ("Artist - Canción (vídeo oficial)", OFFICIAL_MUSIC_VIDEO),
    ],
)
def test_source_phrase_recognition(title: str, expected: str) -> None:
    assert recognize_source_phrases(title)["normalized_presentation_signal"] == expected


@pytest.mark.parametrize(
    "title",
    [
        "Artist - Song (Not a MV)",
        "Artist - Song (Not an MV)",
        "Artist - Song (Unofficial Video)",
        "Artist - Song (Not Official)",
        "Artist - Song (Fan Made Official Style)",
    ],
)
def test_negated_source_terms_do_not_create_positive_video_evidence(title: str) -> None:
    evidence = recognize_source_phrases(title)
    assert evidence["normalized_presentation_signal"] == NEGATED_VIDEO_PRESENTATION
    assert not evidence["explicit_official_source_signal"]


def test_artist_backed_bare_mv_becomes_canonical_video() -> None:
    evidence = derive_source_semantics(_candidate("Artist - Song M/V"))
    assert evidence["source_presentation"]["normalized_source_type"] == OFFICIAL_MUSIC_VIDEO
    assert evidence["canonicality"]["level"] == CANONICAL_STRONG


def test_random_uploader_audio_remains_neutral() -> None:
    evidence = derive_source_semantics(
        _candidate("Artist - Song Audio", artist_channel=False)
    )
    assert evidence["source_presentation"]["normalized_source_type"] == AUDIO_PRESENTATION
    assert evidence["canonicality"]["level"] == CANONICAL_UNKNOWN
    assert not evidence["canonicality"]["unknown_provenance_is_negative"]


def test_artist_controlled_remix_audio_is_canonical_audio() -> None:
    evidence = derive_source_semantics(
        _candidate("Artist - Song (Named Remix Audio)")
    )
    assert evidence["source_presentation"]["normalized_source_type"] == OFFICIAL_AUDIO
    assert evidence["canonicality"]["level"] == CANONICAL_STRONG
    assert evidence["audio_cleanliness"]["level"] == CLEAN_AUDIO_LIKELY


def test_explicit_official_phrase_without_channel_is_supported_not_strong() -> None:
    evidence = derive_source_semantics(
        _candidate("Artist - Song (Official Audio)", artist_channel=False)
    )
    assert evidence["canonicality"]["level"] == CANONICAL_SUPPORTED


def test_distributor_release_corroboration_is_strong_without_artist_channel() -> None:
    evidence = derive_source_semantics(
        _candidate(
            "Artist - Song",
            artist_channel=False,
            release_corroborated=True,
        )
    )
    assert evidence["canonicality"]["level"] == CANONICAL_STRONG
    assert evidence["canonicality"]["release_or_distributor_signal"]


def test_internally_consistent_art_track_is_canonical_clean_audio() -> None:
    evidence = derive_source_semantics(
        _candidate("Artist - Song", artist_channel=False, art_track=True)
    )
    assert evidence["source_presentation"]["normalized_source_type"] == "ART_TRACK_TOPIC"
    assert evidence["canonicality"]["level"] == CANONICAL_STRONG
    assert evidence["audio_cleanliness"]["level"] == CLEAN_AUDIO_LIKELY


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (5.0, VIDEO_PADDING_LOW),
        (5.001, VIDEO_PADDING_POSSIBLE),
        (12.0, VIDEO_PADDING_POSSIBLE),
        (12.001, VIDEO_PADDING_HIGH_OR_UNKNOWN),
        (20.0, VIDEO_PADDING_HIGH_OR_UNKNOWN),
        (20.001, OUTSIDE_EXPERIMENTAL_DURATION_LIMIT),
    ],
)
def test_canonical_music_video_padding_bands(delta: float, expected: str) -> None:
    evidence = derive_source_semantics(
        _candidate(
            "Artist - Song (Official Music Video)",
            delta=delta,
            eligible=delta <= 20,
        )
    )
    assert evidence["audio_cleanliness"]["level"] == expected
    assert evidence["stage5b1g_eligibility_preserved"]["eligible"] is (delta <= 20)


def test_twelve_to_twenty_second_canonical_mv_preserves_existing_eligibility() -> None:
    evidence = derive_source_semantics(
        _candidate("Artist - Song (Official Video)", delta=17.0, eligible=True)
    )
    assert evidence["recording_identity"]["state"] == "RECORDING_COMPATIBLE"
    assert evidence["canonicality"]["level"] == CANONICAL_STRONG
    assert evidence["audio_cleanliness"]["level"] == VIDEO_PADDING_HIGH_OR_UNKNOWN
    assert evidence["stage5b1g_eligibility_preserved"]["eligible"]


@pytest.mark.parametrize(
    "conflict",
    [
        "EXPLICIT_VERSION_CONFLICT",
        "EXPLICIT_PERFORMER_OR_COVER_CONFLICT",
        "EXPLICIT_UNREQUESTED_MODIFICATION_CONFLICT",
    ],
)
def test_source_terminology_cannot_rescue_recording_conflicts(conflict: str) -> None:
    evidence = derive_source_semantics(
        _candidate(
            "Artist - Song (Official Music Video)",
            hard_conflicts=[conflict],
            eligible=False,
        )
    )
    assert evidence["recording_identity"]["state"] == RECORDING_CONFLICT
    assert evidence["canonicality"]["level"] == CANONICAL_UNKNOWN
    assert not evidence["stage5b1g_eligibility_preserved"]["eligible"]


def test_vocabulary_is_small_and_auditable() -> None:
    vocabulary = source_phrase_vocabulary()
    assert len(vocabulary["positive_rules"]) == 10
    assert len(vocabulary["negation_rules"]) == 4
    assert not vocabulary["principles"]["translation_model_used"]


def test_frozen_stage5b1g_replay_and_stage5b1h_diagnostics() -> None:
    config = load_stage5b1h_config(CONFIG)
    assert len(verify_frozen_inputs(config)) == 9
    features, decisions, comparisons, padding, queue = evaluate_stage5b1h(config)
    assert features["track_count"] == 50
    assert decisions["summary"]["stage5b1g_auto_match_count"] == 42
    assert decisions["summary"]["stage5b1g_match_uncertain_count"] == 8
    assert decisions["summary"]["stage5b1h_auto_match_count"] == 42
    assert decisions["summary"]["stage5b1h_match_uncertain_count"] == 8
    assert decisions["summary"]["selection_ids_changed"] == 0
    assert decisions["summary"]["known_human_wrong_selected"] == 0
    assert comparisons["selection_change_count"] == 0
    assert queue["candidate_count"] == 0
    assert sum(row["selected_count"] for row in padding["rows"]) == 42

    diagnostics = {
        row["stable_track_id"]: row for row in comparisons["diagnostic_cases"]
    }
    assert set(diagnostics) == {
        "s5b1c_013",
        "s5b1c_017",
        "s5b1c_025",
        "s5b1c_048",
        "s5b1c_049",
        "s5b1c_050",
    }
    assert all(row["human_label"] == "IDEAL" for row in diagnostics.values())
    assert diagnostics["s5b1c_013"]["normalized_source_type"] == OFFICIAL_MUSIC_VIDEO
    assert diagnostics["s5b1c_017"]["normalized_source_type"] == OFFICIAL_LYRIC_VIDEO
    assert diagnostics["s5b1c_025"]["normalized_source_type"] == OFFICIAL_AUDIO
    assert diagnostics["s5b1c_048"]["padding_risk"]["level"] == VIDEO_PADDING_HIGH_OR_UNKNOWN
    assert diagnostics["s5b1c_049"]["normalized_source_type"] == NEGATED_VIDEO_PRESENTATION
    assert diagnostics["s5b1c_050"]["normalized_source_type"] == OFFICIAL_MUSIC_VIDEO


def test_committed_stage5b1h_artifacts_match_manifest() -> None:
    config = load_stage5b1h_config(CONFIG)
    manifest = json.loads(config.artifacts["manifest"].read_text(encoding="utf-8"))
    assert manifest["status"] == "STAGE5B1H_CANONICAL_SOURCE_SEMANTICS_COMPLETE"
    assert manifest["config"]["sha256"] == file_sha256(CONFIG)
    for row in manifest["artifacts"].values():
        path = ROOT / row["path"]
        assert path.stat().st_size == row["size_bytes"]
        assert file_sha256(path) == row["sha256"]
