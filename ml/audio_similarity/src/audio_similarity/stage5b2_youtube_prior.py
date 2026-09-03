"""Frozen manifest and raw-search contract for Stage 5B.2.

The primary experiment intentionally contains no resolver dependency: Spotify
title plus primary artist is sent to YouTube and the native top-three order is
preserved for independent human and Sol review.
"""
from __future__ import annotations

import json
import re
import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .stage5b1a2_config import YtDlpProviderConfig
from .stage5b1a2_ytdlp import (
    YtDlpDiscoveryAdapter,
    YtDlpPythonBackend,
    YtDlpSearchError,
)
from .stage5b1a_config import QueryConfig
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
DISCOVERY_SCHEMA_VERSION = "stage5b2-youtube-top3-discovery-v1"
SOL_PAYLOAD_SCHEMA_VERSION = "stage5b2-sol-blind-payload-v1"
STATUS_DISCOVERY_RUNNING = "STAGE5B2_YOUTUBE_TOP3_DISCOVERY_RUNNING"
STATUS_DISCOVERY_COMPLETE = "STAGE5B2_YOUTUBE_TOP3_DISCOVERY_COMPLETE"


@dataclass(frozen=True)
class YoutubePriorConfig:
    path: Path
    project_root: Path
    manifest_path: Path
    manifest_sha256: str
    private_snapshot_sha256: str
    provider: YtDlpProviderConfig
    output_dir: Path
    sha256: str


def natural_title_artist_query(track: SpotifyTrack) -> str:
    """Emit the sole frozen query: natural Spotify title + primary artist."""

    title = _SPACE.sub(" ", track.title).strip()
    artist = _SPACE.sub(" ", track.artists[0]).strip()
    query = f"{title} {artist}"
    if '"' in query:
        raise Stage5B1AValidationError("natural query must not contain quotation syntax")
    return query


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def load_youtube_prior_config(path: str | Path) -> YoutubePriorConfig:
    path = Path(path).resolve()
    value = _json(path)
    if value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.2 config schema")
    project_root = path.parents[2]
    manifest = value.get("benchmark_manifest")
    retrieval = value.get("retrieval")
    if not isinstance(manifest, dict) or not isinstance(retrieval, dict):
        raise Stage5B1AValidationError("Stage 5B.2 config is incomplete")
    if (
        retrieval.get("mode") != "ytsearch3"
        or retrieval.get("candidate_limit") != 3
        or retrieval.get("metadata_only") is not True
        or retrieval.get("sequential") is not True
        or retrieval.get("preserve_native_rank") is not True
    ):
        raise Stage5B1AValidationError("Stage 5B.2 raw top-three contract changed")
    manifest_path = project_root / manifest["path"]
    actual = file_sha256(manifest_path)
    if actual != manifest.get("sha256"):
        raise Stage5B1AValidationError("Stage 5B.2 frozen manifest changed")
    hypotheses = value.get("hypotheses", {})
    if hypotheses != {
        "h1_top1_safe_minimum": H1_TOP1_SAFE_MINIMUM,
        "h2_top3_safe_minimum": H2_TOP3_SAFE_MINIMUM,
    }:
        raise Stage5B1AValidationError("Stage 5B.2 predeclared hypotheses changed")
    return YoutubePriorConfig(
        path=path,
        project_root=project_root,
        manifest_path=manifest_path,
        manifest_sha256=actual,
        private_snapshot_sha256=str(value["private_library_snapshot_sha256"]),
        provider=YtDlpProviderConfig(
            candidate_limit=3,
            search_prefix="ytsearch3:",
            extract_flat="in_playlist",
            skip_download=True,
            simulate=True,
            ignore_user_config=True,
            cache_enabled=False,
            socket_timeout_seconds=int(retrieval["socket_timeout_seconds"]),
            max_attempts=int(retrieval["max_attempts"]),
            retry_backoff_seconds=float(retrieval["retry_backoff_seconds"]),
            sleep_between_tracks_seconds=float(retrieval["sleep_between_tracks_seconds"]),
        ),
        output_dir=path.parent,
        sha256=file_sha256(path),
    )


