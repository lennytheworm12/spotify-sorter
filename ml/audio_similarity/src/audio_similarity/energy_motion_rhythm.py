"""Supporting rhythm extraction for the Stage 5F.1 energy/motion sensor."""

from __future__ import annotations

import math
from typing import Any

import librosa
import numpy as np
import scipy.signal

from .energy_motion_config import ExtractionConfig
from .energy_motion_features import EPS, MotionEvidence, quantile


def _round_octave(value: float) -> int:
    """Nearest integer with exact half ties choosing the smaller integer."""
    lower = math.floor(value)
    return lower if value - lower <= 0.5 else lower + 1


def _interp_lag(values: np.ndarray, lag: float) -> float | None:
    if lag < 1 or lag > values.shape[0] - 1:
        return None
    low = int(math.floor(lag))
    high = int(math.ceil(lag))
    if low == high:
        return float(values[low])
    weight = lag - low
    return float((1 - weight) * values[low] + weight * values[high])


def _local_maxima(values: np.ndarray) -> list[int]:
    indices: list[int] = []
    for index, value in enumerate(values):
        left = values[index - 1] if index else -np.inf
        right = values[index + 1] if index + 1 < values.size else -np.inf
        if value >= left and value >= right and value > 0:
            indices.append(index)
    return indices


