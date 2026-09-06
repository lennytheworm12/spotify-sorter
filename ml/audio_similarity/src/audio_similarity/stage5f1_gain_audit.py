"""Mandatory gain-only distribution audit for the frozen original100."""

from __future__ import annotations

import json
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .audio import load_audio
from .energy_motion_config import Stage5F1Config
from .energy_motion_features import extract_motion, normalize_for_motion, preliminary_active_seconds
from .energy_motion_loudness import measure_source_level
from .energy_motion_rhythm import extract_rhythm
from .energy_motion_similarity import compare_tracks, derived_track_features
from .stage5b1b_artifacts import atomic_json


GAINS_DB = (-12.0, -6.0, 6.0)
AUDIT_WORKERS = 4


def _variant(waveform: torch.Tensor, sample_rate: int, gain_db: float, source_sha: str,
             config: Stage5F1Config, environment_sha: str) -> dict[str, Any]:
    scaled = waveform * (10.0 ** (gain_db / 20.0))
    eligible_seconds = preliminary_active_seconds(scaled, sample_rate, config.extraction)
    level = measure_source_level(scaled, sample_rate, config.extraction, config.execution.loudness_timeout_seconds)
    normalized, normalization = normalize_for_motion(scaled, level, config.extraction)
    if normalized is None or eligible_seconds < config.extraction.minimum_active_seconds:
        return {"source_sha256": source_sha, "status": "EXCLUDED", "source_level": {"status": "LOW_CONFIDENCE", "values": level},
                "normalization": normalization, "exclusion_reason": "SOURCE_FLOOR_OR_NORMALIZATION_GATE"}
    motion, evidence = extract_motion(normalized, sample_rate, config.extraction)
    if motion["status"] != "VALID":
        return {"source_sha256": source_sha, "status": "EXCLUDED", "source_level": {"status": "VALID", "values": level},
                "normalization": normalization, "exclusion_reason": "MOTION_UNAVAILABLE"}
    rhythm = extract_rhythm(evidence, config.extraction)
    return {
        "source_sha256": source_sha, "status": "VALID",
        "source_level": {"status": "VALID", "reasons": [], "values": level},
        "normalization": {"status": normalization["status"], "reasons": normalization.get("reasons", []),
                          "values": {k: v for k, v in normalization.items() if k not in {"status", "reasons"}}},
        "activity": {"status": motion["activity"]["status"], "reasons": motion["activity"].get("reasons", []),
                     "values": {k: v for k, v in motion["activity"].items() if k not in {"status", "reasons"}}},
        "percussion": {"status": motion["percussion"]["status"], "reasons": motion["percussion"].get("reasons", []),
                       "values": {k: v for k, v in motion["percussion"].items() if k not in {"status", "reasons"}}},
        "dynamics": {"status": motion["dynamics"]["status"], "reasons": motion["dynamics"].get("reasons", []),
                     "values": {k: v for k, v in motion["dynamics"].items() if k not in {"status", "reasons"}}},
        "pulse": {"status": rhythm["pulse"]["status"], "reasons": rhythm["pulse"].get("reasons", []),
                  "values": {k: v for k, v in rhythm["pulse"].items() if k not in {"status", "reasons"}}},
        "beat": {"status": rhythm["beat"]["status"], "reasons": rhythm["beat"].get("reasons", []),
                 "values": {k: v for k, v in rhythm["beat"].items() if k not in {"status", "reasons"}}},
        "metrical_profiles": rhythm["metrical_profiles"],
    }


def _family_value(track: dict[str, Any], family: str, name: str) -> float | None:
    value = track.get(family, {}).get("values", {}).get(name)
    return float(value) if isinstance(value, (int, float)) and math.isfinite(float(value)) else None


