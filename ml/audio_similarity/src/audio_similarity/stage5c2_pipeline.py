"""Exact-ID acquisition and frozen Stage 5A materialization for Stage 5C.2."""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .stage5a_cache import Stage5ACache
from .stage5a_contract import load_contract
from .stage5a_materialize import TrackInput, materialize, source_sha256
from .stage5b1a_models import Stage5B1AValidationError
from .stage5b1b_artifacts import atomic_json
from .stage5c1_pipeline import (
    YtDlpExactAudioAcquirer,
    _cache_only_encoders,
    _cache_track_row,
    _decode_validation,
    _failure_category,
    _segment_rows,
    load_frozen_encoders,
    verify_model_files,
)
from .stage5c2_discovery import verify_selected_sources
from .stage5c2_manifest import EXPERIMENT_ID, REPORT_DIRECTORY, verify_frozen_manifest
from .stage5c2_rate_limit import (
    AcquisitionRetryPolicy,
    RateLimitedAcquirer,
)


CORPUS = "spotify_library"
CORPUS_VERSION_PREFIX = "stage5c2-representative-100"
ARTIFACT_DIRECTORY = "artifacts/stage5c2_representative_100"
SOURCE_MEDIA_SUFFIXES = frozenset(
    {".aac", ".flac", ".m4a", ".mp3", ".mp4", ".ogg", ".opus", ".part", ".wav", ".webm"}
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _corpus_version(selected_sha256: str) -> str:
    return f"{CORPUS_VERSION_PREFIX}-{selected_sha256[:16]}"


def _ledger(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": "stage5c2-media-identity-v1", "tracks": {}}
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("schema_version") != "stage5c2-media-identity-v1"
        or not isinstance(value.get("tracks"), dict)
    ):
        raise Stage5B1AValidationError("invalid Stage 5C.2 media identity ledger")
    return value


def _track_for_acquirer(track: dict[str, Any]) -> dict[str, Any]:
    """Bridge the shared exact-ID adapter's legacy prefix field without changing identity."""
    return track | {"stage5c1_track_id": track["stage5c2_track_id"]}


def _cache_hit(
    cache: Stage5ACache,
    ledger_row: Any,
    track: dict[str, Any],
    *,
    corpus_version: str,
    vector_contract_sha256: str,
) -> Any:
    if (
        not isinstance(ledger_row, dict)
        or ledger_row.get("video_id") != track["selected_youtube_video_id"]
        or not ledger_row.get("source_audio_sha256")
    ):
        return None
    return cache.successful_track(
        corpus=CORPUS,
        corpus_version=corpus_version,
        stable_track_id=track["spotify_track_id"],
        source_audio_sha256=ledger_row["source_audio_sha256"],
        vector_contract_sha256=vector_contract_sha256,
    )


def run_materialization(
    project_root: str | Path,
    *,
    run_kind: str,
    acquirer: Any | None = None,
    rate_limited_acquirer: Any | None = None,
    encoders: dict[str, Any] | None = None,
    retry_policy: AcquisitionRetryPolicy | None = None,
    report_dir: str | Path | None = None,
    artifact_dir: str | Path | None = None,
    cache_path: str | Path | None = None,
) -> dict[str, Any]:
    if run_kind not in {"first", "cache_rerun"}:
        raise ValueError("run_kind must be first or cache_rerun")
    root = Path(project_root).resolve()
    report = Path(report_dir).resolve() if report_dir else root / REPORT_DIRECTORY
    artifacts = Path(artifact_dir).resolve() if artifact_dir else root / ARTIFACT_DIRECTORY
    cache_file = Path(cache_path).resolve() if cache_path else artifacts / "representations.sqlite"
    report.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    manifest, manifest_sha = verify_frozen_manifest(report / "representative_manifest.json")
    selected, selected_sha = verify_selected_sources(report / "selected_sources.json")
    if selected["representative_manifest_sha256"] != manifest_sha:
        raise Stage5B1AValidationError("selected sources do not match representative manifest")
    contract = load_contract(root / "reports/holistic_stage4a_dual/audio_representation_v1.json")
    corpus_version = _corpus_version(selected_sha)
    ledger_path = artifacts / "media_identity.json"
    media_ledger = _ledger(ledger_path)
    base_acquirer = acquirer or YtDlpExactAudioAcquirer(retries=0)
    limited = rate_limited_acquirer or RateLimitedAcquirer(
        base_acquirer, policy=retry_policy
    )
    temp_root = Path(tempfile.mkdtemp(prefix="spotify-sorter-stage5c2-"))
    started_at = _now()
    started = time.perf_counter()
    acquisition_rows: list[dict[str, Any]] = []
    cleanup_rows: list[dict[str, Any]] = []
    acquired_paths: dict[str, list[Path]] = {}
    decode_rows: dict[str, dict[str, Any]] = {}
    source_by_track: dict[str, str] = {}
    track_inputs: list[TrackInput] = []

    try:
        with Stage5ACache(cache_file) as cache:
            for track in selected["tracks"]:
                spotify_id = track["spotify_track_id"]
                ledger_row = media_ledger["tracks"].get(spotify_id)
                cached = _cache_hit(
                    cache,
                    ledger_row,
                    track,
                    corpus_version=corpus_version,
                    vector_contract_sha256=contract.vector_contract_sha256,
                )
                if cached is not None:
                    source_hash = ledger_row["source_audio_sha256"]
                    source_by_track[spotify_id] = source_hash
                    track_inputs.append(
                        TrackInput(
                            spotify_id,
                            temp_root / f"cache-hit-{spotify_id}.wav",
                            source_hash,
                        )
                    )
                    acquisition_rows.append(
                        {
                            "stage5c2_track_id": track["stage5c2_track_id"],
                            "spotify_track_id": spotify_id,
                            "video_id": track["selected_youtube_video_id"],
                            "exact_url": track["selected_youtube_url"],
                            "provider": "CACHE",
                            "provider_result": "CACHE_HIT_NO_ACQUISITION",
                            "cache_hit": True,
                            "network_attempt_count": 0,
                            "warnings": [],
                            "errors": [],
                        }
                    )
                    decode_rows[spotify_id] = {
                        "status": "CACHE_HIT_NOT_REDECODED",
                        "canonical_pcm_sha256": cached["canonical_pcm_sha256"],
                    }
                    continue

                prefix = f"{track['stage5c2_track_id']}-{track['selected_youtube_video_id']}"
                before = set(temp_root.glob(f"{prefix}.*"))
                phase = "ACQUISITION"
                try:
                    acquisition = limited.acquire(_track_for_acquirer(track), temp_root)
                    path = Path(acquisition["temporary_file_path"])
                    if not path.is_file() or temp_root not in path.resolve().parents:
                        raise RuntimeError("acquirer returned invalid temporary media path")
                    source_hash = source_sha256(path)
                    phase = "DECODE"
                    validation, canonical_hash = _decode_validation(path, contract)
                    validation["canonical_pcm_sha256"] = canonical_hash
                    decode_rows[spotify_id] = validation
                    source_by_track[spotify_id] = source_hash
                    track_inputs.append(TrackInput(spotify_id, path, source_hash))
                    acquisition_rows.append(
                        {
                            "stage5c2_track_id": track["stage5c2_track_id"],
                            "spotify_track_id": spotify_id,
                            "cache_hit": False,
                            "network_attempt_count": len(acquisition["acquisition_attempts"]),
                            "source_audio_sha256": source_hash,
                            **acquisition,
                        }
                    )
                except Exception as exc:
                    diagnostics = getattr(exc, "diagnostics", {})
                    if not isinstance(diagnostics, dict):
                        diagnostics = {}
                    failure_category = diagnostics.get("failure_category")
                    if phase == "DECODE":
                        failure_category = (
                            "SEGMENT_UNAVAILABLE"
                            if "SEGMENT_UNAVAILABLE" in str(exc)
                            else "DECODE_FAILED"
                        )
                    acquisition_rows.append(
                        {
                            "stage5c2_track_id": track["stage5c2_track_id"],
                            "spotify_track_id": spotify_id,
                            "video_id": track["selected_youtube_video_id"],
                            "exact_url": track["selected_youtube_url"],
                            "provider": "yt_dlp_exact_url",
                            "provider_result": "FAILED",
                            "failure_category": failure_category or "ACQUISITION_FAILED",
                            "failure_detail": str(exc)[:2000],
                            "cache_hit": False,
                            "network_attempt_count": len(diagnostics.get("attempts", [])),
                            "warnings": list(diagnostics.get("warnings", [])),
                            "errors": [
                                str(value)[:2000]
                                for value in diagnostics.get("errors", [str(exc)])
                            ],
                        }
                    )
                    decode_rows[spotify_id] = {
                        "status": "FAILED",
                        "failure_detail": str(exc)[:2000],
                    }
                finally:
                    acquired_paths[spotify_id] = sorted(
                        set(temp_root.glob(f"{prefix}.*")) - before
                    )

            acquired_count = sum(
                row["provider_result"] == "SUCCESS" for row in acquisition_rows
            )
            if encoders is None:
                model_files = verify_model_files(root, contract) if acquired_count else {}
                active_encoders = (
                    load_frozen_encoders(root, contract)
                    if acquired_count
                    else _cache_only_encoders(contract)
                )
            else:
                model_files = {"injected_for_test": True}
                active_encoders = encoders
            materialize_started = time.perf_counter()
            stats = materialize(
                track_inputs,
                corpus=CORPUS,
                corpus_version=corpus_version,
                contract=contract,
                cache=cache,
                encoders=active_encoders,
                output_dir=artifacts / "representations",
            )
            materialize_elapsed = time.perf_counter() - materialize_started
            per_track: list[dict[str, Any]] = []
            for track in selected["tracks"]:
                spotify_id = track["spotify_track_id"]
                source_hash = source_by_track.get(spotify_id)
                if not source_hash:
                    acquisition = next(
                        row for row in acquisition_rows if row["spotify_track_id"] == spotify_id
                    )
                    per_track.append(
                        {
                            "stage5c2_track_id": track["stage5c2_track_id"],
                            "spotify_track_id": spotify_id,
                            "status": "FAILED",
                            "failure_category": acquisition.get(
                                "failure_category", "ACQUISITION_FAILED"
                            ),
                            "failure_detail": acquisition.get("failure_detail", ""),
                        }
                    )
                    continue
                row = _cache_track_row(
                    cache,
                    corpus_version=corpus_version,
                    spotify_track_id=spotify_id,
                    source_audio_sha256=source_hash,
                    vector_contract_sha256=contract.vector_contract_sha256,
                )
                if row is None:
                    per_track.append(
                        {
                            "stage5c2_track_id": track["stage5c2_track_id"],
                            "spotify_track_id": spotify_id,
                            "status": "FAILED",
                            "failure_category": "CACHE_WRITE_FAILED",
                            "failure_detail": "no cache row after materialization",
                        }
                    )
                    continue
                item = {
                    "stage5c2_track_id": track["stage5c2_track_id"],
                    "spotify_track_id": spotify_id,
                    "status": row["status"],
                    "failure_category": (
                        ""
                        if row["status"] == "SUCCESS"
                        else _failure_category(row["failure_category"])
                    ),
                    "failure_detail": (
                        "" if row["status"] == "SUCCESS" else row["failure_detail"]
                    ),
                    "source_audio_sha256": source_hash,
                    "canonical_pcm_sha256": row["canonical_pcm_sha256"],
                    "representation_identity": row["representation_identity"],
                    "segments": _segment_rows(cache, row),
                    "cache_hit": next(
                        item["provider_result"] == "CACHE_HIT_NO_ACQUISITION"
                        for item in acquisition_rows
                        if item["spotify_track_id"] == spotify_id
                    ),
                }
                per_track.append(item)
                if row["status"] == "SUCCESS":
                    media_ledger["tracks"][spotify_id] = {
                        "video_id": track["selected_youtube_video_id"],
                        "source_audio_sha256": source_hash,
                        "canonical_pcm_sha256": row["canonical_pcm_sha256"],
                        "representation_identity": row["representation_identity"],
                        "vector_contract_sha256": contract.vector_contract_sha256,
                    }
            cache_manifest = cache.manifest()
        atomic_json(ledger_path, media_ledger)
    finally:
        for track in selected["tracks"]:
            spotify_id = track["spotify_track_id"]
            paths = acquired_paths.get(spotify_id, [])
            existed = any(path.exists() for path in paths)
            errors: list[str] = []
            for path in paths:
                try:
                    if path.exists():
                        path.unlink()
                except Exception as exc:
                    errors.append(str(exc))
            cleanup_rows.append(
                {
                    "stage5c2_track_id": track["stage5c2_track_id"],
                    "spotify_track_id": spotify_id,
                    "temporary_paths": [str(path) for path in paths],
                    "temp_file_existed_before_cleanup": existed,
                    "cleanup_expected": bool(paths),
                    "cleanup_attempted": bool(paths),
                    "temp_files_absent_after_cleanup": all(not path.exists() for path in paths),
                    "errors": errors,
                }
            )
        shutil.rmtree(temp_root, ignore_errors=False)

    _, ending_manifest_sha = verify_frozen_manifest(report / "representative_manifest.json")
    _, ending_selected_sha = verify_selected_sources(report / "selected_sources.json")
    if (ending_manifest_sha, ending_selected_sha) != (manifest_sha, selected_sha):
        raise Stage5B1AValidationError("frozen Stage 5C.2 inputs mutated during acquisition")
    result = {
        "schema_version": "stage5c2-materialization-results-v1",
        "experiment_id": EXPERIMENT_ID,
        "run_kind": run_kind,
        "started_at": started_at,
        "ended_at": _now(),
        "elapsed_seconds": time.perf_counter() - started,
        "representative_manifest_sha256": manifest_sha,
        "selected_sources_sha256": selected_sha,
        "frozen_inputs_unchanged": True,
        "corpus": CORPUS,
        "corpus_version": corpus_version,
        "frozen_contract": {
            "artifact_sha256": contract.artifact_sha256,
            "vector_contract_sha256": contract.vector_contract_sha256,
            "centers_seconds": list(contract.centers_sec),
            "clap_weight": contract.clap_weight,
            "muq_weight": contract.muq_weight,
        },
        "model_files": model_files,
        "manifest_tracks": len(manifest["tracks"]),
        "automated_selected_tracks": len(selected["tracks"]),
        "tracks_attempted": len(selected["tracks"]),
        "full_materialization_successes": sum(
            row["status"] == "SUCCESS" for row in per_track
        ),
        "full_materialization_failures": sum(
            row["status"] != "SUCCESS" for row in per_track
        ),
        "materialization_elapsed_seconds": materialize_elapsed,
        "stage5a_stats": stats.as_dict(),
        "cache_manifest": cache_manifest,
        "tracks": per_track,
        "decode_validation": decode_rows,
        "acquisitions": acquisition_rows,
    }
    retained_media = sorted(
        str(path)
        for directory in (report, artifacts)
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.casefold() in SOURCE_MEDIA_SUFFIXES
    )
    cleanup = {
        "schema_version": "stage5c2-cleanup-audit-v1",
        "experiment_id": EXPERIMENT_ID,
        "run_kind": run_kind,
        "temporary_root": str(temp_root),
        "temporary_root_absent_after_cleanup": not temp_root.exists(),
        "directory_audit_roots": [str(report), str(artifacts)],
        "unintended_retained_source_audio_paths": retained_media,
        "unintended_retained_source_audio_files": len(retained_media),
        "tracks": cleanup_rows,
    }
    attempts = {
        "schema_version": "stage5c2-acquisition-attempts-v1",
        "experiment_id": EXPERIMENT_ID,
        "run_kind": run_kind,
        "selected_sources_sha256": selected_sha,
        "exact_id_only": True,
        "discovery_requests": 0,
        "concurrent_downloads": 0,
        "attempts": limited.attempts,
    }
    if run_kind == "first":
        atomic_json(report / "acquisition_attempts.json", attempts)
        atomic_json(report / "materialization_results.json", result)
        atomic_json(report / "cleanup_audit.json", cleanup)
    else:
        prior = json.loads((report / "materialization_results.json").read_text(encoding="utf-8"))
        prior_identities = {
            row["spotify_track_id"]: row.get("representation_identity")
            for row in prior["tracks"]
            if row.get("status") == "SUCCESS"
        }
        result["cache_rerun_validation"] = {
            "network_acquisition_attempts": len(limited.attempts),
            "reacquisition_prevented": sum(
                row["provider_result"] == "CACHE_HIT_NO_ACQUISITION"
                for row in acquisition_rows
            ),
            "encoder_segments_inferred": (
                stats.clap.inferred_segments + stats.muq.inferred_segments
            ),
            "encoder_rerun": (
                stats.clap.inferred_segments + stats.muq.inferred_segments > 0
            ),
            "representation_hash_equality": {
                row["spotify_track_id"]: (
                    prior_identities[row["spotify_track_id"]]
                    == row.get("representation_identity")
                )
                for row in per_track
                if row.get("status") == "SUCCESS"
                and row["spotify_track_id"] in prior_identities
            },
        }
        result["acquisition_attempts"] = attempts
        result["cleanup"] = cleanup
        atomic_json(report / "cache_rerun_results.json", result)
    return result
