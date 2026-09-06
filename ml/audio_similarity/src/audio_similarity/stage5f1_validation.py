"""Synthetic and engineering validation for Stage 5F.1."""

from __future__ import annotations

import hashlib
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .energy_motion_audio import extract_track, file_sha256
from .energy_motion_config import Stage5F1Config


def _click_signal(bpm: float, dense: bool = False, seconds: int = 40) -> np.ndarray:
    sr = 22050
    time = np.arange(sr * seconds) / sr
    signal = 0.003 * np.sin(2 * np.pi * 220 * time)
    click_time = np.arange(round(0.020 * sr)) / sr
    click = 0.4 * np.sin(2 * np.pi * 1000 * click_time) * np.exp(-click_time / 0.003)
    for at in np.arange(1, seconds - 1, 60 / bpm):
        index = round(at * sr)
        signal[index : index + click.size] += click
    if dense:
        for at in np.arange(1, seconds - 1, 60 / bpm / 4):
            if abs((at - 1) / (60 / bpm) - round((at - 1) / (60 / bpm))) < 1e-6:
                continue
            index = round(at * sr)
            signal[index : index + click.size] += 0.25 * click
    return signal.astype(np.float32)


def validate_synthetic(
    config: Stage5F1Config, environment_sha256: str, implementation_sha256: str
) -> dict[str, Any]:
    fixtures: dict[str, np.ndarray] = {f"click_{bpm}": _click_signal(bpm) for bpm in (60, 75, 90, 120, 150, 180)}
    fixtures["sparse_100"] = _click_signal(100)
    fixtures["dense_100"] = _click_signal(100, dense=True)
    time = np.arange(22050 * 40) / 22050
    fixtures["sustained_tone"] = (0.1 * np.sin(2 * np.pi * 220 * time)).astype(np.float32)
    rng = np.random.default_rng(config.evaluation.seed)
    fixtures["stationary_noise"] = rng.normal(0, 0.05, time.size).astype(np.float32)
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="stage5f1-synthetic-") as directory:
        root = Path(directory)
        extracted: dict[str, dict[str, Any]] = {}
        for name, signal in fixtures.items():
            path = root / f"{name}.wav"
            sf.write(path, signal, 22050, subtype="FLOAT")
            result = extract_track(
                path, file_sha256(path), config.extraction,
                environment_sha256, implementation_sha256,
                config.execution.loudness_timeout_seconds,
            ).as_dict()
            extracted[name] = result
            rows.append({
                "fixture": name,
                "status": result["status"],
                "primary_bpm": result["pulse"]["values"].get("primary_bpm"),
                "pulse_reliability": result["pulse"]["values"].get("pulse_reliability"),
                "onset_rate_hz": result["activity"]["values"].get("onset_rate_hz"),
            })
        checks = []
        for bpm in (60, 75, 90, 120, 150, 180):
            row = extracted[f"click_{bpm}"]
            candidates = row["pulse"]["values"].get("tempo_candidates", [])
            family_match = any(
                candidate.get("supported")
                and abs(math.log2(candidate["bpm"] / bpm) - round(math.log2(candidate["bpm"] / bpm))) <= math.log2(1.04)
                for candidate in candidates
            )
            checks.append({"name": f"tempo_family_{bpm}", "passed": family_match})
        tone = extracted["sustained_tone"]
        checks.append({
            "name": "sustained_tone_abstains",
            "passed": tone["activity"]["values"].get("onset_count") == 0 and tone["pulse"]["status"] != "VALID",
        })
        noise = extracted["stationary_noise"]
        checks.append({"name": "stationary_noise_pulse_not_valid", "passed": noise["pulse"]["status"] != "VALID"})
        sparse = extracted["sparse_100"]["activity"]["values"]["onset_rate_hz"]
        dense = extracted["dense_100"]["activity"]["values"]["onset_rate_hz"]
        checks.append({"name": "dense_onset_rate", "passed": dense >= 1.5 * sparse, "sparse": sparse, "dense": dense})
        reference = fixtures["click_120"]
        gain_results = []
        for gain_db in (-6, 6):
            path = root / f"gain_{gain_db}.wav"
            sf.write(path, reference * (10 ** (gain_db / 20)), 22050, subtype="FLOAT")
            gain_results.append(extract_track(
                path, file_sha256(path), config.extraction,
                environment_sha256, implementation_sha256,
                config.execution.loudness_timeout_seconds,
            ).as_dict())
        base = extracted["click_120"]
        base_rate = base["activity"]["values"]["onset_rate_hz"]
        checks.append({
            "name": "gain_invariant_onset_rate",
            "passed": all(abs(row["activity"]["values"]["onset_rate_hz"] - base_rate) <= max(0.05, 0.05 * base_rate) for row in gain_results),
        })
    return {
        "schema_version": "stage5f1-synthetic-validation-v1",
        "status": "PASSED" if all(check["passed"] for check in checks) else "FAILED",
        "checks": checks,
        "fixture_results": rows,
    }


def validate_golden(track_rows: list[dict[str, Any]], source_manifest: list[dict[str, Any]]) -> dict[str, Any]:
    """Objective frozen real-audio smoke set; no invented perceptual annotations."""
    chosen_ids = sorted(row["spotify_track_id"] for row in source_manifest)[:12]
    by_id = {row["spotify_track_id"]: row for row in track_rows}
    checks = []
    for track_id in chosen_ids:
        row = by_id[track_id]
        duration = row.get("duration_seconds") or 0
        profiles = row.get("temporal_profiles", [])
        covered = max((item["end_seconds"] for item in profiles), default=0)
        checks.append({
            "spotify_track_id": track_id,
            "source_sha256": row["source_sha256"],
            "passed": row["status"] in {"SUCCESS", "PARTIAL"} and row["source_level"]["status"] != "UNAVAILABLE" and abs(covered - duration) <= 0.1,
            "status": row["status"],
            "duration_seconds": duration,
            "profile_coverage_seconds": covered,
        })
    return {
        "schema_version": "stage5f1-objective-golden-validation-v1",
        "selection_rule": "first 12 original100 Spotify IDs ascending, frozen before rating analysis",
        "perceptual_annotation_status": "NOT_PERFORMED_NO_CLAIM",
        "status": "PASSED" if len(checks) == 12 and all(row["passed"] for row in checks) else "FAILED",
        "checks": checks,
        "limitation": "This validates real retained decoding, source identity, family output, and full-duration profiles. It does not invent auditory BPM/arousal annotations.",
    }