def _pulse_stable(reference: dict[str, Any], variant: dict[str, Any]) -> tuple[bool, str]:
    left_status, right_status = reference["pulse"]["status"], variant["pulse"]["status"]
    if left_status != "VALID" and right_status != "VALID":
        return True, "BOTH_ABSTAIN"
    if left_status != right_status:
        return False, "STATUS_CHANGED"
    left = _family_value(reference, "pulse", "primary_bpm")
    right = _family_value(variant, "pulse", "primary_bpm")
    if not left or not right:
        return False, "MISSING_BPM"
    distance = abs(math.log2(left / right) - round(math.log2(left / right)))
    return distance <= math.log2(1.04), "FAMILY_MATCH" if distance <= math.log2(1.04) else "FAMILY_CHANGED"


def _audit_track(membership: dict[str, Any], reference: dict[str, Any], scaler: dict[str, Any],
                 config: Stage5F1Config, environment_sha: str, cache_dir_string: str) -> list[dict[str, Any]]:
        cache_dir = Path(cache_dir_string)
        records: list[dict[str, Any]] = []
        track_id, source_sha = membership["spotify_track_id"], membership["source_sha256"]
        waveform, sample_rate = load_audio(Path(membership["retained_source_path"]))
        peak = float(torch.max(torch.abs(waveform)).item())
        for gain_db in GAINS_DB:
            if gain_db > 0 and peak * (10.0 ** (gain_db / 20.0)) > 0.999:
                records.append({"spotify_track_id": track_id, "gain_db": gain_db, "status": "SKIPPED_WOULD_CLIP"})
                continue
            cache_path = cache_dir / f"{source_sha}_{gain_db:+.0f}.json"
            if cache_path.is_file():
                variant = json.loads(cache_path.read_text())
            else:
                variant = _variant(waveform, sample_rate, gain_db, f"gain-audit:{source_sha}:{gain_db:+.0f}", config, environment_sha)
                atomic_json(cache_path, variant)
            if variant["status"] != "VALID":
                records.append({"spotify_track_id": track_id, "gain_db": gain_db, "status": "EXCLUDED",
                                "reason": variant.get("exclusion_reason")})
                continue
            pair = compare_tracks(track_id, track_id + "@gain", reference, variant, scaler, config.comparison).as_dict()
            ref_derived, var_derived = derived_track_features(reference, scaler), derived_track_features(variant, scaler)
            checks: dict[str, bool] = {}
            deviations: dict[str, float | None] = {}
            ref_lufs = _family_value(reference, "source_level", "integrated_loudness_lufs")
            var_lufs = _family_value(variant, "source_level", "integrated_loudness_lufs")
            deviations["lufs_shift_error"] = abs((var_lufs - ref_lufs) - gain_db) if ref_lufs is not None and var_lufs is not None else None
            checks["lufs_shift"] = deviations["lufs_shift_error"] is not None and deviations["lufs_shift_error"] <= 0.2 + 1e-9
            similarity = pair["components"]["activity"]["similarity"]
            deviations["activity_similarity"] = similarity
            checks["activity_similarity"] = similarity is not None and similarity >= 0.98
            for family, name in (("activity", "onset_rate_hz"), ("percussion", "percussive_onset_rate_hz")):
                left, right = _family_value(reference, family, name), _family_value(variant, family, name)
                diff = abs(left - right) if left is not None and right is not None else None
                deviations[name] = diff
                checks[name] = diff is not None and diff <= max(0.05, 0.05 * left) + 1e-12
            left_flux, right_flux = _family_value(reference, "activity", "spectral_flux_q90"), _family_value(variant, "activity", "spectral_flux_q90")
            deviations["spectral_flux_q90"] = abs(left_flux - right_flux) if left_flux is not None and right_flux is not None else None
            checks["spectral_flux_q90"] = deviations["spectral_flux_q90"] is not None and deviations["spectral_flux_q90"] <= 0.01
            for name in ("dynamic_range_db", "dynamic_complexity_db", "dynamic_step_db"):
                left, right = _family_value(reference, "dynamics", name), _family_value(variant, "dynamics", name)
                diff = abs(left - right) if left is not None and right is not None else None
                deviations[name] = diff
                checks[name] = diff is not None and diff <= 0.2
            left_arousal, right_arousal = ref_derived["arousal_proxy_0_1"], var_derived["arousal_proxy_0_1"]
            deviations["arousal_proxy"] = abs(left_arousal - right_arousal) if left_arousal is not None and right_arousal is not None else None
            checks["arousal_proxy"] = deviations["arousal_proxy"] is not None and deviations["arousal_proxy"] <= 0.03
            pulse_ok, pulse_reason = _pulse_stable(reference, variant)
            checks["pulse_family"] = pulse_ok
            records.append({"spotify_track_id": track_id, "gain_db": gain_db, "status": "PASSED" if all(checks.values()) else "FAILED",
                            "checks": checks, "deviations": deviations, "pulse_reason": pulse_reason})
        return records


