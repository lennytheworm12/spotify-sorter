"""Hash-locked fresh held-out manifest for Stage 5B.1B."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .stage5b1a_models import (
    FeasibilityTrack,
    Stage5B1AValidationError,
    file_sha256,
)


MANIFEST_SCHEMA_VERSION = "stage5b1b-heldout-track-manifest-v1"
EXPERIMENT_ID = "stage5b1b_candidate_resolution_heldout"
TRACK_COUNT = 50


def _purpose(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 1000:
        raise Stage5B1AValidationError("purpose must be a non-empty string at most 1000 characters")
    return value.strip()


@dataclass(frozen=True)
class HeldoutManifest:
    path: Path
    sha256: str
    tracks: tuple[FeasibilityTrack, ...]
    purpose: str

    @property
    def stable_track_ids(self) -> tuple[str, ...]:
        return tuple(item.track.stable_track_id for item in self.tracks)


def load_heldout_manifest(
    path: str | Path, *, expected_sha256: str | None = None
) -> HeldoutManifest:
    manifest_path = Path(path)
    digest = file_sha256(manifest_path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise Stage5B1AValidationError(
            f"frozen held-out manifest SHA-256 mismatch: expected {expected_sha256}, got {digest}"
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.1B held-out manifest schema")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise Stage5B1AValidationError("unexpected Stage 5B.1B held-out experiment ID")
    if payload.get("frozen_before_discovery") is not True:
        raise Stage5B1AValidationError("held-out manifest was not frozen before discovery")
    rows = payload.get("tracks")
    if not isinstance(rows, list) or len(rows) != TRACK_COUNT:
        raise Stage5B1AValidationError(f"held-out manifest must contain exactly {TRACK_COUNT} tracks")
    tracks = tuple(FeasibilityTrack.from_dict(row) for row in rows)
    stable_ids = [item.track.stable_track_id for item in tracks]
    if stable_ids != sorted(stable_ids) or len(stable_ids) != len(set(stable_ids)):
        raise Stage5B1AValidationError("held-out stable_track_id values must be unique and sorted")
    if any(item.track.duration_ms is None for item in tracks):
        raise Stage5B1AValidationError("held-out targets require duration_ms for calibration features")
    years = [item.track.release_year for item in tracks]
    if any(year is None or not 2000 <= year <= 2026 for year in years):
        raise Stage5B1AValidationError("held-out tracks must have release years in 2000–2026")
    return HeldoutManifest(
        path=manifest_path,
        sha256=digest,
        tracks=tracks,
        purpose=_purpose(payload.get("purpose")),
    )
