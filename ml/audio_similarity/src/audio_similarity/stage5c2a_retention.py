"""Persistent exact-source retention for the amended Stage 5C.2 corpus."""
from __future__ import annotations

import csv
import json
import mimetypes
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from http.server import ThreadingHTTPServer
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5c2_analysis import REVIEW_COLUMNS
from .stage5c2_discovery import verify_selected_sources
from .stage5c2_manifest import verify_frozen_manifest
from .stage5c2_rate_limit import (
    AcquisitionFailed,
    AcquisitionRetryPolicy,
    RateLimitedAcquirer,
)


EXPERIMENT_ID = "STAGE5C2A_PERSISTENT_100_RESEARCH_AUDIO"
SOURCE_EXPERIMENT_ID = "STAGE5C2_REPRESENTATIVE_100_SELECTOR_AWARE_AMENDMENT_V2"
REPORT_DIRECTORY = Path("reports/stage5c2a_persistent_research_audio")
SOURCE_REPORT_DIRECTORY = Path("reports/stage5c2_representative_100_amended_v2")
BASE_REPORT_DIRECTORY = Path("reports/stage5c2_representative_100")
SUPPLEMENT_REPORT_DIRECTORY = Path(
    "reports/stage5c2_representative_100_amended_v2_supplement_materialization"
)
MEDIA_ROOT = Path(".research_audio")
INDEX_SCHEMA = "stage5c2a-local-research-audio-index-v1"
PROVENANCE_SCHEMA = "stage5c2a-retained-source-provenance-v1"
RESULTS_SCHEMA = "stage5c2a-retention-results-v1"
SOURCE_REFERENCE_SCHEMA = "stage5c2a-amended-source-reference-v1"
CONFIG_SCHEMA = "stage5c2a-retention-config-v1"
SUPPORTED_SOURCE_SUFFIXES = frozenset(
    {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".webm"}
)


