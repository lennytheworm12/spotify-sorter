"""Stage 5B.1H canonical-source and video-padding semantics.

This layer intentionally does not alter Stage 5B.1G eligibility or ordering.
It gives the frozen global-preference decision a richer, inspectable source
interpretation: recording compatibility, source canonicality, and likely
audio cleanliness are separate evidence dimensions.
"""
from __future__ import annotations

import copy
import csv
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_resolver import AUTO_MATCH, SAFE_LABELS
from .stage5b1g_global_preference import (
    DURATION_TOO_FAR,
    DURATION_UNKNOWN,
    evaluate_stage5b1g,
    load_stage5b1g_config,
    resolve_global_candidates,
)


CONFIG_SCHEMA_VERSION = "stage5b1h-canonical-source-config-v1"
SOURCE_SEMANTICS_SCHEMA_VERSION = "stage5b1h-source-semantics-v1"
PHRASE_SCHEMA_VERSION = "stage5b1h-source-phrase-normalization-v1"
DECISION_SCHEMA_VERSION = "stage5b1h-decisions-v1"
COMPARISON_SCHEMA_VERSION = "stage5b1h-selection-comparisons-v1"
PADDING_SCHEMA_VERSION = "stage5b1h-padding-risk-analysis-v1"
QUEUE_SCHEMA_VERSION = "stage5b1h-human-audit-queue-v1"
MANIFEST_SCHEMA_VERSION = "stage5b1h-artifact-manifest-v1"
POLICY_ID = "CANONICAL_SOURCE_SEMANTICS_V1"
STATUS = "STAGE5B1H_CANONICAL_SOURCE_SEMANTICS_COMPLETE"

RECORDING_COMPATIBLE = "RECORDING_COMPATIBLE"
RECORDING_INCOMPLETE = "RECORDING_INCOMPLETE"
RECORDING_CONFLICT = "RECORDING_CONFLICT"

CANONICAL_STRONG = "CANONICAL_STRONG"
CANONICAL_SUPPORTED = "CANONICAL_SUPPORTED"
CANONICAL_UNKNOWN = "CANONICAL_UNKNOWN"

CLEAN_AUDIO_LIKELY = "CLEAN_AUDIO_LIKELY"
VIDEO_PADDING_LOW = "VIDEO_PADDING_LOW"
VIDEO_PADDING_POSSIBLE = "VIDEO_PADDING_POSSIBLE"
VIDEO_PADDING_HIGH_OR_UNKNOWN = "VIDEO_PADDING_HIGH_OR_UNKNOWN"
OUTSIDE_EXPERIMENTAL_DURATION_LIMIT = "OUTSIDE_EXPERIMENTAL_DURATION_LIMIT"

ART_TRACK_TOPIC = "ART_TRACK_TOPIC"
OFFICIAL_AUDIO = "OFFICIAL_AUDIO"
AUDIO_PRESENTATION = "AUDIO_PRESENTATION"
OFFICIAL_LYRIC_VIDEO = "OFFICIAL_LYRIC_VIDEO"
LYRIC_VIDEO = "LYRIC_VIDEO"
OFFICIAL_MUSIC_VIDEO = "OFFICIAL_MUSIC_VIDEO"
MUSIC_VIDEO = "MUSIC_VIDEO"
NEGATED_VIDEO_PRESENTATION = "NEGATED_VIDEO_PRESENTATION"
OTHER = "OTHER"


@dataclass(frozen=True)
class PhraseRule:
    rule_id: str
    semantic: str
    examples: tuple[str, ...]
    pattern: re.Pattern[str]
    explicit_official: bool = False


