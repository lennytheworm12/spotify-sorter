"""Frozen Stage 5F.1 energy/motion configuration and canonical identities."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from dataclasses import asdict, dataclass, field, fields
from typing import Any


SCHEMA_VERSION = "stage5f1-energy-motion-config-v2"
EXTRACTOR_ID = "FULL_TRACK_ENERGY_MOTION_LIBROSA_FFMPEG_V1"
EXTRACTOR_VERSION = "1.0.0"
ALGORITHM_SPEC_VERSION = "stage5f1-energy-motion-algorithm-v2"


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class ExtractionConfig:
    sample_rate_hz: int = 22050
    hop_length: int = 256
    n_fft: int = 2048
    win_length: int = 2048
    window: str = "hann"
    center: bool = True
    pad_mode: str = "constant"
    maximum_duration_seconds: float = 1800.0
    minimum_active_seconds: float = 10.0
    minimum_pulse_active_seconds: float = 20.0
    minimum_sample_rate_hz: int = 8000
    maximum_sample_rate_hz: int = 192000
    maximum_channels: int = 2
    active_reference_percentile: float = 95.0
    active_db_below_reference: float = 40.0
    absolute_silence_dbfs: float = -80.0
    profile_window_seconds: float = 10.0
    profile_minimum_active_seconds: float = 2.0
    mel_bands: int = 128
    mel_fmin_hz: float = 30.0
    mel_fmax_hz: float = 10000.0
    onset_lag_frames: int = 1
    onset_log_top_db: float = 80.0
    minimum_raw_onset_strength: float = 0.5
    onset_max_size: int = 1
    onset_peak_delta: float = 0.07
    onset_peak_pre_max_frames: int = 3
    onset_peak_post_max_frames: int = 3
    onset_peak_pre_avg_frames: int = 9
    onset_peak_post_avg_frames: int = 9
    onset_peak_wait_frames: int = 3
    hpss_kernel_size: tuple[int, int] = (31, 31)
    hpss_power: float = 2.0
    hpss_margin: tuple[float, float] = (2.0, 2.0)
    tempogram_win_length: int = 768
    minimum_tempo_bpm: float = 30.0
    maximum_tempo_bpm: float = 300.0
    candidate_count: int = 5
    candidate_nms_octaves: float = 0.08
    tempo_match_fraction: float = 0.04
    candidate_support_ratio: float = 0.50
    metrical_factors: tuple[float, ...] = (0.5, 1.0, 2.0, 4.0)
    pulse_reliability_threshold: float = 0.55
    exact_tempo_certainty_threshold: float = 0.60
    loudness_backend: str = "ffmpeg_ebur128_original_channels"
    loudness_dualmono: bool = False
    normalization_mode: str = "integrated_lufs_linear_gain"
    normalization_target_lufs: float = -23.0
    maximum_absolute_normalization_gain_db: float = 20.0
    raw_source_loudness_in_similarity: bool = False


@dataclass(frozen=True)
class ComparisonConfig:
    reference_corpus: str = "original100"
    minimum_reference_values: int = 30
    scaler_clip_z: float = 4.0
    iqr_minimum: float = 1e-6
    exact_sigma_octaves: float = 0.15
    family_sigma_octaves: float = 0.10
    minimum_common_features: int = 2
    minimum_common_weight_fraction: float = 0.75
    production_activation: bool = False


@dataclass(frozen=True)
class EvaluationConfig:
    seed: int = 20260905
    bootstrap_replicates: int = 2000
    high_base_quantile: float = 0.75
    low_rating_max: int = 2
    high_rating_min: int = 4
    minimum_slice_pairs_per_group: int = 20
    minimum_slice_unique_tracks: int = 20
    minimum_slice_unique_artists: int = 10
    minimum_primary_mismatch_difference: float = 0.05
    minimum_core_measurement_coverage: float = 0.95
    minimum_pulse_valid_fraction: float = 0.60


@dataclass(frozen=True)
class ExecutionConfig:
    workers: int = 1
    per_track_timeout_seconds: int = 900
    loudness_timeout_seconds: int = 180
    worker_memory_limit_gib: int = 12
    retry_failed: bool = False


@dataclass(frozen=True)
class Stage5F1Config:
    schema_version: str = SCHEMA_VERSION
    extractor_id: str = EXTRACTOR_ID
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    comparison: ComparisonConfig = field(default_factory=ComparisonConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.as_dict())


def validate_config(config: Stage5F1Config) -> None:
    e, c, v, x = config.extraction, config.comparison, config.evaluation, config.execution
    if config.schema_version != SCHEMA_VERSION or config.extractor_id != EXTRACTOR_ID:
        raise ValueError("unsupported Stage 5F.1 schema or extractor identity")
    positive = {
        "sample_rate_hz": e.sample_rate_hz,
        "hop_length": e.hop_length,
        "n_fft": e.n_fft,
        "win_length": e.win_length,
        "maximum_duration_seconds": e.maximum_duration_seconds,
        "tempogram_win_length": e.tempogram_win_length,
        "exact_sigma_octaves": c.exact_sigma_octaves,
        "family_sigma_octaves": c.family_sigma_octaves,
        "workers": x.workers,
    }
    if any(not math.isfinite(float(value)) or value <= 0 for value in positive.values()):
        raise ValueError(f"configuration values must be positive and finite: {positive}")
    if e.window != "hann" or e.pad_mode != "constant" or not e.center:
        raise ValueError("v1 requires centered Hann STFT with constant padding")
    if e.win_length > e.n_fft or e.mel_fmax_hz > e.sample_rate_hz / 2:
        raise ValueError("invalid FFT or mel frequency bounds")
    if not e.minimum_tempo_bpm < e.maximum_tempo_bpm:
        raise ValueError("tempo bounds are reversed")
    if e.normalization_mode != "integrated_lufs_linear_gain" or e.raw_source_loudness_in_similarity:
        raise ValueError("v1 requires LUFS linear-gain normalization and excludes source loudness")
    for name, value in {
        "pulse reliability": e.pulse_reliability_threshold,
        "metrical certainty": e.exact_tempo_certainty_threshold,
        "common weight": c.minimum_common_weight_fraction,
        "high quantile": v.high_base_quantile,
        "core coverage": v.minimum_core_measurement_coverage,
        "pulse coverage": v.minimum_pulse_valid_fraction,
    }.items():
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be in [0,1]")
    if tuple(e.metrical_factors) != (0.5, 1.0, 2.0, 4.0):
        raise ValueError("v1 metrical factors are frozen")


def default_config() -> Stage5F1Config:
    config = Stage5F1Config()
    validate_config(config)
    return config


def load_config(path: Path) -> Stage5F1Config:
    document = json.loads(path.read_text())
    expected = {"schema_version", "extractor_id", "extraction", "comparison", "evaluation", "execution"}
    if set(document) != expected:
        raise ValueError(f"unknown or missing top-level config keys: {sorted(set(document) ^ expected)}")
    for name, kind in (("extraction", ExtractionConfig), ("comparison", ComparisonConfig),
                       ("evaluation", EvaluationConfig), ("execution", ExecutionConfig)):
        configured = set(document[name])
        declared = {item.name for item in fields(kind)}
        if configured != declared:
            raise ValueError(f"unknown or missing {name} config keys: {sorted(configured ^ declared)}")
    extraction = dict(document["extraction"])
    for name in ("hpss_kernel_size", "hpss_margin", "metrical_factors"):
        extraction[name] = tuple(extraction[name])
    config = Stage5F1Config(
        schema_version=document["schema_version"],
        extractor_id=document["extractor_id"],
        extraction=ExtractionConfig(**extraction),
        comparison=ComparisonConfig(**document["comparison"]),
        evaluation=EvaluationConfig(**document["evaluation"]),
        execution=ExecutionConfig(**document["execution"]),
    )
    validate_config(config)
    return config