def run_gain_audit(root: Path, report: Path, tracks: list[dict[str, Any]], references: dict[str, dict[str, Any]],
                   scaler: dict[str, Any], config: Stage5F1Config, environment_sha: str) -> dict[str, Any]:
    cache_dir = root / ".research_audio/stage5f1_energy_motion/gain_audit" / report.name
    cache_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=AUDIT_WORKERS) as pool:
        futures = [pool.submit(_audit_track, membership, references[membership["spotify_track_id"]], scaler,
                               config, environment_sha, str(cache_dir)) for membership in tracks]
        for track_index, future in enumerate(as_completed(futures), 1):
            records.extend(future.result())
            print(json.dumps({"gain_audit_tracks_processed": track_index, "total": len(tracks)}), flush=True)
    records.sort(key=lambda record: (record["spotify_track_id"], record["gain_db"]))
    eligible = [record for record in records if record["status"] in {"PASSED", "FAILED"}]
    eligible_track_ids = sorted({record["spotify_track_id"] for record in eligible})
    eligible_tracks = len(eligible_track_ids)
    passed = sum(record["status"] == "PASSED" for record in eligible)
    passed_tracks = sum(all(record["status"] == "PASSED" for record in eligible if record["spotify_track_id"] == track_id)
                        for track_id in eligible_track_ids)
    failures_by_gain = {str(gain): sum(record["status"] == "FAILED" and record["gain_db"] == gain for record in eligible) for gain in GAINS_DB}
    eligible_by_gain = {str(gain): sum(record["gain_db"] == gain for record in eligible) for gain in GAINS_DB}
    failure_rates = {key: failures_by_gain[key] / count if count else None for key, count in eligible_by_gain.items()}
    observed_rates = [rate for rate in failure_rates.values() if rate is not None]
    no_direction_bias = not observed_rates or max(observed_rates) - min(observed_rates) <= 0.05
    numeric_keys = sorted({key for record in eligible for key, value in record["deviations"].items() if value is not None})
    summaries = {key: {"max": max(values), "q95": float(np.quantile(values, .95)), "median": float(np.quantile(values, .5))}
                 for key in numeric_keys if (values := [record["deviations"][key] for record in eligible if record["deviations"].get(key) is not None])}
    pass_fraction = passed_tracks / eligible_tracks if eligible_tracks else 0.0
    result = {
        "schema_version": "stage5f1-distribution-gain-audit-v1", "gains_db": list(GAINS_DB),
        "audit_workers": AUDIT_WORKERS,
        "track_count": len(tracks), "eligible_track_count": eligible_tracks, "eligible_variant_count": len(eligible),
        "passed_variant_count": passed, "passed_track_count": passed_tracks, "pass_fraction": pass_fraction,
        "gate_passed": eligible_tracks >= 80 and pass_fraction >= 0.95 and no_direction_bias,
        "systematic_direction_check": {"failures_by_gain": failures_by_gain, "eligible_by_gain": eligible_by_gain,
                                       "failure_rates": failure_rates, "passed": no_direction_bias},
        "deviation_summaries": summaries, "records": records,
    }
    return result
