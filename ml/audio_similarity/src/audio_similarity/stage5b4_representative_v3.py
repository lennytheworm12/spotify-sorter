"""Fresh Representative V3 validation for the frozen Stage 5B.3 selector.

This module freezes the held-out owner-library sample, performs the sole
natural title-plus-primary-artist YouTube query, and replays the imported
Stage 5B.3 selector without adding or removing any veto.
"""
from __future__ import annotations

import csv
import json
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
from .stage5b2_youtube_prior import natural_title_artist_query
from .stage5b3_minimal_selector import (
    AUTO_SELECT,
    DURATION_ANOMALY_SECONDS,
    EXPERIMENT_ID as SELECTOR_ID,
    MATCH_UNCERTAIN,
    select_native_rank,
)
from .stage5b_representative_library import (
    build_benchmark_manifest,
    historical_exclusion_identities,
    load_library_snapshot,
)


BENCHMARK_ID = "STAGE5B4_REPRESENTATIVE_V3"
MANIFEST_SCHEMA_VERSION = "stage5b4-representative-v3-manifest-v1"
CONFIG_SCHEMA_VERSION = "stage5b4-representative-v3-config-v1"
DISCOVERY_SCHEMA_VERSION = "stage5b4-youtube-top3-discovery-v1"
DECISIONS_SCHEMA_VERSION = "stage5b4-automated-selector-decisions-v1"
AUTOMATED_METRICS_SCHEMA_VERSION = "stage5b4-automated-selector-metrics-v1"
STATUS_DISCOVERY_RUNNING = "STAGE5B4_DISCOVERY_RUNNING"
STATUS_DISCOVERY_COMPLETE = "STAGE5B4_DISCOVERY_COMPLETE"
STATUS_SELECTOR_COMPLETE = "STAGE5B4_AUTOMATED_SELECTOR_COMPLETE"
SAMPLE_SIZE = 100
SAMPLE_SEED = "stage5b4-representative-v3-seed-2026-09-03"
AUTOMATED_COVERAGE_GATE = 0.90
AUTOMATED_SAFE_PRECISION_GATE = 0.95
RAW_TOP1_GATE = 0.90
TOP3_REPLICATION_GATE = 0.99
FROZEN_STAGE5B3_COMMIT = "bb2a1dff8901dfe790fe87bdc9d35f7073048155"
FROZEN_STAGE5B3_CALIBRATION = {
    "auto_select_count": 99,
    "match_uncertain_count": 1,
    "human_safe_count": 97,
    "human_wrong_count": 0,
    "human_uncertain_count": 2,
}
_SELECTOR_VETOES = (
    "UNREQUESTED_LIVE_OR_PERFORMANCE",
    "DURATION_ANOMALY_GT_20_SECONDS",
)


@dataclass(frozen=True)
class Stage5B4Config:
    path: Path
    project_root: Path
    output_dir: Path
    manifest_path: Path
    manifest_sha256: str
    snapshot_sha256: str
    provider: YtDlpProviderConfig
    selector_source_path: Path
    selector_source_sha256: str
    selector_artifact_path: Path
    selector_artifact_sha256: str
    sample_size: int
    sha256: str


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_immutable_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        if _json(path) != value:
            raise Stage5B1AValidationError(f"refusing to replace frozen artifact: {path}")
        return
    atomic_json(path, value)


def historical_manifest_paths(project_root: Path) -> tuple[Path, ...]:
    """Return every unique Spotify-track universe used before V3."""

    return (
        project_root / "reports/stage5b1a/frozen_tracks.json",
        project_root / "reports/stage5b1b/heldout_tracks.json",
        project_root / "reports/stage5b1b_fresh_challenge/challenge_tracks.json",
        project_root / "reports/stage5b_representative_library_v1/benchmark_manifest.json",
        project_root / "reports/stage5b_youtube_prior_v1/benchmark_manifest.json",
    )


