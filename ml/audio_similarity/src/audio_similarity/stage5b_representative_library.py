"""Deterministic held-out real-library benchmark construction.

This module is deliberately network-free. A private owner-library snapshot is
collected only after the Stage 5B.1J human gate passes; these helpers normalize,
deduplicate, exclude historical evidence, and freeze a reproducible sample.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_identity import normalize_text
from .stage5b1c_normalization import parse_tier2_title


SNAPSHOT_SCHEMA_VERSION = "stage5b-owner-library-snapshot-v1"
MANIFEST_SCHEMA_VERSION = "stage5b-representative-library-manifest-v1"
DEFAULT_SAMPLE_SIZE = 100
DEFAULT_SAMPLE_SEED = "stage5b-representative-library-v1-seed-2026-09-02"
_ISRC_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$", re.IGNORECASE)


@dataclass(frozen=True)
class LibraryTrack:
    track: SpotifyTrack
    source_keys: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"track": self.track.to_dict(), "source_keys": list(self.source_keys)}


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _release_year(album: dict[str, Any]) -> int | None:
    raw = _text(album.get("release_date"))
    if not raw or len(raw) < 4 or not raw[:4].isdigit():
        return None
    year = int(raw[:4])
    return year if 1800 <= year <= 2200 else None


def _valid_isrc(value: Any) -> str | None:
    """Retain only standard 12-character ISRCs from external metadata."""

    raw = _text(value)
    return raw.upper() if raw and _ISRC_PATTERN.fullmatch(raw) else None


def spotify_track_from_library_item(value: dict[str, Any], stable_id: str) -> SpotifyTrack:
    """Normalize a raw Spotify Web API track or already-sanitized track."""

    raw = value.get("track") if isinstance(value.get("track"), dict) else value
    if not isinstance(raw, dict):
        raise Stage5B1AValidationError("library item does not contain a Spotify track")
    spotify_id = _text(raw.get("id") or raw.get("spotify_track_id"))
    title = _text(raw.get("name") or raw.get("title"))
    artists_raw = raw.get("artists")
    if not isinstance(artists_raw, list):
        raise Stage5B1AValidationError("library track artists must be an array")
    artists = [
        name for item in artists_raw
        if (name := _text(item.get("name") if isinstance(item, dict) else item))
    ]
    album_raw = raw.get("album")
    album = (
        _text(album_raw.get("name"))
        if isinstance(album_raw, dict)
        else _text(album_raw)
    )
    release_year = (
        _release_year(album_raw) if isinstance(album_raw, dict)
        else raw.get("release_year")
    )
    external_ids = raw.get("external_ids")
    isrc = (
        _valid_isrc(external_ids.get("isrc"))
        if isinstance(external_ids, dict)
        else _valid_isrc(raw.get("isrc"))
    )
    return SpotifyTrack.from_dict({
        "stable_track_id": stable_id,
        "spotify_track_id": spotify_id,
        "title": title,
        "artists": artists,
        "album": album,
        "duration_ms": raw.get("duration_ms"),
        "release_year": release_year,
        "isrc": isrc,
    })


def _spotify_identity(track: SpotifyTrack) -> str | None:
    return f"spotify:{track.spotify_track_id}" if track.spotify_track_id else None


def _semantic_identity(track: SpotifyTrack) -> str:
    artists = "|".join(sorted(normalize_text(artist) for artist in track.artists))
    return f"semantic:{normalize_text(track.title)}::{artists}"


def _core_identity(track: SpotifyTrack) -> str:
    artists = "|".join(sorted(normalize_text(artist) for artist in track.artists))
    core = parse_tier2_title(track.title, candidate=False).core_title
    return f"core:{normalize_text(core)}::{artists}"


def track_identities(track: SpotifyTrack) -> frozenset[str]:
    return frozenset(filter(None, (
        _spotify_identity(track), _semantic_identity(track), _core_identity(track)
    )))


def load_library_snapshot(path: str | Path) -> list[LibraryTrack]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected owner-library snapshot schema")
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources:
        raise Stage5B1AValidationError("owner-library snapshot has no sources")
    by_spotify_id: dict[str, SpotifyTrack] = {}
    memberships: dict[str, set[str]] = defaultdict(set)
    ordinal = 0
    for source in sources:
        if not isinstance(source, dict):
            raise Stage5B1AValidationError("invalid owner-library source")
        source_key = _text(source.get("source_key"))
        items = source.get("tracks")
        if not source_key or not isinstance(items, list):
            raise Stage5B1AValidationError("invalid owner-library source fields")
        for item in items:
            if not isinstance(item, dict):
                continue
            raw = item.get("track") if isinstance(item.get("track"), dict) else item
            if not isinstance(raw, dict) or raw.get("is_local") is True:
                continue
            ordinal += 1
            track = spotify_track_from_library_item(item, f"library_raw_{ordinal:06d}")
            if not track.spotify_track_id:
                raise Stage5B1AValidationError("real-library tracks require Spotify IDs")
            existing = by_spotify_id.get(track.spotify_track_id)
            if existing is not None and existing.to_dict() | {"stable_track_id": track.stable_track_id} != track.to_dict() | {"stable_track_id": track.stable_track_id}:
                raise Stage5B1AValidationError(
                    f"conflicting metadata for Spotify track {track.spotify_track_id}"
                )
            by_spotify_id[track.spotify_track_id] = track
            memberships[track.spotify_track_id].add(source_key)
    output = []
    for spotify_id in sorted(by_spotify_id):
        original = by_spotify_id[spotify_id]
        track = SpotifyTrack(
            stable_track_id=f"library_{spotify_id}",
            spotify_track_id=spotify_id,
            title=original.title,
            artists=original.artists,
            album=original.album,
            duration_ms=original.duration_ms,
            release_year=original.release_year,
            isrc=original.isrc,
        )
        output.append(LibraryTrack(track, tuple(sorted(memberships[spotify_id]))))
    if not output:
        raise Stage5B1AValidationError("owner-library snapshot has no usable tracks")
    return output


def _track_objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        keys = {"title", "artists"}
        if keys <= value.keys():
            yield value
        for child in value.values():
            yield from _track_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _track_objects(child)


def historical_exclusion_identities(paths: Iterable[str | Path]) -> tuple[set[str], dict[str, Any]]:
    identities: set[str] = set()
    sources = []
    for raw_path in paths:
        path = Path(raw_path)
        value = json.loads(path.read_text(encoding="utf-8"))
        count_before = len(identities)
        observed = 0
        for raw in _track_objects(value):
            try:
                track = SpotifyTrack.from_dict({
                    "stable_track_id": raw.get("stable_track_id") or f"historical_{observed:06d}",
                    "spotify_track_id": raw.get("spotify_track_id"),
                    "title": raw.get("title"),
                    "artists": raw.get("artists"),
                    "album": raw.get("album"),
                    "duration_ms": raw.get("duration_ms"),
                    "release_year": raw.get("release_year"),
                    "isrc": raw.get("isrc"),
                })
            except Stage5B1AValidationError:
                continue
            observed += 1
            identities.update(track_identities(track))
        sources.append({
            "path": str(path),
            "sha256": file_sha256(path),
            "track_objects": observed,
            "new_identity_count": len(identities) - count_before,
        })
    return identities, {"sources": sources, "identity_count": len(identities)}


def build_benchmark_manifest(
    library: list[LibraryTrack],
    excluded_identities: set[str],
    *,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    seed: str = DEFAULT_SAMPLE_SEED,
    snapshot_sha256: str,
    exclusion_provenance: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(sample_size, bool) or not isinstance(sample_size, int) or sample_size <= 0:
        raise Stage5B1AValidationError("benchmark sample size must be positive")
    if not isinstance(seed, str) or not seed:
        raise Stage5B1AValidationError("benchmark seed is required")
    eligible = [
        item for item in library
        if track_identities(item.track).isdisjoint(excluded_identities)
    ]
    ordered = sorted(
        eligible,
        key=lambda item: hashlib.sha256(
            f"{seed}|{item.track.spotify_track_id}".encode()
        ).hexdigest(),
    )
    selected = ordered[: min(sample_size, len(ordered))]
    rows = []
    for index, item in enumerate(selected, start=1):
        track = item.track
        rows.append({
            "benchmark_id": f"stage5b_library_v1_{index:03d}",
            "spotify_track_id": track.spotify_track_id,
            "title": track.title,
            "artists": list(track.artists),
            "album": track.album,
            "duration_ms": track.duration_ms,
            "release_year": track.release_year,
            "isrc": track.isrc,
            "sample_seed": seed,
            "library_source_keys": list(item.source_keys),
        })
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "benchmark_id": "STAGE5B_REPRESENTATIVE_LIBRARY_V1",
        "sample_seed": seed,
        "requested_sample_size": sample_size,
        "library_unique_track_count": len(library),
        "historically_excluded_track_count": len(library) - len(eligible),
        "eligible_heldout_track_count": len(eligible),
        "sampled_track_count": len(rows),
        "private_library_snapshot_sha256": snapshot_sha256,
        "historical_exclusion_provenance": exclusion_provenance,
        "post_freeze_substitutions": 0,
        "tracks": rows,
    }


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def manifest_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def verify_frozen_manifest(path: str | Path, digest_path: str | Path) -> dict[str, Any]:
    path = Path(path)
    expected = Path(digest_path).read_text(encoding="utf-8").strip()
    actual = file_sha256(path)
    if expected != actual:
        raise Stage5B1AValidationError(
            f"representative benchmark manifest changed: {actual} != {expected}"
        )
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected representative benchmark manifest schema")
    if value.get("sampled_track_count") != len(value.get("tracks", [])):
        raise Stage5B1AValidationError("representative benchmark manifest count changed")
    if value.get("post_freeze_substitutions") != 0:
        raise Stage5B1AValidationError("post-freeze benchmark substitution detected")
    return value