_NEGATION_RULES = (
    PhraseRule(
        "NEGATED_NOT_MV",
        NEGATED_VIDEO_PRESENTATION,
        ("Not a MV", "Not an MV"),
        re.compile(r"\bnot\s+(?:an?\s+)?m\s*/?\s*v\b", re.I),
    ),
    PhraseRule(
        "NEGATED_UNOFFICIAL_VIDEO",
        NEGATED_VIDEO_PRESENTATION,
        ("Unofficial Video",),
        re.compile(r"\bunofficial\s+(?:music\s+)?video\b", re.I),
    ),
    PhraseRule(
        "NEGATED_NOT_OFFICIAL",
        NEGATED_VIDEO_PRESENTATION,
        ("Not Official",),
        re.compile(r"\bnot\s+official\b", re.I),
    ),
    PhraseRule(
        "NEGATED_FAN_MADE_OFFICIAL_STYLE",
        NEGATED_VIDEO_PRESENTATION,
        ("Fan Made Official Style",),
        re.compile(r"\bfan[ -]?made\s+official\s+style\b", re.I),
    ),
)

_POSITIVE_RULES = (
    PhraseRule(
        "OFFICIAL_LYRIC_VIDEO",
        OFFICIAL_LYRIC_VIDEO,
        ("Official Lyric Video",),
        re.compile(r"\bofficial\s+lyrics?\s+video\b", re.I),
        True,
    ),
    PhraseRule(
        "OFFICIAL_AUDIO",
        OFFICIAL_AUDIO,
        ("Official Audio",),
        re.compile(r"\bofficial\s+audio\b", re.I),
        True,
    ),
    PhraseRule(
        "OFFICIAL_MUSIC_VIDEO",
        OFFICIAL_MUSIC_VIDEO,
        ("Official Music Video", "Official Video", "Official M/V", "Official MV"),
        re.compile(
            r"\bofficial\s+(?:(?:music\s+)?video|m\s*/?\s*v)\b",
            re.I,
        ),
        True,
    ),
    PhraseRule(
        "FRENCH_OFFICIAL_VIDEO",
        OFFICIAL_MUSIC_VIDEO,
        ("clip officiel", "vidéo officielle"),
        re.compile(r"\b(?:clip\s+officiel|vid[eé]o\s+officielle?)\b", re.I),
        True,
    ),
    PhraseRule(
        "SPANISH_OFFICIAL_VIDEO",
        OFFICIAL_MUSIC_VIDEO,
        ("video oficial", "vídeo oficial"),
        re.compile(r"\bv[ií]deo\s+oficial\b", re.I),
        True,
    ),
    PhraseRule(
        "MV_PRESENTATION",
        MUSIC_VIDEO,
        ("M/V", "MV"),
        re.compile(r"(?<!\w)m\s*/?\s*v(?!\w)", re.I),
    ),
    PhraseRule(
        "MUSIC_VIDEO_PRESENTATION",
        MUSIC_VIDEO,
        ("Music Video",),
        re.compile(r"\bmusic\s+video\b", re.I),
    ),
    PhraseRule(
        "LYRIC_VIDEO",
        LYRIC_VIDEO,
        ("Lyric Video", "Lyrics Video"),
        re.compile(r"\blyrics?\s+video\b", re.I),
    ),
    PhraseRule(
        "LYRICS_PRESENTATION",
        LYRIC_VIDEO,
        ("Lyric", "Lyrics", "Letra"),
        re.compile(r"\b(?:lyrics?|letra)\b", re.I),
    ),
    PhraseRule(
        "AUDIO_PRESENTATION",
        AUDIO_PRESENTATION,
        ("Audio", "Remix Audio"),
        re.compile(r"\baudio\b", re.I),
    ),
)

_PRESENTATION_PRIORITY = {
    OFFICIAL_AUDIO: 0,
    OFFICIAL_LYRIC_VIDEO: 1,
    OFFICIAL_MUSIC_VIDEO: 2,
    LYRIC_VIDEO: 3,
    MUSIC_VIDEO: 4,
    AUDIO_PRESENTATION: 5,
}


