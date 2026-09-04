"""Exact-ID acquisition and frozen Stage 5A materialization for Stage 5C.1."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import torchaudio

from .stage4a_sampling import MINIMUM_SAMPLES, Stage4AError, cache_windows, decode, pcm_sha256
from .stage5a_cache import Stage5ACache
from .stage5a_contract import RepresentationContract, load_contract
from .stage5a_materialize import TrackInput, materialize, source_sha256
from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5c1_manifest import EXPERIMENT_ID, verify_frozen_manifest


CORPUS = "spotify_library"
CORPUS_VERSION_PREFIX = "stage5c1-curated-25"
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class ExactAudioAcquirer(Protocol):
    def acquire(self, track: dict[str, Any], output_dir: Path) -> dict[str, Any]: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _YtDlpLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def debug(self, _message: str) -> None:
        return None

    def warning(self, message: str) -> None:
        self.warnings.append(str(message))

    def error(self, message: str) -> None:
        self.errors.append(str(message))


class YtDlpExactAudioAcquirer:
    """Acquire only the first 30 seconds of an exact frozen YouTube watch URL."""

    def __init__(self, *, socket_timeout_seconds: float = 20.0, retries: int = 2):
        self.socket_timeout_seconds = socket_timeout_seconds
        self.retries = retries

    def _options(self, output_template: Path, logger: _YtDlpLogger) -> dict[str, Any]:
        from yt_dlp.utils import download_range_func

        return {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": str(output_template),
            "noplaylist": True,
            "ignoreconfig": True,
            "quiet": True,
            "no_warnings": False,
            "logger": logger,
            "socket_timeout": self.socket_timeout_seconds,
            "retries": self.retries,
            "fragment_retries": self.retries,
            "extractor_retries": self.retries,
            "skip_unavailable_fragments": False,
            "download_ranges": download_range_func(None, [(0.0, 30.0)]),
            "force_keyframes_at_cuts": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                    "preferredquality": "0",
                }
            ],
        }

    def acquire(self, track: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        from yt_dlp import YoutubeDL

        video_id = track["selected_youtube_video_id"]
        if not VIDEO_ID.fullmatch(video_id):
            raise Stage5B1AValidationError(f"invalid frozen YouTube video ID: {video_id}")
        exact_url = f"https://www.youtube.com/watch?v={video_id}"
        if track.get("selected_youtube_url") != exact_url:
            raise Stage5B1AValidationError("manifest URL is not the exact frozen watch URL")
        prefix = f"{track['stage5c1_track_id']}-{video_id}"
        logger = _YtDlpLogger()
        output_template = output_dir / f"{prefix}.%(ext)s"
        started_at = _now()
        started = time.perf_counter()
        with YoutubeDL(self._options(output_template, logger)) as ydl:
            info = ydl.extract_info(exact_url, download=True)
        if not isinstance(info, dict) or info.get("id") != video_id:
            raise RuntimeError("yt-dlp exact-URL extraction returned a different video ID")
        matches = sorted(output_dir.glob(f"{prefix}.*"))
        audio_files = [path for path in matches if path.suffix.lower() == ".wav"]
        if len(audio_files) != 1:
            raise RuntimeError(f"expected one WAV output, found {len(audio_files)}")
        path = audio_files[0]
        if path.stat().st_size <= 44:
            raise RuntimeError("acquired audio output is empty")
        return {
            "provider": "yt_dlp_exact_url",
            "provider_result": "SUCCESS",
            "video_id": video_id,
            "exact_url": exact_url,
            "requested_section_seconds": [0.0, 30.0],
            "acquisition_started_at": started_at,
            "acquisition_ended_at": _now(),
            "elapsed_seconds": time.perf_counter() - started,
            "output_format": "wav",
            "temporary_file_path": str(path),
            "file_size_bytes": path.stat().st_size,
            "provider_title": info.get("title"),
            "provider_duration_seconds": info.get("duration"),
            "warnings": logger.warnings,
            "errors": logger.errors,
        }


class _CacheOnlyEncoder:
    def __init__(self, encoder_id: str, embedding_dim: int):
        self.encoder_id = encoder_id
        self.embedding_dim = embedding_dim

    def encode_segment(self, _waveform, _sample_rate):
        raise RuntimeError("cache-only encoder must never run inference")


def _canonical_corpus_version(manifest_sha256: str) -> str:
    return f"{CORPUS_VERSION_PREFIX}-{manifest_sha256[:16]}"


def _media_ledger(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": "stage5c1-media-identity-v1", "tracks": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "stage5c1-media-identity-v1" or not isinstance(payload.get("tracks"), dict):
        raise Stage5B1AValidationError("invalid Stage 5C.1 media identity ledger")
    return payload


def _decode_validation(path: Path, contract: RepresentationContract) -> tuple[dict[str, Any], str]:
    info = torchaudio.info(str(path))
    waveform = decode(path)
    windows = []
    if len(waveform) >= MINIMUM_SAMPLES:
        windows = [
            window for window in cache_windows(len(waveform))
            if window.center_sec in contract.centers_sec
        ]
    all_windows = tuple(window.center_sec for window in windows) == contract.centers_sec
    result = {
        "status": "SUCCESS" if all_windows else "SEGMENT_UNAVAILABLE",
        "container_duration_seconds": info.num_frames / info.sample_rate,
        "source_sample_rate_hz": info.sample_rate,
        "source_channel_count": info.num_channels,
        "decoded_duration_seconds": len(waveform) / contract.sample_rate,
        "canonical_sample_rate_hz": contract.sample_rate,
        "canonical_channel_count": 1,
        "canonical_sample_count": len(waveform),
        "required_segment_centers_seconds": list(contract.centers_sec),
        "required_windows_available": all_windows,
        "segment_windows": [
            {
                "center_second": window.center_sec,
                "start_sample": window.start_sample,
                "end_sample": window.end_sample,
            }
            for window in windows
        ],
    }
    if not all_windows:
        raise Stage4AError("SEGMENT_UNAVAILABLE: all frozen K=3 windows are required")
    return result, pcm_sha256(waveform)


def _cache_track_row(
    cache: Stage5ACache,
    *,
    corpus_version: str,
    spotify_track_id: str,
    source_audio_sha256: str,
    vector_contract_sha256: str,
):
    return cache.db.execute(
        """SELECT * FROM tracks WHERE corpus=? AND corpus_version=?
           AND stable_track_id=? AND source_audio_sha256=?
           AND vector_contract_sha256=?""",
        (CORPUS, corpus_version, spotify_track_id, source_audio_sha256, vector_contract_sha256),
    ).fetchone()


def _segment_rows(cache: Stage5ACache, representation_row) -> list[dict[str, Any]]:
    rows = cache.db.execute(
        """SELECT encoder_id, center_sec, start_sample, end_sample, status,
                  embedding_sha256, encode_ms, attempt_count
           FROM segments WHERE corpus=? AND corpus_version=? AND stable_track_id=?
             AND source_audio_sha256=? AND canonical_pcm_sha256=?
           ORDER BY encoder_id, center_sec""",
        (
            representation_row["corpus"],
            representation_row["corpus_version"],
            representation_row["stable_track_id"],
            representation_row["source_audio_sha256"],
            representation_row["canonical_pcm_sha256"],
        ),
    ).fetchall()
    return [dict(row) for row in rows]


def verify_model_files(project_root: Path, contract: RepresentationContract) -> dict[str, Any]:
    clap = contract.encoder("laion_clap")
    checkpoint = project_root / clap.provenance["checkpoint"]
    checkpoint_hash = file_sha256(checkpoint)
    if checkpoint_hash != clap.provenance["checkpoint_sha256"]:
        raise Stage5B1AValidationError("CLAP checkpoint hash does not match frozen contract")
    muq = contract.encoder("muq_mulan_large")
    snapshot = (
        Path.home()
        / ".cache/huggingface/hub/models--OpenMuQ--MuQ-MuLan-large/snapshots"
        / muq.provenance["revision"]
    )
    files = {}
    for name, expected in (
        ("pytorch_model.bin", muq.provenance["weights_sha256"]),
        ("config.json", muq.provenance["config_sha256"]),
    ):
        path = snapshot / name
        actual = file_sha256(path)
        if actual != expected:
            raise Stage5B1AValidationError(f"MuQ {name} hash does not match frozen contract")
        files[name] = {"path": str(path), "sha256": actual}
    return {
        "clap": {"path": str(checkpoint), "sha256": checkpoint_hash},
        "muq": files,
    }


def load_frozen_encoders(project_root: Path, contract: RepresentationContract):
    from .holistic_encoders import LaionClapEncoder, MuQMulanEncoder

    clap_contract = contract.encoder("laion_clap")
    muq_contract = contract.encoder("muq_mulan_large")
    clap = LaionClapEncoder(
        checkpoint_path=str(project_root / clap_contract.provenance["checkpoint"])
    )
    muq = MuQMulanEncoder(revision=muq_contract.provenance["revision"])
    return {clap.encoder_id: clap, muq.encoder_id: muq}


def _cache_only_encoders(contract: RepresentationContract) -> dict[str, _CacheOnlyEncoder]:
    return {
        encoder.encoder_id: _CacheOnlyEncoder(encoder.encoder_id, encoder.dimension)
        for encoder in contract.encoders
    }


def _failure_category(stage5a_category: str) -> str:
    return {
        "DECODE_FAILURE": "DECODE_FAILED",
        "INVALID_OR_TOO_SHORT_AUDIO": "SEGMENT_UNAVAILABLE",
        "CLAP_INFERENCE_FAILURE": "CLAP_FAILED",
        "MUQ_INFERENCE_FAILURE": "MUQ_FAILED",
        "PERSISTENCE_MATERIALIZATION_FAILURE": "CACHE_WRITE_FAILED",
    }.get(stage5a_category, stage5a_category or "MATERIALIZATION_FAILED")


def run_materialization_attempt(
    project_root: str | Path,
    *,
    run_kind: str,
    acquirer: ExactAudioAcquirer | None = None,
    encoders: dict[str, Any] | None = None,
    cache_path: str | Path | None = None,
    artifact_root: str | Path | None = None,
    report_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run one resumable pass; cache hits bypass acquisition and encoder loading."""
    if run_kind not in {"first", "cache_rerun"}:
        raise ValueError("run_kind must be 'first' or 'cache_rerun'")
    root = Path(project_root).resolve()
    report = Path(report_dir) if report_dir else root / "reports/stage5c1_curated_25_materialization"
    artifacts = Path(artifact_root) if artifact_root else root / "artifacts/stage5c1_curated_25_materialization"
    if not report.is_absolute():
        report = root / report
    if not artifacts.is_absolute():
        artifacts = root / artifacts
    cache_path = Path(cache_path) if cache_path else artifacts / "representations.sqlite"
    if not cache_path.is_absolute():
        cache_path = root / cache_path
    report.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)

    manifest_path = report / "curated_manifest.json"
    manifest, manifest_sha = verify_frozen_manifest(manifest_path)
    contract = load_contract(root / "reports/holistic_stage4a_dual/audio_representation_v1.json")
    corpus_version = _canonical_corpus_version(manifest_sha)
    ledger_path = artifacts / "media_identity.json"
    ledger = _media_ledger(ledger_path)
    acquirer = acquirer or YtDlpExactAudioAcquirer()
    started_at = _now()
    started = time.perf_counter()
    temp_root = Path(tempfile.mkdtemp(prefix="spotify-sorter-stage5c1-"))
    acquisition_rows: list[dict[str, Any]] = []
    cleanup_rows: list[dict[str, Any]] = []
    decode_rows: dict[str, dict[str, Any]] = {}
    track_inputs: list[TrackInput] = []
    source_by_track: dict[str, str] = {}
    acquired_paths: dict[str, list[Path]] = {}

    try:
        with Stage5ACache(cache_path) as cache:
            for track in manifest["tracks"]:
                spotify_id = track["spotify_track_id"]
                stable_id = spotify_id
                ledger_row = ledger["tracks"].get(spotify_id)
                cached = None
                if (
                    isinstance(ledger_row, dict)
                    and ledger_row.get("video_id") == track["selected_youtube_video_id"]
                    and ledger_row.get("source_audio_sha256")
                ):
                    cached = cache.successful_track(
                        corpus=CORPUS,
                        corpus_version=corpus_version,
                        stable_track_id=stable_id,
                        source_audio_sha256=ledger_row["source_audio_sha256"],
                        vector_contract_sha256=contract.vector_contract_sha256,
                    )
                if cached is not None:
                    source_hash = ledger_row["source_audio_sha256"]
                    source_by_track[spotify_id] = source_hash
                    track_inputs.append(
                        TrackInput(stable_id, temp_root / f"cache-hit-{spotify_id}.wav", source_hash)
                    )
                    acquisition_rows.append(
                        {
                            "stage5c1_track_id": track["stage5c1_track_id"],
                            "spotify_track_id": spotify_id,
                            "video_id": track["selected_youtube_video_id"],
                            "exact_url": track["selected_youtube_url"],
                            "provider": "CACHE",
                            "provider_result": "CACHE_HIT_NO_ACQUISITION",
                            "reacquisition": False,
                            "warnings": [],
                            "errors": [],
                        }
                    )
                    decode_rows[spotify_id] = {
                        "status": "CACHE_HIT_NOT_REDECODED",
                        "canonical_pcm_sha256": cached["canonical_pcm_sha256"],
                    }
                    continue

                prefix = f"{track['stage5c1_track_id']}-{track['selected_youtube_video_id']}"
                before = set(temp_root.glob(f"{prefix}.*"))
                phase = "ACQUISITION"
                try:
                    acquisition = acquirer.acquire(track, temp_root)
                    path = Path(acquisition["temporary_file_path"])
                    if not path.is_file() or temp_root not in path.resolve().parents:
                        raise RuntimeError("acquirer returned an invalid temporary output path")
                    acquisition = {
                        "stage5c1_track_id": track["stage5c1_track_id"],
                        "spotify_track_id": spotify_id,
                        "reacquisition": run_kind == "cache_rerun",
                        **acquisition,
                    }
                    source_hash = source_sha256(path)
                    acquisition["source_audio_sha256"] = source_hash
                    phase = "DECODE"
                    validation, canonical_hash = _decode_validation(path, contract)
                    validation["canonical_pcm_sha256"] = canonical_hash
                    decode_rows[spotify_id] = validation
                    source_by_track[spotify_id] = source_hash
                    track_inputs.append(TrackInput(stable_id, path, source_hash))
                    acquisition_rows.append(acquisition)
                except Exception as exc:
                    acquisition_rows.append(
                        {
                            "stage5c1_track_id": track["stage5c1_track_id"],
                            "spotify_track_id": spotify_id,
                            "video_id": track["selected_youtube_video_id"],
                            "exact_url": track["selected_youtube_url"],
                            "provider": "yt_dlp_exact_url",
                            "provider_result": "FAILED",
                            "failure_category": (
                                "SEGMENT_UNAVAILABLE"
                                if "SEGMENT_UNAVAILABLE" in str(exc)
                                else "DECODE_FAILED"
                                if phase == "DECODE"
                                else "ACQUISITION_FAILED"
                            ),
                            "failure_detail": str(exc)[:2000],
                            "reacquisition": run_kind == "cache_rerun",
                            "warnings": [],
                            "errors": [str(exc)[:2000]],
                        }
                    )
                    decode_rows[spotify_id] = {
                        "status": "FAILED",
                        "failure_detail": str(exc)[:2000],
                    }
                finally:
                    acquired_paths[spotify_id] = sorted(set(temp_root.glob(f"{prefix}.*")) - before)

            uncached_count = sum(
                row["provider_result"] == "SUCCESS" for row in acquisition_rows
            )
            if encoders is None:
                model_files = verify_model_files(root, contract) if uncached_count else {}
                active_encoders = (
                    load_frozen_encoders(root, contract)
                    if uncached_count
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
            for track in manifest["tracks"]:
                spotify_id = track["spotify_track_id"]
                source_hash = source_by_track.get(spotify_id)
                if not source_hash:
                    acquisition = next(row for row in acquisition_rows if row["spotify_track_id"] == spotify_id)
                    per_track.append(
                        {
                            "stage5c1_track_id": track["stage5c1_track_id"],
                            "spotify_track_id": spotify_id,
                            "status": "FAILED",
                            "failure_category": acquisition.get("failure_category", "ACQUISITION_FAILED"),
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
                            "stage5c1_track_id": track["stage5c1_track_id"],
                            "spotify_track_id": spotify_id,
                            "status": "FAILED",
                            "failure_category": "CACHE_WRITE_FAILED",
                            "failure_detail": "no Stage 5A cache row after materialization",
                        }
                    )
                    continue
                item = {
                    "stage5c1_track_id": track["stage5c1_track_id"],
                    "spotify_track_id": spotify_id,
                    "status": row["status"],
                    "failure_category": _failure_category(row["failure_category"]),
                    "failure_detail": row["failure_detail"],
                    "source_audio_sha256": source_hash,
                    "canonical_pcm_sha256": row["canonical_pcm_sha256"],
                    "representation_identity": row["representation_identity"],
                    "segments": _segment_rows(cache, row),
                    "cache_hit": next(
                        acquisition["provider_result"] == "CACHE_HIT_NO_ACQUISITION"
                        for acquisition in acquisition_rows
                        if acquisition["spotify_track_id"] == spotify_id
                    ),
                }
                per_track.append(item)
                if row["status"] == "SUCCESS":
                    ledger["tracks"][spotify_id] = {
                        "video_id": track["selected_youtube_video_id"],
                        "source_audio_sha256": source_hash,
                        "canonical_pcm_sha256": row["canonical_pcm_sha256"],
                        "representation_identity": row["representation_identity"],
                        "vector_contract_sha256": contract.vector_contract_sha256,
                    }
            cache_manifest = cache.manifest()

        atomic_json(ledger_path, ledger)
    finally:
        for track in manifest["tracks"]:
            spotify_id = track["spotify_track_id"]
            paths = acquired_paths.get(spotify_id, [])
            existed = any(path.exists() for path in paths)
            errors = []
            for path in paths:
                try:
                    if path.exists():
                        path.unlink()
                except Exception as exc:
                    errors.append(str(exc))
            cleanup_rows.append(
                {
                    "stage5c1_track_id": track["stage5c1_track_id"],
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

    _, ending_sha = verify_frozen_manifest(manifest_path)
    if ending_sha != manifest_sha:
        raise Stage5B1AValidationError("curated manifest mutated during materialization")

    acquisition_payload = {
        "schema_version": "stage5c1-acquisition-results-v1",
        "experiment_id": EXPERIMENT_ID,
        "run_kind": run_kind,
        "manifest_sha256": manifest_sha,
        "exact_url_only": True,
        "discovery_queries_executed": 0,
        "media_substitutions": 0,
        "tracks": acquisition_rows,
    }
    cleanup_payload = {
        "schema_version": "stage5c1-cleanup-results-v1",
        "experiment_id": EXPERIMENT_ID,
        "run_kind": run_kind,
        "temporary_root": str(temp_root),
        "temporary_root_absent_after_cleanup": not temp_root.exists(),
        "tracks": cleanup_rows,
    }
    success_count = sum(row["status"] == "SUCCESS" for row in per_track)
    result = {
        "schema_version": "stage5c1-materialization-results-v1",
        "experiment_id": EXPERIMENT_ID,
        "run_kind": run_kind,
        "started_at": started_at,
        "ended_at": _now(),
        "elapsed_seconds": time.perf_counter() - started,
        "manifest_sha256": manifest_sha,
        "manifest_unchanged": ending_sha == manifest_sha,
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
        "tracks_attempted": len(manifest["tracks"]),
        "full_materialization_successes": success_count,
        "full_materialization_failures": len(manifest["tracks"]) - success_count,
        "materialization_elapsed_seconds": materialize_elapsed,
        "stage5a_stats": stats.as_dict(),
        "cache_manifest": cache_manifest,
        "tracks": per_track,
        "decode_validation": decode_rows,
    }
    if run_kind == "first":
        atomic_json(report / "acquisition_results.json", acquisition_payload)
        atomic_json(report / "materialization_results.json", result)
        atomic_json(report / "cleanup_results.json", cleanup_payload)
    else:
        prior_path = report / "materialization_results.json"
        prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.is_file() else {"tracks": []}
        prior_hashes = {
            row["spotify_track_id"]: row.get("representation_identity")
            for row in prior.get("tracks", [])
            if row.get("status") == "SUCCESS"
        }
        result["cache_rerun_validation"] = {
            "acquisition_requests": sum(row["provider_result"] == "SUCCESS" for row in acquisition_rows),
            "reacquisition_prevented": sum(row["provider_result"] == "CACHE_HIT_NO_ACQUISITION" for row in acquisition_rows),
            "encoder_segments_inferred": stats.clap.inferred_segments + stats.muq.inferred_segments,
            "encoder_rerun": stats.clap.inferred_segments + stats.muq.inferred_segments > 0,
            "representation_hash_equality": {
                row["spotify_track_id"]: (
                    prior_hashes.get(row["spotify_track_id"]) == row.get("representation_identity")
                )
                for row in per_track
                if row.get("status") == "SUCCESS" and row["spotify_track_id"] in prior_hashes
            },
        }
        result["acquisition"] = acquisition_payload
        result["cleanup"] = cleanup_payload
        atomic_json(report / "cache_rerun_results.json", result)
    return result
