"""Pairwise MIR similarity metrics + background calibration (design sections 9-13).

Every metric returns a RAW score; interpretability comes from empirical
percentiles against deterministic background pair distributions — never by
comparing raw scales across metric families.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ONSET_FIXED_LENGTH = 512


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na <= 0 or nb <= 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _l2_normalize_columns(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=0, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def dtw_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Deterministic DTW over frame sequences (frames x dims). Returns mean-per-step cost."""
    import librosa

    if a.shape[1] > b.shape[1]:
        a, b = b, a
    cost = np.sqrt(
        ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=-1)
    )  # (frames_a, frames_b)
    D, path = librosa.sequence.dtw(C=cost)
    if path.size == 0:
        return float("inf")
    total = float(D[-1, -1])
    steps = int(path.shape[1])
    return float(total / max(steps, 1))


def _dtw_similarity(a: np.ndarray, b: np.ndarray) -> float:
    d = dtw_distance(a, b)
    return float(1.0 / (1.0 + d))


def _fixed_length(x: np.ndarray, length: int = ONSET_FIXED_LENGTH) -> np.ndarray:
    if len(x) == length:
        return x
    idx = np.linspace(0, len(x) - 1e-9, num=length).astype(np.int64)
    return x[idx]


# ---------------------------------------------------------------------------
# factor pair scores (raw components only; percentiles applied separately)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MelodyComponents:
    chroma_global_cos: float
    chroma_dtw_sim: float
    transposition_best_cos: float
    transposition_best_shift: int


@dataclass(frozen=True)
class RhythmComponents:
    onset_cos_fixed: float
    onset_dtw_sim: float
    tempogram_cos: float
    bpm_difference: float


@dataclass(frozen=True)
class TimbreComponents:
    timbre_cos: float


def melody_components(chroma_a: np.ndarray, chroma_b: np.ndarray) -> MelodyComponents:
    global_a, global_b = chroma_a.mean(axis=1), chroma_b.mean(axis=1)
    global_cos = _cosine(global_a, global_b)

    norm_a, norm_b = _l2_normalize_columns(chroma_a), _l2_normalize_columns(chroma_b)
    dtw_sim = _dtw_similarity(norm_a.T, norm_b.T)

    best_cos, best_shift = -1.0, 0
    for shift in range(12):
        # roll candidate DOWN by 'shift': best_shift is the semitone offset of B relative to A
        cos = _cosine(global_a, np.roll(global_b, -shift))
        if cos > best_cos:
            best_cos, best_shift = cos, shift

    return MelodyComponents(
        chroma_global_cos=global_cos,
        chroma_dtw_sim=float(max(dtw_sim, 0.0)),
        transposition_best_cos=float(best_cos),
        transposition_best_shift=int(best_shift),
    )


def rhythm_components(
    onset_a: np.ndarray,
    onset_b: np.ndarray,
    periodicity_a: np.ndarray,
    periodicity_b: np.ndarray,
    bpm_a: float,
    bpm_b: float,
) -> RhythmComponents:
    fa = _l2_normalize_columns(_fixed_length(onset_a)[None, :])[0]
    fb = _l2_normalize_columns(_fixed_length(onset_b)[None, :])[0]
    onset_cos = _cosine(fa, fb)

    na = onset_a / max(np.linalg.norm(onset_a), 1e-9)
    nb = onset_b / max(np.linalg.norm(onset_b), 1e-9)
    onset_dtw = _dtw_similarity(na[None, :], nb[None, :])

    return RhythmComponents(
        onset_cos_fixed=float(onset_cos),
        onset_dtw_sim=float(max(onset_dtw, 0.0)),
        tempogram_cos=_cosine(periodicity_a, periodicity_b),
        bpm_difference=abs(float(bpm_a) - float(bpm_b)),
    )


def timbre_components(timbre_a: np.ndarray, timbre_b: np.ndarray) -> TimbreComponents:
    return TimbreComponents(timbre_cos=_cosine(timbre_a, timbre_b))


MELODY_COMPONENT_NAMES = ("chroma_global_cos", "chroma_dtw_sim", "transposition_best_cos")
RHYTHM_COMPONENT_NAMES = ("onset_cos_fixed", "onset_dtw_sim", "tempogram_cos")
TIMBRE_COMPONENT_NAMES = ("timbre_cos",)


# ---------------------------------------------------------------------------
# background calibration
# ---------------------------------------------------------------------------


class BackgroundCalibration:
    """Empirical null distributions -> percentiles for every raw component."""

    def __init__(self, distributions: dict[str, np.ndarray]):
        self.distributions = {k: np.sort(np.asarray(v, dtype=np.float64)) for k, v in distributions.items()}

    def percentile(self, metric: str, raw: float) -> float:
        if metric not in self.distributions or len(self.distributions[metric]) == 0:
            return float("nan")
        sorted_vals = self.distributions[metric]
        rank = np.searchsorted(sorted_vals, raw, side="right")
        return float(rank * 100.0 / len(sorted_vals))

    def percentiles(self, values: dict[str, float]) -> dict[str, float]:
        return {k: self.percentile(k, v) for k, v in values.items()}

    def zscore(self, metric: str, raw: float) -> float:
        vals = self.distributions.get(metric)
        if vals is None or len(vals) < 2:
            return float("nan")
        mu, sigma = float(vals.mean()), float(vals.std())
        return (raw - mu) / sigma if sigma > 0 else 0.0

    def to_dict(self) -> dict[str, list[float]]:
        return {k: v.tolist() for k, v in self.distributions.items()}


def factor_scores(percentiles: dict[str, float]) -> dict[str, float]:
    """Design section 13: M/R/T as mean constituent percentiles (already 0-100)."""
    m = np.mean([percentiles[k] for k in MELODY_COMPONENT_NAMES])
    r = np.mean([percentiles[k] for k in RHYTHM_COMPONENT_NAMES])
    t = percentiles["timbre_cos"]
    return {"melody": float(m), "rhythm": float(r), "timbre": float(t)}


def specificity(target_factor: str, scores: dict[str, float]) -> float:
    """Design section 14 diagnostic margin."""
    others = [v for k, v in scores.items() if k != target_factor]
    return float(scores[target_factor] - np.mean(others))
