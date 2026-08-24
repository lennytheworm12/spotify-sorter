"""MIR metric tests incl. synthetic invariance fixtures (design section 27).

The fixtures validate the EVALUATOR, not MERIT: same-tune/different-timbre
must score high on melody metrics and lower on timbre, etc.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_similarity.mir_features import (
    FeatureCache,
    MirFeatureError,
    extract_features,
    feature_config_hash,
)
from audio_similarity.mir_metrics import (
    BackgroundCalibration,
    factor_scores,
    melody_components,
    rhythm_components,
    specificity,
    timbre_components,
)

SR = 24000


# ---------------------------------------------------------------------------
# synthetic clip builders (same family as evaluation/make_examples.py)
# ---------------------------------------------------------------------------


def _note(freq: float | None, dur: float, kind: str = "sine") -> np.ndarray:
    t = np.linspace(0.0, dur, int(SR * dur), endpoint=False)
    if freq is None:
        return 0.3 * np.random.default_rng(0).normal(size=len(t)) * np.exp(-t * 12)
    env = np.minimum(1.0, np.arange(len(t)) / (0.008 * SR)) * np.exp(-t * 2.5)
    if kind == "sine":
        return 0.5 * env * np.sin(2 * np.pi * freq * t)
    if kind == "buzz":
        return 0.18 * env * sum(np.sin(2 * np.pi * freq * k * t) / k for k in range(1, 10))
    raise ValueError(kind)


def melody_clip(note_seq: list[float], note_dur: float, kind: str) -> np.ndarray:
    parts = [_note(f, note_dur * 0.9, kind) for f in note_seq]
    return np.concatenate([p for pair in zip(parts, [np.zeros(int(SR * 0.04))] * len(parts)) for p in pair])


C, D, E, F, G, A = 523.25, 587.33, 659.25, 698.46, 783.99, 880.0


@pytest.fixture(scope="module")
def clips():
    tune_a = [C, E, G, E]
    tune_b = [G, A, F, D]
    return {
        # same tune, different timbre -> melody invariant fixture
        "melody_query": melody_clip(tune_a, 0.35, "sine"),
        "melody_same_tune": melody_clip(tune_a, 0.35, "buzz"),
        # different tune, similar-ish simple timbre -> control
        "different_tune": melody_clip(tune_b, 0.35, "sine"),
        # rhythm fixture: same event timings, different pitches
        "rhythm_query": _rhythm_clip(220.0),
        "rhythm_same_timing": _rhythm_clip(440.0),
        # timbre fixture: same buzzy timbre, different tunes
        "timbre_query": melody_clip([C, E, G], 0.35, "buzz"),
        "timbre_same_palette": melody_clip([A, G, E], 0.42, "buzz"),
        "noise": np.random.default_rng(1).normal(size=SR).astype(np.float64) * 0.2,
    }


def _rhythm_clip(pitch: float) -> np.ndarray:
    sr = SR
    n = int(sr * 4)
    out = np.zeros(n)
    hits = [(0.0, "kick"), (0.5, "snare"), (1.0, "kick"), (1.25, "kick"),
            (1.5, "snare"), (2.0, "kick"), (2.5, "snare"), (3.0, "kick"), (3.25, "snare")]
    for start, kind in hits:
        idx = int(start * sr)
        length = int(0.15 * sr)
        t = np.linspace(0, 0.15, length)
        if kind == "kick":
            out[idx:idx+length] += 0.8 * np.sin(2 * np.pi * pitch * t * 0.3) * np.exp(-t * 25)
        else:
            rng = np.random.default_rng(int(start * 1000))
            out[idx:idx+length] += 0.5 * rng.normal(size=length) * np.exp(-t * 35)
    return out


@pytest.fixture(scope="module")
def feats(clips):
    return {name: extract_features(wav) for name, wav in clips.items()}


# ---------------------------------------------------------------------------
# extraction validity
# ---------------------------------------------------------------------------


def test_all_features_finite_and_shaped(feats):
    for name, f in feats.items():
        assert f.chroma_mean.shape == (12,)
        assert f.chroma_sequence.ndim == 2 and f.chroma_sequence.shape[0] == 12
        assert f.onset_envelope.size > 0
        assert f.periodicity_profile.size > 0
        assert 30 <= f.tempo_bpm <= 300 or f.tempo_bpm == 0
        assert f.timbre_vector.ndim == 1 and f.timbre_vector.size >= 40
        for arr in (f.chroma_mean, f.chroma_sequence, f.onset_envelope,
                    f.periodicity_profile, f.timbre_vector):
            assert np.isfinite(arr).all(), name


def test_deterministic_reextraction(clips):
    a = extract_features(clips["melody_query"])
    b = extract_features(clips["melody_query"])
    assert np.array_equal(a.chroma_sequence, b.chroma_sequence)
    assert np.array_equal(a.onset_envelope, b.onset_envelope)
    assert a.tempo_bpm == b.tempo_bpm


def test_short_clip_raises():
    with pytest.raises(MirFeatureError):
        extract_features(np.zeros(100))


def test_config_hash_changes_with_version():
    h1 = feature_config_hash()
    h2 = feature_config_hash({"custom": 1})
    assert h1 != h2


# ---------------------------------------------------------------------------
# invariance fixtures: the evaluator must see what a human hears
# ---------------------------------------------------------------------------


def test_melody_invariance_fixture(feats):
    """Same tune different timbre: melody HIGH, timbre LOWER."""
    m = melody_components(
        feats["melody_query"].chroma_sequence, feats["melody_same_tune"].chroma_sequence
    )
    t_same_tune = timbre_components(
        feats["melody_query"].timbre_vector, feats["melody_same_tune"].timbre_vector
    )
    m_control = melody_components(
        feats["melody_query"].chroma_sequence, feats["different_tune"].chroma_sequence
    )
    assert m.transposition_best_cos > 0.90, f"melody sim too low: {m}"
    assert m.transposition_best_cos > m_control.transposition_best_cos
    assert t_same_tune.timbre_cos < m.transposition_best_cos


def test_rhythm_invariance_fixture(feats):
    """Same event timings different pitches: rhythm HIGH, melody LOW."""
    r = rhythm_components(
        feats["rhythm_query"].onset_envelope, feats["rhythm_same_timing"].onset_envelope,
        feats["rhythm_query"].periodicity_profile, feats["rhythm_same_timing"].periodicity_profile,
        feats["rhythm_query"].tempo_bpm, feats["rhythm_same_timing"].tempo_bpm,
    )
    m_cross = melody_components(
        feats["rhythm_query"].chroma_sequence, feats["rhythm_same_timing"].chroma_sequence
    )
    assert r.tempogram_cos > 0.95, f"tempogram sim too low: {r}"
    assert r.onset_cos_fixed > 0.8
    assert m_cross.transposition_best_cos < r.tempogram_cos


def test_timbre_invariance_fixture(feats):
    """Same tone palette different tunes: timbre HIGH relative to melody."""
    t = timbre_components(feats["timbre_query"].timbre_vector, feats["timbre_same_palette"].timbre_vector)
    m = melody_components(
        feats["timbre_query"].chroma_sequence, feats["timbre_same_palette"].chroma_sequence
    )
    assert t.timbre_cos > 0.9, f"timbre sim too low: {t}"
    assert m.transposition_best_cos < t.timbre_cos


# ---------------------------------------------------------------------------
# metric primitives
# ---------------------------------------------------------------------------


def test_identity_similarity_is_one():
    chroma = np.abs(np.random.default_rng(0).normal(size=(12, 50))) + 0.01
    m = melody_components(chroma, chroma.copy())
    assert m.chroma_global_cos == pytest.approx(1.0)
    assert m.chroma_dtw_sim == pytest.approx(1.0)
    assert m.transposition_best_shift == 0

    onset = np.abs(np.random.default_rng(1).normal(size=200))
    r = rhythm_components(onset, onset.copy(), np.ones(64), np.ones(64), 120.0, 120.0)
    assert r.onset_cos_fixed == pytest.approx(1.0)
    assert r.bpm_difference == 0.0


def test_transposition_shift_detects_key_change():
    base = np.zeros(12)
    base[[0, 4, 7]] = [1.0, 0.8, 0.6]          # C major-ish
    transposed = np.roll(base, 2)               # same pattern shifted +2 semitones
    m = melody_components(np.tile(base[:, None], (1, 10)), np.tile(transposed[:, None], (1, 10)))
    assert m.transposition_best_shift == 2
    assert m.transposition_best_cos == pytest.approx(1.0, abs=0.02)
    assert m.chroma_global_cos < m.transposition_best_cos


def test_dtw_symmetry_on_identical_sequences():
    seq = np.abs(np.random.default_rng(3).normal(size=(60, 12))) + 0.01
    from audio_similarity.mir_metrics import dtw_distance
    assert dtw_distance(seq, seq) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# percentile calibration / factor scores / specificity
# ---------------------------------------------------------------------------


def test_percentile_boundaries():
    bg = BackgroundCalibration({"metric": np.array([1.0, 2.0, 3.0, 4.0, 5.0])})
    assert bg.percentile("metric", 1.0) == pytest.approx(20.0)
    assert bg.percentile("metric", 3.0) == pytest.approx(60.0)
    assert bg.percentile("metric", 5.0) == pytest.approx(100.0)
    assert bg.percentile("metric", 0.5) == pytest.approx(0.0)
    assert bg.percentile("unknown", 1.0) != bg.percentile("unknown", 1.0)  # NaN


def test_factor_scores_are_component_means():
    scores = factor_scores({
        "chroma_global_cos": 80, "chroma_dtw_sim": 70, "transposition_best_cos": 90,
        "onset_cos_fixed": 30, "onset_dtw_sim": 40, "tempogram_cos": 50,
        "timbre_cos": 20,
    })
    assert scores["melody"] == pytest.approx(80.0)
    assert scores["rhythm"] == pytest.approx(40.0)
    assert scores["timbre"] == pytest.approx(20.0)


def test_specificity_margin():
    assert specificity("melody", {"melody": 0.9, "rhythm": 0.4, "timbre": 0.5}) == pytest.approx(0.45)
    assert specificity("timbre", {"melody": 0.8, "rhythm": 0.8, "timbre": 0.2}) == pytest.approx(-0.6)


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------


def test_feature_cache_roundtrip(tmp_path):
    wav = melody_clip([C, E, G], 0.3, "sine")
    cache = FeatureCache(tmp_path)
    feats = cache.get_or_extract(wav)
    assert cache.get(feats.audio_hash) is not None
    again = cache.get_or_extract(wav)   # second call must hit cache
    assert np.array_equal(again.chroma_sequence, feats.chroma_sequence)