@dataclass(frozen=True)
class Stage5B1HConfig:
    path: Path
    project_root: Path
    experiment_id: str
    policy_id: str
    stage5b1g_config: Path
    frozen_inputs: dict[str, dict[str, Any]]
    artifacts: dict[str, Path]
    sha256: str


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def load_stage5b1h_config(path: Path) -> Stage5B1HConfig:
    path = path.resolve()
    value = _json_object(path)
    if value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.1H config schema")
    if value.get("policy_id") != POLICY_ID:
        raise Stage5B1AValidationError("unexpected Stage 5B.1H policy ID")
    project_root = path.parent.parent
    frozen = value.get("frozen_inputs")
    artifacts = value.get("artifacts")
    if not isinstance(frozen, dict) or not frozen:
        raise Stage5B1AValidationError("Stage 5B.1H frozen inputs are required")
    if not isinstance(artifacts, dict) or not artifacts:
        raise Stage5B1AValidationError("Stage 5B.1H artifacts are required")
    return Stage5B1HConfig(
        path=path,
        project_root=project_root,
        experiment_id=str(value["experiment_id"]),
        policy_id=str(value["policy_id"]),
        stage5b1g_config=project_root / str(value["stage5b1g_config"]),
        frozen_inputs=dict(frozen),
        artifacts={
            name: project_root / str(target) for name, target in artifacts.items()
        },
        sha256=file_sha256(path),
    )


def verify_frozen_inputs(config: Stage5B1HConfig) -> dict[str, dict[str, Any]]:
    verified = {}
    for name, value in config.frozen_inputs.items():
        path = config.project_root / str(value["path"])
        actual = file_sha256(path)
        expected = str(value["sha256"])
        if actual != expected:
            raise Stage5B1AValidationError(
                f"frozen Stage 5B.1H input changed: {name}: {actual} != {expected}"
            )
        verified[name] = {
            "path": str(path.relative_to(config.project_root)),
            "sha256": actual,
            "size_bytes": path.stat().st_size,
        }
    return verified


def source_phrase_vocabulary() -> dict[str, Any]:
    """Return the small, auditable source-language vocabulary."""

    def row(rule: PhraseRule, polarity: str) -> dict[str, Any]:
        return {
            "rule_id": rule.rule_id,
            "polarity": polarity,
            "semantic": rule.semantic,
            "examples": list(rule.examples),
            "pattern": rule.pattern.pattern,
            "explicit_official": rule.explicit_official,
        }

    return {
        "schema_version": PHRASE_SCHEMA_VERSION,
        "scope": "small deterministic high-confidence source-presentation vocabulary",
        "positive_rules": [row(rule, "POSITIVE") for rule in _POSITIVE_RULES],
        "negation_rules": [row(rule, "NEGATED") for rule in _NEGATION_RULES],
        "principles": {
            "translation_model_used": False,
            "bare_audio_requires_corroboration": True,
            "bare_mv_requires_corroboration": True,
            "negation_precedes_positive_mv_detection": True,
        },
    }


def _matches(text: str, rules: tuple[PhraseRule, ...]) -> list[dict[str, Any]]:
    rows = []
    for rule in rules:
        for match in rule.pattern.finditer(text):
            rows.append({
                "rule_id": rule.rule_id,
                "semantic": rule.semantic,
                "matched_text": match.group(0),
                "explicit_official": rule.explicit_official,
            })
    return rows


def recognize_source_phrases(title: str) -> dict[str, Any]:
    """Recognize source presentation without inferring recording correctness."""

    title = str(title or "")
    negative = _matches(title, _NEGATION_RULES)
    positive = _matches(title, _POSITIVE_RULES)
    if negative:
        positive = [
            row
            for row in positive
            if row["semantic"] not in {MUSIC_VIDEO, OFFICIAL_MUSIC_VIDEO}
        ]
    ordered = sorted(
        positive,
        key=lambda row: _PRESENTATION_PRIORITY.get(row["semantic"], 99),
    )
    return {
        "title": title,
        "description_inspected_for_source_phrases": False,
        "normalized_presentation_signal": (
            NEGATED_VIDEO_PRESENTATION
            if negative and not ordered
            else ordered[0]["semantic"]
            if ordered
            else OTHER
        ),
        "explicit_official_source_signal": any(
            row["explicit_official"] for row in ordered
        ),
        "positive_phrase_evidence": ordered,
        "negation_evidence": negative,
    }


