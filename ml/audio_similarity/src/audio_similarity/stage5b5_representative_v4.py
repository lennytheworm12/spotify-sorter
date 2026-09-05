"""Fresh V4 validation of frozen artist-decomposition discovery and selection."""
from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .stage5b1a2_config import YtDlpProviderConfig
from .stage5b1a2_ytdlp import YtDlpDiscoveryAdapter, YtDlpPythonBackend
from .stage5b1a_config import QueryConfig
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b3_minimal_selector import (
    AUTO_SELECT,
    DURATION_ANOMALY_SECONDS,
    EXPERIMENT_ID as SELECTOR_ID,
    select_native_rank,
)
from .stage5b4c_artist_decomposition import (
    ALL_QUERY_VARIANTS_EMPTY,
    FALLBACK_SUCCESS,
    PRIMARY_SUCCESS,
    PROVIDER_ERROR,
    QUERY_CONTRACT_ID,
    build_artist_decomposition_plan,
    discover_with_artist_decomposition,
)
from .stage5b4c_artist_decomposition_experiment import (
    verify_artist_decomposition_history,
)
from .stage5b_representative_library import (
    build_benchmark_manifest,
    historical_exclusion_identities,
    load_library_snapshot,
    track_identities,
)


BENCHMARK_ID = "STAGE5B5_REPRESENTATIVE_LIBRARY_V4"
OUTPUT_DIRECTORY = "reports/stage5b5_representative_v4"
MANIFEST_SCHEMA_VERSION = "stage5b5-representative-v4-manifest-v1"
CONFIG_SCHEMA_VERSION = "stage5b5-representative-v4-config-v1"
DISCOVERY_SCHEMA_VERSION = "stage5b5-representative-v4-discovery-v1"
DECISIONS_SCHEMA_VERSION = "stage5b5-representative-v4-decisions-v1"
PRELIMINARY_METRICS_SCHEMA_VERSION = "stage5b5-preliminary-selector-metrics-v1"
STATUS_DISCOVERY_RUNNING = "STAGE5B5_DISCOVERY_RUNNING"
STATUS_DISCOVERY_COMPLETE = "STAGE5B5_DISCOVERY_COMPLETE"
STATUS_SELECTOR_FROZEN_HIDDEN = "STAGE5B5_SELECTOR_FROZEN_HIDDEN"
SAMPLE_SIZE = 100
SAMPLE_SEED = "stage5b5-representative-v4-seed-2026-09-03"
AUTOMATED_COVERAGE_GATE = 0.90
AUTOMATED_SAFE_PRECISION_GATE = 0.95
RAW_TOP1_GATE = 0.90
TOP3_SAFE_GATE = 0.99
_SELECTOR_VETOES = (
    "UNREQUESTED_LIVE_OR_PERFORMANCE",
    "DURATION_ANOMALY_GT_20_SECONDS",
)


@dataclass(frozen=True)
class Stage5B5Config:
    path: Path
    project_root: Path
    output_dir: Path
    manifest_path: Path
    manifest_sha256: str
    provider: YtDlpProviderConfig
    query_source_path: Path
    query_source_sha256: str
    decomposition_source_path: Path
    decomposition_source_sha256: str
    selector_source_path: Path
    selector_source_sha256: str
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


def historical_json_paths(project_root: Path) -> tuple[Path, ...]:
    """Every prior track universe or Stage 5B.4 query supplement."""

    return tuple(
        project_root / relative
        for relative in (
            "reports/stage5b1a/frozen_tracks.json",
            "reports/stage5b1b/heldout_tracks.json",
            "reports/stage5b1b_fresh_challenge/challenge_tracks.json",
            "reports/stage5b_representative_library_v1/benchmark_manifest.json",
            "reports/stage5b_youtube_prior_v1/benchmark_manifest.json",
            "reports/stage5b4_representative_v3/benchmark_manifest.json",
            "reports/stage5b4a_query_contract_repair/repaired_discovery.json",
            "reports/stage5b4b_playwright_fallback/primary_discovery.json",
            "reports/stage5b4c_youtube_data_api_fallback/primary_discovery.json",
            "reports/stage5b4c_artist_query_decomposition/targeted_discovery.json",
        )
    )