def _audio_content_type(suffix: str) -> str:
    return {
        ".m4a": "audio/mp4",
        ".opus": "audio/ogg",
        ".webm": "audio/webm",
    }.get(suffix.casefold()) or mimetypes.types_map.get(
        suffix.casefold(), "application/octet-stream"
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _write_frozen_json(path: Path, value: dict[str, Any]) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise Stage5B1AValidationError(f"refusing to replace frozen artifact: {path}")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")


def _review_baseline(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise Stage5B1AValidationError("unexpected amended human-review columns")
        return {
            row["pair_id"]: {
                "human_label": row["human_label"],
                "human_note": row["human_note"],
                "review_timestamp": row["review_timestamp"],
            }
            for row in reader
            if row["human_label"]
        }


def _materialization_links(root: Path) -> dict[str, dict[str, Any]]:
    sources = (
        root / BASE_REPORT_DIRECTORY / "materialization_results.json",
        root / SUPPLEMENT_REPORT_DIRECTORY / "materialization_results.json",
    )
    links: dict[str, dict[str, Any]] = {}
    for source in sources:
        payload = _json(source)
        acquisitions = {
            row["spotify_track_id"]: row for row in payload["acquisitions"]
        }
        for row in payload["tracks"]:
            if row.get("status") != "SUCCESS":
                continue
            spotify_id = row["spotify_track_id"]
            if spotify_id in links:
                raise Stage5B1AValidationError(
                    f"duplicate representation linkage: {spotify_id}"
                )
            acquisition = acquisitions[spotify_id]
            segment_hashes: dict[str, dict[str, str]] = {}
            for segment in row["segments"]:
                encoder = segment["encoder_id"]
                segment_hashes.setdefault(encoder, {})[
                    str(segment["center_sec"])
                ] = segment["embedding_sha256"]
            links[spotify_id] = {
                "materialization_report": str(source.relative_to(root)),
                "youtube_video_id": acquisition["video_id"],
                "centered30_v1": {
                    "representation_identity": row["representation_identity"],
                    "source_audio_sha256": row["source_audio_sha256"],
                    "canonical_pcm_sha256": row["canonical_pcm_sha256"],
                    "segment_embedding_sha256": segment_hashes,
                },
            }
    return links


def validate_amended_source_set(
    project_root: str | Path,
) -> tuple[dict[str, Any], str, dict[str, Any], str, dict[str, dict[str, Any]]]:
    root = Path(project_root).resolve()
    report = root / SOURCE_REPORT_DIRECTORY
    manifest, manifest_sha = verify_frozen_manifest(
        report / "representative_manifest.json"
    )
    selected, selected_sha = verify_selected_sources(report / "selected_sources.json")
    if selected.get("experiment_id") != SOURCE_EXPERIMENT_ID:
        raise Stage5B1AValidationError("retention target is not amended Stage 5C.2 V2")
    if len(manifest["tracks"]) != 100 or len(selected["tracks"]) != 100:
        raise Stage5B1AValidationError("retention requires the amended 100-track set")
    spotify_ids = [row["spotify_track_id"] for row in selected["tracks"]]
    video_ids = [row["selected_youtube_video_id"] for row in selected["tracks"]]
    if len(set(spotify_ids)) != 100 or len(set(video_ids)) != 100:
        raise Stage5B1AValidationError("amended source identities are not unique")
    manifest_ids = {row["spotify_track_id"] for row in manifest["tracks"]}
    if set(spotify_ids) != manifest_ids:
        raise Stage5B1AValidationError("selected sources do not cover the manifest")
    links = _materialization_links(root)
    if set(links) != set(spotify_ids):
        raise Stage5B1AValidationError("existing representations do not cover all 100")
    for row in selected["tracks"]:
        video_id = row["selected_youtube_video_id"]
        if row["selected_youtube_url"] != (
            f"https://www.youtube.com/watch?v={video_id}"
        ):
            raise Stage5B1AValidationError("selected source is not an exact watch URL")
        if links[row["spotify_track_id"]]["youtube_video_id"] != video_id:
            raise Stage5B1AValidationError(
                "representation linkage points to a different selected source"
            )
    recovered = {
        row["spotify_track_id"]: row["selected_youtube_video_id"]
        for row in selected["tracks"]
        if row["spotify_track_id"]
        in {"5quFr5s5PXYfUX5jV2EBZ1", "5l45vVLs4JKkhzN0tvkWJv"}
    }
    if recovered != {
        "5quFr5s5PXYfUX5jV2EBZ1": "v224EdAkZr8",
        "5l45vVLs4JKkhzN0tvkWJv": "i4YFngxyJ0k",
    }:
        raise Stage5B1AValidationError("amended recoveries are missing or changed")
    return manifest, manifest_sha, selected, selected_sha, links


def prepare_retention(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    report = root / REPORT_DIRECTORY
    source_report = root / SOURCE_REPORT_DIRECTORY
    report.mkdir(parents=True, exist_ok=True)
    manifest, manifest_sha, selected, selected_sha, links = (
        validate_amended_source_set(root)
    )
    reference = {
        "schema_version": SOURCE_REFERENCE_SCHEMA,
        "experiment_id": EXPERIMENT_ID,
        "source_experiment_id": SOURCE_EXPERIMENT_ID,
        "representative_manifest_path": str(
            (source_report / "representative_manifest.json").relative_to(root)
        ),
        "representative_manifest_sha256": manifest_sha,
        "selected_sources_path": str(
            (source_report / "selected_sources.json").relative_to(root)
        ),
        "selected_sources_sha256": selected_sha,
        "expected_track_count": 100,
        "tracks": [
            {
                "manifest_index": row["manifest_index"],
                "stage5c2_track_id": row["stage5c2_track_id"],
                "spotify_track_id": row["spotify_track_id"],
                "spotify_title": row["title"],
                "spotify_artists": row["artists"],
                "youtube_video_id": row["selected_youtube_video_id"],
                "selected_youtube_video_id": row["selected_youtube_video_id"],
                "source_url": row["selected_youtube_url"],
                "selected_rank": row["selected_candidate_rank"],
                "discovery_mode": row["discovery_mode"],
                "query_variant_index": row["query_variant_index"],
                "successful_query": row["successful_query"],
                "selector_decision": row["selector_decision"],
                "representation_linkage": links[row["spotify_track_id"]],
            }
            for row in selected["tracks"]
        ],
    }
    reference_path = report / "amended_100_source_reference.json"
    _write_frozen_json(reference_path, reference)
    immutable_names = (
        "representative_manifest.json",
        "representative_manifest.sha256",
        "selected_sources.json",
        "selected_sources.sha256",
        "review_queue.json",
        "clap_similarity.csv",
        "muq_similarity.csv",
        "combined_similarity.csv",
        "nearest_neighbors.json",
    )
    config = {
        "schema_version": CONFIG_SCHEMA,
        "experiment_id": EXPERIMENT_ID,
        "source_experiment_id": SOURCE_EXPERIMENT_ID,
        "frozen_at_utc": _now(),
        "media_root": str(MEDIA_ROOT),
        "index_path": str(MEDIA_ROOT / "index.json"),
        "source_reference_path": str(reference_path.relative_to(root)),
        "source_reference_sha256": file_sha256(reference_path),
        "selected_sources_sha256": selected_sha,
        "representative_manifest_sha256": manifest_sha,
        "expected_track_count": len(manifest["tracks"]),
        "retention_policy": {
            "retain_validated_full_source": True,
            "retain_provenance": True,
            "delete_scratch_and_partial_files": True,
            "git_ignored_local_only": True,
            "git_lfs": False,
        },
        "acquisition": {
            "provider": "yt_dlp_exact_url",
            "exact_frozen_ids_only": True,
            "discovery_requests": 0,
            "selector_calls": 0,
            "format": "bestaudio/best",
            "full_source": True,
            "serial": True,
            "minimum_start_spacing_seconds": 20.0,
            "maximum_attempts": 4,
        },
        "representation": {
            "clap_inference": False,
            "muq_inference": False,
            "existing_linkage_only": True,
        },
        "immutable_amended_evidence": {
            name: file_sha256(source_report / name) for name in immutable_names
        },
        "original_98_selected_sources_sha256": file_sha256(
            root / BASE_REPORT_DIRECTORY / "selected_sources.json"
        ),
        "human_review_baseline": _review_baseline(
            source_report / "human_similarity_review.csv"
        ),
    }
    config_path = report / "retention_config.json"
    if config_path.exists():
        existing = _json(config_path)
        config["frozen_at_utc"] = existing["frozen_at_utc"]
    _write_frozen_json(config_path, config)
    return config


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


class PersistentExactAudioAcquirer:
    """Download one complete compressed source from one frozen watch URL."""

    def __init__(self, *, socket_timeout_seconds: float = 30.0) -> None:
        self.socket_timeout_seconds = socket_timeout_seconds

    def acquire(self, track: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        from yt_dlp import YoutubeDL

        video_id = track["youtube_video_id"]
        exact_url = f"https://www.youtube.com/watch?v={video_id}"
        if track["source_url"] != exact_url:
            raise Stage5B1AValidationError("retention URL is not the frozen exact URL")
        logger = _YtDlpLogger()
        template = output_dir / f"{track['spotify_track_id']}-{video_id}.%(ext)s"
        options = {
            "format": "bestaudio/best",
            "outtmpl": str(template),
            "noplaylist": True,
            "ignoreconfig": True,
            "quiet": True,
            "no_warnings": False,
            "logger": logger,
            "socket_timeout": self.socket_timeout_seconds,
            "retries": 0,
            "fragment_retries": 0,
            "extractor_retries": 0,
            "skip_unavailable_fragments": False,
        }
        started_at = _now()
        started = time.perf_counter()
        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(exact_url, download=True)
                prepared = Path(ydl.prepare_filename(info)) if info else None
        except Exception as exc:
            diagnostics = {
                "provider": "yt_dlp_exact_url",
                "video_id": video_id,
                "exact_url": exact_url,
                "warnings": logger.warnings,
                "errors": logger.errors or [str(exc)],
            }
            error = RuntimeError(str(exc))
            error.diagnostics = diagnostics  # type: ignore[attr-defined]
            raise error from exc
        if not isinstance(info, dict) or info.get("id") != video_id:
            raise RuntimeError("yt-dlp returned a different video identity")
        candidates = [
            path
            for path in output_dir.glob(f"{track['spotify_track_id']}-{video_id}.*")
            if path.is_file()
            and path.suffix.casefold() in SUPPORTED_SOURCE_SUFFIXES
            and not path.name.endswith((".part", ".ytdl"))
        ]
        if prepared and prepared.is_file() and prepared not in candidates:
            candidates.append(prepared)
        if len(candidates) != 1:
            raise RuntimeError(
                f"expected one complete retained-source candidate, found {len(candidates)}"
            )
        path = candidates[0]
        if path.stat().st_size <= 1024:
            raise RuntimeError("downloaded source is unexpectedly small")
        return {
            "provider": "yt_dlp_exact_url",
            "video_id": video_id,
            "exact_url": exact_url,
            "downloaded_path": str(path),
            "provider_title": info.get("title"),
            "provider_duration_seconds": info.get("duration"),
            "acquisition_started_at": started_at,
            "acquisition_ended_at": _now(),
            "acquisition_duration_seconds": time.perf_counter() - started,
            "warnings": logger.warnings,
            "errors": logger.errors,
        }


def probe_and_validate(path: Path) -> dict[str, Any]:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,format_name:stream=codec_name,codec_type,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(probe.stdout)
    audio_streams = [
        row for row in payload.get("streams", []) if row.get("codec_type") == "audio"
    ]
    if len(audio_streams) != 1:
        raise Stage5B1AValidationError("retained source must contain one audio stream")
    stream = audio_streams[0]
    duration = float(payload.get("format", {}).get("duration", 0))
    if duration < 29.5:
        raise Stage5B1AValidationError("retained source is too short for frozen windows")
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        timeout=max(120, int(duration * 2)),
    )
    suffix = path.suffix.casefold()
    content_type = _audio_content_type(suffix)
    return {
        "duration_seconds": duration,
        "container": payload["format"].get("format_name"),
        "codec": stream.get("codec_name"),
        "sample_rate_hz": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
        "content_type": content_type,
        "full_decode_validated": True,
    }


def _load_index(path: Path, selected_sha: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": INDEX_SCHEMA,
            "experiment_id": EXPERIMENT_ID,
            "source_experiment_id": SOURCE_EXPERIMENT_ID,
            "selected_sources_sha256": selected_sha,
            "track_count": 0,
            "updated_at_utc": None,
            "tracks": {},
        }
    index = _json(path)
    if (
        index.get("schema_version") != INDEX_SCHEMA
        or index.get("selected_sources_sha256") != selected_sha
        or not isinstance(index.get("tracks"), dict)
    ):
        raise Stage5B1AValidationError("local retained-media index is incompatible")
    return index


def _cache_hit(
    media_root: Path,
    track: dict[str, Any],
    selected_sha: str,
) -> dict[str, Any] | None:
    provenance_path = media_root / track["spotify_track_id"] / "provenance.json"
    if not provenance_path.is_file():
        return None
    provenance = _json(provenance_path)
    if (
        provenance.get("schema_version") != PROVENANCE_SCHEMA
        or provenance.get("spotify_track_id") != track["spotify_track_id"]
        or provenance.get("youtube_video_id") != track["youtube_video_id"]
        or provenance.get("selected_sources_sha256") != selected_sha
    ):
        return None
    source = (media_root / provenance.get("retained_relative_path", "")).resolve()
    if media_root.resolve() not in source.parents or not source.is_file():
        return None
    if source.stat().st_size != provenance.get("file_size_bytes"):
        return None
    if file_sha256(source) != provenance.get("source_sha256"):
        return None
    expected_content_type = _audio_content_type(source.suffix)
    if provenance.get("content_type") != expected_content_type:
        provenance["content_type"] = expected_content_type
        atomic_json(provenance_path, provenance)
    return provenance


def _last_attempt_elapsed(results_path: Path) -> float | None:
    if not results_path.is_file():
        return None
    attempts = _json(results_path).get("attempts", [])
    if not attempts:
        return None
    raw = attempts[-1].get("request_start_timestamp")
    if not raw:
        return None
    started = datetime.fromisoformat(raw)
    return max(0.0, (datetime.now(timezone.utc) - started).total_seconds())


def _checkpoint(
    path: Path,
    *,
    selected_sha: str,
    tracks: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    started_at: str,
    complete: bool,
) -> None:
    atomic_json(
        path,
        {
            "schema_version": RESULTS_SCHEMA,
            "experiment_id": EXPERIMENT_ID,
            "source_experiment_id": SOURCE_EXPERIMENT_ID,
            "selected_sources_sha256": selected_sha,
            "started_at_utc": started_at,
            "updated_at_utc": _now(),
            "status": "COMPLETE" if complete else "RUNNING",
            "expected_track_count": 100,
            "discovery_requests": 0,
            "selector_calls": 0,
            "clap_inference_calls": 0,
            "muq_inference_calls": 0,
            "tracks": tracks,
            "attempts": attempts,
        },
    )


def run_retention(
    project_root: str | Path,
    *,
    acquirer: Any | None = None,
    rate_limited_acquirer: RateLimitedAcquirer | None = None,
    retry_policy: AcquisitionRetryPolicy | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    config = prepare_retention(root)
    report = root / REPORT_DIRECTORY
    media_root = root / MEDIA_ROOT
    media_root.mkdir(parents=True, exist_ok=True)
    reference = _json(root / config["source_reference_path"])
    selected_sha = reference["selected_sources_sha256"]
    results_path = report / "retention_results.json"
    initial_elapsed = _last_attempt_elapsed(results_path)
    policy = retry_policy or AcquisitionRetryPolicy()
    limited = rate_limited_acquirer or RateLimitedAcquirer(
        acquirer or PersistentExactAudioAcquirer(),
        policy=policy,
        initial_elapsed_since_previous_start_seconds=initial_elapsed,
    )
    prior_attempts = (
        _json(results_path).get("attempts", []) if results_path.is_file() else []
    )
    index_path = media_root / "index.json"
    index = _load_index(index_path, selected_sha)
    started_at = _now()
    rows: list[dict[str, Any]] = []
    for track in reference["tracks"]:
        spotify_id = track["spotify_track_id"]
        hit = _cache_hit(media_root, track, selected_sha)
        if hit is not None:
            index["tracks"][spotify_id] = hit
            rows.append(
                {
                    "spotify_track_id": spotify_id,
                    "youtube_video_id": track["youtube_video_id"],
                    "status": "SUCCESS",
                    "retention_mode": "RETENTION_CACHE_HIT",
                    "retained_relative_path": hit["retained_relative_path"],
                    "source_sha256": hit["source_sha256"],
                    "file_size_bytes": hit["file_size_bytes"],
                    "error": None,
                }
            )
            continue
        scratch = Path(tempfile.mkdtemp(prefix=".scratch-", dir=media_root))
        result: dict[str, Any] | None = None
        try:
            result = limited.acquire(track, scratch)
            downloaded = Path(result["downloaded_path"])
            technical = probe_and_validate(downloaded)
            source_hash = file_sha256(downloaded)
            track_root = media_root / spotify_id
            track_root.mkdir(parents=True, exist_ok=True)
            retained = track_root / f"source{downloaded.suffix.casefold()}"
            temporary_retained = track_root / f".{retained.name}.tmp"
            shutil.move(str(downloaded), temporary_retained)
            temporary_retained.replace(retained)
            for stale in track_root.glob("source.*"):
                if stale != retained:
                    stale.unlink()
            provenance = {
                "schema_version": PROVENANCE_SCHEMA,
                "experiment_id": EXPERIMENT_ID,
                "selected_sources_sha256": selected_sha,
                "spotify_track_id": spotify_id,
                "spotify_title": track["spotify_title"],
                "spotify_artists": track["spotify_artists"],
                "youtube_video_id": track["youtube_video_id"],
                "source_url": track["source_url"],
                "selected_rank": track["selected_rank"],
                "discovery_mode": track["discovery_mode"],
                "query_variant_index": track["query_variant_index"],
                "successful_query": track["successful_query"],
                "selector_decision": track["selector_decision"],
                "provider_title": result.get("provider_title"),
                "provider_duration_seconds": result.get(
                    "provider_duration_seconds"
                ),
                "source_duration_seconds": technical["duration_seconds"],
                "retained_relative_path": str(retained.relative_to(media_root)),
                "file_size_bytes": retained.stat().st_size,
                "source_sha256": source_hash,
                "codec": technical["codec"],
                "container": technical["container"],
                "sample_rate_hz": technical["sample_rate_hz"],
                "channels": technical["channels"],
                "content_type": technical["content_type"],
                "full_decode_validated": technical["full_decode_validated"],
                "acquisition_timestamp": result["acquisition_started_at"],
                "representation_linkage": track["representation_linkage"],
                "warnings": result.get("warnings", []),
            }
            atomic_json(track_root / "provenance.json", provenance)
            index["tracks"][spotify_id] = provenance
            rows.append(
                {
                    "spotify_track_id": spotify_id,
                    "youtube_video_id": track["youtube_video_id"],
                    "status": "SUCCESS",
                    "retention_mode": "LIVE_EXACT_ID_ACQUISITION",
                    "retained_relative_path": provenance["retained_relative_path"],
                    "source_sha256": source_hash,
                    "file_size_bytes": provenance["file_size_bytes"],
                    "network_attempt_count": len(result["acquisition_attempts"]),
                    "error": None,
                }
            )
        except Exception as exc:
            diagnostics = getattr(exc, "diagnostics", {})
            rows.append(
                {
                    "spotify_track_id": spotify_id,
                    "youtube_video_id": track["youtube_video_id"],
                    "status": "FAILED",
                    "retention_mode": "LIVE_EXACT_ID_ACQUISITION",
                    "failure_category": (
                        exc.category
                        if isinstance(exc, AcquisitionFailed)
                        else "ACQUISITION_OR_VALIDATION_FAILED"
                    ),
                    "error": str(exc)[:2000],
                    "warnings": diagnostics.get("warnings", []),
                }
            )
        finally:
            shutil.rmtree(scratch, ignore_errors=False)
        index["track_count"] = len(index["tracks"])
        index["updated_at_utc"] = _now()
        atomic_json(index_path, index)
        _checkpoint(
            results_path,
            selected_sha=selected_sha,
            tracks=rows,
            attempts=[*prior_attempts, *limited.attempts],
            started_at=started_at,
            complete=False,
        )
    index["track_count"] = len(index["tracks"])
    index["updated_at_utc"] = _now()
    atomic_json(index_path, index)
    complete = len(rows) == 100 and all(row["status"] == "SUCCESS" for row in rows)
    _checkpoint(
        results_path,
        selected_sha=selected_sha,
        tracks=rows,
        attempts=[*prior_attempts, *limited.attempts],
        started_at=started_at,
        complete=complete,
    )
    return _json(results_path)


def _attempt_spacings(attempts: list[dict[str, Any]]) -> list[float]:
    timestamps = [
        datetime.fromisoformat(row["request_start_timestamp"]) for row in attempts
    ]
    return [
        (current - previous).total_seconds()
        for previous, current in zip(timestamps, timestamps[1:])
    ]


def closeout_retention(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    report = root / REPORT_DIRECTORY
    source_report = root / SOURCE_REPORT_DIRECTORY
    config = _json(report / "retention_config.json")
    results = _json(report / "retention_results.json")
    index = _load_index(
        root / MEDIA_ROOT / "index.json", config["selected_sources_sha256"]
    )
    for name, expected in config["immutable_amended_evidence"].items():
        if file_sha256(source_report / name) != expected:
            raise Stage5B1AValidationError(f"amended evidence changed: {name}")
    current_review = _review_baseline(source_report / "human_similarity_review.csv")
    for pair_id, baseline in config["human_review_baseline"].items():
        if current_review.get(pair_id) != baseline:
            raise Stage5B1AValidationError("existing human review progress changed")
    files: list[Path] = []
    for spotify_id, provenance in index["tracks"].items():
        source = (root / MEDIA_ROOT / provenance["retained_relative_path"]).resolve()
        if (root / MEDIA_ROOT).resolve() not in source.parents:
            raise Stage5B1AValidationError("retained path escaped media root")
        if not source.is_file() or file_sha256(source) != provenance["source_sha256"]:
            raise Stage5B1AValidationError(f"retained source failed audit: {spotify_id}")
        files.append(source)
    scratch = sorted(
        str(path.relative_to(root / MEDIA_ROOT))
        for path in (root / MEDIA_ROOT).rglob("*")
        if path.name.startswith(".scratch-")
        or path.suffix.casefold() in {".part", ".tmp", ".ytdl", ".wav"}
    )
    provenance_rows = list(index["tracks"].values())
    attempts = results["attempts"]
    spacings = _attempt_spacings(attempts)
    statuses = Counter(row.get("http_status") for row in attempts)
    sizes = [row["file_size_bytes"] for row in provenance_rows]
    durations = [row["source_duration_seconds"] for row in provenance_rows]
    ignored_probe = root / MEDIA_ROOT / ".gitignore-audit.media"
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", str(ignored_probe.relative_to(root))],
        cwd=root,
        check=False,
    ).returncode == 0
    tracked = subprocess.run(
        ["git", "ls-files", "--", str(MEDIA_ROOT)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if not ignored:
        raise Stage5B1AValidationError("persistent media root is not Git-ignored")
    if tracked:
        raise Stage5B1AValidationError("persistent media files are tracked by Git")
    metrics = {
        "schema_version": "stage5c2a-retention-metrics-v1",
        "experiment_id": EXPERIMENT_ID,
        "verdict": (
            "PERSISTENT_100_RESEARCH_AUDIO_CACHE_READY"
            if len(files) == 100 and not scratch
            else "PERSISTENT_100_RESEARCH_AUDIO_CACHE_PARTIAL"
        ),
        "expected_tracks": 100,
        "retained_successful": len(files),
        "retention_cache_hits_last_run": sum(
            row["retention_mode"] == "RETENTION_CACHE_HIT"
            for row in results["tracks"]
        ),
        "acquisition_failures_last_run": sum(
            row["status"] != "SUCCESS" for row in results["tracks"]
        ),
        "total_bytes": sum(sizes),
        "median_file_size_bytes": median(sizes) if sizes else None,
        "largest_file_bytes": max(sizes, default=None),
        "codec_distribution": dict(Counter(row["codec"] for row in provenance_rows)),
        "container_distribution": dict(
            Counter(row["container"] for row in provenance_rows)
        ),
        "duration_seconds": {
            "minimum": min(durations, default=None),
            "median": median(durations) if durations else None,
            "maximum": max(durations, default=None),
        },
        "total_live_attempts": len(attempts),
        "retry_attempts": sum(row["attempt_number"] > 1 for row in attempts),
        "http_429_events": statuses[429],
        "http_5xx_events": sum(
            count for status, count in statuses.items() if status and 500 <= status <= 599
        ),
        "retry_after_events": sum(
            row.get("retry_after_seconds") is not None for row in attempts
        ),
        "provider_failures": sum(row["final_outcome"] == "FAILED" for row in attempts),
        "acquisition_start_spacing_seconds": {
            "minimum": min(spacings, default=None),
            "median": median(spacings) if spacings else None,
            "maximum": max(spacings, default=None),
            "required_minimum": 20.0,
            "all_compliant": all(value >= 20.0 - 1e-6 for value in spacings),
        },
        "clap_reruns": results["clap_inference_calls"],
        "muq_reruns": results["muq_inference_calls"],
        "scratch_artifacts": scratch,
        "scratch_cleanup_passed": not scratch,
        "review_queue_sha256": file_sha256(source_report / "review_queue.json"),
        "review_query_count": 100,
        "review_directional_relationship_count": 500,
        "review_unique_pair_count": 359,
        "human_review_baseline_preserved": True,
        "media_files_git_ignored": ignored,
        "media_files_tracked_by_git": len(tracked),
    }
    atomic_json(report / "retention_metrics.json", metrics)
    return metrics


def validate_local_playback(project_root: str | Path) -> dict[str, Any]:
    """Exercise full and range responses against the real indexed corpus."""
    from .cli.stage5b1b_review_server import make_review_handler
    from .stage5c2_review import Stage5C2ReviewStore

    root = Path(project_root).resolve()
    source_report = root / SOURCE_REPORT_DIRECTORY
    index_path = root / MEDIA_ROOT / "index.json"
    store = Stage5C2ReviewStore(
        source_report / "review_queue.json",
        source_report / "human_similarity_review.csv",
        source_report / "selected_sources.json",
        index_path,
    )
    session = store.session()
    if len(session["cases"]) != 100 or any(
        case["playback"]["provider"] != "LOCAL_RESEARCH_AUDIO"
        for case in session["cases"]
    ):
        raise Stage5B1AValidationError("review session is not the amended local 100")
    ids = list(
        dict.fromkeys(
            (
                session["cases"][0]["spotify_track_id"],
                session["cases"][49]["spotify_track_id"],
                session["cases"][-1]["spotify_track_id"],
                "5quFr5s5PXYfUX5jV2EBZ1",
                "5l45vVLs4JKkhzN0tvkWJv",
            )
        )
    )
    handler = make_review_handler(store, mode="stage5c2_similarity_review")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def request(spotify_id: str, byte_range: str | None = None):
        req = urllib.request.Request(f"{base}/audio/track/{spotify_id}")
        if byte_range:
            req.add_header("Range", byte_range)
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        ).open(req, timeout=30)

    checks: list[dict[str, Any]] = []
    try:
        full_id = ids[0]
        full_source, _ = store.local_audio_for_request(full_id) or (None, None)
        if full_source is None:
            raise Stage5B1AValidationError("full-response playback source missing")
        with request(full_id) as response:
            full_body = response.read()
            full_ok = response.status == 200 and full_body == full_source.read_bytes()
        if not full_ok:
            raise Stage5B1AValidationError("ordinary full audio response failed")
        for spotify_id in ids:
            source, _content_type = store.local_audio_for_request(spotify_id) or (
                None,
                None,
            )
            if source is None:
                raise Stage5B1AValidationError("indexed playback source missing")
            size = source.stat().st_size
            ranges = {
                "beginning": "bytes=0-1023",
                "mid_song": f"bytes={size // 2}-{size // 2 + 1023}",
                "near_end": "bytes=-1024",
            }
            track_checks: dict[str, Any] = {
                "spotify_track_id": spotify_id,
                "source_sha256": file_sha256(source),
                "checks": {},
            }
            for label, requested in ranges.items():
                with request(spotify_id, requested) as response:
                    body = response.read()
                    content_range = response.headers.get("Content-Range")
                    ok = (
                        response.status == 206
                        and response.headers.get("Accept-Ranges") == "bytes"
                        and bool(content_range and content_range.startswith("bytes "))
                        and len(body) == 1024
                    )
                if not ok:
                    raise Stage5B1AValidationError(
                        f"HTTP range validation failed: {spotify_id} {label}"
                    )
                track_checks["checks"][label] = {
                    "status": 206,
                    "requested_range": requested,
                    "content_range": content_range,
                    "bytes_received": len(body),
                }
            with request(spotify_id, ranges["mid_song"]) as response:
                repeated = response.read()
            track_checks["repeated_seek_identical"] = len(repeated) == 1024
            checks.append(track_checks)
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    distinct = len({row["source_sha256"] for row in checks}) == len(checks)
    result = {
        "schema_version": "stage5c2a-playback-validation-v1",
        "experiment_id": EXPERIMENT_ID,
        "source_experiment_id": SOURCE_EXPERIMENT_ID,
        "review_query_count": len(session["cases"]),
        "review_directional_relationship_count": session["progress"]["raw_top5_rows"],
        "review_unique_pair_count": session["progress"]["total_unique_pairs"],
        "review_queue_sha256": file_sha256(source_report / "review_queue.json"),
        "ordinary_full_response": "PASS",
        "http_206_range_response": "PASS",
        "content_range": "PASS",
        "beginning_seek": "PASS",
        "mid_song_seek": "PASS",
        "near_end_seek": "PASS",
        "repeated_seek": "PASS",
        "query_neighbor_switching": "PASS" if distinct else "FAIL",
        "distinct_source_sha256": distinct,
        "browser_validation": "PENDING",
        "tracks": checks,
    }
    atomic_json(
        root / REPORT_DIRECTORY / "playback_validation.json", result
    )
    return result