def historical_review_paths(project_root: Path) -> tuple[Path, ...]:
    """Return prior human-review files that carry Spotify track identities."""

    return (
        project_root / "reports/stage5b_representative_library_v1/human_review.csv",
        project_root / "reports/stage5b_youtube_prior_v1/human_review.csv",
        project_root / "reports/stage5b3_minimal_selector/human_review.csv",
    )


def _spotify_ids_from_json(path: Path) -> set[str]:
    output: set[str] = set()
    stack: list[Any] = [_json(path)]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            spotify_id = value.get("spotify_track_id")
            if isinstance(spotify_id, str) and spotify_id:
                output.add(spotify_id)
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return output


def _review_exclusion_audit(
    manifest_paths: Iterable[Path], review_paths: Iterable[Path]
) -> dict[str, Any]:
    manifest_ids = set().union(*(_spotify_ids_from_json(path) for path in manifest_paths))
    reviewed_ids: set[str] = set()
    sources = []
    for path in review_paths:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            ids = {
                row["spotify_track_id"].strip()
                for row in reader
                if row.get("spotify_track_id", "").strip()
            }
        reviewed_ids.update(ids)
        sources.append({
            "path": str(path),
            "sha256": file_sha256(path),
            "spotify_track_count": len(ids),
        })
    uncovered = sorted(reviewed_ids - manifest_ids)
    if uncovered:
        raise Stage5B1AValidationError(
            f"prior human reviews contain {len(uncovered)} unexcluded Spotify tracks"
        )
    return {
        "review_sources": sources,
        "unique_reviewed_spotify_track_count": len(reviewed_ids),
        "uncovered_reviewed_spotify_track_count": 0,
    }


def _selector_identity(project_root: Path) -> dict[str, Any]:
    source = project_root / "src/audio_similarity/stage5b3_minimal_selector.py"
    artifact = project_root / "reports/stage5b3_minimal_selector/minimal_selector_decisions.json"
    value = _json(artifact)
    summary = value.get("summary", {})
    expected = {
        key: summary.get(key) for key in FROZEN_STAGE5B3_CALIBRATION
    }
    if (
        value.get("experiment_id") != SELECTOR_ID
        or expected != FROZEN_STAGE5B3_CALIBRATION
        or summary.get("success_gate_passed") is not True
        or value.get("policy", {}).get("duration_boundary_seconds")
        != DURATION_ANOMALY_SECONDS
        or tuple(value.get("policy", {}).get("vetoes", [])) != _SELECTOR_VETOES
    ):
        raise Stage5B1AValidationError("frozen Stage 5B.3 selector evidence changed")
    return {
        "selector_id": SELECTOR_ID,
        "source_commit": FROZEN_STAGE5B3_COMMIT,
        "implementation": {
            "path": str(source.relative_to(project_root)),
            "sha256": file_sha256(source),
        },
        "calibration_decisions": {
            "path": str(artifact.relative_to(project_root)),
            "sha256": file_sha256(artifact),
        },
        "contract": {
            "native_rank_is_primary": True,
            "vetoes": list(_SELECTOR_VETOES),
            "duration_veto_operator": ">",
            "duration_boundary_seconds": DURATION_ANOMALY_SECONDS,
            "positive_proof_requirements": [],
        },
        "calibration_reproduction": FROZEN_STAGE5B3_CALIBRATION,
        "production_activated": False,
    }


def _query_identity(project_root: Path) -> dict[str, Any]:
    source = project_root / "src/audio_similarity/stage5b2_youtube_prior.py"
    return {
        "query_id": "NATURAL_SPOTIFY_TITLE_PRIMARY_ARTIST_V1",
        "template": "{spotify_title} {primary_artist}",
        "quotes": False,
        "forced_official_token": False,
        "alternate_queries": 0,
        "resolver_title_rewriting": False,
        "implementation": {
            "path": str(source.relative_to(project_root)),
            "sha256": file_sha256(source),
        },
    }


