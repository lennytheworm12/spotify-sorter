"""Deterministic full-track energy and motion DSP for Stage 5F.1."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import librosa
import numpy as np
import torch
import torchaudio

from .energy_motion_config import ExtractionConfig


EPS = 1e-12


@dataclass
class MotionEvidence:
    waveform: np.ndarray
    magnitude: np.ndarray
    frame_times: np.ndarray
    cell_durations: np.ndarray
    active: np.ndarray
    rms_dbfs: np.ndarray
    onset_raw: np.ndarray
    onset_normalized: np.ndarray
    onset_frames: np.ndarray
    percussive_onset_frames: np.ndarray
    percussive_magnitude: np.ndarray
    active_duration_seconds: float


def quantile(values: np.ndarray, q: float) -> float | None:
    return float(np.quantile(values, q, method="linear")) if values.size else None


def summarize(values: np.ndarray, prefix: str) -> dict[str, float | None]:
    if not values.size:
        return {f"{prefix}_{name}": None for name in ("mean", "q50", "q90", "iqr")}
    return {
        f"{prefix}_mean": float(np.mean(values, dtype=np.float64)),
        f"{prefix}_q50": quantile(values, 0.50),
        f"{prefix}_q90": quantile(values, 0.90),
        f"{prefix}_iqr": quantile(values, 0.75) - quantile(values, 0.25),
    }


def preliminary_active_seconds(waveform: torch.Tensor, sample_rate: int, config: ExtractionConfig) -> float:
    array = waveform.detach().cpu().numpy().astype(np.float64, copy=False)
    power = np.mean(array * array, axis=0)
    frame_length = max(1, round(config.n_fft * sample_rate / config.sample_rate_hz))
    hop = max(1, round(config.hop_length * sample_rate / config.sample_rate_hz))
    padded = np.pad(power, (frame_length // 2, frame_length // 2), mode="constant")
    frames = librosa.util.frame(padded, frame_length=frame_length, hop_length=hop)
    rms = np.sqrt(np.mean(frames, axis=0, dtype=np.float64))
    db = 20 * np.log10(np.maximum(rms, EPS))
    duration = array.shape[1] / sample_rate
    times = np.arange(db.size, dtype=np.float64) * hop / sample_rate
    cells = np.minimum(hop / sample_rate, np.maximum(0.0, duration - times))
    return float(np.sum(cells[db > config.absolute_silence_dbfs], dtype=np.float64))


def normalize_for_motion(
    waveform: torch.Tensor, source_level: dict[str, float | None], config: ExtractionConfig
) -> tuple[torch.Tensor | None, dict[str, Any]]:
    integrated = source_level.get("integrated_loudness_lufs")
    if integrated is None or not math.isfinite(integrated) or integrated <= -69:
        return None, {"status": "UNAVAILABLE", "reasons": ["LOUDNESS_UNAVAILABLE"]}
    gain_db = config.normalization_target_lufs - integrated
    values: dict[str, Any] = {
        "target_lufs": config.normalization_target_lufs,
        "normalization_gain_db": gain_db,
        "mode": config.normalization_mode,
    }
    if abs(gain_db) > config.maximum_absolute_normalization_gain_db:
        return None, {"status": "UNAVAILABLE", "reasons": ["EXTREME_NORMALIZATION_GAIN"], **values}
    normalized = waveform * (10.0 ** (gain_db / 20.0))
    values["normalized_float_peak"] = float(torch.max(torch.abs(normalized)))
    return normalized, {"status": "VALID", "reasons": [], **values}


def mono_resample(waveform: torch.Tensor, sample_rate: int, config: ExtractionConfig) -> tuple[np.ndarray | None, float]:
    original_power = float(torch.mean(waveform.double() ** 2))
    mono = waveform.mean(dim=0)
    mono_power = float(torch.mean(mono.double() ** 2))
    ratio = mono_power / original_power if original_power > 0 else 0.0
    if ratio < 0.01:
        return None, ratio
    if sample_rate != config.sample_rate_hz:
        mono = torchaudio.functional.resample(
            mono, sample_rate, config.sample_rate_hz,
            lowpass_filter_width=6, rolloff=0.99,
            resampling_method="sinc_interp_hann", beta=None,
        )
    return mono.detach().cpu().numpy().astype(np.float32, copy=False), ratio


def _frame_clock(waveform: np.ndarray, config: ExtractionConfig) -> tuple[np.ndarray, ...]:
    duration = waveform.size / config.sample_rate_hz
    magnitude = np.abs(librosa.stft(
        waveform, n_fft=config.n_fft, hop_length=config.hop_length,
        win_length=config.win_length, window=config.window,
        center=config.center, pad_mode=config.pad_mode,
    )).astype(np.float32)
    frame_count = min(magnitude.shape[1], int(math.ceil(duration * config.sample_rate_hz / config.hop_length)))
    magnitude = magnitude[:, :frame_count]
    rms = librosa.feature.rms(
        y=waveform, frame_length=config.n_fft, hop_length=config.hop_length,
        center=config.center, pad_mode=config.pad_mode,
    )[0, :frame_count]
    rms_db = 20 * np.log10(np.maximum(rms, EPS))
    reference = float(np.quantile(rms_db, config.active_reference_percentile / 100, method="linear"))
    active = (rms_db > config.absolute_silence_dbfs) & (rms_db >= reference - config.active_db_below_reference)
    times = np.arange(frame_count, dtype=np.float64) * config.hop_length / config.sample_rate_hz
    cell = np.minimum(config.hop_length / config.sample_rate_hz, np.maximum(0.0, duration - times))
    return magnitude, times, cell, active, rms_db


def _onset_envelope(
    power: np.ndarray, active: np.ndarray, mel_filter: np.ndarray, config: ExtractionConfig
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mel_power = mel_filter @ power
    spectrum = librosa.power_to_db(mel_power, ref=1.0, amin=1e-10, top_db=config.onset_log_top_db)
    raw = librosa.onset.onset_strength(
        S=spectrum, sr=config.sample_rate_hz, hop_length=config.hop_length,
        n_fft=config.n_fft, lag=config.onset_lag_frames,
        max_size=config.onset_max_size, detrend=False, center=True, aggregate=np.mean,
    )[: active.size].astype(np.float32)
    clean = np.where(raw >= config.minimum_raw_onset_strength, raw, 0.0)
    positive = clean[active & (clean > 0)]
    normalized = np.zeros_like(clean)
    if positive.size:
        denominator = float(np.quantile(positive, 0.95, method="linear"))
        normalized = np.clip(clean / max(denominator, EPS), 0, 1)
        normalized[~active] = 0
    frames = librosa.onset.onset_detect(
        onset_envelope=normalized, sr=config.sample_rate_hz, hop_length=config.hop_length,
        normalize=False, backtrack=False, units="frames", sparse=True,
        pre_max=config.onset_peak_pre_max_frames, post_max=config.onset_peak_post_max_frames,
        pre_avg=config.onset_peak_pre_avg_frames, post_avg=config.onset_peak_post_avg_frames,
        wait=config.onset_peak_wait_frames, delta=config.onset_peak_delta,
    )
    frames = frames[(frames < active.size) & active[np.minimum(frames, active.size - 1)]]
    return raw, normalized, frames.astype(np.int64)


def _shape_flux(magnitude: np.ndarray, active: np.ndarray) -> tuple[dict[str, Any], np.ndarray]:
    totals = np.sum(magnitude, axis=0, dtype=np.float64)
    normalized = np.divide(magnitude, totals, where=totals > EPS, out=np.zeros_like(magnitude))
    raw = np.sum(np.maximum(normalized[:, 1:] - normalized[:, :-1], 0), axis=0, dtype=np.float64)
    valid = active[1:] & active[:-1] & (totals[1:] > EPS) & (totals[:-1] > EPS)
    values = raw[valid]
    result = summarize(values, "spectral_flux")
    result["spectral_flux_valid_transition_fraction"] = float(np.mean(valid)) if valid.size else 0.0
    result["spectral_flux_valid_transition_count"] = int(valid.sum())
    return result, np.concatenate(([np.nan], np.where(valid, raw, np.nan)))


def _weighted_energy_ratio(component: np.ndarray, mixture: np.ndarray, active: np.ndarray, cells: np.ndarray) -> float | None:
    weights = cells[active]
    denominator = float(np.sum((mixture[:, active] ** 2) * weights, dtype=np.float64))
    if denominator <= EPS:
        return None
    numerator = float(np.sum((component[:, active] ** 2) * weights, dtype=np.float64))
    return numerator / denominator


def _dynamic_features(waveform: torch.Tensor, sample_rate: int) -> tuple[dict[str, Any], np.ndarray]:
    array = waveform.detach().cpu().numpy().astype(np.float64, copy=False)
    duration = array.shape[1] / sample_rate
    blocks: list[float] = []
    for start in range(0, array.shape[1], sample_rate):
        segment = array[:, start : start + sample_rate]
        if segment.shape[1] < sample_rate / 2:
            continue
        blocks.append(10 * math.log10(max(float(np.mean(segment * segment)), EPS)))
    block_db = np.asarray(blocks)
    if not block_db.size:
        return {"block_count": 0}, block_db
    eligible = (block_db > -80) & (block_db >= np.quantile(block_db, 0.95, method="linear") - 40)
    selected = block_db[eligible]
    result: dict[str, Any] = {"block_count": int(block_db.size), "eligible_block_count": int(selected.size)}
    if selected.size >= 10:
        median = float(np.quantile(selected, 0.5, method="linear"))
        result.update({
            "dynamic_range_db": quantile(selected, 0.9) - quantile(selected, 0.1),
            "dynamic_complexity_db": float(np.mean(np.abs(selected - median))),
        })
    else:
        result.update({"dynamic_range_db": None, "dynamic_complexity_db": None})
    transitions = np.abs(np.diff(block_db))[(eligible[1:] & eligible[:-1])]
    result["eligible_transition_count"] = int(transitions.size)
    result["dynamic_step_db"] = quantile(transitions, 0.5) if transitions.size >= 5 else None
    result["duration_seconds"] = duration
    return result, block_db


def extract_motion(normalized: torch.Tensor, sample_rate: int, config: ExtractionConfig) -> tuple[dict[str, Any], MotionEvidence | None]:
    mono, mono_ratio = mono_resample(normalized, sample_rate, config)
    if mono is None:
        return {"status": "UNAVAILABLE", "reasons": ["MONO_CANCELLATION"], "mono_energy_ratio": mono_ratio}, None
    magnitude, times, cells, active, rms_db = _frame_clock(mono, config)
    active_duration = float(np.sum(cells[active], dtype=np.float64))
    if active_duration < config.minimum_active_seconds:
        return {"status": "UNAVAILABLE", "reasons": ["INSUFFICIENT_ACTIVE_AUDIO"], "active_duration_seconds": active_duration, "mono_energy_ratio": mono_ratio}, None
    power = magnitude * magnitude
    mel_filter = librosa.filters.mel(
        sr=config.sample_rate_hz, n_fft=config.n_fft, n_mels=config.mel_bands,
        fmin=config.mel_fmin_hz, fmax=config.mel_fmax_hz,
        htk=False, norm="slaney", dtype=np.float32,
    )
    onset_raw, onset_norm, onset_frames = _onset_envelope(power, active, mel_filter, config)
    flux_result, flux_series = _shape_flux(magnitude, active)
    harmonic, percussive_magnitude = librosa.decompose.hpss(
        magnitude, kernel_size=config.hpss_kernel_size,
        power=config.hpss_power, mask=False, margin=config.hpss_margin,
    )
    residual = np.maximum(magnitude - harmonic - percussive_magnitude, 0)
    percussive_raw, _percussive_norm, percussive_frames = _onset_envelope(percussive_magnitude * percussive_magnitude, active, mel_filter, config)
    percussive_ratio = _weighted_energy_ratio(percussive_magnitude, magnitude, active, cells)
    residual_ratio = _weighted_energy_ratio(residual, magnitude, active, cells)
    activity = {
        "status": "VALID" if flux_result["spectral_flux_valid_transition_count"] >= 100 else "LOW_CONFIDENCE",
        "reasons": [] if flux_result["spectral_flux_valid_transition_count"] >= 100 else ["INSUFFICIENT_FLUX_TRANSITIONS"],
        "active_duration_seconds": active_duration,
        "active_fraction": active_duration / (mono.size / config.sample_rate_hz),
        "onset_count": int(onset_frames.size),
        "onset_rate_hz": float(onset_frames.size / active_duration),
        **summarize(onset_raw[active], "onset_strength"),
        **flux_result,
    }
    percussion_status = "LOW_CONFIDENCE" if residual_ratio is not None and residual_ratio > 0.60 else "VALID"
    percussion_result = {
        "status": percussion_status,
        "reasons": ["HIGH_HPSS_RESIDUAL"] if percussion_status != "VALID" else [],
        "percussive_onset_count": int(percussive_frames.size),
        "percussive_onset_rate_hz": float(percussive_frames.size / active_duration),
        "percussive_energy_ratio": percussive_ratio,
        "hpss_residual_energy_ratio": residual_ratio,
        "percussive_onset_q90": quantile(percussive_raw[active], 0.90),
    }
    dynamic, _ = _dynamic_features(normalized, sample_rate)
    dynamic_valid = all(dynamic.get(key) is not None for key in ("dynamic_range_db", "dynamic_complexity_db", "dynamic_step_db"))
    dynamic.update({"status": "VALID" if dynamic_valid else "LOW_CONFIDENCE", "reasons": [] if dynamic_valid else ["INSUFFICIENT_DYNAMIC_BLOCKS"]})
    profiles = _temporal_profiles(
        mono.size / config.sample_rate_hz, times, cells, active, rms_db,
        onset_frames, percussive_frames, flux_series, percussion_result, config,
    )
    evidence = MotionEvidence(
        waveform=mono, magnitude=magnitude, frame_times=times, cell_durations=cells,
        active=active, rms_dbfs=rms_db, onset_raw=onset_raw,
        onset_normalized=onset_norm, onset_frames=onset_frames,
        percussive_onset_frames=percussive_frames, percussive_magnitude=percussive_magnitude,
        active_duration_seconds=active_duration,
    )
    return {
        "status": "VALID", "reasons": [], "mono_energy_ratio": mono_ratio,
        "activity": activity, "percussion": percussion_result, "dynamics": dynamic,
        "temporal_profiles": profiles,
    }, evidence


def _temporal_profiles(
    duration: float, times: np.ndarray, cells: np.ndarray, active: np.ndarray,
    rms_db: np.ndarray, onset_frames: np.ndarray, percussive_frames: np.ndarray,
    flux: np.ndarray, percussion: dict[str, Any], config: ExtractionConfig,
) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    event_times = times[onset_frames]
    percussive_times = times[percussive_frames]
    for start in np.arange(0, duration, config.profile_window_seconds):
        end = min(duration, start + config.profile_window_seconds)
        overlap = np.maximum(0.0, np.minimum(times + cells, end) - np.maximum(times, start))
        active_seconds = float(np.sum(overlap[active]))
        frames = active & (overlap > 0)
        valid = active_seconds >= config.profile_minimum_active_seconds
        flux_values = flux[frames & np.isfinite(flux)]
        profiles.append({
            "start_seconds": float(start), "end_seconds": float(end),
            "active_duration_seconds": active_seconds,
            "active_fraction": active_seconds / (end - start),
            "status": "VALID" if valid else "UNAVAILABLE",
            "median_rms_dbfs": quantile(rms_db[frames], 0.5) if valid else None,
            "onset_rate_hz": float(np.sum((event_times >= start) & (event_times < end)) / active_seconds) if valid else None,
            "percussive_onset_rate_hz": float(np.sum((percussive_times >= start) & (percussive_times < end)) / active_seconds) if valid else None,
            "spectral_flux_q90": quantile(flux_values, 0.9) if valid else None,
            "percussive_energy_ratio": percussion.get("percussive_energy_ratio") if valid else None,
        })
    return profiles
