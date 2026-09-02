"""Interpretable offline candidate policies for Stage 5B.1B calibration."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .stage5b1a_models import Stage5B1AValidationError


AUTO_MATCH = "AUTO_MATCH"
MATCH_UNCERTAIN = "MATCH_UNCERTAIN"
SAFE_LABELS = {"IDEAL", "ACCEPTABLE"}
HUMAN_LABEL_STATES = {
    "IDEAL": "SAFE",
    "ACCEPTABLE": "SAFE",
    "WRONG": "UNSAFE",
    "UNCERTAIN": "UNRESOLVED",
}
DURATION_BANDS = ("DURATION_VERY_CLOSE", "DURATION_CLOSE", "DURATION_MODERATE", "DURATION_FAR")
SOURCE_ORDER = {
    "ART_TRACK_TOPIC": 0,
    "OFFICIAL_AUDIO": 1,
    "LYRIC_VIDEO": 2,
    "OFFICIAL_MUSIC_VIDEO": 3,
    "OTHER": 4,
}


@dataclass(frozen=True)
class DurationBoundaries:
    very_close_seconds: float
    close_seconds: float
    moderate_seconds: float
    derivation: str = "ceil(q50/q75/q90 of eligible human SAFE absolute deltas)"

    def __post_init__(self) -> None:
        values = (self.very_close_seconds, self.close_seconds, self.moderate_seconds)
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise Stage5B1AValidationError("duration boundaries must be finite and non-negative")
        if not self.very_close_seconds <= self.close_seconds <= self.moderate_seconds:
            raise Stage5B1AValidationError("duration boundaries must be monotonic")


@dataclass(frozen=True)
class PolicySpec:
    policy_id: str
    require_exact_identity: bool
    minimum_title_similarity: float
    require_primary_artist: bool
    require_complete_version_evidence: bool
    maximum_duration_band: str
    canonical_or_official_only: bool
    allow_lyric_fallback: bool
    lyric_min_relative_view_strength: float | None
    official_video_maximum_duration_band: str | None
    allow_other_source: bool

    def __post_init__(self) -> None:
        if self.maximum_duration_band not in DURATION_BANDS:
            raise Stage5B1AValidationError("invalid maximum duration band")
        if (
            self.official_video_maximum_duration_band is not None
            and self.official_video_maximum_duration_band not in DURATION_BANDS
        ):
            raise Stage5B1AValidationError("invalid official-video duration band")
        if not 0 <= self.minimum_title_similarity <= 1:
            raise Stage5B1AValidationError("title similarity boundary must be in [0, 1]")
        if self.lyric_min_relative_view_strength is not None and not (
            0 <= self.lyric_min_relative_view_strength <= 1
        ):
            raise Stage5B1AValidationError("relative-view boundary must be in [0, 1]")


def human_label_state(label: str) -> str:
    try:
        return HUMAN_LABEL_STATES[label]
    except KeyError as exc:
        raise Stage5B1AValidationError(f"invalid human candidate label: {label}") from exc


def _linear_quantile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise Stage5B1AValidationError("cannot derive duration boundaries without SAFE examples")
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def derive_duration_boundaries(
    feature_rows: Iterable[tuple[dict[str, Any], str]],
) -> tuple[DurationBoundaries, dict[str, Any]]:
    values = sorted(
        float(delta)
        for feature, label in feature_rows
        if label in SAFE_LABELS
        and feature["recording_eligible"]
        and (delta := feature["duration"]["absolute_duration_delta_seconds"]) is not None
    )
    raw = {name: _linear_quantile(values, q) for name, q in (("q50", 0.5), ("q75", 0.75), ("q90", 0.9))}
    rounded = [float(math.ceil(raw[name])) for name in ("q50", "q75", "q90")]
    rounded[1] = max(rounded[0], rounded[1])
    rounded[2] = max(rounded[1], rounded[2])
    boundaries = DurationBoundaries(*rounded)
    return boundaries, {
        "eligible_human_safe_example_count": len(values),
        "raw_quantiles_seconds": raw,
        "frozen_boundaries_seconds": asdict(boundaries),
        "rounding": "ceil to whole seconds; monotonicity enforced",
    }


def duration_band(delta: float | None, boundaries: DurationBoundaries) -> str:
    if delta is None:
        return "DURATION_UNKNOWN"
    if delta <= boundaries.very_close_seconds:
        return "DURATION_VERY_CLOSE"
    if delta <= boundaries.close_seconds:
        return "DURATION_CLOSE"
    if delta <= boundaries.moderate_seconds:
        return "DURATION_MODERATE"
    return "DURATION_FAR"


def policy_variants() -> tuple[PolicySpec, ...]:
    """Predeclared hierarchy variants; only evidence requirements differ."""
    return (
        PolicySpec(
            policy_id="POLICY_CONSERVATIVE_V1",
            require_exact_identity=True,
            minimum_title_similarity=1.0,
            require_primary_artist=True,
            require_complete_version_evidence=True,
            maximum_duration_band="DURATION_VERY_CLOSE",
            canonical_or_official_only=True,
            allow_lyric_fallback=False,
            lyric_min_relative_view_strength=None,
            official_video_maximum_duration_band=None,
            allow_other_source=False,
        ),
        PolicySpec(
            policy_id="POLICY_BALANCED_V1",
            require_exact_identity=True,
            minimum_title_similarity=1.0,
            require_primary_artist=True,
            require_complete_version_evidence=True,
            maximum_duration_band="DURATION_CLOSE",
            canonical_or_official_only=False,
            allow_lyric_fallback=True,
            lyric_min_relative_view_strength=0.001,
            official_video_maximum_duration_band="DURATION_VERY_CLOSE",
            allow_other_source=False,
        ),
        PolicySpec(
            policy_id="POLICY_PERMISSIVE_V1",
            require_exact_identity=False,
            minimum_title_similarity=0.75,
            require_primary_artist=True,
            require_complete_version_evidence=False,
            maximum_duration_band="DURATION_MODERATE",
            canonical_or_official_only=False,
            allow_lyric_fallback=True,
            lyric_min_relative_view_strength=None,
            official_video_maximum_duration_band="DURATION_MODERATE",
            allow_other_source=True,
        ),
    )


def _band_rank(value: str) -> int:
    return DURATION_BANDS.index(value) if value in DURATION_BANDS else len(DURATION_BANDS)


def _canonical_strength(feature: dict[str, Any]) -> tuple[str, int]:
    provenance = feature["source"]["provenance"]
    if provenance["topic_channel_signal"] and provenance["provided_to_youtube_by_signal"]:
        return "PROVENANCE_CANONICAL", 0
    if (
        provenance["topic_channel_signal"]
        or provenance["provided_to_youtube_by_signal"]
        or provenance["auto_generated_by_youtube_signal"]
    ):
        return "PROVENANCE_CANONICAL", 1
    if provenance["structured_release_metadata_signal"]:
        return "PROVENANCE_STRONG", 2
    if feature["source"]["uploader_or_channel_artist_match"]:
        return "PROVENANCE_SUPPORTING", 3
    return "PROVENANCE_WEAK", 4


def _identity_tier(feature: dict[str, Any], spec: PolicySpec) -> str:
    identity = feature["identity"]
    if identity["title_exact_normalized_match"] and identity["primary_artist_match"]:
        return "IDENTITY_EXACT"
    if (
        identity["primary_artist_match"]
        and identity["title_similarity"] >= spec.minimum_title_similarity
    ):
        return "IDENTITY_STRONG"
    return "IDENTITY_WEAK"


def _candidate_gate(
    feature: dict[str, Any], spec: PolicySpec, boundaries: DurationBoundaries
) -> tuple[bool, list[str], dict[str, Any]]:
    reasons: list[str] = []
    versions = feature["versions"]
    source_type = feature["source"]["source_type"]
    band = duration_band(feature["duration"]["absolute_duration_delta_seconds"], boundaries)
    identity_tier = _identity_tier(feature, spec)
    provenance_tier, provenance_rank = _canonical_strength(feature)

    if not feature["recording_eligible"]:
        reasons.extend(feature["ineligible_auto_match_reasons"])
    if versions["version_conflict_count"]:
        reasons.append("explicit target-relative version conflict")
    if spec.require_exact_identity and identity_tier != "IDENTITY_EXACT":
        reasons.append("policy requires exact normalized title and explicit primary performer")
    elif identity_tier == "IDENTITY_WEAK":
        reasons.append("identity evidence below policy requirement")
    if spec.require_primary_artist and not feature["identity"]["primary_artist_match"]:
        reasons.append("primary performer is not explicitly matched")
    if spec.require_complete_version_evidence and versions["version_absent_count"]:
        reasons.append("target version evidence is incomplete")
    if _band_rank(band) > _band_rank(spec.maximum_duration_band):
        reasons.append(f"{band} exceeds {spec.maximum_duration_band}")

    canonical = provenance_tier in {"PROVENANCE_CANONICAL", "PROVENANCE_STRONG"}
    if spec.canonical_or_official_only and not (
        canonical or source_type == "OFFICIAL_AUDIO"
    ):
        reasons.append("policy requires canonical provenance or Official Audio")
    if source_type == "LYRIC_VIDEO":
        if not spec.allow_lyric_fallback:
            reasons.append("policy does not allow lyric fallback")
        minimum = spec.lyric_min_relative_view_strength
        actual = feature["weak_evidence"]["relative_view_strength"]
        if minimum is not None and (actual is None or actual < minimum):
            reasons.append("lyric fallback lacks calibrated relative-view support")
    if source_type == "OFFICIAL_MUSIC_VIDEO":
        limit = spec.official_video_maximum_duration_band
        if limit is None or _band_rank(band) > _band_rank(limit):
            reasons.append("music-video duration evidence is insufficient for this policy")
    if source_type == "OTHER" and not spec.allow_other_source and not canonical:
        reasons.append("policy does not auto-select noncanonical OTHER sources")

    derived = {
        "identity_tier": identity_tier,
        "version_state": (
            "VERSION_CONFLICT" if versions["version_conflict_count"]
            else "VERSION_INCOMPLETE" if versions["version_absent_count"]
            else "VERSION_MATCH"
        ),
        "duration_band": band,
        "provenance_tier": provenance_tier,
        "provenance_rank": provenance_rank,
        "source_type": source_type,
    }
    return not reasons, reasons, derived


def _ordering_key(item: dict[str, Any]) -> tuple[Any, ...]:
    feature = item["feature"]
    derived = item["derived"]
    description = feature["description_evidence"]
    weak = feature["weak_evidence"]
    view_rank = weak["view_rank_among_plausible_candidates"]
    identity_rank = 0 if derived["identity_tier"] == "IDENTITY_EXACT" else 1
    version_rank = 0 if derived["version_state"] == "VERSION_MATCH" else 1
    return (
        identity_rank,
        version_rank,
        _band_rank(derived["duration_band"]),
        derived["provenance_rank"],
        SOURCE_ORDER[derived["source_type"]],
        0 if description["description_album_match"] is True else 1,
        0 if description["description_release_year_match"] is True else 1,
        0 if view_rank is not None else 1,
        int(view_rank) if view_rank is not None else 1_000_000,
        int(weak["search_rank"]),
    )


def resolve_track(
    track_row: dict[str, Any], spec: PolicySpec, boundaries: DurationBoundaries
) -> dict[str, Any]:
    plausible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for wrapped in track_row["candidates"]:
        candidate = wrapped["candidate"]
        feature = wrapped["features"]
        accepted, reasons, derived = _candidate_gate(feature, spec, boundaries)
        evidence = {
            "video_id": candidate["youtube_video_id"],
            "candidate_rank": candidate["rank"],
            "title": candidate.get("title"),
            "derived": derived,
            "duration": feature["duration"],
            "provenance": feature["source"]["provenance"],
            "relative_view_strength": feature["weak_evidence"]["relative_view_strength"],
            "reasons": reasons,
        }
        if accepted:
            plausible.append({**evidence, "feature": feature})
        else:
            excluded.append(evidence)
    ordered = sorted(plausible, key=_ordering_key)
    if not ordered:
        return {
            "status": MATCH_UNCERTAIN,
            "policy_rule_id": spec.policy_id,
            "selected_video_id": None,
            "selected_candidate_rank": None,
            "ranked_plausible_candidates": [],
            "uncertainty_reason": "no candidate satisfies the policy's hierarchical safety gate",
            "evidence_summary": {"plausible_count": 0, "excluded_count": len(excluded)},
            "excluded_candidates": excluded,
        }
    selected = ordered[0]
    return {
        "status": AUTO_MATCH,
        "policy_rule_id": spec.policy_id,
        "selected_video_id": selected["video_id"],
        "selected_candidate_rank": selected["candidate_rank"],
        "selection_reason": (
            "passed identity/version/duration/source gate; lexicographic hierarchy chose "
            "recording evidence before provenance, source quality, views, and rank"
        ),
        "confidence_tier": spec.policy_id.removeprefix("POLICY_").removesuffix("_V1"),
        "evidence_summary": {
            **selected["derived"],
            "duration": selected["duration"],
            "provenance": selected["provenance"],
            "relative_view_strength": selected["relative_view_strength"],
            "plausible_count": len(ordered),
            "excluded_count": len(excluded),
        },
        "ranked_plausible_candidates": [item["video_id"] for item in ordered],
        "excluded_candidates": excluded,
    }


def resolve_dataset(
    dataset: dict[str, Any], spec: PolicySpec, boundaries: DurationBoundaries
) -> dict[str, Any]:
    tracks = [
        {
            "stable_track_id": row["track"]["stable_track_id"],
            "decision": resolve_track(row, spec, boundaries),
        }
        for row in dataset["tracks"]
    ]
    return {
        "schema_version": "stage5b1b-resolver-decisions-v1",
        "policy": asdict(spec),
        "duration_boundaries": asdict(boundaries),
        "production_auto_match_activated": False,
        "tracks": tracks,
        "summary": {
            "track_count": len(tracks),
            "auto_match_count": sum(row["decision"]["status"] == AUTO_MATCH for row in tracks),
            "match_uncertain_count": sum(row["decision"]["status"] == MATCH_UNCERTAIN for row in tracks),
        },
    }