def freeze_v3_manifest(
    project_root: str | Path,
    snapshot_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    snapshot_path = Path(snapshot_path).resolve()
    output_dir = Path(output_dir).resolve()
    manifests = historical_manifest_paths(project_root)
    reviews = historical_review_paths(project_root)
    if not all(path.is_file() for path in (*manifests, *reviews, snapshot_path)):
        raise Stage5B1AValidationError("V3 source or historical exclusion evidence is incomplete")
    library = load_library_snapshot(snapshot_path)
    excluded, provenance = historical_exclusion_identities(manifests)
    review_audit = _review_exclusion_audit(manifests, reviews)
    manifest = build_benchmark_manifest(
        library,
        excluded,
        sample_size=SAMPLE_SIZE,
        seed=SAMPLE_SEED,
        snapshot_sha256=file_sha256(snapshot_path),
        exclusion_provenance=provenance,
    )
    manifest.update({
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "prior_review_exclusion_audit": review_audit,
    })
    manifest["tracks"] = [
        row | {"benchmark_id": f"stage5b4_representative_v3_{index:03d}"}
        for index, row in enumerate(manifest["tracks"], start=1)
    ]
    if manifest["sampled_track_count"] != SAMPLE_SIZE:
        raise Stage5B1AValidationError(
            f"V3 requires 100 fresh tracks; only {manifest['sampled_track_count']} remain"
        )
    selected = {row["spotify_track_id"] for row in manifest["tracks"]}
    prior_ids = set().union(*(_spotify_ids_from_json(path) for path in manifests))
    if selected & prior_ids:
        raise Stage5B1AValidationError("V3 manifest overlaps historical Spotify track IDs")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "benchmark_manifest.json"
    _write_immutable_json(manifest_path, manifest)
    digest = file_sha256(manifest_path)
    digest_path = output_dir / "benchmark_manifest.sha256"
    if digest_path.exists() and digest_path.read_text(encoding="utf-8").strip() != digest:
        raise Stage5B1AValidationError("V3 manifest digest lock changed")
    if not digest_path.exists():
        digest_path.write_text(digest + "\n", encoding="utf-8")
    config = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "benchmark_manifest": {
            "path": str(manifest_path.relative_to(project_root)),
            "sha256": digest,
        },
        "private_library_snapshot_sha256": file_sha256(snapshot_path),
        "sample_seed": SAMPLE_SEED,
        "sample_size": SAMPLE_SIZE,
        "historical_exclusion_paths": [
            {"path": str(path.relative_to(project_root)), "sha256": file_sha256(path)}
            for path in manifests
        ],
        "prior_review_exclusion_audit": review_audit,
        "query": _query_identity(project_root),
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
        "selector": _selector_identity(project_root),
        "gates": {
            "automated_coverage_minimum": AUTOMATED_COVERAGE_GATE,
            "automated_safe_precision_minimum": AUTOMATED_SAFE_PRECISION_GATE,
            "raw_top1_safe_minimum": RAW_TOP1_GATE,
            "top3_safe_recall_replication_minimum": TOP3_REPLICATION_GATE,
            "systematic_wrong_family_minimum_count": 2,
            "harmful_false_veto_requires_refinement": True,
        },
        "review": {
            "protocol": "SEQUENTIAL_NATIVE_RANKS_UNTIL_FIRST_SAFE_THEN_SELECTOR_SUPPLEMENT",
            "labels": ["IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"],
            "safe_labels": ["IDEAL", "ACCEPTABLE"],
            "rank1_non_safe_reason_required": True,
            "automated_decisions_hidden": True,
        },
        "scope_guards": {
            "selector_tuning_permitted": False,
            "query_tuning_permitted": False,
            "post_freeze_substitution_permitted": False,
            "audio_downloads": 0,
            "video_downloads": 0,
            "clap_calls": 0,
            "muq_calls": 0,
            "production_activation": False,
        },
    }
    _write_immutable_json(output_dir / "benchmark_config.json", config)
    return {"manifest": manifest, "config": config, "manifest_sha256": digest}