def load_youtube_prior_manifest(config: YoutubePriorConfig) -> dict[str, Any]:
    value = _json(config.manifest_path)
    if (
        value.get("schema_version") != MANIFEST_SCHEMA_VERSION
        or value.get("benchmark_id") != BENCHMARK_ID
        or value.get("sampled_track_count") != SAMPLE_SIZE
        or len(value.get("tracks", [])) != SAMPLE_SIZE
        or value.get("post_freeze_substitutions") != 0
    ):
        raise Stage5B1AValidationError("invalid frozen Stage 5B.2 manifest")
    return value


def _manifest_track(row: dict[str, Any]) -> SpotifyTrack:
    return SpotifyTrack.from_dict({
        "stable_track_id": row["benchmark_id"],
        "spotify_track_id": row["spotify_track_id"],
        "title": row["title"],
        "artists": row["artists"],
        "album": row.get("album"),
        "duration_ms": row.get("duration_ms"),
        "release_year": row.get("release_year"),
        "isrc": row.get("isrc"),
    })


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _query_config() -> QueryConfig:
    # The adapter receives an explicit query; this inert config cannot rewrite it.
    return QueryConfig(
        variant_id="natural-spotify-title-primary-artist-v1",
        template="{normalized_title} {primary_artist}",
        normalize_featured_artist_noise=False,
    )


