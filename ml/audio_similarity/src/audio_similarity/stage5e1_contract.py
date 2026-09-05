"""Frozen preparation contract for the Stage 5E.1 four-arm experiment."""
from __future__ import annotations

import importlib.metadata
import hashlib
import json
import math
import os
import platform
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .stage4a_sampling import MINIMUM_SAMPLES, SAMPLE_RATE
from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5c2a_retention import probe_and_validate


EXPERIMENT_ID = "STAGE5E1_FOUR_ARM_FULL_SONG_RETRIEVAL"
REPORT_DIRECTORY = Path("reports/stage5e1_four_arm_retrieval")
MEDIA_ROOT = Path(".research_audio")
BASELINE_CHECKPOINT = Path("models/music_audioset_epoch_15_esc_90.14.pt")
FUSION_CHECKPOINT = Path("models/630k-audioset-fusion-best.pt")
FUSION_DOWNLOAD_NAME = "630k-audioset-fusion-best.pt"
FUSION_DOWNLOAD_URL = (
    "https://huggingface.co/lukewys/laion_clap/resolve/main/"
    + FUSION_DOWNLOAD_NAME
)
FUSION_EXPECTED_SHA256 = "fb171dd9b608aebdac3d89286cd7615c5100af4cc7dc37797c7fb8d3cc15e3a5"
FUSION_EXPECTED_SIZE_BYTES = 1_863_889_051
FUSION_SOURCE_REVISION = "bc020633ac5bc0bb364febd3b97401ca42816cea"
BASELINE_EXPECTED_SHA256 = "fae3e9c087f2909c28a09dc31c8dfcdacbc42ba44c70e972b58c1bd1caf6dedd"
BASELINE_EXPECTED_SIZE_BYTES = 2_352_471_003
MINIMUM_DURATION_SECONDS = MINIMUM_SAMPLES / SAMPLE_RATE
CLAP_WEIGHT = 0.7172981519
MUQ_WEIGHT = 0.2827018481


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _write_frozen(path: Path, value: Any) -> None:
    encoded = _canonical_bytes(value)
    if path.exists() and path.read_bytes() != encoded:
        raise Stage5B1AValidationError(f"refusing to replace frozen Stage 5E.1 artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(encoded)


def _write_sha(path: Path) -> str:
    digest = file_sha256(path)
    marker = path.with_suffix(".sha256")
    value = f"{digest}\n".encode()
    if marker.exists() and marker.read_bytes() != value:
        raise Stage5B1AValidationError(f"frozen digest differs: {marker}")
    if not marker.exists():
        marker.write_bytes(value)
    return digest


def _state_keys(path: Path) -> list[str]:
    import torch

    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(checkpoint, dict):
        raise Stage5B1AValidationError("CLAP checkpoint is not a state dictionary")
    state = checkpoint.get("state_dict", checkpoint)
    if not isinstance(state, dict) or not state:
        raise Stage5B1AValidationError("CLAP checkpoint has no model state")
    return sorted(str(key) for key in state)


def inspect_clap_checkpoint(
    path: Path,
    *,
    expected_sha256: str | None = None,
    expected_size_bytes: int | None = None,
) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": str(path),
            "present": False,
            "expected_sha256": expected_sha256,
            "expected_size_bytes": expected_size_bytes,
            "trusted_source_identity": None,
            "trained_aff_available": False,
            "state_key_count": None,
            "fusion_state_key_count": None,
            "sha256": None,
        }
    actual_sha256 = file_sha256(path)
    actual_size_bytes = path.stat().st_size
    identity_matches = (
        (expected_sha256 is None or actual_sha256 == expected_sha256)
        and (expected_size_bytes is None or actual_size_bytes == expected_size_bytes)
    )
    if not identity_matches:
        return {
            "path": str(path),
            "present": True,
            "sha256": actual_sha256,
            "size_bytes": actual_size_bytes,
            "expected_sha256": expected_sha256,
            "expected_size_bytes": expected_size_bytes,
            "trusted_source_identity": False,
            "trained_aff_available": False,
            "state_key_count": None,
            "fusion_state_key_count": None,
        }
    keys = _state_keys(path)
    fusion_keys = [
        key for key in keys
        if "fusion_model" in key.casefold() or "mel_conv2d" in key.casefold()
    ]
    has_aff = any("fusion_model" in key.casefold() for key in fusion_keys)
    has_local_projection = any("mel_conv2d" in key.casefold() for key in fusion_keys)
    return {
        "path": str(path),
        "present": True,
        "sha256": actual_sha256,
        "size_bytes": actual_size_bytes,
        "expected_sha256": expected_sha256,
        "expected_size_bytes": expected_size_bytes,
        "trusted_source_identity": True,
        "state_key_count": len(keys),
        "fusion_state_key_count": len(fusion_keys),
        "has_aff_parameters": has_aff,
        "has_local_projection_parameters": has_local_projection,
        "trained_aff_available": has_aff and has_local_projection,
        "fusion_key_examples": fusion_keys[:20],
    }