def historical_review_paths(project_root: Path) -> tuple[Path, ...]:
    return tuple(
        project_root / relative
        for relative in (
            "reports/stage5b_representative_library_v1/human_review.csv",
            "reports/stage5b_youtube_prior_v1/human_review.csv",
            "reports/stage5b3_minimal_selector/human_review.csv",
            "reports/stage5b4_representative_v3/human_review.csv",
            "reports/stage5b4a_query_contract_repair/human_review.csv",
            "reports/stage5b4b_playwright_fallback/human_review.csv",
            "reports/stage5b4c_youtube_data_api_fallback/human_review.csv",
            "reports/stage5b4c_artist_query_decomposition/human_review.csv",
        )
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
    json_paths: Iterable[Path], review_paths: Iterable[Path]
) -> dict[str, Any]:
    excluded_ids = set().union(*(_spotify_ids_from_json(path) for path in json_paths))
    reviewed_ids: set[str] = set()
    sources = []
    for path in review_paths:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            ids = {
                row.get("spotify_track_id", "").strip()
                for row in reader
                if row.get("spotify_track_id", "").strip()
            }
        reviewed_ids.update(ids)
        sources.append(
            {
                "path": str(path),
                "sha256": file_sha256(path),
                "spotify_track_count": len(ids),
            }
        )
    uncovered = reviewed_ids - excluded_ids
    if uncovered:
        raise Stage5B1AValidationError(
            f"prior reviews contain {len(uncovered)} unexcluded Spotify tracks"
        )
    return {
        "sources": sources,
        "unique_reviewed_spotify_track_count": len(reviewed_ids),
        "uncovered_reviewed_spotify_track_count": 0,
    }


def _identity(path: Path, project_root: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(project_root)),
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _verify_identity_tree(value: Any, project_root: Path, label: str) -> None:
    """Recursively verify hash records embedded by a prior artifact manifest."""

    if isinstance(value, dict) and {"path", "sha256"} <= value.keys():
        path = project_root / str(value["path"])
        if not path.is_file() or file_sha256(path) != value["sha256"]:
            raise Stage5B1AValidationError(f"frozen historical identity changed: {label}")
        return
    if isinstance(value, dict):
        for name, child in value.items():
            _verify_identity_tree(child, project_root, f"{label}.{name}")


def _frozen_contracts(project_root: Path) -> dict[str, Any]:
    history = verify_artist_decomposition_history(project_root)
    query_source = project_root / "src/audio_similarity/stage5b4a_query_contract_repair.py"
    decomposition_source = (
        project_root / "src/audio_similarity/stage5b4c_artist_decomposition.py"
    )
    selector_source = project_root / "src/audio_similarity/stage5b3_minimal_selector.py"
    metrics = _json(
        project_root
        / "reports/stage5b4c_artist_query_decomposition/decomposition_metrics.json"
    )
    if (
        metrics.get("verdict") != "ARTIST_DECOMPOSITION_FALLBACK_VALIDATED"
        or metrics.get("frozen_candidate_contract") != QUERY_CONTRACT_ID
        or metrics.get("scope_guards", {}).get("production_activation") is not False
    ):
        raise Stage5B1AValidationError("Stage 5B.4C discovery contract is not frozen")
    decomposition_manifest_path = (
        project_root
        / "reports/stage5b4c_artist_query_decomposition/artifact_manifest.json"
    )
    decomposition_manifest = _json(decomposition_manifest_path)
    if decomposition_manifest.get("verdict") != (
        "ARTIST_DECOMPOSITION_FALLBACK_VALIDATED"
    ):
        raise Stage5B1AValidationError("unexpected Stage 5B.4C artifact verdict")
    for group in ("artifacts", "implementation", "frozen_inputs"):
        _verify_identity_tree(
            decomposition_manifest.get(group, {}), project_root, f"stage5b4c.{group}"
        )
    if file_sha256(selector_source) != history["selector"]["sha256"]:
        raise Stage5B1AValidationError("Stage 5B.3 selector implementation changed")
    return {
        "discovery": {
            "contract_id": QUERY_CONTRACT_ID,
            "primary": "sanitized raw Spotify title + first 3 distinct credited artists",
            "zero_result_fallback": "same title + one credited artist in credited order",
            "maximum_artists": 3,
            "stop_at_first_non_empty_pool": True,
            "candidate_pool_merging": False,
            "query_source": _identity(query_source, project_root),
            "decomposition_source": _identity(decomposition_source, project_root),
            "validation_metrics": _identity(
                project_root
                / "reports/stage5b4c_artist_query_decomposition/decomposition_metrics.json",
                project_root,
            ),
        },
        "selection": {
            "selector_id": SELECTOR_ID,
            "native_rank_is_primary": True,
            "vetoes": list(_SELECTOR_VETOES),
            "duration_veto_operator": ">",
            "duration_boundary_seconds": DURATION_ANOMALY_SECONDS,
            "implementation": _identity(selector_source, project_root),
            "validation_artifact": history["selector"],
        },
        "prior_supplement_manifest": history["official_data_api_manifest"],
        "decomposition_artifact_manifest": _identity(
            decomposition_manifest_path,
            project_root,
        ),
    }


