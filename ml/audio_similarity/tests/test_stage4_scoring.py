from __future__ import annotations

import numpy as np
import pytest

from audio_similarity.stage4_scoring import (
    LATE, RECURRENCE, UNIFORM, all_rankings, bounded_recurrence_mean,
    generate_trials, query_bootstrap, recurrence_weights, symmetric_top2_score,
    uniform_mean, verdict,
)


def segments(seed: int, dimension: int = 8):
    return np.random.default_rng(seed).normal(size=(5, dimension)).astype(np.float32)


def test_uniform_normalizes_segments_before_mean_and_output():
    raw = segments(1) * np.arange(1, 6)[:, None]
    expected_rows = raw / np.linalg.norm(raw, axis=1, keepdims=True)
    expected = expected_rows.mean(axis=0); expected /= np.linalg.norm(expected)
    assert np.allclose(uniform_mean(raw), expected)
    assert np.linalg.norm(uniform_mean(raw)) == pytest.approx(1.0)


def test_equal_recurrence_is_exact_uniform_and_bounds_hold():
    raw = np.eye(5, dtype=np.float32)
    aggregate, weights = bounded_recurrence_mean(raw)
    assert np.array_equal(weights, np.full(5, 0.2))
    assert np.array_equal(aggregate, uniform_mean(raw))


def test_recurrence_is_permutation_equivariant_and_bounded():
    raw = segments(2)
    permutation = [3, 0, 4, 1, 2]
    weights = recurrence_weights(raw)
    permuted = recurrence_weights(raw[permutation])
    assert np.allclose(permuted, weights[permutation])
    assert weights.min() >= 0.15 and weights.max() <= 0.25
    assert weights.sum() == pytest.approx(1.0)


def test_exact_symmetric_top2_formula():
    q = np.eye(5)
    c = np.eye(5)
    # each row/column's top two are 1 and 0
    assert symmetric_top2_score(q, c) == pytest.approx(0.5)
    assert symmetric_top2_score(q, c) == symmetric_top2_score(c, q)


def test_late_only_reranks_uniform_top100_boundary():
    store = {f"t{i:03}": segments(i, 8) for i in range(105)}
    ranks = all_rankings(["t000"], store)["t000"]
    assert len(ranks[LATE]) == 100
    uniform_top100 = {track for track, _ in ranks[UNIFORM][:100]}
    assert {track for track, _ in ranks[LATE]} == uniform_top100


def test_retrieval_and_ties_use_stable_track_id():
    base = np.eye(5, 8, dtype=np.float32)
    store = {"q": base, "b": base, "a": base, "z": segments(9)}
    ranks = all_rankings(["q"], store)["q"][UNIFORM]
    assert [row[0] for row in ranks[:2]] == ["a", "b"]


def test_trial_generation_is_opaque_deterministic_and_strict():
    ranking = {"q": {
        UNIFORM: [("x", .9), ("y", .8), ("z", .1)],
        RECURRENCE: [("y", .9), ("x", .8), ("z", .1)],
        LATE: [("z", .9), ("x", .8), ("y", .1)],
    }}
    first = generate_trials(ranking, 42, {"q": "INTERIM"})
    second = generate_trials(ranking, 42, {"q": "INTERIM"})
    assert first == second
    public, keys = first
    assert public and all(set(row) == {"trial_id", "split", "question"} for row in public)
    assert set(keys) == {row["trial_id"] for row in public}
    assert all(row["trial_id"].startswith("s4_") and "q" not in row["trial_id"] for row in public)


def test_bootstrap_is_query_level_and_fixed_seed():
    values = {"q1": 0.0, "q2": 1.0, "q3": 1.0}
    assert query_bootstrap(values, 50_000, 7) == query_bootstrap(values, 50_000, 7)


@pytest.mark.parametrize("args,expected", [
    ((-.01,(-.2,.1),-.02,(-.2,.1)), "UNIFORM_MEAN_WINS"),
    ((.02,(-.1,.1),.01,(-.1,.1)), "INSUFFICIENT_EVIDENCE_PICK_SIMPLER"),
    ((.06,(.01,.12),.01,(-.1,.1)), "RECURRENCE_WEIGHTING_WINS"),
    ((.01,(-.1,.1),.06,(.01,.12)), "LATE_INTERACTION_WINS"),
    ((.06,(.01,.12),.06,(.01,.12),.03,(-.01,.08)), "RECURRENCE_WEIGHTING_WINS"),
    ((.06,(.01,.12),.06,(.01,.12),.06,(.01,.11)), "LATE_INTERACTION_WINS"),
])
def test_all_final_verdict_paths(args, expected):
    assert verdict(*args) == expected


def test_protocol_failure_always_selects_simple_insufficiency():
    assert verdict(.5,(.4,.6),.5,(.4,.6),protocol_failure=True) == "INSUFFICIENT_EVIDENCE_PICK_SIMPLER"