def inspect_aff_feasibility(root: Path) -> dict[str, Any]:
    distribution = importlib.metadata.distribution("laion-clap")
    package = Path(distribution.locate_file("laion_clap")).resolve()
    hook = package / "hook.py"
    data = package / "training/data.py"
    fusion = package / "clap_module/feature_fusion.py"
    current = inspect_clap_checkpoint(
        root / BASELINE_CHECKPOINT,
        expected_sha256=BASELINE_EXPECTED_SHA256,
        expected_size_bytes=BASELINE_EXPECTED_SIZE_BYTES,
    )
    candidate = inspect_clap_checkpoint(
        root / FUSION_CHECKPOINT,
        expected_sha256=FUSION_EXPECTED_SHA256,
        expected_size_bytes=FUSION_EXPECTED_SIZE_BYTES,
    )
    current["path"] = str(BASELINE_CHECKPOINT)
    candidate["path"] = str(FUSION_CHECKPOINT)
    status = "AFF_READY" if candidate["trained_aff_available"] else "AFF_CHECKPOINT_REQUIRED"
    return {
        "schema_version": "stage5e1-aff-feasibility-v1",
        "experiment_id": EXPERIMENT_ID,
        "status": status,
        "installed_laion_clap_version": distribution.version,
        "installed_implementation": {
            "hook_sha256": file_sha256(hook),
            "feature_preprocessing_sha256": file_sha256(data),
            "aff_implementation_sha256": file_sha256(fusion),
            "native_fusion_type": "aff_2d",
            "maximum_waveform_samples": 480000,
            "sample_rate_hz": 48000,
            "global_view": "full-song log-mel resized to one 10-second mel extent",
            "local_views": "one native 10-second log-mel crop from each temporal third",
            "native_view_count": 4,
            "native_randomness": (
                "NumPy selects one local start per temporal third and an otherwise unused "
                "compatibility waveform crop; Stage 5E.1 freezes the selected mel-frame starts"
            ),
            "learned_fusion_layers": "HTSAT patch_embed.mel_conv2d plus patch_embed.fusion_model AFF",
        },
        "current_baseline_checkpoint": current,
        "required_fusion_checkpoint": candidate,
        "official_fusion_checkpoint": {
            "filename": FUSION_DOWNLOAD_NAME,
            "source_url": FUSION_DOWNLOAD_URL,
            "source_revision": FUSION_SOURCE_REVISION,
            "expected_sha256": FUSION_EXPECTED_SHA256,
            "expected_size_bytes": FUSION_EXPECTED_SIZE_BYTES,
            "download_authorized": bool(
                candidate.get("present") and candidate.get("trusted_source_identity")
            ),
        },
        "comparison_design": {
            "a_and_c_checkpoint": str(BASELINE_CHECKPOINT),
            "a_and_c_architecture": "HTSAT-base music-specialized non-fusion",
            "b_and_d_checkpoint": str(FUSION_CHECKPOINT),
            "b_and_d_architecture": "HTSAT-tiny general-audio native fusion",
            "b_vs_d_is_matched_checkpoint": True,
            "a_vs_c_is_matched_checkpoint": True,
            "cross_pair_checkpoint_confound": True,
        },
    }


