"""Frozen retrospective analysis for Stage 5F.1."""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

import numpy as np
from scipy.stats import spearmanr

from .energy_motion_config import EvaluationConfig


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values, kind="stable")
    ordered_values, ordered_weights = values[order], weights[order]
    target = np.sum(ordered_weights) / 2
    return float(ordered_values[np.flatnonzero(np.cumsum(ordered_weights) >= target)[0]])


def _effect(rows: list[dict[str, Any]], weights: np.ndarray | None = None) -> float | None:
    if weights is None:
        weights = np.ones(len(rows), dtype=np.float64)
    low = np.asarray([row["activity_mismatch"] for row in rows if row["group"] == "low"], dtype=np.float64)
    high = np.asarray([row["activity_mismatch"] for row in rows if row["group"] == "high"], dtype=np.float64)
    low_weights = np.asarray([weights[index] for index, row in enumerate(rows) if row["group"] == "low"])
    high_weights = np.asarray([weights[index] for index, row in enumerate(rows) if row["group"] == "high"])
    if not low.size or not high.size or low_weights.sum() == 0 or high_weights.sum() == 0:
        return None
    return _weighted_median(low, low_weights) - _weighted_median(high, high_weights)


def node_bootstrap(rows: list[dict[str, Any]], track_ids: list[str], config: EvaluationConfig) -> dict[str, Any]:
    rng = np.random.default_rng(config.seed)
    positions = {track_id: index for index, track_id in enumerate(track_ids)}
    results: list[float] = []
    for _ in range(config.bootstrap_replicates):
        multiplicity = np.bincount(rng.integers(0, len(track_ids), len(track_ids)), minlength=len(track_ids))
        weights = np.asarray([
            multiplicity[positions[row["left_spotify_id"]]] * multiplicity[positions[row["right_spotify_id"]]]
            for row in rows
        ], dtype=np.float64)
        effect = _effect(rows, weights)
        if effect is not None:
            results.append(effect)
    return {
        "method": "track-node-bootstrap",
        "replicates_requested": config.bootstrap_replicates,
        "replicates_valid": len(results),
        "interval_95": [
            float(np.quantile(results, 0.025, method="linear")),
            float(np.quantile(results, 0.975, method="linear")),
        ] if len(results) >= int(0.95 * config.bootstrap_replicates) else None,
    }


def artist_bootstrap(rows: list[dict[str, Any]], artist_by_track: dict[str, str], config: EvaluationConfig) -> dict[str, Any]:
    groups = sorted({artist for artist in artist_by_track.values() if artist})
    if not groups or any(not artist_by_track.get(track) for row in rows for track in (row["left_spotify_id"], row["right_spotify_id"])):
        return {"method": "artist-group-bootstrap", "replicates_requested": config.bootstrap_replicates,
                "replicates_valid": 0, "interval_95": None, "reason": "MISSING_ARTIST_GROUP"}
    rng = np.random.default_rng(config.seed)
    positions = {group: index for index, group in enumerate(groups)}
    results: list[float] = []
    for _ in range(config.bootstrap_replicates):
        multiplicity = np.bincount(rng.integers(0, len(groups), len(groups)), minlength=len(groups))
        weights = []
        for row in rows:
            left = positions[artist_by_track[row["left_spotify_id"]]]
            right = positions[artist_by_track[row["right_spotify_id"]]]
            weights.append(multiplicity[left] if left == right else multiplicity[left] * multiplicity[right])
        effect = _effect(rows, np.asarray(weights, dtype=np.float64))
        if effect is not None:
            results.append(effect)
    return {
        "method": "artist-group-bootstrap", "group_count": len(groups),
        "replicates_requested": config.bootstrap_replicates, "replicates_valid": len(results),
        "interval_95": [float(np.quantile(results, 0.025, method="linear")),
                        float(np.quantile(results, 0.975, method="linear"))]
        if len(results) >= int(0.95 * config.bootstrap_replicates) else None,
    }


def _correlation(rows: list[dict[str, Any]], x: str, y: str) -> dict[str, Any]:
    pairs = [(row.get(x), row.get(y)) for row in rows]
    pairs = [(float(a), float(b)) for a, b in pairs if a is not None and b is not None and math.isfinite(float(a)) and math.isfinite(float(b))]
    if len(pairs) < 3 or len({a for a, _ in pairs}) < 2 or len({b for _, b in pairs}) < 2:
        return {"rho": None, "count": len(pairs), "reason": "INSUFFICIENT_OR_CONSTANT_INPUT"}
    result = spearmanr([a for a, _ in pairs], [b for _, b in pairs])
    return {"rho": float(result.statistic), "count": len(pairs)}


