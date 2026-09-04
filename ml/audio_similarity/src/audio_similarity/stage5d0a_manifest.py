"""Deterministic catalog normalization and batching for Stage 5D.0A."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json


EXPERIMENT_ID = "STAGE5D0A_COMMERCIAL_SEED_BATCH_0001"
REPORT_DIRECTORY = "reports/stage5d0a_seed_batch_0001"
CATALOG_INPUT_SCHEMA = "stage5d0a-commercial-seed-catalog-input-v1"
GLOBAL_MANIFEST_SCHEMA = "stage5d0a-global-seed-catalog-manifest-v1"
BATCH_MANIFEST_SCHEMA = "stage5d0a-seed-batch-manifest-v1"
ORDERING_SEED = "stage5d0a-commercial-seed-order-2026-09-04-v1"
MAX_BATCH_SIZE = 500
MIN_YEAR = 2000
MAX_YEAR = 2026


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def document_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _normalized_track(raw: dict[str, Any], ordinal: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise Stage5B1AValidationError("commercial catalog tracks must be objects")
    track = SpotifyTrack.from_dict(
        {
            "stable_track_id": f"stage5d0a_catalog_{ordinal:06d}",
            "spotify_track_id": raw.get("spotify_track_id") or raw.get("id"),
            "title": raw.get("title") or raw.get("name"),
            "artists": raw.get("artists"),
            "album": raw.get("album"),
            "duration_ms": raw.get("duration_ms"),
            "release_year": raw.get("release_year"),
            "isrc": raw.get("isrc"),
        }
    )
    if not track.spotify_track_id:
        raise Stage5B1AValidationError("commercial catalog tracks require Spotify IDs")
    if track.release_year is None or not MIN_YEAR <= track.release_year <= MAX_YEAR:
        raise Stage5B1AValidationError("commercial catalog track is outside 2000–2026")
    source_memberships = raw.get("source_memberships")
    if not isinstance(source_memberships, list) or not source_memberships:
        raise Stage5B1AValidationError(
            "commercial catalog tracks require source memberships"
        )
    if any(not isinstance(item, str) or not item.strip() for item in source_memberships):
        raise Stage5B1AValidationError("invalid commercial catalog source membership")
    normalized = {
        "spotify_track_id": track.spotify_track_id,
        "title": track.title,
        "artists": list(track.artists),
        "album": track.album,
        "duration_ms": track.duration_ms,
        "release_year": track.release_year,
        "isrc": track.isrc,
        "source_memberships": sorted(set(source_memberships)),
    }
    for field in ("recording_id", "assigned_bucket", "assigned_year", "alias_ranks",
                  "ranking_key", "collapsed_spotify_ids", "all_occurrences", "spotify_release_date"):
        if field in raw:
            normalized[field] = raw[field]
    return normalized


def build_global_manifest(
    catalog_input: dict[str, Any],
    *,
    catalog_input_sha256: str,
    ordering_seed: str = ORDERING_SEED,
    batch_size: int = MAX_BATCH_SIZE,
) -> dict[str, Any]:
    """Normalize, Spotify-ID deduplicate, seeded-order, and partition a catalog."""
    if catalog_input.get("schema_version") != CATALOG_INPUT_SCHEMA:
        raise Stage5B1AValidationError("missing commercial seed catalog design input")
    design = catalog_input.get("catalog_design")
    tracks = catalog_input.get("tracks")
    if not isinstance(design, dict) or not design.get("design_id"):
        raise Stage5B1AValidationError("commercial catalog design metadata is required")
    if not isinstance(tracks, list) or not tracks:
        raise Stage5B1AValidationError("commercial seed catalog is empty")
    if not isinstance(ordering_seed, str) or not ordering_seed:
        raise Stage5B1AValidationError("ordering seed is required")
    if isinstance(batch_size, bool) or not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise Stage5B1AValidationError("batch size must be between 1 and 500")

    by_spotify_id: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    for ordinal, raw in enumerate(tracks, start=1):
        normalized = _normalized_track(raw, ordinal)
        spotify_id = normalized["spotify_track_id"]
        prior = by_spotify_id.get(spotify_id)
        if prior is None:
            by_spotify_id[spotify_id] = normalized
            continue
        comparable_keys = (
            "title",
            "artists",
            "album",
            "duration_ms",
            "release_year",
            "isrc",
        )
        if any(prior[key] != normalized[key] for key in comparable_keys):
            raise Stage5B1AValidationError(
                f"conflicting metadata for Spotify track {spotify_id}"
            )
        prior["source_memberships"] = sorted(
            set(prior["source_memberships"]) | set(normalized["source_memberships"])
        )
        duplicate_count += 1

    ordered = sorted(
        by_spotify_id.values(),
        key=lambda row: hashlib.sha256(
            f"{ordering_seed}|{row['spotify_track_id']}".encode()
        ).hexdigest(),
    )
    manifest_tracks = []
    for index, row in enumerate(ordered, start=1):
        batch_number = (index - 1) // batch_size + 1
        batch_position = (index - 1) % batch_size + 1
        manifest_tracks.append(
            {
                "global_index": index,
                "batch_number": batch_number,
                "batch_position": batch_position,
                "stage5d0a_track_id": f"stage5d0a_{index:06d}",
                **row,
            }
        )
    batch_count = (len(manifest_tracks) + batch_size - 1) // batch_size
    year_counts: dict[str, int] = {}
    for row in manifest_tracks:
        year = str(row["release_year"])
        year_counts[year] = year_counts.get(year, 0) + 1
    return {
        "schema_version": GLOBAL_MANIFEST_SCHEMA,
        "experiment_family": "STAGE5D_COMMERCIAL_SEED_CORPUS",
        "catalog_design": design,
        "catalog_input_sha256": catalog_input_sha256,
        "ordering": {
            "method": "SHA256_SEED_PLUS_SPOTIFY_ID_ASCENDING",
            "seed": ordering_seed,
            "manual_curation_after_ordering": False,
        },
        "year_bounds": {"minimum": MIN_YEAR, "maximum": MAX_YEAR},
        "input_track_count": len(tracks),
        "spotify_id_duplicate_count": duplicate_count,
        "unique_track_count": len(manifest_tracks),
        "batch_size": batch_size,
        "batch_count": batch_count,
        "year_distribution": dict(sorted(year_counts.items())),
        "tracks": manifest_tracks,
    }


def build_batch_manifest(
    global_manifest: dict[str, Any], batch_number: int
) -> dict[str, Any]:
    if global_manifest.get("schema_version") != GLOBAL_MANIFEST_SCHEMA:
        raise Stage5B1AValidationError("invalid Stage 5D global manifest")
    if isinstance(batch_number, bool) or not isinstance(batch_number, int) or batch_number < 1:
        raise Stage5B1AValidationError("batch number must be positive")
    tracks = [
        row for row in global_manifest["tracks"] if row["batch_number"] == batch_number
    ]
    if not tracks:
        raise Stage5B1AValidationError(f"batch {batch_number:04d} does not exist")
    if len(tracks) > MAX_BATCH_SIZE:
        raise Stage5B1AValidationError("a Stage 5D batch cannot exceed 500 tracks")
    expected_positions = list(range(1, len(tracks) + 1))
    if [row["batch_position"] for row in tracks] != expected_positions:
        raise Stage5B1AValidationError("batch positions are not contiguous")
    return {
        "schema_version": BATCH_MANIFEST_SCHEMA,
        "experiment_id": (
            EXPERIMENT_ID
            if batch_number == 1
            else f"STAGE5D_COMMERCIAL_SEED_BATCH_{batch_number:04d}"
        ),
        "batch_number": batch_number,
        "global_manifest_sha256": document_sha256(global_manifest),
        "requested_track_count": len(tracks),
        "maximum_track_count": MAX_BATCH_SIZE,
        "automatic_next_batch": False,
        "tracks": tracks,
    }


def _write_immutable_json(path: Path, value: dict[str, Any]) -> None:
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != value:
            raise Stage5B1AValidationError(f"refusing to replace frozen artifact: {path}")
        return
    atomic_json(path, value)


def freeze_catalog_and_batch_one(
    catalog_input_path: str | Path,
    report_directory: str | Path,
    *,
    ordering_seed: str = ORDERING_SEED,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Freeze the full ordering and Batch 0001; never create a later batch here."""
    source = Path(catalog_input_path).resolve()
    report = Path(report_directory).resolve()
    catalog_input = json.loads(source.read_text(encoding="utf-8"))
    global_manifest = build_global_manifest(
        catalog_input,
        catalog_input_sha256=file_sha256(source),
        ordering_seed=ordering_seed,
    )
    batch = build_batch_manifest(global_manifest, 1)
    report.mkdir(parents=True, exist_ok=True)
    global_path = report / "global_seed_catalog_manifest.json"
    batch_path = report / "batch_0001_manifest.json"
    _write_immutable_json(global_path, global_manifest)
    _write_immutable_json(batch_path, batch)
    global_sha = file_sha256(global_path)
    batch_sha = file_sha256(batch_path)
    for path, digest in (
        (report / "global_seed_catalog_manifest.sha256", global_sha),
        (report / "batch_0001_manifest.sha256", batch_sha),
    ):
        if path.is_file() and path.read_text(encoding="utf-8").strip() != digest:
            raise Stage5B1AValidationError(f"frozen digest changed: {path}")
        if not path.is_file():
            path.write_text(digest + "\n", encoding="utf-8")
    return global_manifest, batch