def _historical_review_ids(root: Path) -> set[str]:
    path = root / "reports/stage5c2_representative_100_amended_v2/selected_sources.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["spotify_track_id"]) for row in payload["tracks"]}


def _source_file(directory: Path) -> Path:
    sources = [
        path for path in directory.glob("source.*")
        if path.is_file() and not path.name.endswith((".part", ".ytdl"))
    ]
    if len(sources) != 1:
        raise Stage5B1AValidationError(
            f"expected one retained source in {directory}, found {len(sources)}"
        )
    return sources[0]


def audit_corpus(
    root: Path,
    *,
    probe: Callable[..., dict[str, Any]] = probe_and_validate,
    provenance_paths: list[Path] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    media_root = (root / MEDIA_ROOT).resolve()
    reviewed_ids = _historical_review_ids(root)
    tracks: list[dict[str, Any]] = []
    youtube_groups: dict[str, list[str]] = defaultdict(list)
    source_groups: dict[str, list[str]] = defaultdict(list)
    frozen_paths = (
        sorted(provenance_paths)
        if provenance_paths is not None
        else sorted(media_root.glob("*/provenance.json"))
    )
    snapshot_members = []
    for provenance_path in frozen_paths:
        provenance_path = provenance_path.resolve()
        if media_root not in provenance_path.parents:
            raise Stage5B1AValidationError("retained provenance escapes the media root")
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        spotify_id = str(provenance.get("spotify_track_id", ""))
        if not spotify_id or provenance_path.parent.name != spotify_id:
            raise Stage5B1AValidationError("retained source has invalid Spotify identity")
        source = _source_file(provenance_path.parent).resolve()
        if media_root not in source.parents:
            raise Stage5B1AValidationError("retained source escapes the media root")
        expected_size = int(provenance.get("file_size_bytes", -1))
        expected_sha = str(provenance.get("source_sha256", ""))
        actual_sha = file_sha256(source)
        if source.stat().st_size != expected_size or actual_sha != expected_sha:
            raise Stage5B1AValidationError(f"retained source integrity failed: {spotify_id}")
        snapshot_members.append(
            {
                "spotify_track_id": spotify_id,
                "provenance_sha256": file_sha256(provenance_path),
                "source_sha256": actual_sha,
            }
        )
        if provenance.get("full_decode_validated") is not True:
            raise Stage5B1AValidationError(f"retained source lacks decode provenance: {spotify_id}")
        technical = probe(source, minimum_duration_seconds=0.0)
        duration = float(technical["duration_seconds"])
        eligible = duration >= MINIMUM_DURATION_SECONDS
        youtube_id = str(
            provenance.get("youtube_video_id")
            or provenance.get("selected_youtube_video_id")
            or ""
        )
        if not youtube_id:
            raise Stage5B1AValidationError(f"retained source lacks YouTube identity: {spotify_id}")
        youtube_groups[youtube_id].append(spotify_id)
        source_groups[actual_sha].append(spotify_id)
        linkage = provenance.get("representation_linkage") or {}
        if isinstance(linkage, dict) and "centered30_v1" in linkage:
            linkage = linkage["centered30_v1"]
        linked_source_sha = (
            linkage.get("source_audio_sha256") if isinstance(linkage, dict) else None
        )
        tracks.append(
            {
                "spotify_track_id": spotify_id,
                "title": provenance.get("spotify_title"),
                "artists": provenance.get("spotify_artists") or [],
                "album": provenance.get("album"),
                "release_year": provenance.get("release_year"),
                "youtube_video_id": youtube_id,
                "retained_source_path": str(source.relative_to(root)),
                "source_sha256": actual_sha,
                "file_size_bytes": source.stat().st_size,
                "duration_seconds": duration,
                "codec": technical.get("codec"),
                "container": technical.get("container"),
                "sample_rate_hz": technical.get("sample_rate_hz"),
                "channels": technical.get("channels"),
                "provenance_schema_version": provenance.get("schema_version"),
                "existing_centered30_representation_identity": (
                    linkage.get("representation_identity") if isinstance(linkage, dict) else None
                ),
                "existing_centered30_source_sha256": linked_source_sha,
                "existing_centered30_matches_retained_source": linked_source_sha == actual_sha,
                "historical_stage5c2_review_member": spotify_id in reviewed_ids,
                "eligible": eligible,
                "exclusion_reason": None if eligible else "FROZEN_BASELINE_MINIMUM_AUDIO_UNAVAILABLE",
            }
        )
    if not tracks or len({row["spotify_track_id"] for row in tracks}) != len(tracks):
        raise Stage5B1AValidationError("retained corpus is empty or has duplicate Spotify IDs")
    for row in tracks:
        row["shared_youtube_source_ids"] = sorted(youtube_groups[row["youtube_video_id"]])
        row["shared_source_sha256_ids"] = sorted(source_groups[row["source_sha256"]])
    eligible_tracks = [row for row in tracks if row["eligible"]]
    chunk_count = sum(math.ceil(row["duration_seconds"] / 10.0) for row in eligible_tracks)
    snapshot_sha = hashlib.sha256(
        json.dumps(snapshot_members, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    audit = {
        "schema_version": "stage5e1-corpus-audit-v1",
        "experiment_id": EXPERIMENT_ID,
        "retained_track_count": len(tracks),
        "retained_source_snapshot_sha256": snapshot_sha,
        "eligible_track_count": len(eligible_tracks),
        "excluded_track_count": len(tracks) - len(eligible_tracks),
        "historical_review_members": sum(row["historical_stage5c2_review_member"] for row in tracks),
        "shared_youtube_video_groups": [
            {"youtube_video_id": key, "spotify_track_ids": sorted(ids)}
            for key, ids in sorted(youtube_groups.items()) if len(ids) > 1
        ],
        "identical_source_byte_groups": [
            {"source_sha256": key, "spotify_track_ids": sorted(ids)}
            for key, ids in sorted(source_groups.items()) if len(ids) > 1
        ],
        "estimated_inference_views": {
            "a_centered30_segments_maximum": len(eligible_tracks) * 3,
            "b_native_aff": len(eligible_tracks),
            "c_full_song_10_second_chunks": chunk_count,
            "d_native_global_plus_three_locals": len(eligible_tracks) * 4,
        },
        "tracks": tracks,
    }
    manifest = {
        "schema_version": "stage5e1-frozen-corpus-manifest-v1",
        "experiment_id": EXPERIMENT_ID,
        "identity_key": "spotify_track_id",
        "minimum_duration_seconds": MINIMUM_DURATION_SECONDS,
        "retained_source_snapshot_sha256": snapshot_sha,
        "track_count": len(eligible_tracks),
        "tracks": eligible_tracks,
    }
    return audit, manifest


def _resources(root: Path) -> dict[str, Any]:
    usage = shutil.disk_usage(root)
    return {
        "platform": platform.platform(),
        "logical_cpu_count": os.cpu_count(),
        "disk_total_bytes": usage.total,
        "disk_free_bytes": usage.free,
        "gpu": "queried separately at execution time",
    }


def active_retention_batches(root: Path) -> list[str]:
    active = []
    for path in sorted((root / MEDIA_ROOT).glob("*/batch_*/state.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") in {"RUNNING", "STOPPING"}:
            active.append(str(path.relative_to(root)))
    return active


def _write_feasibility_report(
    path: Path,
    feasibility: dict[str, Any],
    *,
    corpus_summary: str,
) -> None:
    lines = [
        "# Stage 5E.1 CLAP AFF feasibility", "",
        f"**Status:** `{feasibility['status']}`", "",
        f"The current baseline checkpoint has {feasibility['current_baseline_checkpoint']['state_key_count']} "
        "state keys and no trained AFF or fusion-local projection parameters. Enabling native fusion with "
        "that checkpoint would leave new fusion layers untrained.", "",
        "The installed LAION CLAP implementation defines native `aff_2d` with a resized global "
        "log-mel view and three 10-second local log-mel crops. Its official fusion checkpoint is "
        f"`{FUSION_DOWNLOAD_NAME}` (SHA-256 `{FUSION_EXPECTED_SHA256}`).", "",
        "A matched design uses the current checkpoint for A/C and the fusion checkpoint for B/D. "
        "B versus D then isolates learned AFF from arithmetic view averaging; A versus C isolates "
        "centered sampling from full-song chunk averaging. Comparisons across those pairs retain a checkpoint confound.", "",
        corpus_summary, "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def prepare_stage5e1(
    root: str | Path,
    *,
    snapshot_active_retention: bool = False,
) -> dict[str, Any]:
    project = Path(root).resolve()
    report = project / REPORT_DIRECTORY
    report.mkdir(parents=True, exist_ok=True)
    feasibility = inspect_aff_feasibility(project)
    # This diagnostic advances from CHECKPOINT_REQUIRED to READY after the
    # explicitly gated model arrives; the final experiment config freezes it.
    (report / "aff_feasibility.json").write_bytes(_canonical_bytes(feasibility))
    active_batches = active_retention_batches(project)
    if active_batches and not snapshot_active_retention:
        preparation = {
            "schema_version": "stage5e1-preparation-status-v1",
            "experiment_id": EXPERIMENT_ID,
            "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "CORPUS_FREEZE_DEFERRED",
            "aff_status": feasibility["status"],
            "active_retention_batches": active_batches,
            "network_audio_downloads": 0,
            "representation_inference_calls": 0,
        }
        (report / "preparation_status.json").write_bytes(_canonical_bytes(preparation))
        _write_feasibility_report(
            report / "feasibility_report.md",
            feasibility,
            corpus_summary=(
                "The final corpus freeze is deferred while a retained-media batch is active. "
                "No network requests or encoder inference ran during preparation."
            ),
        )
        return preparation
    provenance_snapshot = sorted((project / MEDIA_ROOT).glob("*/provenance.json"))
    audit, manifest = audit_corpus(project, provenance_paths=provenance_snapshot)
    audit["active_retention_batches_at_snapshot"] = active_batches
    audit["snapshot_membership_closed_before_audit"] = True
    manifest["active_retention_batches_at_snapshot"] = active_batches
    manifest["snapshot_membership_closed_before_audit"] = True
    _write_frozen(report / "corpus_audit.json", audit)
    _write_frozen(report / "corpus_manifest.json", manifest)
    manifest_sha = _write_sha(report / "corpus_manifest.json")
    preparation = {
        "schema_version": "stage5e1-preparation-status-v1",
        "experiment_id": EXPERIMENT_ID,
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": feasibility["status"],
        "corpus_manifest_sha256": manifest_sha,
        "eligible_track_count": manifest["track_count"],
        "resources": _resources(project),
        "network_audio_downloads": 0,
        "representation_inference_calls": 0,
    }
    # Status is diagnostic and may advance after the explicitly gated checkpoint arrives.
    (report / "preparation_status.json").write_bytes(_canonical_bytes(preparation))
    _write_feasibility_report(
        report / "feasibility_report.md",
        feasibility,
        corpus_summary=(
            f"The frozen eligible corpus contains {manifest['track_count']} tracks. "
            "No network requests or encoder inference ran during preparation."
        ),
    )
    return preparation
