"""Frozen manifest and raw-search contract for Stage 5B.2.

The primary experiment intentionally contains no resolver dependency: Spotify
title plus primary artist is sent to YouTube and the native top-three order is
preserved for independent human and Sol review.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b_representative_library import (
    build_benchmark_manifest,
    historical_exclusion_identities,
    load_library_snapshot,
)


MANIFEST_SCHEMA_VERSION = "stage5b2-youtube-prior-manifest-v1"
CONFIG_SCHEMA_VERSION = "stage5b2-youtube-prior-config-v1"
BENCHMARK_ID = "STAGE5B_YOUTUBE_PRIOR_V1"
SAMPLE_SEED = "stage5b-youtube-prior-v1-seed-2026-09-02"
SAMPLE_SIZE = 100
H1_TOP1_SAFE_MINIMUM = 0.90
H2_TOP3_SAFE_MINIMUM = 0.99
_SPACE = re.compile(r"\s+")


def natural_title_artist_query(track: SpotifyTrack) -> str:
    """Emit the sole frozen query: natural Spotify title + primary artist."""

    title = _SPACE.sub(" ", track.title).strip()
    artist = _SPACE.sub(" ", track.artists[0]).strip()
    query = f"{title} {artist}"
    if '"' in query:
        raise Stage5B1AValidationError("natural query must not contain quotation syntax")
    return query


def historical_manifest_paths(project_root: Path) -> tuple[Path, ...]:
    return (
        project_root / "reports/stage5b1a/frozen_tracks.json",
        project_root / "reports/stage5b1b/heldout_tracks.json",
        project_root / "reports/stage5b1b_fresh_challenge/challenge_tracks.json",
        project_root / "reports/stage5b_representative_library_v1/benchmark_manifest.json",
    )


def _write_immutable_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != value:
            raise Stage5B1AValidationError(f"refusing to replace frozen artifact: {path}")
        return
    atomic_json(path, value)


def _assert_no_spotify_overlap(
    tracks: Iterable[dict[str, Any]], historical_paths: Iterable[Path]
) -> None:
    selected = {row["spotify_track_id"] for row in tracks}
    for path in historical_paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        stack = [value]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                spotify_id = item.get("spotify_track_id")
                if isinstance(spotify_id, str) and spotify_id in selected:
                    raise Stage5B1AValidationError(
                        f"fresh Stage 5B.2 Spotify overlap in {path.name}"
                    )
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)


def freeze_youtube_prior_manifest(
    project_root: str | Path,
    snapshot_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    snapshot_path = Path(snapshot_path).resolve()
    output_dir = Path(output_dir).resolve()
    historical_paths = historical_manifest_paths(project_root)
    if not all(path.is_file() for path in historical_paths):
        raise Stage5B1AValidationError("historical Stage 5B exclusion evidence is incomplete")
    library = load_library_snapshot(snapshot_path)
    excluded, provenance = historical_exclusion_identities(historical_paths)
    manifest = build_benchmark_manifest(
        library,
        excluded,
        sample_size=SAMPLE_SIZE,
        seed=SAMPLE_SEED,
        snapshot_sha256=file_sha256(snapshot_path),
        exclusion_provenance=provenance,
    )
    manifest["schema_version"] = MANIFEST_SCHEMA_VERSION
    manifest["benchmark_id"] = BENCHMARK_ID
    manifest["tracks"] = [
        row | {"benchmark_id": f"stage5b_youtube_prior_v1_{index:03d}"}
        for index, row in enumerate(manifest["tracks"], start=1)
    ]
    _assert_no_spotify_overlap(manifest["tracks"], historical_paths)
    if manifest["sampled_track_count"] != SAMPLE_SIZE:
        raise Stage5B1AValidationError(
            f"Stage 5B.2 requires 100 held-out tracks, found {manifest['sampled_track_count']}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "benchmark_manifest.json"
    _write_immutable_json(manifest_path, manifest)
    manifest_sha = file_sha256(manifest_path)
    digest_path = output_dir / "benchmark_manifest.sha256"
    if digest_path.exists() and digest_path.read_text(encoding="utf-8").strip() != manifest_sha:
        raise Stage5B1AValidationError("Stage 5B.2 manifest digest lock changed")
    if not digest_path.exists():
        digest_path.write_text(manifest_sha + "\n", encoding="utf-8")
    config = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "benchmark_manifest": {
            "path": str(manifest_path.relative_to(project_root)),
            "sha256": manifest_sha,
        },
        "private_library_snapshot_sha256": file_sha256(snapshot_path),
        "sample_seed": SAMPLE_SEED,
        "sample_size": SAMPLE_SIZE,
        "historical_exclusion_paths": [
            {
                "path": str(path.relative_to(project_root)),
                "sha256": file_sha256(path),
            }
            for path in historical_paths
        ],
        "query": {
            "query_id": "NATURAL_SPOTIFY_TITLE_PRIMARY_ARTIST_V1",
            "template": "{spotify_title} {primary_artist}",
            "quotes": False,
            "forced_official_token": False,
            "alternate_queries": 0,
            "resolver_title_rewriting": False,
        },
        "retrieval": {
            "provider": "yt_dlp",
            "mode": "ytsearch3",
            "candidate_limit": 3,
            "preserve_native_rank": True,
            "metadata_only": True,
            "sequential": True,
            "sleep_between_tracks_seconds": 3.0,
            "socket_timeout_seconds": 30,
            "max_attempts": 2,
            "retry_backoff_seconds": 2.0,
        },
        "hypotheses": {
            "h1_top1_safe_minimum": H1_TOP1_SAFE_MINIMUM,
            "h2_top3_safe_minimum": H2_TOP3_SAFE_MINIMUM,
        },
        "review": {
            "labels": ["IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"],
            "safe_labels": ["IDEAL", "ACCEPTABLE"],
            "adaptive_stop_after_first_safe": True,
            "human_ground_truth": True,
            "sol_secondary_only": True,
        },
        "scope_guards": {
            "existing_resolver_invocations": 0,
            "candidate_reranking": False,
            "audio_downloads": 0,
            "video_downloads": 0,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
            "benchmark_tuning_permitted": False,
        },
    }
    _write_immutable_json(output_dir / "benchmark_config.json", config)
    return {"manifest": manifest, "config": config, "manifest_sha256": manifest_sha}
