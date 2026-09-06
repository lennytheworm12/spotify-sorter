"""Reference scaling and symmetric Stage 5F.1 track comparison."""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, Iterable

import numpy as np

from .energy_motion_config import ComparisonConfig, canonical_sha256
from .energy_motion_schema import PairFeatures


FEATURES: dict[str, tuple[str, str]] = {
    "onset_rate_hz": ("activity", "onset_rate_hz"),
    "percussive_onset_rate_hz": ("percussion", "percussive_onset_rate_hz"),
    "spectral_flux_q90": ("activity", "spectral_flux_q90"),
    "percussive_energy_ratio": ("percussion", "percussive_energy_ratio"),
    "beat_strength_proxy": ("beat", "beat_strength_proxy"),
    "dynamic_range_db": ("dynamics", "dynamic_range_db"),
    "dynamic_complexity_db": ("dynamics", "dynamic_complexity_db"),
    "dynamic_step_db": ("dynamics", "dynamic_step_db"),
    "loudness_range_lu": ("source_level", "loudness_range_lu"),
    "integrated_loudness_lufs": ("source_level", "integrated_loudness_lufs"),
    "local_family_iqr_octaves": ("pulse", "local_family_iqr_octaves"),
    "local_family_mad_octaves": ("pulse", "local_family_mad_octaves"),
    "beat_interval_robust_cv": ("beat", "beat_interval_robust_cv"),
    "pulse_reliability": ("pulse", "pulse_reliability"),
    "beat_onset_support": ("beat", "beat_onset_support"),
}

GROUPS: dict[str, tuple[str, ...]] = {
    "activity": ("onset_rate_hz", "percussive_onset_rate_hz", "spectral_flux_q90"),
    "attack_texture": ("percussive_energy_ratio", "beat_strength_proxy"),
    "dynamics": ("dynamic_range_db", "dynamic_complexity_db", "dynamic_step_db", "loudness_range_lu"),
    "pulse_stability": ("local_family_iqr_octaves", "local_family_mad_octaves", "beat_interval_robust_cv", "pulse_reliability", "beat_onset_support"),
    "felt_pace": ("onset_rate_hz", "percussive_onset_rate_hz", "spectral_flux_q90", "beat_strength_proxy"),
}

LOG1P_FEATURES = {"onset_rate_hz", "percussive_onset_rate_hz", "dynamic_complexity_db", "dynamic_step_db"}


def canonical_pair_id(left: str, right: str) -> str:
    if left == right:
        return f"{left}::{right}"
    return "::".join(sorted((left, right)))


def _family(track: dict[str, Any], name: str) -> dict[str, Any]:
    family = track.get(name, {})
    if "values" in family:
        return family
    return {"status": family.get("status"), "values": {k: v for k, v in family.items() if k not in {"status", "reasons"}}}


def raw_feature(track: dict[str, Any], name: str) -> float | None:
    family_name, field = FEATURES[name]
    family = _family(track, family_name)
    value = family.get("values", {}).get(field)
    if value is None or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None
    if family_name in {"activity", "percussion", "dynamics", "beat", "pulse"} and family.get("status") != "VALID":
        return None
    return float(value)


def _transform(name: str, value: float) -> float:
    return math.log1p(value) if name in LOG1P_FEATURES else value


def fit_reference_scaler(
    tracks: Iterable[dict[str, Any]], comparison: ComparisonConfig, corpus_sha256: str
) -> dict[str, Any]:
    unique: dict[str, dict[str, Any]] = {}
    for track in tracks:
        unique.setdefault(track["source_sha256"], track)
    features: dict[str, Any] = {}
    for name in FEATURES:
        values = [
            _transform(name, value)
            for track in unique.values()
            if (value := raw_feature(track, name)) is not None
        ]
        values.sort()
        if len(values) < comparison.minimum_reference_values:
            features[name] = {"enabled": False, "valid_count": len(values), "reason": "INSUFFICIENT_REFERENCE_VALUES"}
            continue
        array = np.asarray(values, dtype=np.float64)
        median = float(np.quantile(array, 0.5, method="linear"))
        iqr = float(np.quantile(array, 0.75, method="linear") - np.quantile(array, 0.25, method="linear"))
        if iqr < comparison.iqr_minimum:
            features[name] = {"enabled": False, "valid_count": len(values), "reason": "REFERENCE_IQR_TOO_SMALL"}
            continue
        features[name] = {
            "enabled": True,
            "valid_count": len(values),
            "transform": "log1p" if name in LOG1P_FEATURES else "identity",
            "median": median,
            "iqr": iqr,
            "sorted_reference_values": values,
        }
    scaler = {
        "schema_version": "stage5f1-energy-motion-scaler-v1",
        "reference_corpus": comparison.reference_corpus,
        "reference_corpus_sha256": corpus_sha256,
        "source_count": len(unique),
        "clip_z": comparison.scaler_clip_z,
        "features": features,
    }
    scaler["scaler_sha256"] = canonical_sha256(scaler)
    return scaler