def freeze_v4_manifest(
    project_root: str | Path,
    snapshot_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    snapshot_path = Path(snapshot_path).resolve()
    output_dir = Path(output_dir).resolve()
    json_paths = historical_json_paths(project_root)
    review_paths = historical_review_paths(project_root)
    if not all(path.is_file() for path in (*json_paths, *review_paths, snapshot_path)):
        raise Stage5B1AValidationError("V4 source or exclusion evidence is incomplete")
    contracts = _frozen_contracts(project_root)
    library = load_library_snapshot(snapshot_path)
    excluded, provenance = historical_exclusion_identities(json_paths)
    review_audit = _review_exclusion_audit(json_paths, review_paths)
    manifest = build_benchmark_manifest(
        library,
        excluded,
        sample_size=SAMPLE_SIZE,
        seed=SAMPLE_SEED,
        snapshot_sha256=file_sha256(snapshot_path),
        exclusion_provenance=provenance,
    )
    manifest.update(
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "benchmark_id": BENCHMARK_ID,
            "prior_review_exclusion_audit": review_audit,
            "freshness_scope": "NEVER_USED_IN_V1_V2_V3_OR_STAGE5B4A_C",
        }
    )
    manifest["tracks"] = [
        row | {"benchmark_id": f"stage5b5_representative_v4_{index:03d}"}
        for index, row in enumerate(manifest["tracks"], start=1)
    ]
    if manifest["sampled_track_count"] != SAMPLE_SIZE:
        raise Stage5B1AValidationError(
            f"V4 requires 100 fresh tracks; only {manifest['sampled_track_count']} remain"
        )
    selected = {
        identity
        for row in manifest["tracks"]
        for identity in track_identities(_manifest_track(row))
    }
    if selected & excluded:
        raise Stage5B1AValidationError("V4 overlaps a historical track identity")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "benchmark_manifest.json"
    _write_immutable_json(manifest_path, manifest)
    digest = file_sha256(manifest_path)
    digest_path = output_dir / "benchmark_manifest.sha256"
    if digest_path.exists() and digest_path.read_text(encoding="utf-8").strip() != digest:
        raise Stage5B1AValidationError("V4 manifest digest lock changed")
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
            _identity(path, project_root) for path in json_paths
        ],
        "prior_review_exclusion_audit": review_audit,
        "contracts": contracts,
        "retrieval": {
            "provider": "yt_dlp",
            "mode": "ytsearch3",
            "candidate_limit": 3,
            "metadata_only": True,
            "preserve_native_rank": True,
            "sequential": True,
            "sleep_between_tracks_seconds": 1.0,
            "socket_timeout_seconds": 30,
            "max_attempts": 2,
            "retry_backoff_seconds": 2.0,
        },
        "gates": {
            "automated_coverage_minimum": AUTOMATED_COVERAGE_GATE,
            "automated_safe_precision_minimum": AUTOMATED_SAFE_PRECISION_GATE,
            "raw_top1_safe_minimum": RAW_TOP1_GATE,
            "top3_safe_minimum": TOP3_SAFE_GATE,
        },
        "review": {
            "labels": ["IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"],
            "safe_labels": ["IDEAL", "ACCEPTABLE"],
            "protocol": "SEQUENTIAL_NATIVE_RANKS_UNTIL_SAFE_PLUS_BLIND_SELECTED_RANK_SUPPLEMENT",
            "rank1_non_safe_reason_required": True,
            "selector_decisions_exposed_before_review_complete": False,
        },
        "scope_guards": {
            "query_tuning_permitted": False,
            "selector_tuning_permitted": False,
            "post_freeze_substitution_permitted": False,
            "alternate_provider_fallbacks": 0,
            "audio_downloads": 0,
            "video_downloads": 0,
            "clap_calls": 0,
            "muq_calls": 0,
            "production_activation": False,
        },
    }
    _write_immutable_json(output_dir / "benchmark_config.json", config)
    return {"manifest": manifest, "config": config, "manifest_sha256": digest}