def analyze_rated_pairs(
    all_pairs: list[dict[str, Any]],
    track_rows: list[dict[str, Any]],
    config: EvaluationConfig,
    gain_gate_passed: bool = True,
) -> dict[str, Any]:
    base_values = np.asarray([row["base_combined"] for row in all_pairs], dtype=np.float64)
    cutoff = float(np.quantile(base_values, config.high_base_quantile, method="linear"))
    rated = [row for row in all_pairs if row.get("human_rating") is not None]
    slice_rows = []
    for row in rated:
        similarity = row.get("activity_similarity")
        if row["base_combined"] < cutoff or similarity is None:
            continue
        rating = row["human_rating"]
        group = "low" if rating <= config.low_rating_max else "high" if rating >= config.high_rating_min else None
        if group:
            slice_rows.append(row | {"group": group, "activity_mismatch": 1 - similarity})
    low = [row for row in slice_rows if row["group"] == "low"]
    high = [row for row in slice_rows if row["group"] == "high"]
    point = _effect(slice_rows)
    bootstrap = node_bootstrap(slice_rows, sorted(row["spotify_track_id"] for row in track_rows), config) if low and high else {
        "method": "track-node-bootstrap", "replicates_requested": config.bootstrap_replicates,
        "replicates_valid": 0, "interval_95": None,
    }
    unique_tracks = len({track for row in slice_rows for track in (row["left_spotify_id"], row["right_spotify_id"])})
    artist_by_track = {row["spotify_track_id"]: row.get("artist_credit") or "" for row in track_rows}
    unique_artists = len({artist_by_track[track] for row in slice_rows for track in (row["left_spotify_id"], row["right_spotify_id"]) if artist_by_track[track]})
    artist_group_bootstrap = artist_bootstrap(slice_rows, artist_by_track, config) if low and high else {
        "method": "artist-group-bootstrap", "replicates_requested": config.bootstrap_replicates,
        "replicates_valid": 0, "interval_95": None,
    }
    component_names = ("activity", "attack_texture", "dynamics", "pulse_stability", "felt_pace",
                       "exact_tempo", "tempo_family", "subdivision")
    correlations = {f"{component}_similarity_vs_{target}": _correlation(rated, f"{component}_similarity", target)
                    for component in component_names for target in ("a_clap", "muq", "base_combined", "human_rating")}
    core_valid = sum(
        row.get("activity", {}).get("status") == "VALID"
        and row.get("percussion", {}).get("status") == "VALID"
        and row.get("source_level", {}).get("status") == "VALID"
        for row in track_rows
    )
    pulse_valid = sum(row.get("pulse", {}).get("status") == "VALID" for row in track_rows)
    support_pass = (
        len(low) >= config.minimum_slice_pairs_per_group
        and len(high) >= config.minimum_slice_pairs_per_group
        and unique_tracks >= config.minimum_slice_unique_tracks
        and unique_artists >= config.minimum_slice_unique_artists
    )
    effect_pass = point is not None and point >= config.minimum_primary_mismatch_difference
    interval = bootstrap["interval_95"]
    bootstrap_pass = interval is not None and interval[0] > 0
    artist_interval = artist_group_bootstrap["interval_95"]
    artist_bootstrap_pass = artist_interval is not None and artist_interval[0] > -0.02
    nonredundant = all(
        correlations[f"activity_similarity_vs_{target}"]["rho"] is None
        or abs(correlations[f"activity_similarity_vs_{target}"]["rho"]) < 0.95
        for target in ("a_clap", "muq", "base_combined")
    )
    core_pass = core_valid / len(track_rows) >= config.minimum_core_measurement_coverage
    clean_slice = [row for row in slice_rows if not row.get("normalization_warning")]
    clean_low = sum(row["group"] == "low" for row in clean_slice)
    clean_high = sum(row["group"] == "high" for row in clean_slice)
    clean_effect = _effect(clean_slice)
    normalization_sensitivity_pass = clean_low >= 10 and clean_high >= 10 and clean_effect is not None and clean_effect > 0
    verdict = "SUPPORTED" if all((support_pass, effect_pass, bootstrap_pass, artist_bootstrap_pass,
                                  nonredundant, core_pass, normalization_sensitivity_pass, gain_gate_passed)) else "DIAGNOSTIC-ONLY"
    report = {
        "schema_version": "stage5f1-retrospective-analysis-v1",
        "verdict": verdict,
        "production_activation": False,
        "reranking_executed": False,
        "reranking_reason": "Stage 5F.1 revised design reserves reranking for a separate Stage 5F.2 design",
        "base_high_similarity_cutoff": cutoff,
        "pair_counts": {
            "all_eligible_original100": len(all_pairs), "rated": len(rated),
            "primary_low": len(low), "primary_high": len(high),
            "primary_unique_tracks": unique_tracks, "primary_unique_artists": unique_artists,
        },
        "coverage": {
            "track_count": len(track_rows), "core_valid_count": core_valid,
            "core_valid_fraction": core_valid / len(track_rows),
            "pulse_valid_count": pulse_valid, "pulse_valid_fraction": pulse_valid / len(track_rows),
        },
        "primary_effect": {
            "median_mismatch_difference": point,
            "bootstrap": bootstrap,
            "artist_group_bootstrap": artist_group_bootstrap,
            "support_gate_passed": support_pass,
            "effect_gate_passed": effect_pass,
            "bootstrap_gate_passed": bootstrap_pass,
            "artist_bootstrap_gate_passed": artist_bootstrap_pass,
        },
        "correlations": correlations,
        "nonredundancy_gate_passed": nonredundant,
        "gain_audit_gate_passed": gain_gate_passed,
        "normalization_sensitivity": {"low_count": clean_low, "high_count": clean_high,
                                      "median_mismatch_difference": clean_effect,
                                      "gate_passed": normalization_sensitivity_pass},
        "limitations": [
            "Historical ratings are model-selected and are not a prospective retrieval holdout.",
            "No new judgments were requested; missing labels were not imputed.",
            "The engineering golden set verifies retained decoding and full-duration contracts; no new auditory annotations were fabricated.",
            "Arousal and danceability outputs are transparent engineering proxies, not calibrated perceptual truth.",
        ],
        "counterexamples": {
            "high_activity_similarity_low_rating": sorted(
                [row for row in rated if row.get("activity_similarity") is not None and row["human_rating"] <= 2],
                key=lambda row: (-row["activity_similarity"], row["pair_id"]),
            )[:20],
            "low_activity_similarity_high_rating": sorted(
                [row for row in rated if row.get("activity_similarity") is not None and row["human_rating"] >= 4],
                key=lambda row: (row["activity_similarity"], row["pair_id"]),
            )[:20],
        },
    }
    return report