def scaled_feature(track: dict[str, Any], name: str, scaler: dict[str, Any]) -> float | None:
    spec = scaler["features"].get(name, {})
    value = raw_feature(track, name)
    if value is None or not spec.get("enabled"):
        return None
    return float(np.clip((_transform(name, value) - spec["median"]) / spec["iqr"], -scaler["clip_z"], scaler["clip_z"]))


def percentile_feature(track: dict[str, Any], name: str, scaler: dict[str, Any]) -> float | None:
    value = raw_feature(track, name)
    spec = scaler["features"].get(name, {})
    if value is None or not spec.get("enabled"):
        return None
    transformed = _transform(name, value)
    values = np.asarray(spec["sorted_reference_values"])
    lower = int(np.searchsorted(values, transformed, side="left"))
    upper = int(np.searchsorted(values, transformed, side="right"))
    return (lower + 0.5 * (upper - lower)) / values.size


def derived_track_features(track: dict[str, Any], scaler: dict[str, Any]) -> dict[str, Any]:
    names = ("onset_rate_hz", "percussive_onset_rate_hz", "spectral_flux_q90")
    percentiles = {name: percentile_feature(track, name, scaler) for name in names}
    arousal = float(np.mean(list(percentiles.values()))) if all(value is not None for value in percentiles.values()) else None
    pulse = _family(track, "pulse")
    beat = _family(track, "beat")
    reliability = pulse.get("values", {}).get("pulse_reliability")
    support = beat.get("values", {}).get("beat_onset_support")
    danceability = math.sqrt(reliability * support) if pulse.get("status") == beat.get("status") == "VALID" and reliability is not None and support is not None else None
    return {
        "source_sha256": track["source_sha256"],
        "scaler_sha256": scaler["scaler_sha256"],
        "arousal_proxy_0_1": arousal,
        "danceability_proxy_0_1": danceability,
        "beat_drive_proxy": beat.get("values", {}).get("beat_strength_proxy") if beat.get("status") == "VALID" else None,
        "percentiles": percentiles,
    }


def _group(
    left: dict[str, Any], right: dict[str, Any], name: str,
    scaler: dict[str, Any], comparison: ComparisonConfig,
) -> tuple[dict[str, Any], dict[str, float], list[str]]:
    configured = GROUPS[name]
    differences: dict[str, float] = {}
    common: list[str] = []
    for feature in configured:
        lv = scaled_feature(left, feature, scaler)
        rv = scaled_feature(right, feature, scaler)
        if lv is not None and rv is not None:
            common.append(feature)
            differences[feature] = abs(lv - rv)
    fraction = len(common) / len(configured)
    usable = len(common) >= comparison.minimum_common_features and fraction >= comparison.minimum_common_weight_fraction
    if not usable:
        return {"similarity": None, "mismatch": None, "abstain": True, "effective_mismatch": 0.0}, differences, common
    distance = float(np.mean(list(differences.values())))
    similarity = math.exp(-distance)
    reliability = 1.0
    if name in {"attack_texture", "pulse_stability", "felt_pace"}:
        lr = _family(left, "pulse").get("values", {}).get("pulse_reliability")
        rr = _family(right, "pulse").get("values", {}).get("pulse_reliability")
        if name != "felt_pace" or "beat_strength_proxy" in common:
            reliability = min(lr or 0.0, rr or 0.0)
    return {
        "similarity": similarity,
        "mismatch": 1 - similarity,
        "abstain": False,
        "pair_reliability": reliability,
        "effective_mismatch": reliability * (1 - similarity),
    }, differences, common