def load_v3_config(path: str | Path) -> Stage5B4Config:
    path = Path(path).resolve()
    value = _json(path)
    if value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.4 config schema")
    project_root = path.parents[2]
    manifest_info = value.get("benchmark_manifest", {})
    selector = value.get("selector", {})
    implementation = selector.get("implementation", {})
    calibration = selector.get("calibration_decisions", {})
    manifest_path = project_root / str(manifest_info.get("path"))
    source_path = project_root / str(implementation.get("path"))
    artifact_path = project_root / str(calibration.get("path"))
    for artifact, expected, label in (
        (manifest_path, manifest_info.get("sha256"), "manifest"),
        (source_path, implementation.get("sha256"), "selector implementation"),
        (artifact_path, calibration.get("sha256"), "selector calibration"),
    ):
        if not artifact.is_file() or file_sha256(artifact) != expected:
            raise Stage5B1AValidationError(f"frozen V3 {label} changed")
    retrieval = value.get("retrieval", {})
    query = value.get("query", {})
    query_implementation = query.get("implementation", {})
    query_source = project_root / str(query_implementation.get("path"))
    if not query_source.is_file() or file_sha256(query_source) != query_implementation.get("sha256"):
        raise Stage5B1AValidationError("frozen V3 natural-query implementation changed")
    if query != {
        "query_id": "NATURAL_SPOTIFY_TITLE_PRIMARY_ARTIST_V1",
        "template": "{spotify_title} {primary_artist}",
        "quotes": False,
        "forced_official_token": False,
        "alternate_queries": 0,
        "resolver_title_rewriting": False,
        "implementation": query_implementation,
    }:
        raise Stage5B1AValidationError("V3 natural-query contract changed")
    if (
        retrieval.get("mode") != "ytsearch3"
        or retrieval.get("candidate_limit") != 3
        or retrieval.get("metadata_only") is not True
        or retrieval.get("sequential") is not True
        or retrieval.get("preserve_native_rank") is not True
    ):
        raise Stage5B1AValidationError("V3 discovery contract changed")
    if selector.get("selector_id") != SELECTOR_ID or selector.get("contract") != {
        "native_rank_is_primary": True,
        "vetoes": list(_SELECTOR_VETOES),
        "duration_veto_operator": ">",
        "duration_boundary_seconds": DURATION_ANOMALY_SECONDS,
        "positive_proof_requirements": [],
    }:
        raise Stage5B1AValidationError("frozen Stage 5B.3 selector contract changed")
    if selector.get("calibration_reproduction") != FROZEN_STAGE5B3_CALIBRATION:
        raise Stage5B1AValidationError("Stage 5B.3 calibration identity changed")
    scope = value.get("scope_guards", {})
    if (
        scope.get("selector_tuning_permitted") is not False
        or scope.get("query_tuning_permitted") is not False
        or scope.get("post_freeze_substitution_permitted") is not False
        or scope.get("production_activation") is not False
        or scope.get("audio_downloads") != 0
        or scope.get("video_downloads") != 0
    ):
        raise Stage5B1AValidationError("V3 scope guards changed")
    return Stage5B4Config(
        path=path,
        project_root=project_root,
        output_dir=path.parent,
        manifest_path=manifest_path,
        manifest_sha256=str(manifest_info["sha256"]),
        snapshot_sha256=str(value["private_library_snapshot_sha256"]),
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
        selector_source_path=source_path,
        selector_source_sha256=str(implementation["sha256"]),
        selector_artifact_path=artifact_path,
        selector_artifact_sha256=str(calibration["sha256"]),
        sample_size=int(value["sample_size"]),
        sha256=file_sha256(path),
    )