def load_v4_config(path: str | Path) -> Stage5B5Config:
    path = Path(path).resolve()
    value = _json(path)
    if value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise Stage5B1AValidationError("unexpected Stage 5B.5 config schema")
    project_root = path.parents[2]
    manifest_info = value.get("benchmark_manifest", {})
    contracts = value.get("contracts", {})
    if contracts != _frozen_contracts(project_root):
        raise Stage5B1AValidationError("frozen V4 contract identities changed")
    discovery = contracts.get("discovery", {})
    selection = contracts.get("selection", {})
    query_info = discovery.get("query_source", {})
    decomposition_info = discovery.get("decomposition_source", {})
    selector_info = selection.get("implementation", {})
    resolved = (
        (project_root / str(manifest_info.get("path")), manifest_info.get("sha256"), "manifest"),
        (project_root / str(query_info.get("path")), query_info.get("sha256"), "query"),
        (
            project_root / str(decomposition_info.get("path")),
            decomposition_info.get("sha256"),
            "decomposition",
        ),
        (project_root / str(selector_info.get("path")), selector_info.get("sha256"), "selector"),
    )
    for artifact, expected, label in resolved:
        if not artifact.is_file() or file_sha256(artifact) != expected:
            raise Stage5B1AValidationError(f"frozen V4 {label} identity changed")
    if (
        discovery.get("contract_id") != QUERY_CONTRACT_ID
        or discovery.get("maximum_artists") != 3
        or discovery.get("stop_at_first_non_empty_pool") is not True
        or discovery.get("candidate_pool_merging") is not False
    ):
        raise Stage5B1AValidationError("frozen V4 discovery contract changed")
    if (
        selection.get("selector_id") != SELECTOR_ID
        or selection.get("native_rank_is_primary") is not True
        or selection.get("vetoes") != list(_SELECTOR_VETOES)
        or selection.get("duration_veto_operator") != ">"
        or selection.get("duration_boundary_seconds") != DURATION_ANOMALY_SECONDS
    ):
        raise Stage5B1AValidationError("frozen V4 selection contract changed")
    retrieval = value.get("retrieval", {})
    if (
        retrieval.get("mode") != "ytsearch3"
        or retrieval.get("candidate_limit") != 3
        or retrieval.get("metadata_only") is not True
        or retrieval.get("preserve_native_rank") is not True
        or retrieval.get("sequential") is not True
    ):
        raise Stage5B1AValidationError("frozen V4 retrieval contract changed")
    scope = value.get("scope_guards", {})
    if (
        scope.get("query_tuning_permitted") is not False
        or scope.get("selector_tuning_permitted") is not False
        or scope.get("post_freeze_substitution_permitted") is not False
        or scope.get("production_activation") is not False
        or scope.get("audio_downloads") != 0
        or scope.get("video_downloads") != 0
    ):
        raise Stage5B1AValidationError("frozen V4 scope guards changed")
    return Stage5B5Config(
        path=path,
        project_root=project_root,
        output_dir=path.parent,
        manifest_path=resolved[0][0],
        manifest_sha256=str(manifest_info["sha256"]),
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
        query_source_path=resolved[1][0],
        query_source_sha256=str(query_info["sha256"]),
        decomposition_source_path=resolved[2][0],
        decomposition_source_sha256=str(decomposition_info["sha256"]),
        selector_source_path=resolved[3][0],
        selector_source_sha256=str(selector_info["sha256"]),
        sample_size=int(value["sample_size"]),
        sha256=file_sha256(path),
    )