def _recording_identity(global_features: dict[str, Any]) -> dict[str, Any]:
    identity = global_features["identity"]
    versions = global_features["versions"]
    conflicts = list(global_features["hard_conflicts"])
    strong = bool(
        identity["strong_structural_title_identity"]
        and identity["strong_primary_performer_identity"]
        and versions["complete_and_compatible"]
        and not conflicts
    )
    state = (
        RECORDING_CONFLICT
        if conflicts
        else RECORDING_COMPATIBLE
        if strong
        else RECORDING_INCOMPLETE
    )
    return {
        "state": state,
        "strong_core_title_identity": identity["strong_structural_title_identity"],
        "strong_primary_performer_identity": identity[
            "strong_primary_performer_identity"
        ],
        "complete_compatible_version_evidence": versions[
            "complete_and_compatible"
        ],
        "hard_conflicts": conflicts,
    }


def _canonicality(
    recording: dict[str, Any],
    phrases: dict[str, Any],
    global_features: dict[str, Any],
) -> dict[str, Any]:
    provenance = global_features["provenance"]
    compatible = recording["state"] == RECORDING_COMPATIBLE
    artist_channel = bool(provenance["channel_or_uploader_performer_match"])
    release_corroborated = bool(
        provenance["art_track_internally_consistent"]
        or provenance["release_metadata_corroborated"]
    )
    official_phrase = bool(phrases["explicit_official_source_signal"])
    bare_presentational_claim = phrases["normalized_presentation_signal"] in {
        AUDIO_PRESENTATION,
        LYRIC_VIDEO,
        MUSIC_VIDEO,
    }
    if compatible and (release_corroborated or artist_channel):
        level = CANONICAL_STRONG
        reason = (
            "recording-compatible metadata plus internally consistent release provenance"
            if release_corroborated
            else "recording-compatible metadata plus artist-matching channel/uploader provenance"
        )
    elif compatible and official_phrase:
        level = CANONICAL_SUPPORTED
        reason = "recording-compatible metadata plus an explicit official-source phrase"
    else:
        level = CANONICAL_UNKNOWN
        reason = (
            "source claim is uncorroborated or recording identity is incomplete/conflicting"
        )
    return {
        "level": level,
        "reason": reason,
        "artist_channel_or_uploader_signal": artist_channel,
        "release_or_distributor_signal": release_corroborated,
        "explicit_official_source_phrase_signal": official_phrase,
        "bare_presentation_claim_requires_corroboration": bare_presentational_claim,
        "unknown_provenance_is_negative": False,
    }


def _normalized_source_type(
    phrases: dict[str, Any],
    canonicality: dict[str, Any],
    global_features: dict[str, Any],
) -> str:
    if global_features["provenance"]["art_track_internally_consistent"]:
        return ART_TRACK_TOPIC
    presentation = phrases["normalized_presentation_signal"]
    corroborated = canonicality["level"] in {
        CANONICAL_STRONG,
        CANONICAL_SUPPORTED,
    }
    if presentation == NEGATED_VIDEO_PRESENTATION:
        return NEGATED_VIDEO_PRESENTATION
    if presentation == OFFICIAL_AUDIO:
        return OFFICIAL_AUDIO
    if presentation == AUDIO_PRESENTATION:
        return OFFICIAL_AUDIO if corroborated else AUDIO_PRESENTATION
    if presentation == OFFICIAL_LYRIC_VIDEO:
        return OFFICIAL_LYRIC_VIDEO
    if presentation == LYRIC_VIDEO:
        return OFFICIAL_LYRIC_VIDEO if corroborated else LYRIC_VIDEO
    if presentation == OFFICIAL_MUSIC_VIDEO:
        return OFFICIAL_MUSIC_VIDEO
    if presentation == MUSIC_VIDEO:
        return OFFICIAL_MUSIC_VIDEO if corroborated else MUSIC_VIDEO
    return OTHER