def load_v3_manifest(config: Stage5B4Config) -> dict[str, Any]:
    value = _json(config.manifest_path)
    if (
        value.get("schema_version") != MANIFEST_SCHEMA_VERSION
        or value.get("benchmark_id") != BENCHMARK_ID
        or value.get("sampled_track_count") != config.sample_size
        or len(value.get("tracks", [])) != config.sample_size
        or value.get("post_freeze_substitutions") != 0
    ):
        raise Stage5B1AValidationError("invalid frozen Stage 5B.4 manifest")
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


def _query_config() -> QueryConfig:
    return QueryConfig(
        variant_id="stage5b4-natural-title-primary-artist-v1",
        template="{normalized_title} {primary_artist}",
        normalize_featured_artist_noise=False,
    )


def _discovery_document(
    config: Stage5B4Config,
    rows: list[dict[str, Any]],
    *,
    status: str,
    started_at: str,
    elapsed_seconds: float,
) -> dict[str, Any]:
    versions = sorted({
        str(row["outcome"].get("provider", {}).get("version"))
        for row in rows
        if row["outcome"].get("provider", {}).get("version")
    })
    return {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "status": status,
        "benchmark_id": BENCHMARK_ID,
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
            "tracks_total": config.sample_size,
            "tracks_completed": len(rows),
            "search_failures": sum(row["outcome"].get("error") is not None for row in rows),
            "tracks_with_candidates": sum(bool(row["outcome"].get("candidates")) for row in rows),
            "zero_candidate_tracks": sum(not row["outcome"].get("candidates") for row in rows),
            "candidate_count": sum(len(row["outcome"].get("candidates", [])) for row in rows),
            "warning_count": sum(len(row["outcome"].get("warnings", [])) for row in rows),
        },
        "tracks": rows,
        "scope_guards": {
            "query_variants_per_track": 1,
            "candidate_reranking": False,
            "selector_invocations": 0,
            "audio_downloads": 0,
            "video_downloads": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
    }


def run_v3_discovery(
    config: Stage5B4Config,
    adapter: YtDlpDiscoveryAdapter | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    manifest = load_v3_manifest(config)
    output = config.output_dir / "youtube_top3_discovery.json"
    existing = _json(output) if output.exists() else None
    if existing and existing.get("status") == STATUS_DISCOVERY_COMPLETE:
        raise Stage5B1AValidationError("Stage 5B.4 discovery is already frozen")
    rows = list(existing.get("tracks", [])) if existing else []
    expected_ids = [row["benchmark_id"] for row in manifest["tracks"]]
    if [row.get("benchmark_id") for row in rows] != expected_ids[:len(rows)]:
        raise Stage5B1AValidationError("partial V3 discovery is not a manifest prefix")
    adapter = adapter or YtDlpDiscoveryAdapter(
        config.provider, _query_config(), YtDlpPythonBackend(config.provider)
    )
    started_at = existing.get("started_at_utc") if existing else _now()
    started_clock = time.monotonic()
    for index, manifest_row in enumerate(manifest["tracks"][len(rows):], start=len(rows)):
        track = _manifest_track(manifest_row)
        requested = _now()
        try:
            query = natural_title_artist_query(track)
        except Stage5B1AValidationError as exc:
            query = " ".join(f"{track.title} {track.artists[0]}".split())
            outcome = {
                "track": track.to_dict(),
                "query": query,
                "candidates": [],
                "candidate_video_ids": [],
                "warnings": [],
                "error": {
                    "error_type": "QUERY_CONTRACT_VALIDATION_FAILURE",
                    "message": str(exc),
                    "retryable": False,
                },
            }
        else:
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
        ) or len(candidates) > 3:
            raise Stage5B1AValidationError("V3 native candidate order changed")
        rows.append({
            "benchmark_id": track.stable_track_id,
            "query": query,
            "requested_at_utc": requested,
            "completed_at_utc": _now(),
            "outcome": outcome,
        })
        atomic_json(output, _discovery_document(
            config,
            rows,
            status=STATUS_DISCOVERY_RUNNING,
            started_at=started_at,
            elapsed_seconds=0.0,
        ))
        if index + 1 < config.sample_size:
            sleep(config.provider.sleep_between_tracks_seconds)
    result = _discovery_document(
        config,
        rows,
        status=STATUS_DISCOVERY_COMPLETE,
        started_at=started_at,
        elapsed_seconds=time.monotonic() - started_clock,
    )
    atomic_json(output, result)
    return result