def extract_rhythm(evidence: MotionEvidence | None, config: ExtractionConfig) -> dict[str, Any]:
    if evidence is None:
        return {
            "pulse": {"status": "UNAVAILABLE", "reasons": ["MOTION_UNAVAILABLE"]},
            "beat": {"status": "UNAVAILABLE", "reasons": ["MOTION_UNAVAILABLE"]},
            "metrical_profiles": [],
        }
    frame_count = evidence.active.size
    window = scipy.signal.windows.hann(config.tempogram_win_length, sym=False)
    window /= np.sum(window)
    centered = scipy.signal.convolve(
        evidence.onset_normalized, window, mode="same", method="direct"
    )
    detrended = evidence.onset_normalized - centered
    tempogram = librosa.feature.tempogram(
        onset_envelope=detrended,
        sr=config.sample_rate_hz,
        hop_length=config.hop_length,
        win_length=config.tempogram_win_length,
        center=True,
        window="hann",
        norm=None,
    )[:, :frame_count]
    zero = tempogram[0]
    valid_columns = zero > EPS
    rho = np.zeros_like(tempogram, dtype=np.float32)
    np.divide(tempogram, zero, where=valid_columns, out=rho)
    rho = np.maximum(rho, 0)
    half = config.tempogram_win_length // 2
    full_context = np.zeros(frame_count, dtype=bool)
    if frame_count > 2 * half:
        full_context[half : frame_count - half] = True
    active_fraction = scipy.signal.convolve(
        evidence.active.astype(np.float64),
        np.ones(config.tempogram_win_length) / config.tempogram_win_length,
        mode="same",
        method="direct",
    )
    eligible = full_context & valid_columns & (active_fraction >= 0.50)
    frequencies = librosa.tempo_frequencies(
        config.tempogram_win_length,
        sr=config.sample_rate_hz,
        hop_length=config.hop_length,
    )
    allowed = np.isfinite(frequencies) & (frequencies >= config.minimum_tempo_bpm) & (frequencies <= config.maximum_tempo_bpm)
    allowed_indices = np.flatnonzero(allowed)
    eligible_indices = np.flatnonzero(eligible)
    reasons: list[str] = []
    if not eligible_indices.size:
        reasons.append("NO_ELIGIBLE_TEMPO_COLUMNS")
        return {
            "pulse": {"status": "LOW_CONFIDENCE", "reasons": reasons, "pulse_reliability": 0.0},
            "beat": {"status": "UNAVAILABLE", "reasons": reasons},
            "metrical_profiles": [],
        }
    allowed_values = rho[np.ix_(allowed_indices, eligible_indices)]
    local_argmax = np.argmax(allowed_values, axis=0)
    local_strength = allowed_values[local_argmax, np.arange(eligible_indices.size)]
    local_bpms = frequencies[allowed_indices[local_argmax]]
    local_accepted = local_strength >= 0.15
    global_strength = np.quantile(allowed_values, 0.75, axis=1, method="linear")
    candidates: list[dict[str, Any]] = []
    for index in sorted(
        _local_maxima(global_strength),
        key=lambda i: (-float(global_strength[i]), -float(frequencies[allowed_indices[i]])),
    ):
        bpm = float(frequencies[allowed_indices[index]])
        if any(abs(math.log2(bpm / row["bpm"])) < config.candidate_nms_octaves for row in candidates):
            continue
        candidates.append({"bpm": bpm, "raw_strength": float(global_strength[index])})
        if len(candidates) == config.candidate_count:
            break
    if not candidates:
        candidates = [{
            "bpm": float(frequencies[allowed_indices[int(np.argmax(global_strength))]]),
            "raw_strength": float(np.max(global_strength)),
        }]
    primary = candidates[0]
    aggregate_all = np.quantile(rho[:, eligible_indices], 0.75, axis=1, method="linear")
    for relation, factor in (("HALF", 0.5), ("DOUBLE", 2.0)):
        target = primary["bpm"] * factor
        if not config.minimum_tempo_bpm <= target <= config.maximum_tempo_bpm:
            reasons.append("OCTAVE_PARTNER_OUT_OF_RANGE")
            continue
        lag = 60 * config.sample_rate_hz / (config.hop_length * target)
        strength = _interp_lag(aggregate_all, lag)
        if strength is None:
            continue
        if not any(abs(math.log2(target / row["bpm"])) < config.candidate_nms_octaves for row in candidates):
            candidates.append({"bpm": target, "raw_strength": strength})
    strongest = max(row["raw_strength"] for row in candidates)
    total = sum(max(row["raw_strength"], 0) for row in candidates)
    for row in candidates:
        ratio = math.log2(row["bpm"] / primary["bpm"])
        row["relation_to_primary"] = "PRIMARY" if row is primary else (
            "HALF" if abs(ratio + 1) <= math.log2(1 + config.tempo_match_fraction) else
            "DOUBLE" if abs(ratio - 1) <= math.log2(1 + config.tempo_match_fraction) else "OTHER"
        )
        row["normalized_strength"] = row["raw_strength"] / total if total > EPS else 0.0
        row["support_ratio"] = row["raw_strength"] / strongest if strongest > EPS else 0.0
        row["supported"] = row["raw_strength"] >= 0.15 and row["support_ratio"] >= config.candidate_support_ratio
    candidates.sort(key=lambda row: (-row["raw_strength"], -row["bpm"]))
    accepted_bpms = local_bpms[local_accepted]
    if accepted_bpms.size:
        log_bpms = np.log2(accepted_bpms)
        offsets = np.asarray([_round_octave(float(x - math.log2(primary["bpm"]))) for x in log_bpms])
        aligned = log_bpms - offsets
        center = quantile(aligned, 0.5)
        family_mad = float(np.median(np.abs(aligned - center)))
        family_iqr = quantile(aligned, 0.75) - quantile(aligned, 0.25)
        raw_iqr = quantile(log_bpms, 0.75) - quantile(log_bpms, 0.25)
        raw_mad = float(np.median(np.abs(log_bpms - np.median(log_bpms))))
        octave_switch_fraction = float(np.mean(offsets != 0))
    else:
        family_mad = family_iqr = raw_iqr = raw_mad = None
        octave_switch_fraction = None
    other_strength = max((row["raw_strength"] for row in candidates if row is not primary), default=0.0)
    octave_strength = max((row["raw_strength"] for row in candidates if row["relation_to_primary"] in {"HALF", "DOUBLE"}), default=0.0)
    metrical_certainty = float(np.clip(1 - other_strength / max(primary["raw_strength"], EPS), 0, 1))
    octave_ambiguity = float(np.clip(octave_strength / max(primary["raw_strength"], EPS), 0, 1))
    periodic_strength = float(np.median(local_strength))
    strength_score = float(np.clip((periodic_strength - 0.10) / 0.50, 0, 1))
    coverage_score = float(np.mean(local_accepted))
    stability_score = math.exp(-(family_mad or 0) / 0.10) if family_mad is not None else 0.0
    duration_score = float(np.clip(evidence.active_duration_seconds / 30, 0, 1))
    reliability = (strength_score * coverage_score * stability_score * duration_score) ** 0.25
    eligible_seconds = float(np.sum(evidence.cell_durations[eligible]))
    if evidence.active_duration_seconds < config.minimum_pulse_active_seconds:
        reasons.append("INSUFFICIENT_PULSE_ACTIVE_AUDIO")
    if eligible_seconds < 10:
        reasons.append("INSUFFICIENT_ELIGIBLE_TEMPO_DURATION")
    if evidence.onset_frames.size < 8:
        reasons.append("INSUFFICIENT_ONSETS")
    if not accepted_bpms.size:
        reasons.append("NO_ACCEPTED_LOCAL_TEMPOS")
    if reasons and any(reason.startswith(("INSUFFICIENT", "NO_ACCEPTED")) for reason in reasons):
        reliability = 0.0
    pulse_status = "VALID" if reliability >= config.pulse_reliability_threshold else "LOW_CONFIDENCE"
    pulse = {
        "status": pulse_status,
        "reasons": sorted(set(reasons)),
        "primary_bpm": primary["bpm"],
        "global_tempo_bpm": primary["bpm"],
        "tempo_candidates": candidates,
        "pulse_reliability": float(reliability),
        "periodic_strength": periodic_strength,
        "periodic_frame_fraction": coverage_score,
        "strength_score": strength_score,
        "coverage_score": coverage_score,
        "stability_score": stability_score,
        "duration_score": duration_score,
        "metrical_certainty": metrical_certainty,
        "octave_ambiguity": octave_ambiguity,
        "exact_tempo_eligible": bool(
            pulse_status == "VALID"
            and metrical_certainty >= config.exact_tempo_certainty_threshold
            and "OCTAVE_PARTNER_OUT_OF_RANGE" not in reasons
        ),
        "eligible_tempo_duration_seconds": eligible_seconds,
        "local_tempo_q10_bpm": quantile(accepted_bpms, 0.10),
        "local_tempo_q25_bpm": quantile(accepted_bpms, 0.25),
        "local_tempo_q50_bpm": quantile(accepted_bpms, 0.50),
        "local_tempo_q75_bpm": quantile(accepted_bpms, 0.75),
        "local_tempo_q90_bpm": quantile(accepted_bpms, 0.90),
        "local_tempo_iqr_octaves": raw_iqr,
        "local_tempo_mad_octaves": raw_mad,
        "local_family_iqr_octaves": family_iqr,
        "local_family_mad_octaves": family_mad,
        "octave_switch_fraction": octave_switch_fraction,
        "tempo_change_warning": bool(family_iqr is not None and family_iqr > 0.10),
    }
    beat = _beat_diagnostics(evidence, primary["bpm"], reliability, pulse_status, config)
    profiles = _metrical_profiles(rho, eligible_indices, candidates, config)
    return {"pulse": pulse, "beat": beat, "metrical_profiles": profiles}


