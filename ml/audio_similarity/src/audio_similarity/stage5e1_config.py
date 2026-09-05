"""Frozen configuration and per-track sampling plans for Stage 5E.1."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError, file_sha256
from .stage5e1_contract import (
    BASELINE_CHECKPOINT,
    BASELINE_EXPECTED_SHA256,
    CLAP_WEIGHT,
    EXPERIMENT_ID,
    FUSION_CHECKPOINT,
    FUSION_EXPECTED_SHA256,
    FUSION_SOURCE_REVISION,
    MUQ_WEIGHT,
    REPORT_DIRECTORY,
    _write_frozen,
    _write_sha,
    inspect_aff_feasibility,
)
from .stage5e1_sampling import SAMPLING_SEED, sampling_plan


def experiment_config() -> dict[str, Any]:
    return {
        "schema_version": "stage5e1-four-arm-experiment-config-v1",
        "experiment_id": EXPERIMENT_ID,
        "sampling_seed": SAMPLING_SEED,
        "embedding_dimension": 512,
        "similarity": {
            "metric": "cosine",
            "clap_weight": CLAP_WEIGHT,
            "muq_weight": MUQ_WEIGHT,
            "weights_tuned_in_stage5e1": False,
        },
        "fixed_muq": {
            "representation": "centered30_v1",
            "sample_rate_hz": 24000,
            "window_seconds": 5,
            "centers_seconds": [5, 15, 25],
            "segment_normalization": "L2",
            "pooling": "equal arithmetic mean",
            "pooled_normalization": "L2",
        },
        "arms": {
            "A": {
                "identity": "A_CENTERED30_CURRENT_MUSIC_CLAP_V1",
                "checkpoint": str(BASELINE_CHECKPOINT),
                "checkpoint_sha256": BASELINE_EXPECTED_SHA256,
                "architecture": "HTSAT-base",
                "views": "three 5-second windows centered at 5, 15, 25 seconds",
                "pooling": "L2 each, equal arithmetic mean, L2 result",
            },
            "B": {
                "identity": "B_NATIVE_AFF_GENERAL_AUDIO_CLAP_V1",
                "checkpoint": str(FUSION_CHECKPOINT),
                "checkpoint_sha256": FUSION_EXPECTED_SHA256,
                "checkpoint_revision": FUSION_SOURCE_REVISION,
                "architecture": "HTSAT-tiny",
                "views": "native resized global log-mel plus deterministic front/middle/back 10-second log-mel crops",
                "pooling": "trained native aff_2d feature fusion",
            },
            "C": {
                "identity": "C_FULL_SONG_10S_CHUNK_MEAN_MUSIC_CLAP_V1",
                "checkpoint": str(BASELINE_CHECKPOINT),
                "checkpoint_sha256": BASELINE_EXPECTED_SHA256,
                "architecture": "HTSAT-base",
                "views": "consecutive non-overlapping 10-second chunks covering the full source",
                "final_partial_chunk": "native repeatpad to 10 seconds",
                "short_track": "one native repeatpadded chunk",
                "pooling": "L2 each, equal per-chunk arithmetic mean including final partial, L2 result",
            },
            "D": {
                "identity": "D_NATIVE_GLOBAL3_EQUAL_MEAN_GENERAL_AUDIO_CLAP_V1",
                "checkpoint": str(FUSION_CHECKPOINT),
                "checkpoint_sha256": FUSION_EXPECTED_SHA256,
                "checkpoint_revision": FUSION_SOURCE_REVISION,
                "architecture": "HTSAT-tiny",
                "views": "exact same frozen global/front/middle/back log-mel tensors as B",
                "pooling": "embed views independently, L2 each, equal arithmetic mean, L2 result",
                "native_difference_note": "D bypasses learned feature fusion by embedding each native mel view independently under the matched fusion checkpoint",
            },
        },
        "comparison_interpretation": {
            "A_vs_C_matched_checkpoint": True,
            "B_vs_D_matched_checkpoint_and_views": True,
            "cross_pair_checkpoint_architecture_confound": True,
        },
        "retrieval": {
            "primary_corpus": "intersection of successful A/B/C/D and fixed MuQ vectors",
            "top_k": [5, 10],
            "self_matches_excluded": True,
            "duplicate_filter": "exclude candidate pairs sharing source SHA-256 or YouTube video ID",
            "tie_breaker": "Spotify track ID ascending",
        },
    }


def freeze_experiment(root: str | Path) -> dict[str, Any]:
    project = Path(root).resolve()
    report = project / REPORT_DIRECTORY
    manifest_path = report / "corpus_manifest.json"
    if not manifest_path.is_file():
        raise Stage5B1AValidationError("run Stage 5E.1 prepare before freezing the experiment")
    feasibility = inspect_aff_feasibility(project)
    if feasibility["status"] != "AFF_READY":
        raise Stage5B1AValidationError("trained official CLAP fusion checkpoint is required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("retained_source_snapshot_sha256"):
        raise Stage5B1AValidationError("corpus manifest lacks an immutable retained-source snapshot")
    config = experiment_config()
    config["corpus_manifest_sha256"] = file_sha256(manifest_path)
    config["native_clap_implementation"] = feasibility["installed_implementation"]
    config["installed_laion_clap_version"] = feasibility["installed_laion_clap_version"]
    config["checkpoint_comparison_isolation"] = feasibility["comparison_design"]
    _write_frozen(report / "experiment_config.json", config)
    config_sha = _write_sha(report / "experiment_config.json")
    # Freeze against the exact waveform length produced by the experiment's
    # decode/resample path, not a rounded container-duration estimate.
    from .stage5e1_encoders import decode_mono

    track_plans = []
    for track in manifest["tracks"]:
        waveform = decode_mono(project / track["retained_source_path"], 48_000)
        track_plans.append(
            {
                "spotify_track_id": track["spotify_track_id"],
                "source_sha256": track["source_sha256"],
                "plan": sampling_plan(len(waveform), track["source_sha256"]),
            }
        )
    plans = {
        "schema_version": "stage5e1-sampling-plans-v1",
        "experiment_id": EXPERIMENT_ID,
        "corpus_manifest_sha256": file_sha256(manifest_path),
        "experiment_config_sha256": config_sha,
        "tracks": track_plans,
    }
    _write_frozen(report / "sampling_plans.json", plans)
    return {
        "status": "EXPERIMENT_FROZEN",
        "track_count": manifest["track_count"],
        "corpus_manifest_sha256": file_sha256(manifest_path),
        "experiment_config_sha256": config_sha,
        "sampling_plans_sha256": file_sha256(report / "sampling_plans.json"),
    }
