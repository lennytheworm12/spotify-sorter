"""Frozen Stage 4 aggregation, exact retrieval, trial, and decision rules."""
from __future__ import annotations

import hashlib
import itertools
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

UNIFORM = "uniform_mean_v1"
RECURRENCE = "bounded_recurrence_mean_v1"
LATE = "mean_top100_symmetric_top2_v1"
METHODS = (UNIFORM, RECURRENCE, LATE)


class Stage4ScoringError(ValueError):
    pass


def _unit_rows(vectors: np.ndarray) -> np.ndarray:
    x = np.asarray(vectors, dtype=np.float64)
    if x.ndim != 2 or x.shape[0] != 5 or not np.isfinite(x).all():
        raise Stage4ScoringError(f"expected finite K=5 matrix, got {x.shape}")
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    if np.any(norms <= 0):
        raise Stage4ScoringError("zero-norm segment")
    return x / norms


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 0 or not np.isfinite(norm):
        raise Stage4ScoringError("zero/non-finite aggregate")
    return (vector / norm).astype(np.float32)


def uniform_mean(segments: np.ndarray) -> np.ndarray:
    return _unit(_unit_rows(segments).mean(axis=0))


def recurrence_weights(segments: np.ndarray) -> np.ndarray:
    u = _unit_rows(segments)
    similarity = np.maximum(0.0, u @ u.T)
    recurrence = (similarity.sum(axis=1) - 1.0) / 4.0
    deviation = recurrence - recurrence.mean()
    scale = float(np.max(np.abs(deviation)))
    z = np.zeros(5) if scale <= 1e-12 else deviation / scale
    multipliers = 1.0 + 0.25 * z
    weights = multipliers / multipliers.sum()
    if np.any(weights < 0.15 - 1e-12) or np.any(weights > 0.25 + 1e-12):
        raise AssertionError(f"frozen recurrence bounds violated: {weights}")
    return weights


