"""Source-independent track and frozen-manifest models for Stage 5B.1A."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MANIFEST_SCHEMA_VERSION = "stage5b1a-frozen-track-manifest-v1"
EXPERIMENT_ID = "stage5b1a_firecrawl_youtube_discovery_feasibility"
_SPOTIFY_ID = re.compile(r"^[A-Za-z0-9]{22}$")
_ISRC = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{7}$")


class Stage5B1AValidationError(ValueError):
    """Raised when discovery input or frozen metadata violates its contract."""


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _required_text(value: Any, field: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Stage5B1AValidationError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise Stage5B1AValidationError(f"{field} exceeds {maximum} characters")
    return normalized


def _optional_text(value: Any, field: str, maximum: int = 500) -> str | None:
    if value is None:
        return None
    return _required_text(value, field, maximum)


@dataclass(frozen=True)
class SpotifyTrack:
    """Normalized metadata boundary; independent of Spotify and Firecrawl clients."""

    stable_track_id: str
    title: str
    artists: tuple[str, ...]
    spotify_track_id: str | None = None
    album: str | None = None
    duration_ms: int | None = None
    release_year: int | None = None
    isrc: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SpotifyTrack":
        if not isinstance(value, dict):
            raise Stage5B1AValidationError("track must be an object")
        artists = value.get("artists")
        if not isinstance(artists, list) or not artists:
            raise Stage5B1AValidationError("artists must be a non-empty array")
        normalized_artists = tuple(
            _required_text(artist, f"artists[{index}]", 200)
            for index, artist in enumerate(artists)
        )
        if len(set(normalized_artists)) != len(normalized_artists):
            raise Stage5B1AValidationError("artists must not contain duplicates")

        spotify_track_id = _optional_text(
            value.get("spotify_track_id"), "spotify_track_id", 22
        )
        if spotify_track_id and not _SPOTIFY_ID.fullmatch(spotify_track_id):
            raise Stage5B1AValidationError("spotify_track_id must be 22 base62 characters")

        duration_ms = value.get("duration_ms")
        if duration_ms is not None and (
            not isinstance(duration_ms, int)
            or isinstance(duration_ms, bool)
            or not 1 <= duration_ms <= 86_400_000
        ):
            raise Stage5B1AValidationError("duration_ms must be a positive integer at most 24 hours")

        release_year = value.get("release_year")
        if release_year is not None and (
            not isinstance(release_year, int)
            or isinstance(release_year, bool)
            or not 1900 <= release_year <= 2100
        ):
            raise Stage5B1AValidationError("release_year must be between 1900 and 2100")

        isrc = _optional_text(value.get("isrc"), "isrc", 12)
        if isrc:
            isrc = isrc.upper()
            if not _ISRC.fullmatch(isrc):
                raise Stage5B1AValidationError("isrc must be a 12-character ISRC without separators")

        return cls(
            stable_track_id=_required_text(value.get("stable_track_id"), "stable_track_id", 200),
            spotify_track_id=spotify_track_id,
            title=_required_text(value.get("title"), "title"),
            artists=normalized_artists,
            album=_optional_text(value.get("album"), "album"),
            duration_ms=duration_ms,
            release_year=release_year,
            isrc=isrc,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stable_track_id": self.stable_track_id,
            "spotify_track_id": self.spotify_track_id,
            "title": self.title,
            "artists": list(self.artists),
            "album": self.album,
            "duration_ms": self.duration_ms,
            "release_year": self.release_year,
            "isrc": self.isrc,
        }


@dataclass(frozen=True)
class FeasibilityTrack:
    track: SpotifyTrack
    case_tags: tuple[str, ...]
    case_rationale: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FeasibilityTrack":
        if not isinstance(value, dict):
            raise Stage5B1AValidationError("manifest track entry must be an object")
        tags = value.get("case_tags")
        if not isinstance(tags, list) or not tags:
            raise Stage5B1AValidationError("case_tags must be a non-empty array")
        normalized_tags = tuple(
            _required_text(tag, f"case_tags[{index}]", 100) for index, tag in enumerate(tags)
        )
        if len(set(normalized_tags)) != len(normalized_tags):
            raise Stage5B1AValidationError("case_tags must not contain duplicates")
        return cls(
            track=SpotifyTrack.from_dict(value.get("track")),
            case_tags=normalized_tags,
            case_rationale=_required_text(value.get("case_rationale"), "case_rationale", 1000),
        )


@dataclass(frozen=True)
class FrozenTrackManifest:
    path: Path
    sha256: str
    tracks: tuple[FeasibilityTrack, ...]
    purpose: str

    @property
    def stable_track_ids(self) -> tuple[str, ...]:
        return tuple(item.track.stable_track_id for item in self.tracks)


def load_frozen_manifest(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
) -> FrozenTrackManifest:
    manifest_path = Path(path)
    digest = file_sha256(manifest_path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise Stage5B1AValidationError(
            f"frozen manifest SHA-256 mismatch: expected {expected_sha256}, got {digest}"
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected frozen manifest schema version")
    if payload.get("experiment_id") != EXPERIMENT_ID:
        raise Stage5B1AValidationError("unexpected experiment ID")
    if payload.get("frozen_before_live_discovery") is not True:
        raise Stage5B1AValidationError("manifest must be frozen before live discovery")
    rows = payload.get("tracks")
    if not isinstance(rows, list) or not 20 <= len(rows) <= 30:
        raise Stage5B1AValidationError("frozen feasibility manifest must contain 20–30 tracks")
    tracks = tuple(FeasibilityTrack.from_dict(row) for row in rows)
    stable_ids = [item.track.stable_track_id for item in tracks]
    if len(stable_ids) != len(set(stable_ids)):
        raise Stage5B1AValidationError("stable_track_id values must be unique")
    if stable_ids != sorted(stable_ids):
        raise Stage5B1AValidationError("manifest tracks must be sorted by stable_track_id")
    years = [item.track.release_year for item in tracks]
    if any(year is None or not 2000 <= year <= 2026 for year in years):
        raise Stage5B1AValidationError("feasibility tracks must have release years in 2000–2026")
    return FrozenTrackManifest(
        path=manifest_path,
        sha256=digest,
        tracks=tracks,
        purpose=_required_text(payload.get("purpose"), "purpose", 1000),
    )