def load_v4_manifest(config: Stage5B5Config) -> dict[str, Any]:
    value = _json(config.manifest_path)
    if (
        value.get("schema_version") != MANIFEST_SCHEMA_VERSION
        or value.get("benchmark_id") != BENCHMARK_ID
        or value.get("sampled_track_count") != config.sample_size
        or len(value.get("tracks", [])) != config.sample_size
        or value.get("post_freeze_substitutions") != 0
    ):
        raise Stage5B1AValidationError("invalid frozen Stage 5B.5 manifest")
    return value


def _manifest_track(row: dict[str, Any]) -> SpotifyTrack:
    return SpotifyTrack.from_dict(
        {
            "stable_track_id": row["benchmark_id"],
            "spotify_track_id": row["spotify_track_id"],
            "title": row["title"],
            "artists": row["artists"],
            "album": row.get("album"),
            "duration_ms": row.get("duration_ms"),
            "release_year": row.get("release_year"),
            "isrc": row.get("isrc"),
        }
    )


def _adapter(config: Stage5B5Config) -> YtDlpDiscoveryAdapter:
    inert_query = QueryConfig(
        variant_id="stage5b5-explicit-frozen-query",
        template="{normalized_title} {primary_artist}",
        normalize_featured_artist_noise=False,
    )
    return YtDlpDiscoveryAdapter(
        config.provider,
        inert_query,
        YtDlpPythonBackend(config.provider),
    )