def _beat_diagnostics(
    evidence: MotionEvidence, primary_bpm: float, reliability: float,
    pulse_status: str, config: ExtractionConfig,
) -> dict[str, Any]:
    _, frames = librosa.beat.beat_track(
        onset_envelope=evidence.onset_normalized,
        sr=config.sample_rate_hz,
        hop_length=config.hop_length,
        bpm=primary_bpm,
        tightness=100,
        trim=True,
        units="frames",
        sparse=True,
    )
    frames = np.asarray(frames, dtype=int)
    frames = frames[(frames < evidence.active.size) & evidence.active[np.minimum(frames, evidence.active.size - 1)]]
    intervals: list[float] = []
    for left, right in zip(frames[:-1], frames[1:]):
        support = float(np.sum(evidence.cell_durations[left : right + 1] * evidence.active[left : right + 1]))
        total = float(np.sum(evidence.cell_durations[left : right + 1]))
        if total > 0 and support / total >= 0.80:
            intervals.append((right - left) * config.hop_length / config.sample_rate_hz)
    ibi = np.asarray(intervals)
    valid = frames.size >= 8 and ibi.size >= 5
    if valid:
        median_ibi = float(np.median(ibi))
        cv = 1.4826 * float(np.median(np.abs(ibi - median_ibi))) / max(median_ibi, EPS)
        strengths = [
            float(np.max(evidence.onset_normalized[max(0, frame - 2) : min(evidence.active.size, frame + 3)]))
            for frame in frames
        ]
        onbeat = float(np.median(strengths))
        background = float(np.median(evidence.onset_normalized[evidence.active]))
        support = float(np.clip((onbeat - background) / max(1 - background, EPS), 0, 1))
    else:
        median_ibi = cv = support = None
    status = "VALID" if valid and pulse_status == "VALID" else "LOW_CONFIDENCE"
    return {
        "status": status,
        "reasons": [] if status == "VALID" else ["INSUFFICIENT_OR_LOW_CONFIDENCE_BEAT_EVIDENCE"],
        "beat_count": int(frames.size),
        "median_interbeat_interval_seconds": median_ibi,
        "beat_interval_robust_cv": cv,
        "beat_regularity_proxy": math.exp(-cv / 0.10) if cv is not None else None,
        "beat_onset_support": support,
        "beat_strength_proxy": reliability * support if support is not None and status == "VALID" else None,
        "first_beat_seconds": float(frames[0] * config.hop_length / config.sample_rate_hz) if frames.size else None,
        "last_beat_seconds": float(frames[-1] * config.hop_length / config.sample_rate_hz) if frames.size else None,
    }


def _metrical_profiles(
    rho: np.ndarray, eligible_indices: np.ndarray,
    candidates: list[dict[str, Any]], config: ExtractionConfig,
) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for candidate in candidates:
        if not candidate["supported"]:
            continue
        bpm = candidate["bpm"]
        fundamental_lag = 60 * config.sample_rate_hz / (config.hop_length * bpm)
        values: dict[str, float | None] = {}
        ratios: list[list[float]] = [[] for _ in config.metrical_factors]
        for column in eligible_indices:
            fundamental = _interp_lag(rho[:, column], fundamental_lag)
            if fundamental is None or fundamental < 0.15:
                continue
            for index, factor in enumerate(config.metrical_factors):
                sampled = _interp_lag(rho[:, column], fundamental_lag / factor)
                if sampled is not None:
                    ratios[index].append(float(np.clip(sampled / fundamental, 0, 4)))
        support_frames = max((len(items) for items in ratios), default=0)
        support_seconds = support_frames * config.hop_length / config.sample_rate_hz
        for factor, items in zip(config.metrical_factors, ratios):
            values[str(factor)] = float(np.median(items)) if items and support_seconds >= 5 else None
        profiles.append({
            "bpm": bpm,
            "candidate_strength": candidate["raw_strength"],
            "support_duration_seconds": support_seconds,
            "factors": values,
        })
    return sorted(profiles, key=lambda row: row["bpm"])