def _padding_risk(
    normalized_source_type: str,
    canonicality: dict[str, Any],
    delta: float | None,
) -> dict[str, Any]:
    if delta is None or not math.isfinite(delta) or delta > 20:
        return {
            "level": OUTSIDE_EXPERIMENTAL_DURATION_LIMIT,
            "reason": "duration is missing/non-finite or exceeds the frozen 20-second limit",
        }
    canonical = canonicality["level"] != CANONICAL_UNKNOWN
    if normalized_source_type == ART_TRACK_TOPIC and canonical:
        return {
            "level": CLEAN_AUDIO_LIKELY,
            "reason": "internally consistent Art Track/release audio",
        }
    if normalized_source_type == OFFICIAL_AUDIO and canonical and delta <= 5:
        return {
            "level": CLEAN_AUDIO_LIKELY,
            "reason": "canonical audio presentation within five seconds of target duration",
        }
    if normalized_source_type in {
        OFFICIAL_MUSIC_VIDEO,
        OFFICIAL_LYRIC_VIDEO,
        MUSIC_VIDEO,
        LYRIC_VIDEO,
    }:
        if canonical and delta <= 5:
            level = VIDEO_PADDING_LOW
            reason = "canonical video presentation within five seconds of target duration"
        elif canonical and delta <= 12:
            level = VIDEO_PADDING_POSSIBLE
            reason = "canonical video presentation has five-to-twelve seconds of excess runtime"
        else:
            level = VIDEO_PADDING_HIGH_OR_UNKNOWN
            reason = "video presentation has twelve-to-twenty seconds of padding or weak canonicality"
        return {"level": level, "reason": reason}
    if normalized_source_type == OFFICIAL_AUDIO and canonical:
        return {
            "level": (
                VIDEO_PADDING_POSSIBLE if delta <= 12 else VIDEO_PADDING_HIGH_OR_UNKNOWN
            ),
            "reason": "canonical audio wording is present but runtime suggests presentation padding",
        }
    return {
        "level": VIDEO_PADDING_HIGH_OR_UNKNOWN,
        "reason": "metadata does not establish a clean canonical audio presentation",
    }


def derive_source_semantics(candidate_record: dict[str, Any]) -> dict[str, Any]:
    """Derive 1H semantics while retaining frozen 1G eligibility verbatim."""

    snapshot = candidate_record["snapshot"]
    global_features = candidate_record["global_features"]
    phrases = recognize_source_phrases(str(snapshot.get("title") or ""))
    recording = _recording_identity(global_features)
    canonicality = _canonicality(recording, phrases, global_features)
    normalized = _normalized_source_type(phrases, canonicality, global_features)
    delta = global_features["duration"]["absolute_duration_delta_seconds"]
    padding = _padding_risk(normalized, canonicality, delta)
    legacy = global_features["source"]["effective_preference_source_type"]
    legacy_equivalent = {
        ART_TRACK_TOPIC: "ART_TRACK_TOPIC",
        OFFICIAL_AUDIO: "OFFICIAL_AUDIO",
        AUDIO_PRESENTATION: "OTHER",
        OFFICIAL_LYRIC_VIDEO: "LYRIC_VIDEO",
        LYRIC_VIDEO: "LYRIC_VIDEO",
        OFFICIAL_MUSIC_VIDEO: "OFFICIAL_MUSIC_VIDEO",
        MUSIC_VIDEO: "OFFICIAL_MUSIC_VIDEO",
        NEGATED_VIDEO_PRESENTATION: "OTHER",
        OTHER: "OTHER",
    }[normalized]
    return {
        "schema_version": SOURCE_SEMANTICS_SCHEMA_VERSION,
        "track_id": global_features["track_id"],
        "candidate_video_id": global_features["candidate_video_id"],
        "recording_identity": recording,
        "source_presentation": {
            **phrases,
            "normalized_source_type": normalized,
            "legacy_effective_source_type": legacy,
            "legacy_equivalent_source_type": legacy_equivalent,
            "legacy_classification_changed": legacy != legacy_equivalent,
        },
        "canonicality": canonicality,
        "audio_cleanliness": padding,
        "duration": {
            "absolute_duration_delta_seconds": delta,
            "stage5b1g_duration_bucket": global_features["duration"]["bucket"],
            "within_frozen_twenty_second_limit": global_features["duration"][
                "bucket"
            ]
            not in {DURATION_TOO_FAR, DURATION_UNKNOWN},
        },
        "stage5b1g_eligibility_preserved": copy.deepcopy(
            global_features["eligibility"]
        ),
        "source_semantics_can_override_recording_conflict": False,
    }