def _discovery_document(
    config: YoutubePriorConfig,
    rows: list[dict[str, Any]],
    *,
    status: str,
    started_at: str,
    elapsed_seconds: float,
) -> dict[str, Any]:
    versions = sorted({
        str(row["outcome"].get("provider", {}).get("version"))
        for row in rows if row["outcome"].get("provider", {}).get("version")
    })
    return {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "status": status,
        "benchmark_manifest_sha256": config.manifest_sha256,
        "benchmark_config_sha256": config.sha256,
        "started_at_utc": started_at,
        "completed_at_utc": _now() if status == STATUS_DISCOVERY_COMPLETE else None,
        "elapsed_current_process_seconds": elapsed_seconds,
        "provider": {
            "name": "yt_dlp",
            "versions": versions,
            "search_mode": "ytsearch3",
            "candidate_limit": 3,
            "metadata_only": True,
            "native_rank_preserved": True,
            "sequential": True,
            "sleep_between_tracks_seconds": config.provider.sleep_between_tracks_seconds,
        },
        "summary": {
            "tracks_total": SAMPLE_SIZE,
            "tracks_completed": len(rows),
            "search_failures": sum(row["outcome"].get("error") is not None for row in rows),
            "tracks_with_candidates": sum(bool(row["outcome"].get("candidates")) for row in rows),
            "zero_candidate_tracks": sum(not row["outcome"].get("candidates") for row in rows),
            "candidate_count": sum(len(row["outcome"].get("candidates", [])) for row in rows),
            "warning_count": sum(len(row["outcome"].get("warnings", [])) for row in rows),
        },
        "tracks": rows,
        "scope_guards": {
            "existing_resolver_invocations": 0,
            "candidate_reranking": False,
            "alternate_queries": 0,
            "audio_downloads": 0,
            "video_downloads": 0,
            "stage5a_calls": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
    }


def run_top3_discovery(
    config: YoutubePriorConfig,
    adapter: YtDlpDiscoveryAdapter | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    manifest = load_youtube_prior_manifest(config)
    output = config.output_dir / "youtube_top3_discovery.json"
    existing = _json(output) if output.exists() else None
    if existing and existing.get("status") == STATUS_DISCOVERY_COMPLETE:
        raise Stage5B1AValidationError("Stage 5B.2 discovery is already frozen")
    rows = list(existing.get("tracks", [])) if existing else []
    expected_ids = [row["benchmark_id"] for row in manifest["tracks"]]
    if [row.get("benchmark_id") for row in rows] != expected_ids[:len(rows)]:
        raise Stage5B1AValidationError("partial Stage 5B.2 discovery is not a manifest prefix")
    adapter = adapter or YtDlpDiscoveryAdapter(
        config.provider, _query_config(), YtDlpPythonBackend(config.provider)
    )
    started_at = existing.get("started_at_utc") if existing else _now()
    started_clock = time.monotonic()
    for index, manifest_row in enumerate(manifest["tracks"][len(rows):], start=len(rows)):
        track = _manifest_track(manifest_row)
        query = natural_title_artist_query(track)
        requested = _now()
        try:
            outcome = adapter.discover_query(track, query, limit=3).to_dict()
        except YtDlpSearchError as exc:
            outcome = {
                "track": track.to_dict(),
                "query": query,
                "candidates": [],
                "candidate_video_ids": [],
                "warnings": list(exc.warnings),
                "error": exc.to_dict(),
            }
        candidates = outcome.get("candidates", [])
        if [candidate.get("rank") for candidate in candidates] != list(
            range(1, len(candidates) + 1)
        ):
            raise Stage5B1AValidationError("YouTube native candidate order changed")
        rows.append({
            "benchmark_id": track.stable_track_id,
            "query": query,
            "requested_at_utc": requested,
            "completed_at_utc": _now(),
            "outcome": outcome,
        })
        atomic_json(output, _discovery_document(
            config, rows, status=STATUS_DISCOVERY_RUNNING,
            started_at=started_at, elapsed_seconds=0.0,
        ))
        if index + 1 < SAMPLE_SIZE:
            sleep(config.provider.sleep_between_tracks_seconds)
    result = _discovery_document(
        config, rows, status=STATUS_DISCOVERY_COMPLETE,
        started_at=started_at, elapsed_seconds=time.monotonic() - started_clock,
    )
    atomic_json(output, result)
    return result


def build_blinded_sol_payload(config: YoutubePriorConfig) -> dict[str, Any]:
    manifest = load_youtube_prior_manifest(config)
    discovery_path = config.output_dir / "youtube_top3_discovery.json"
    discovery = _json(discovery_path)
    if discovery.get("status") != STATUS_DISCOVERY_COMPLETE:
        raise Stage5B1AValidationError("Stage 5B.2 discovery is not complete")
    target_by_id = {row["benchmark_id"]: row for row in manifest["tracks"]}
    tracks = []
    mapping = []
    for row in discovery["tracks"]:
        benchmark_id = row["benchmark_id"]
        target = target_by_id[benchmark_id]
        candidates = list(row["outcome"].get("candidates", []))
        shuffled = sorted(candidates, key=lambda candidate: hashlib.sha256(
            f"stage5b2-sol-v1|{benchmark_id}|{candidate['youtube_video_id']}".encode()
        ).hexdigest())
        blind_candidates = []
        map_candidates = []
        for index, candidate in enumerate(shuffled, start=1):
            blind_id = f"C{index}"
            blind_candidates.append({
                "blind_candidate_id": blind_id,
                "video_id": candidate["youtube_video_id"],
                "url": candidate["canonical_url"],
                "title": candidate.get("title"),
                "uploader": candidate.get("uploader"),
                "channel": candidate.get("channel"),
                "duration_seconds": candidate.get("duration_seconds"),
                "view_count": candidate.get("view_count"),
                "description": candidate.get("description"),
            })
            map_candidates.append({
                "blind_candidate_id": blind_id,
                "video_id": candidate["youtube_video_id"],
                "native_rank": candidate["rank"],
            })
        tracks.append({
            "benchmark_id": benchmark_id,
            "spotify_target": {
                "title": target["title"],
                "artists": target["artists"],
                "album": target.get("album"),
                "duration_seconds": target.get("duration_ms") / 1000
                if target.get("duration_ms") is not None else None,
                "release_year": target.get("release_year"),
            },
            "candidates": blind_candidates,
        })
        mapping.append({"benchmark_id": benchmark_id, "candidates": map_candidates})
    payload = {
        "schema_version": SOL_PAYLOAD_SCHEMA_VERSION,
        "benchmark_manifest_sha256": config.manifest_sha256,
        "discovery_sha256": file_sha256(discovery_path),
        "candidate_order": "DETERMINISTICALLY_SHUFFLED",
        "search_rank_visible": False,
        "human_labels_visible": False,
        "resolver_evidence_visible": False,
        "track_count": len(tracks),
        "candidate_count": sum(len(row["candidates"]) for row in tracks),
        "tracks": tracks,
    }
    atomic_json(config.output_dir / "sol_blind_payload.json", payload)
    atomic_json(config.output_dir / "sol_private_rank_mapping.json", {
        "schema_version": "stage5b2-sol-private-rank-mapping-v1",
        "payload_sha256": file_sha256(config.output_dir / "sol_blind_payload.json"),
        "tracks": mapping,
    })
    return payload


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
