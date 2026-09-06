"""Validated full-track extraction orchestration for Stage 5F.1."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch

from .audio import load_audio
from .energy_motion_config import (
    ALGORITHM_SPEC_VERSION,
    EXTRACTOR_ID,
    EXTRACTOR_VERSION,
    ExtractionConfig,
    canonical_sha256,
)
from .energy_motion_features import (
    extract_motion,
    normalize_for_motion,
    preliminary_active_seconds,
)
from .energy_motion_loudness import measure_source_level
from .energy_motion_rhythm import extract_rhythm
from .energy_motion_schema import FamilyResult, TrackFeatures


TRACK_SCHEMA_VERSION = "stage5f1-energy-motion-track-v1"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extraction_config_sha256(config: ExtractionConfig) -> str:
    return canonical_sha256(asdict(config))


def algorithm_spec_sha256() -> str:
    return canonical_sha256({"algorithm_spec_version": ALGORITHM_SPEC_VERSION})


def _family(document: dict[str, Any], *, default_status: str = "UNAVAILABLE") -> FamilyResult:
    status = str(document.get("status", default_status))
    reasons = tuple(str(value) for value in document.get("reasons", []))
    values = {key: value for key, value in document.items() if key not in {"status", "reasons"}}
    return FamilyResult(status=status, reasons=reasons, values=values)


def _failure_track(
    *, source_sha256: str, environment_sha256: str, implementation_sha256: str,
    config: ExtractionConfig, code: str, message: str,
) -> TrackFeatures:
    unavailable = FamilyResult("UNAVAILABLE", (code,), {})
    return TrackFeatures(
        schema_version=TRACK_SCHEMA_VERSION,
        extractor_id=EXTRACTOR_ID,
        extractor_version=EXTRACTOR_VERSION,
        algorithm_spec_sha256=algorithm_spec_sha256(),
        implementation_sha256=implementation_sha256,
        extraction_config_sha256=extraction_config_sha256(config),
        environment_sha256=environment_sha256,
        source_sha256=source_sha256,
        duration_seconds=None,
        source_sample_rate_hz=None,
        source_channels=None,
        analysis_sample_rate_hz=config.sample_rate_hz,
        normalization=unavailable,
        status="FAILED",
        warnings=(),
        failure={"stage": "source_or_decode", "code": code, "message": message[:500]},
        source_level=unavailable,
        dynamics=unavailable,
        activity=unavailable,
        percussion=unavailable,
        pulse=unavailable,
        beat=unavailable,
    )


def extract_track(
    path: Path,
    expected_source_sha256: str,
    config: ExtractionConfig,
    environment_sha256: str,
    implementation_sha256: str,
    loudness_timeout_seconds: int = 180,
) -> TrackFeatures:
    if not path.is_file():
        return _failure_track(
            source_sha256=expected_source_sha256, environment_sha256=environment_sha256,
            implementation_sha256=implementation_sha256, config=config,
            code="MISSING_SOURCE", message=f"missing local source: {path.name}",
        )
    observed_sha = file_sha256(path)
    if observed_sha != expected_source_sha256:
        return _failure_track(
            source_sha256=expected_source_sha256, environment_sha256=environment_sha256,
            implementation_sha256=implementation_sha256, config=config,
            code="SOURCE_HASH_MISMATCH", message="retained source SHA-256 did not match frozen manifest",
        )
    try:
        waveform, sample_rate = load_audio(path)
    except Exception as exc:
        return _failure_track(
            source_sha256=expected_source_sha256, environment_sha256=environment_sha256,
            implementation_sha256=implementation_sha256, config=config,
            code="DECODE_ERROR", message=str(exc),
        )
    channels, samples = int(waveform.shape[0]), int(waveform.shape[1])
    duration = samples / sample_rate
    invalid = (
        sample_rate < config.minimum_sample_rate_hz
        or sample_rate > config.maximum_sample_rate_hz
        or channels < 1
        or channels > config.maximum_channels
        or duration > config.maximum_duration_seconds
    )
    if invalid:
        return _failure_track(
            source_sha256=expected_source_sha256, environment_sha256=environment_sha256,
            implementation_sha256=implementation_sha256, config=config,
            code="INVALID_SOURCE_METADATA", message=f"sr={sample_rate}, channels={channels}, duration={duration}",
        )
    warnings: list[str] = []
    eligible_seconds = preliminary_active_seconds(waveform, sample_rate, config)
    try:
        level_values = measure_source_level(waveform, sample_rate, config, loudness_timeout_seconds)
        if duration < 30 or eligible_seconds < 10:
            level_values["loudness_range_lu"] = None
            warnings.append("INSUFFICIENT_LRA_DURATION")
        if level_values["clipped_sample_fraction"] is not None and level_values["clipped_sample_fraction"] > 0.001:
            warnings.append("POSSIBLE_CLIPPING")
        level_status = "VALID" if eligible_seconds >= 10 and (level_values["integrated_loudness_lufs"] or -70) > -69 else "LOW_CONFIDENCE"
        level_reasons = [] if level_status == "VALID" else ["NO_ACTIVE_AUDIO_OR_LOUDNESS_FLOOR"]
        source_level = FamilyResult(level_status, tuple(level_reasons), level_values)
    except Exception as exc:
        source_level = FamilyResult("UNAVAILABLE", ("LOUDNESS_BACKEND_FAILURE",), {"message": str(exc)[:500]})
        level_values = {"integrated_loudness_lufs": None}
    if eligible_seconds < config.minimum_active_seconds:
        normalized = None
        normalization_document = {"status": "UNAVAILABLE", "reasons": ["SOURCE_FLOOR"]}
    else:
        normalized, normalization_document = normalize_for_motion(waveform, level_values, config)
    if normalization_document["status"] != "VALID":
        warnings.extend(normalization_document.get("reasons", []))
    normalization = _family(normalization_document)
    unavailable = FamilyResult("UNAVAILABLE", tuple(normalization_document.get("reasons", ["NORMALIZATION_UNAVAILABLE"])), {})
    if normalized is None:
        status = "PARTIAL" if source_level.status != "UNAVAILABLE" else "FAILED"
        return TrackFeatures(
            schema_version=TRACK_SCHEMA_VERSION, extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION, algorithm_spec_sha256=algorithm_spec_sha256(),
            implementation_sha256=implementation_sha256,
            extraction_config_sha256=extraction_config_sha256(config),
            environment_sha256=environment_sha256, source_sha256=expected_source_sha256,
            duration_seconds=duration, source_sample_rate_hz=sample_rate, source_channels=channels,
            analysis_sample_rate_hz=config.sample_rate_hz, normalization=normalization,
            status=status, warnings=tuple(warnings), failure=None,
            source_level=source_level, dynamics=unavailable, activity=unavailable,
            percussion=unavailable, pulse=unavailable, beat=unavailable,
        )
    try:
        motion, evidence = extract_motion(normalized, sample_rate, config)
        if motion["status"] != "VALID":
            reason = tuple(motion.get("reasons", ["MOTION_UNAVAILABLE"]))
            motion_unavailable = FamilyResult("UNAVAILABLE", reason, {
                key: value for key, value in motion.items() if key not in {"status", "reasons"}
            })
            return TrackFeatures(
                schema_version=TRACK_SCHEMA_VERSION, extractor_id=EXTRACTOR_ID,
                extractor_version=EXTRACTOR_VERSION, algorithm_spec_sha256=algorithm_spec_sha256(),
                implementation_sha256=implementation_sha256,
                extraction_config_sha256=extraction_config_sha256(config),
                environment_sha256=environment_sha256, source_sha256=expected_source_sha256,
                duration_seconds=duration, source_sample_rate_hz=sample_rate, source_channels=channels,
                analysis_sample_rate_hz=config.sample_rate_hz, normalization=normalization,
                status="PARTIAL", warnings=tuple(warnings + list(reason)), failure=None,
                source_level=source_level, dynamics=motion_unavailable, activity=motion_unavailable,
                percussion=motion_unavailable, pulse=motion_unavailable, beat=motion_unavailable,
            )
        rhythm = extract_rhythm(evidence, config)
    except Exception as exc:
        unavailable_dsp = FamilyResult("UNAVAILABLE", ("DSP_FAILURE",), {"message": str(exc)[:500]})
        return TrackFeatures(
            schema_version=TRACK_SCHEMA_VERSION, extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION, algorithm_spec_sha256=algorithm_spec_sha256(),
            implementation_sha256=implementation_sha256,
            extraction_config_sha256=extraction_config_sha256(config),
            environment_sha256=environment_sha256, source_sha256=expected_source_sha256,
            duration_seconds=duration, source_sample_rate_hz=sample_rate, source_channels=channels,
            analysis_sample_rate_hz=config.sample_rate_hz, normalization=normalization,
            status="PARTIAL", warnings=tuple(warnings + ["DSP_FAILURE"]),
            failure={"stage": "dsp", "code": "DSP_FAILURE", "message": str(exc)[:500]},
            source_level=source_level, dynamics=unavailable_dsp, activity=unavailable_dsp,
            percussion=unavailable_dsp, pulse=unavailable_dsp, beat=unavailable_dsp,
        )
    family_documents = [motion["activity"], motion["percussion"], motion["dynamics"], rhythm["pulse"], rhythm["beat"]]
    status = "SUCCESS" if all(doc["status"] != "UNAVAILABLE" for doc in family_documents) else "PARTIAL"
    if motion["mono_energy_ratio"] < 0.01:
        warnings.append("MONO_CANCELLATION")
    if normalization.values.get("normalization_gain_db") is not None and abs(normalization.values["normalization_gain_db"]) > config.maximum_absolute_normalization_gain_db:
        warnings.append("EXTREME_NORMALIZATION_GAIN")
    return TrackFeatures(
        schema_version=TRACK_SCHEMA_VERSION, extractor_id=EXTRACTOR_ID,
        extractor_version=EXTRACTOR_VERSION, algorithm_spec_sha256=algorithm_spec_sha256(),
        implementation_sha256=implementation_sha256,
        extraction_config_sha256=extraction_config_sha256(config),
        environment_sha256=environment_sha256, source_sha256=expected_source_sha256,
        duration_seconds=duration, source_sample_rate_hz=sample_rate, source_channels=channels,
        analysis_sample_rate_hz=config.sample_rate_hz, normalization=normalization,
        status=status, warnings=tuple(warnings), failure=None, source_level=source_level,
        dynamics=_family(motion["dynamics"]), activity=_family(motion["activity"]),
        percussion=_family(motion["percussion"]), pulse=_family(rhythm["pulse"]),
        beat=_family(rhythm["beat"]), metrical_profiles=tuple(rhythm["metrical_profiles"]),
        temporal_profiles=tuple(motion["temporal_profiles"]),
    )