def _discovery_document(
    config: Stage5B5Config,
    rows: list[dict[str, Any]],
    *,
    status: str,
    started_at: str,
    process_elapsed: float,
) -> dict[str, Any]:
    outcomes = [row["discovery"] for row in rows]
    attempts = [attempt for outcome in outcomes for attempt in outcome["attempts"]]
    return {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "status": status,
        "benchmark_manifest_sha256": config.manifest_sha256,
        "benchmark_config_sha256": config.sha256,
        "started_at_utc": started_at,
        "completed_at_utc": _now() if status == STATUS_DISCOVERY_COMPLETE else None,
        "elapsed_current_process_seconds": process_elapsed,
        "summary": {
            "tracks_total": config.sample_size,
            "tracks_completed": len(rows),
            "primary_success_count": sum(
                outcome["outcome"] == PRIMARY_SUCCESS for outcome in outcomes
            ),
            "fallback_trigger_count": sum(len(outcome["attempts"]) > 1 for outcome in outcomes),
            "fallback_success_count": sum(
                outcome["outcome"] == FALLBACK_SUCCESS for outcome in outcomes
            ),
            "all_query_variants_empty_count": sum(
                outcome["outcome"] == ALL_QUERY_VARIANTS_EMPTY for outcome in outcomes
            ),
            "provider_error_count": sum(
                outcome["outcome"] == PROVIDER_ERROR for outcome in outcomes
            ),
            "tracks_with_candidates": sum(bool(outcome["candidates"]) for outcome in outcomes),
            "zero_candidate_tracks": sum(not outcome["candidates"] for outcome in outcomes),
            "candidate_count": sum(len(outcome["candidates"]) for outcome in outcomes),
            "provider_request_count": len(attempts),
            "provider_warning_count": sum(len(attempt["warnings"]) for attempt in attempts),
            "provider_elapsed_seconds": sum(attempt["elapsed_seconds"] for attempt in attempts),
        },
        "tracks": rows,
        "scope_guards": {
            "maximum_queries_per_track": 4,
            "fallback_only_after_zero": True,
            "candidate_pool_merges": 0,
            "candidate_reranking": False,
            "selector_invocations": 0,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
    }


def run_v4_discovery(
    config: Stage5B5Config,
    provider: Any | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    manifest = load_v4_manifest(config)
    output = config.output_dir / "youtube_top3_discovery.json"
    existing = _json(output) if output.exists() else None
    if existing and existing.get("status") == STATUS_DISCOVERY_COMPLETE:
        raise Stage5B1AValidationError("Stage 5B.5 discovery is already frozen")
    rows = list(existing.get("tracks", [])) if existing else []
    expected_ids = [row["benchmark_id"] for row in manifest["tracks"]]
    if [row.get("benchmark_id") for row in rows] != expected_ids[: len(rows)]:
        raise Stage5B1AValidationError("partial V4 discovery is not a manifest prefix")
    adapter = provider or _adapter(config)
    started_at = existing.get("started_at_utc") if existing else _now()
    started_clock = time.monotonic()
    for index, manifest_row in enumerate(manifest["tracks"][len(rows) :], start=len(rows)):
        track = _manifest_track(manifest_row)
        expected_plan = build_artist_decomposition_plan(track).to_dict()
        requested_at = _now()
        outcome = discover_with_artist_decomposition(track, adapter)
        if outcome["query_plan"] != expected_plan:
            raise Stage5B1AValidationError("V4 query plan changed during discovery")
        candidates = outcome["candidates"]
        if (
            [candidate.get("rank") for candidate in candidates]
            != list(range(1, len(candidates) + 1))
            or len(candidates) > 3
        ):
            raise Stage5B1AValidationError("V4 native candidate order changed")
        rows.append(
            {
                "benchmark_id": track.stable_track_id,
                "requested_at_utc": requested_at,
                "completed_at_utc": _now(),
                "discovery": outcome,
            }
        )
        atomic_json(
            output,
            _discovery_document(
                config,
                rows,
                status=STATUS_DISCOVERY_RUNNING,
                started_at=started_at,
                process_elapsed=time.monotonic() - started_clock,
            ),
        )
        if index + 1 < config.sample_size:
            sleep(config.provider.sleep_between_tracks_seconds)
    result = _discovery_document(
        config,
        rows,
        status=STATUS_DISCOVERY_COMPLETE,
        started_at=started_at,
        process_elapsed=time.monotonic() - started_clock,
    )
    atomic_json(output, result)
    return result


def run_frozen_selector(config: Stage5B5Config) -> tuple[dict[str, Any], dict[str, Any]]:
    """Freeze selector outputs without reading or exposing any human label."""

    manifest = load_v4_manifest(config)
    discovery_path = config.output_dir / "youtube_top3_discovery.json"
    discovery = _json(discovery_path)
    if (
        discovery.get("status") != STATUS_DISCOVERY_COMPLETE
        or discovery.get("benchmark_manifest_sha256") != config.manifest_sha256
    ):
        raise Stage5B1AValidationError("complete frozen V4 discovery is required")
    targets = {row["benchmark_id"]: row for row in manifest["tracks"]}
    tracks = []
    for row in discovery["tracks"]:
        benchmark_id = row["benchmark_id"]
        candidates = row["discovery"]["candidates"]
        tracks.append(
            {
                "benchmark_id": benchmark_id,
                "spotify_target": targets[benchmark_id],
                "discovery_mode": row["discovery"]["discovery_mode"],
                "query_variant_index": row["discovery"]["query_variant_index"],
                "successful_query": row["discovery"]["successful_query"],
                **select_native_rank(targets[benchmark_id], candidates),
            }
        )
    auto = [row for row in tracks if row["decision"] == AUTO_SELECT]
    decisions = {
        "schema_version": DECISIONS_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "status": STATUS_SELECTOR_FROZEN_HIDDEN,
        "benchmark_manifest_sha256": config.manifest_sha256,
        "discovery_sha256": file_sha256(discovery_path),
        "selector": {
            "selector_id": SELECTOR_ID,
            "implementation_sha256": config.selector_source_sha256,
            "vetoes": list(_SELECTOR_VETOES),
            "duration_boundary_seconds": DURATION_ANOMALY_SECONDS,
            "modified_for_v4": False,
        },
        "human_labels_visible": False,
        "tracks": tracks,
        "scope_guards": {
            "human_labels_read": 0,
            "human_labels_used_in_decisions": False,
            "selector_tuning": False,
            "production_activation": False,
        },
    }
    metrics = {
        "schema_version": PRELIMINARY_METRICS_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "status": STATUS_SELECTOR_FROZEN_HIDDEN,
        "denominator_tracks": config.sample_size,
        "auto_select_count": len(auto),
        "auto_select_coverage": len(auto) / config.sample_size,
        "match_uncertain_count": config.sample_size - len(auto),
        "selected_rank_distribution": {
            f"rank_{rank}": sum(row.get("selected_rank") == rank for row in tracks)
            for rank in (1, 2, 3)
        }
        | {"none": sum(row.get("selected_rank") is None for row in tracks)},
        "human_outcomes": None,
        "human_labels_used_in_decisions": False,
    }
    _write_immutable_json(config.output_dir / "automated_selector_decisions.json", decisions)
    _write_immutable_json(config.output_dir / "preliminary_selector_metrics.json", metrics)
    return decisions, metrics