def bounded_recurrence_mean(segments: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    u = _unit_rows(segments)
    weights = recurrence_weights(u)
    return _unit(np.sum(weights[:, None] * u, axis=0)), weights


def symmetric_top2_score(query_segments: np.ndarray, candidate_segments: np.ndarray) -> float:
    q, c = _unit_rows(query_segments), _unit_rows(candidate_segments)
    matrix = q @ c.T
    q_best = np.sort(matrix, axis=1)[:, -2:].mean(axis=1).mean()
    c_best = np.sort(matrix, axis=0)[-2:, :].mean(axis=0).mean()
    return float((q_best + c_best) / 2.0)


def exact_rank(query_id: str, vectors: dict[str, np.ndarray], excluded: set[str] | None = None) -> list[tuple[str, float]]:
    excluded = set(excluded or ()) | {query_id}
    query = vectors[query_id]
    rows = [(track_id, float(query @ vector)) for track_id, vector in vectors.items() if track_id not in excluded]
    return sorted(rows, key=lambda row: (-row[1], row[0]))


def late_rerank(query_id: str, uniform_vectors: dict[str, np.ndarray], segments: dict[str, np.ndarray], excluded: set[str] | None = None, depth: int = 100) -> list[tuple[str, float]]:
    first_stage = exact_rank(query_id, uniform_vectors, excluded)[:depth]
    rows = [(track_id, symmetric_top2_score(segments[query_id], segments[track_id])) for track_id, _ in first_stage]
    return sorted(rows, key=lambda row: (-row[1], row[0]))


def all_rankings(query_ids: list[str], segments: dict[str, np.ndarray], identity_exclusions: dict[str, set[str]] | None = None) -> dict[str, dict[str, list[tuple[str, float]]]]:
    uniform = {key: uniform_mean(value) for key, value in segments.items()}
    recurrence = {key: bounded_recurrence_mean(value)[0] for key, value in segments.items()}
    exclusions = identity_exclusions or {}
    return {query: {
        UNIFORM: exact_rank(query, uniform, exclusions.get(query)),
        RECURRENCE: exact_rank(query, recurrence, exclusions.get(query)),
        LATE: late_rerank(query, uniform, segments, exclusions.get(query)),
    } for query in query_ids}


def _orientation(seed: int, identity: str) -> bool:
    return hashlib.sha256(f"{seed}|{identity}".encode()).digest()[0] & 1 == 1


def generate_trials(rankings: dict[str, dict[str, list[tuple[str, float]]]], seed: int, split_by_query: dict[str, str], initial_depth: int = 20, expansion_depth: int = 50) -> tuple[list[dict], dict[str, dict]]:
    """Select one deterministic strict inversion per method pair and query."""
    public, keys = [], {}
    pairs = ((UNIFORM, RECURRENCE), (UNIFORM, LATE), (RECURRENCE, LATE))
    for query_id in sorted(rankings):
        used: set[tuple[str, str]] = set()
        for left, right in pairs:
            selected = None
            for depth in (initial_depth, expansion_depth):
                lrows, rrows = rankings[query_id][left][:depth], rankings[query_id][right][:depth]
                lr, rr = {t: i + 1 for i, (t, _) in enumerate(lrows)}, {t: i + 1 for i, (t, _) in enumerate(rrows)}
                ls, rs = dict(lrows), dict(rrows)
                choices = []
                universe = sorted(set(lr) | set(rr))
                for x, y in itertools.combinations(universe, 2):
                    lx, ly = lr.get(x, depth + 1), lr.get(y, depth + 1)
                    rx, ry = rr.get(x, depth + 1), rr.get(y, depth + 1)
                    if (lx - ly) * (rx - ry) >= 0 or tuple(sorted((x, y))) in used:
                        continue
                    # x is the candidate preferred by left.
                    if lx > ly:
                        x, y = y, x
                        lx, ly, rx, ry = ly, lx, ry, rx
                    choices.append(((max(lx, ly, rx, ry), lx + ly + rx + ry, -(abs(lx-ly) + abs(rx-ry)), x, y), x, y, ls.get(x), ls.get(y), rs.get(x), rs.get(y)))
                if choices:
                    selected = min(choices)
                    break
            if selected is None:
                continue
            _, x, y, lxs, lys, rxs, rys = selected
            used.add(tuple(sorted((x, y))))
            identity = f"{query_id}|{left}|{right}|{min(x,y)}|{max(x,y)}"
            trial_id = "s4_" + hashlib.sha256(identity.encode()).hexdigest()[:20]
            swap = _orientation(seed, identity)
            a, b = (y, x) if swap else (x, y)
            public.append({"trial_id": trial_id, "split": split_by_query[query_id], "question": "Taking the songs as a whole, which candidate sounds more like the query overall?"})
            keys[trial_id] = {"query_id": query_id, "candidate_a": a, "candidate_b": b, "method_x": left, "method_y": right, "method_x_candidate": x, "method_y_candidate": y, "scores": {left: {x: lxs, y: lys}, right: {x: rxs, y: rys}}, "ranks_depth": depth, "split": split_by_query[query_id]}
    return public, keys


def query_bootstrap(values: dict[str, float], draws: int = 50_000, seed: int = 20260904) -> tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    data = np.asarray([values[key] for key in sorted(values)], dtype=np.float64)
    rng = np.random.default_rng(seed)
    samples = data[rng.integers(0, len(data), size=(draws, len(data)))].mean(axis=1)
    return tuple(float(x) for x in np.quantile(samples, [0.025, 0.975]))


def verdict(recurrence_improvement: float, recurrence_ci: tuple[float, float], late_improvement: float, late_ci: tuple[float, float], bc_improvement: float = 0.0, bc_ci: tuple[float, float] = (0.0, 0.0), protocol_failure: bool = False) -> str:
    if protocol_failure:
        return "INSUFFICIENT_EVIDENCE_PICK_SIMPLER"
    rec_pass = recurrence_improvement >= 0.05 and recurrence_ci[0] > 0
    late_pass = late_improvement >= 0.05 and late_ci[0] > 0
    if not rec_pass and not late_pass:
        return "UNIFORM_MEAN_WINS" if recurrence_improvement <= 0 and late_improvement <= 0 else "INSUFFICIENT_EVIDENCE_PICK_SIMPLER"
    if rec_pass and not late_pass:
        return "RECURRENCE_WEIGHTING_WINS"
    if late_pass and not rec_pass:
        return "LATE_INTERACTION_WINS"
    return "LATE_INTERACTION_WINS" if bc_improvement >= 0.05 and bc_ci[0] > 0 else "RECURRENCE_WEIGHTING_WINS"
