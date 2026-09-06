"""Strict persisted schemas for Stage 5F.1 records."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any


FAMILY_STATUSES = {"VALID", "LOW_CONFIDENCE", "UNAVAILABLE"}
TRACK_STATUSES = {"SUCCESS", "PARTIAL", "FAILED"}


@dataclass(frozen=True)
class FamilyResult:
    status: str
    reasons: tuple[str, ...] = ()
    values: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in FAMILY_STATUSES:
            raise ValueError(f"invalid family status: {self.status}")
        object.__setattr__(self, "reasons", tuple(sorted(set(self.reasons))))
        _validate_finite(self.values)


@dataclass(frozen=True)
class TrackFeatures:
    schema_version: str
    extractor_id: str
    extractor_version: str
    algorithm_spec_sha256: str
    implementation_sha256: str
    extraction_config_sha256: str
    environment_sha256: str
    source_sha256: str
    duration_seconds: float | None
    source_sample_rate_hz: int | None
    source_channels: int | None
    analysis_sample_rate_hz: int
    normalization: FamilyResult
    status: str
    warnings: tuple[str, ...]
    failure: dict[str, str] | None
    source_level: FamilyResult
    dynamics: FamilyResult
    activity: FamilyResult
    percussion: FamilyResult
    pulse: FamilyResult
    beat: FamilyResult
    metrical_profiles: tuple[dict[str, Any], ...] = ()
    temporal_profiles: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.status not in TRACK_STATUSES:
            raise ValueError(f"invalid track status: {self.status}")
        object.__setattr__(self, "warnings", tuple(sorted(set(self.warnings))))
        _validate_finite(asdict(self))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PairFeatures:
    pair_id: str
    left_spotify_id: str
    right_spotify_id: str
    left_source_sha256: str
    right_source_sha256: str
    comparison_config_sha256: str
    scaler_sha256: str
    components: dict[str, Any]
    feature_differences: dict[str, Any]
    common_feature_masks: dict[str, list[str]]
    metrical_alignment: dict[str, Any] | None

    def __post_init__(self) -> None:
        _validate_finite(asdict(self))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validate_finite(value: Any, path: str = "root") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite scalar at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_finite(item, f"{path}[{index}]")