def run_frozen_selector(config: Stage5B4Config) -> tuple[dict[str, Any], dict[str, Any]]:
    """Replay the imported Stage 5B.3 policy without using human evidence."""

    manifest = load_v3_manifest(config)
    discovery_path = config.output_dir / "youtube_top3_discovery.json"
    discovery = _json(discovery_path)
    if (
        discovery.get("status") != STATUS_DISCOVERY_COMPLETE
        or discovery.get("benchmark_manifest_sha256") != config.manifest_sha256
    ):
        raise Stage5B1AValidationError("complete frozen V3 discovery is required")
    targets = {row["benchmark_id"]: row for row in manifest["tracks"]}
    tracks = []
    for row in discovery["tracks"]:
        target = targets[row["benchmark_id"]]
        decision = select_native_rank(target, row["outcome"].get("candidates", []))
        tracks.append({
            "benchmark_id": row["benchmark_id"],
            "spotify_target": target,
            "query": row["query"],
            **decision,
        })
    if len(tracks) != config.sample_size:
        raise Stage5B1AValidationError("V3 automated selector denominator changed")
    auto = [row for row in tracks if row["decision"] == AUTO_SELECT]
    rank_counts = {
        f"rank_{rank}": sum(row["selected_rank"] == rank for row in auto)
        for rank in (1, 2, 3)
    }
    rank_counts["none"] = config.sample_size - len(auto)
    metrics = {
        "schema_version": AUTOMATED_METRICS_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "status": STATUS_SELECTOR_COMPLETE,
        "denominator_tracks": config.sample_size,
        "auto_select_count": len(auto),
        "auto_select_coverage": len(auto) / config.sample_size,
        "match_uncertain_count": config.sample_size - len(auto),
        "selected_rank_distribution": rank_counts,
        "coverage_gate": {
            "minimum": AUTOMATED_COVERAGE_GATE,
            "passed": len(auto) / config.sample_size >= AUTOMATED_COVERAGE_GATE,
        },
        "human_outcomes": None,
        "human_labels_used_in_decisions": False,
    }
    decisions = {
        "schema_version": DECISIONS_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "status": STATUS_SELECTOR_COMPLETE,
        "benchmark_manifest_sha256": config.manifest_sha256,
        "discovery_sha256": file_sha256(discovery_path),
        "selector": {
            "selector_id": SELECTOR_ID,
            "implementation_sha256": config.selector_source_sha256,
            "calibration_decisions_sha256": config.selector_artifact_sha256,
            "vetoes": list(_SELECTOR_VETOES),
            "duration_boundary_seconds": DURATION_ANOMALY_SECONDS,
            "modified_for_v3": False,
        },
        "human_labels_visible": False,
        "tracks": tracks,
        "scope_guards": {
            "human_labels_used_in_decisions": False,
            "old_proof_heavy_resolver_invocations": 0,
            "selector_tuning": False,
            "production_activation": False,
        },
    }
    _write_immutable_json(config.output_dir / "automated_selector_decisions.json", decisions)
    metrics_path = config.output_dir / "automated_selector_metrics.json"
    if metrics_path.exists():
        existing_metrics = _json(metrics_path)
        if existing_metrics | {"human_outcomes": None} != metrics:
            raise Stage5B1AValidationError("frozen V3 automated metrics changed")
        metrics = existing_metrics
    else:
        atomic_json(metrics_path, metrics)
    return decisions, metrics