def _load_review_evidence(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    evidence = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            label = row["candidate_review_label"].strip().upper()
            if not label:
                continue
            if label not in {"IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"}:
                raise Stage5B1AValidationError(f"invalid Stage 5B.1G review label: {label}")
            key = (row["stable_track_id"], row["candidate_video_id"])
            if key in evidence:
                raise Stage5B1AValidationError(
                    f"duplicate Stage 5B.1G review identity: {key}"
                )
            evidence[key] = {
                "label": label,
                "sources": ["stage5b1g_human_review"],
                "notes": (
                    [{
                        "source": "stage5b1g_human_review",
                        "note": row["candidate_note"],
                    }]
                    if row["candidate_note"]
                    else []
                ),
            }
    return evidence


def _selected(track_row: dict[str, Any], video_id: str | None) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in track_row["candidates"]
            if row["snapshot"]["video_id"] == video_id
        ),
        None,
    )


def evaluate_stage5b1h(
    config: Stage5B1HConfig,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Replay frozen 1G and materialize 1H semantics without policy mutation."""

    verify_frozen_inputs(config)
    stage5b1g = load_stage5b1g_config(config.stage5b1g_config)
    base_features, base_decisions, *_ = evaluate_stage5b1g(stage5b1g)
    if base_decisions["summary"]["global_auto_match_count"] != 42:
        raise Stage5B1AValidationError("frozen Stage 5B.1G AUTO_MATCH count changed")
    if base_decisions["summary"]["global_match_uncertain_count"] != 8:
        raise Stage5B1AValidationError("frozen Stage 5B.1G MATCH_UNCERTAIN count changed")

    committed = _json_object(
        config.project_root
        / str(config.frozen_inputs["stage5b1g_decisions"]["path"])
    )
    committed_by_id = {row["stable_track_id"]: row for row in committed["tracks"]}
    for row in base_decisions["tracks"]:
        expected = committed_by_id[row["stable_track_id"]]["global_preference_decision"]
        if row["global_preference_decision"] != expected:
            raise Stage5B1AValidationError(
                f"frozen Stage 5B.1G decision changed: {row['stable_track_id']}"
            )

    features = copy.deepcopy(base_features)
    review = _load_review_evidence(
        config.project_root
        / str(config.frozen_inputs["stage5b1g_human_review"]["path"])
    )
    for track_row in features["tracks"]:
        stable_id = track_row["track"]["stable_track_id"]
        for candidate in track_row["candidates"]:
            snapshot = candidate["snapshot"]
            added = review.get((stable_id, snapshot["video_id"]))
            if added:
                current = snapshot.get("human_evidence")
                if current and current.get("label") != added["label"]:
                    raise Stage5B1AValidationError(
                        f"conflicting human evidence for {stable_id}/{snapshot['video_id']}"
                    )
                snapshot["human_evidence"] = added
            candidate["source_semantics"] = derive_source_semantics(candidate)

    base_by_id = {row["stable_track_id"]: row for row in base_decisions["tracks"]}
    decision_rows = []
    selected_records = []
    for track_row in features["tracks"]:
        stable_id = track_row["track"]["stable_track_id"]
        base = base_by_id[stable_id]["global_preference_decision"]
        replay = resolve_global_candidates(track_row)
        if replay != base:
            raise Stage5B1AValidationError(
                f"Stage 5B.1H changed frozen global preference: {stable_id}"
            )
        selected = _selected(track_row, replay.get("selected_video_id"))
        if selected:
            selected_records.append(selected)
        decision_rows.append({
            "stable_track_id": stable_id,
            "stage5b1g_decision": base,
            "stage5b1h_decision": {
                **copy.deepcopy(replay),
                "policy_rule_id": POLICY_ID,
                "selection_reason": (
                    "frozen Stage 5B.1G global preference preserved; Stage 5B.1H adds "
                    "canonicality and padding-risk semantics without changing eligibility/order"
                )
                if replay["status"] == AUTO_MATCH
                else replay.get("uncertainty_reason"),
                "source_semantics": (
                    copy.deepcopy(selected["source_semantics"]) if selected else None
                ),
            },
            "selection_changed": False,
        })

    auto = sum(row["stage5b1h_decision"]["status"] == AUTO_MATCH for row in decision_rows)
    uncertain = len(decision_rows) - auto
    legacy_changes = [
        row
        for track in features["tracks"]
        for row in track["candidates"]
        if row["source_semantics"]["source_presentation"][
            "legacy_classification_changed"
        ]
    ]
    canonical_counts = Counter(
        row["source_semantics"]["canonicality"]["level"] for row in selected_records
    )
    padding_counts = Counter(
        row["source_semantics"]["audio_cleanliness"]["level"]
        for row in selected_records
    )
    selected_human = Counter(
        (row["snapshot"].get("human_evidence") or {}).get("label", "UNREVIEWED")
        for row in selected_records
    )
    source_counts = Counter(
        row["source_semantics"]["source_presentation"]["normalized_source_type"]
        for row in selected_records
    )
    compact_tracks = []
    for track_row in features["tracks"]:
        stable_id = track_row["track"]["stable_track_id"]
        selected_id = base_by_id[stable_id]["global_preference_decision"].get(
            "selected_video_id"
        )
        compact_tracks.append({
            "track": track_row["track"],
            "query": track_row["query"],
            "candidates": [
                {
                    "video_id": row["snapshot"]["video_id"],
                    "search_rank": row["snapshot"]["search_rank"],
                    "title": row["snapshot"]["title"],
                    "uploader": row["snapshot"].get("uploader"),
                    "channel": row["snapshot"].get("channel"),
                    "duration_seconds": row["snapshot"].get("duration_seconds"),
                    "view_count": row["snapshot"].get("view_count"),
                    "human_label": (
                        row["snapshot"].get("human_evidence") or {}
                    ).get("label"),
                    "sol_label": (
                        row["snapshot"].get("sol_evidence") or {}
                    ).get("label"),
                    "selected_by_stage5b1g": row["snapshot"]["video_id"] == selected_id,
                    "source_semantics": row["source_semantics"],
                }
                for row in track_row["candidates"]
            ],
        })
    features_doc = {
        "schema_version": SOURCE_SEMANTICS_SCHEMA_VERSION,
        "status": STATUS,
        "policy_id": POLICY_ID,
        "dataset_role": "FROZEN_Q0_STAGE5B1G_SELECTION_SEMANTICS_REFINEMENT",
        "track_count": len(features["tracks"]),
        "candidate_count": sum(len(row["candidates"]) for row in features["tracks"]),
        "summary": {
            "legacy_source_classifications_changed": len(legacy_changes),
            "selected_canonicality_counts": dict(sorted(canonical_counts.items())),
            "selected_padding_risk_counts": dict(sorted(padding_counts.items())),
            "selected_source_type_counts": dict(sorted(source_counts.items())),
        },
        "tracks": compact_tracks,
    }
    decisions_doc = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "status": STATUS,
        "policy_id": POLICY_ID,
        "summary": {
            "stage5b1g_auto_match_count": 42,
            "stage5b1g_match_uncertain_count": 8,
            "stage5b1h_auto_match_count": auto,
            "stage5b1h_match_uncertain_count": uncertain,
            "selection_ids_changed": 0,
            "coverage_before": 42 / 50,
            "coverage_after": auto / 50,
            "known_human_safe_selected": sum(
                selected_human[label] for label in SAFE_LABELS
            ),
            "known_human_wrong_selected": selected_human["WRONG"],
            "known_human_uncertain_selected": selected_human["UNCERTAIN"],
            "selected_human_label_counts": dict(sorted(selected_human.items())),
        },
        "scope_guards": {
            "q0_discovery_changed": False,
            "searches_run": 0,
            "media_downloads": 0,
            "sol_rerun": False,
            "historical_resolver_policies_changed": False,
            "stage5b1g_eligibility_and_ordering_preserved": True,
        },
        "tracks": decision_rows,
    }

    diagnostic_ids = {
        "s5b1c_013",
        "s5b1c_017",
        "s5b1c_025",
        "s5b1c_048",
        "s5b1c_049",
        "s5b1c_050",
    }
    diagnostic_rows = []
    for track_row, decision_row in zip(features["tracks"], decision_rows):
        stable_id = track_row["track"]["stable_track_id"]
        selected = _selected(
            track_row, decision_row["stage5b1h_decision"].get("selected_video_id")
        )
        if stable_id in diagnostic_ids and selected:
            semantic = selected["source_semantics"]
            diagnostic_rows.append({
                "stable_track_id": stable_id,
                "candidate_video_id": selected["snapshot"]["video_id"],
                "candidate_title": selected["snapshot"]["title"],
                "source_phrase_evidence": semantic["source_presentation"][
                    "positive_phrase_evidence"
                ],
                "negation_evidence": semantic["source_presentation"][
                    "negation_evidence"
                ],
                "normalized_source_type": semantic["source_presentation"][
                    "normalized_source_type"
                ],
                "recording_identity": semantic["recording_identity"],
                "canonicality": semantic["canonicality"],
                "absolute_duration_delta_seconds": semantic["duration"][
                    "absolute_duration_delta_seconds"
                ],
                "padding_risk": semantic["audio_cleanliness"],
                "selected": True,
                "human_label": (
                    selected["snapshot"].get("human_evidence") or {}
                ).get("label"),
                "sol_label": (
                    selected["snapshot"].get("sol_evidence") or {}
                ).get("label"),
            })
    comparisons_doc = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "status": STATUS,
        "selection_change_count": 0,
        "comparisons": [],
        "diagnostic_cases": diagnostic_rows,
        "legacy_source_classification_changes": [
            {
                "stable_track_id": row["snapshot"]["track_id"],
                "candidate_video_id": row["snapshot"]["video_id"],
                "candidate_title": row["snapshot"]["title"],
                "legacy_effective_source_type": row["source_semantics"][
                    "source_presentation"
                ]["legacy_effective_source_type"],
                "normalized_source_type": row["source_semantics"][
                    "source_presentation"
                ]["normalized_source_type"],
            }
            for row in legacy_changes
        ],
    }

    padding_rows = []
    for level in (
        CLEAN_AUDIO_LIKELY,
        VIDEO_PADDING_LOW,
        VIDEO_PADDING_POSSIBLE,
        VIDEO_PADDING_HIGH_OR_UNKNOWN,
        OUTSIDE_EXPERIMENTAL_DURATION_LIMIT,
    ):
        all_rows = [
            candidate
            for track in features["tracks"]
            for candidate in track["candidates"]
            if candidate["source_semantics"]["audio_cleanliness"]["level"] == level
        ]
        candidate_keys = {
            (
                row["source_semantics"]["track_id"],
                row["source_semantics"]["candidate_video_id"],
            )
            for row in all_rows
        }
        selected_rows = [
            row
            for row in selected_records
            if (
                row["source_semantics"]["track_id"],
                row["source_semantics"]["candidate_video_id"],
            )
            in candidate_keys
        ]
        labels = Counter(
            (row["snapshot"].get("human_evidence") or {}).get("label", "UNREVIEWED")
            for row in selected_rows
        )
        padding_rows.append({
            "padding_risk": level,
            "candidate_count": len(all_rows),
            "selected_count": len(selected_rows),
            "selected_human_label_counts": dict(sorted(labels.items())),
        })
    padding_doc = {
        "schema_version": PADDING_SCHEMA_VERSION,
        "status": STATUS,
        "rows": padding_rows,
        "canonical_mv_duration_semantics": {
            "zero_to_five_seconds": VIDEO_PADDING_LOW,
            "over_five_to_twelve_seconds": VIDEO_PADDING_POSSIBLE,
            "over_twelve_to_twenty_seconds": VIDEO_PADDING_HIGH_OR_UNKNOWN,
            "over_twenty_seconds": OUTSIDE_EXPERIMENTAL_DURATION_LIMIT,
        },
    }
    queue_doc = {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "status": "NO_REVIEW_REQUIRED",
        "policy_id": POLICY_ID,
        "track_count": 0,
        "candidate_count": 0,
        "cases": [],
    }
    return features_doc, decisions_doc, comparisons_doc, padding_doc, queue_doc