def _tempo_components(
    left: dict[str, Any], right: dict[str, Any], comparison: ComparisonConfig
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    lp = _family(left, "pulse")
    rp = _family(right, "pulse")
    lv, rv = lp.get("values", {}), rp.get("values", {})
    lbpm, rbpm = lv.get("primary_bpm"), rv.get("primary_bpm")
    if lp.get("status") != "VALID" or rp.get("status") != "VALID" or not lbpm or not rbpm:
        return {
            "exact_tempo": {"similarity": None, "abstain": True, "effective_mismatch": 0.0},
            "tempo_family": {"similarity": None, "abstain": True, "effective_mismatch": 0.0},
            "subdivision": {"similarity": None, "abstain": True, "effective_mismatch": 0.0},
        }, None
    log_ratio = math.log2(lbpm / rbpm)
    nearest = math.floor(log_ratio) if log_ratio - math.floor(log_ratio) <= 0.5 else math.floor(log_ratio) + 1
    exact_distance = abs(log_ratio)
    family_distance = abs(log_ratio - nearest)
    reliability = min(float(lv["pulse_reliability"]), float(rv["pulse_reliability"]))
    exact_eligible = bool(lv.get("exact_tempo_eligible") and rv.get("exact_tempo_eligible"))
    exact_similarity = math.exp(-0.5 * (exact_distance / comparison.exact_sigma_octaves) ** 2)
    family_similarity = math.exp(-0.5 * (family_distance / comparison.family_sigma_octaves) ** 2)
    subdivision, alignment = _subdivision_similarity(left, right, reliability)
    return {
        "exact_tempo": {
            "similarity": exact_similarity,
            "abstain": not exact_eligible,
            "diagnostic_only": not exact_eligible,
            "pair_reliability": reliability,
            "effective_mismatch": reliability * (1 - exact_similarity) if exact_eligible else 0.0,
        },
        "tempo_family": {
            "similarity": family_similarity, "abstain": False,
            "pair_reliability": reliability,
            "effective_mismatch": reliability * (1 - family_similarity),
        },
        "subdivision": subdivision,
    }, alignment


def _subdivision_similarity(left: dict[str, Any], right: dict[str, Any], reliability: float) -> tuple[dict[str, Any], dict[str, Any] | None]:
    candidates: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for lp in left.get("metrical_profiles", []):
        for rp in right.get("metrical_profiles", []):
            ratio = math.log2(rp["bpm"] / lp["bpm"])
            exponent = math.floor(ratio) if ratio - math.floor(ratio) <= 0.5 else math.floor(ratio) + 1
            aligned_left = lp["bpm"] * 2 ** exponent
            if not 30 <= aligned_left <= 300 or abs(math.log2(aligned_left / rp["bpm"])) > math.log2(1.04):
                continue
            values = []
            for factor in ("0.5", "2.0", "4.0"):
                lvalue, rvalue = lp["factors"].get(factor), rp["factors"].get(factor)
                if lvalue is None or rvalue is None:
                    break
                values.append(abs(math.log1p(lvalue) - math.log1p(rvalue)))
            if len(values) == 3:
                candidates.append((float(np.mean(values)), lp, rp))
    if not candidates:
        return {"similarity": None, "abstain": True, "effective_mismatch": 0.0}, None
    distance, lp, rp = min(candidates, key=lambda item: (item[0], item[1]["bpm"], item[2]["bpm"]))
    similarity = math.exp(-distance)
    return {
        "similarity": similarity, "abstain": False, "pair_reliability": reliability,
        "effective_mismatch": reliability * (1 - similarity),
    }, {"left_bpm": lp["bpm"], "right_bpm": rp["bpm"], "alternatives_considered": len(candidates)}


def compare_tracks(
    left_id: str, right_id: str, left: dict[str, Any], right: dict[str, Any],
    scaler: dict[str, Any], comparison: ComparisonConfig,
) -> PairFeatures:
    components: dict[str, Any] = {}
    differences: dict[str, Any] = {}
    masks: dict[str, list[str]] = {}
    for name in GROUPS:
        component, delta, common = _group(left, right, name, scaler, comparison)
        components[name] = component
        differences[name] = delta
        masks[name] = common
    tempo, alignment = _tempo_components(left, right, comparison)
    components.update(tempo)
    components["energy_motion"] = components["activity"]
    return PairFeatures(
        pair_id=canonical_pair_id(left_id, right_id),
        left_spotify_id=left_id,
        right_spotify_id=right_id,
        left_source_sha256=left["source_sha256"],
        right_source_sha256=right["source_sha256"],
        comparison_config_sha256=canonical_sha256(asdict(comparison)),
        scaler_sha256=scaler["scaler_sha256"],
        components=components,
        feature_differences=differences,
        common_feature_masks=masks,
        metrical_alignment=alignment,
    )
