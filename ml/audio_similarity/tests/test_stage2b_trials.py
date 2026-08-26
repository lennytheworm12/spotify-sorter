from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd

from audio_similarity.stage2b_audio import PcmIdentity, canonical_pcm, compute_pcm_identity, float32_le_bytes
from audio_similarity.stage2b_trials import (
    _eligible_disagreements,
    _opaque_id,
    _orientation,
    _score_order,
    identity_duplicate,
)
from tests.helpers import save_wav, synth_waveform

ROOT = Path(__file__).parents[1]
REPORT = ROOT / "reports/holistic_stage2b"


def ident(track_id: int, source: str, pcm30: str, center: str) -> PcmIdentity:
    return PcmIdentity(track_id, source, pcm30, center, 720000, 300000, 420000)


def test_identity_duplicate_rules_and_distinct_retention():
    base = ident(1, "source1", "pcm1", "center1")
    assert identity_duplicate(base, ident(1, "other", "other", "other"))
    assert identity_duplicate(base, ident(2, "source1", "other", "other"))
    assert identity_duplicate(base, ident(2, "other", "pcm1", "other"))
    assert identity_duplicate(base, ident(2, "other", "other", "center1"))
    assert not identity_duplicate(base, ident(2, "source2", "pcm2", "center2"))


def test_duplicate_policy_api_cannot_receive_encoder_scores():
    assert tuple(inspect.signature(identity_duplicate).parameters) == ("first", "second")
    source = inspect.getsource(identity_duplicate).casefold()
    assert "score" not in source and "cosine" not in source


def test_exact_center5_pcm_bounds_bytes_and_hash(tmp_path):
    path = save_wav(tmp_path / "clip.wav", synth_waveform(30.0, seed=4), 24000)
    canonical, excerpt, start, end = canonical_pcm(path)
    assert canonical.shape == (720000,)
    assert (start, end) == (300000, 420000)
    np.testing.assert_array_equal(excerpt, canonical[start:end])
    assert len(float32_le_bytes(excerpt)) == 120000 * 4
    first = compute_pcm_identity(4, "abc", path)
    second = compute_pcm_identity(4, "abc", path)
    assert first == second


def test_exact_retrieval_is_l2_cosine_then_track_id_tiebroken():
    vectors = {
        1: np.array([1.0, 0.0], dtype=np.float32),
        2: np.array([0.8, 0.6], dtype=np.float32),
        3: np.array([0.8, -0.6], dtype=np.float32),
        4: np.array([0.0, 1.0], dtype=np.float32),
    }
    first = _score_order(vectors, 1, {1})
    second = _score_order(vectors, 1, {1})
    assert first == second
    assert first[0] == [2, 3, 4]


def test_strict_disagreement_ranking_and_orientation_are_deterministic():
    identities = {track: ident(track, f"s{track}", f"p{track}", f"c{track}") for track in (10, 11, 12, 13)}
    scores = {
        "x": {10: .9, 11: .1, 12: .8, 13: .2},
        "y": {10: .1, 11: .9, 12: .2, 13: .8},
    }
    ranks = {
        "x": {10: 1, 12: 2, 13: 3, 11: 4},
        "y": {11: 1, 13: 2, 12: 3, 10: 4},
    }
    rows = _eligible_disagreements(1, "x", "y", [10, 12], [11, 13], scores, ranks, identities)
    assert rows
    assert all(scores["x"][row["preferred_x"]] > scores["x"][row["preferred_y"]] for row in rows)
    assert all(scores["y"][row["preferred_y"]] > scores["y"][row["preferred_x"]] for row in rows)
    canonical = "1|x__vs__y|10|11"
    assert _orientation(42, canonical) == _orientation(42, canonical)
    assert _opaque_id(42, canonical) == _opaque_id(42, canonical)
    assert "10" not in _opaque_id(42, canonical)


def test_frozen_real_trials_are_balanced_strict_unique_and_blinded():
    balance = json.loads((REPORT / "trial_balance.json").read_text())
    keys = json.loads((REPORT / "trial_keys.json").read_text())["trials"]
    human = pd.read_csv(REPORT / "holistic_trials.csv")
    assert balance["gate_passed"] is True
    assert balance["selected_pair_counts"] == {
        "laion_clap__vs__mert_5120": 80,
        "laion_clap__vs__muq_mulan_large": 80,
        "mert_5120__vs__muq_mulan_large": 80,
    }
    assert len(human) == len(keys) == 240
    assert set(human.columns) == {"trial_id", "question", "choice", "note", "rated_by", "choice_log"}
    forbidden = {"model", "score", "split", "track", "title", "artist", "album", "genre", "query"}
    assert not any(any(word in column.casefold() for word in forbidden) for column in human.columns)
    pairs_by_query: dict[int, set[tuple[int, int]]] = {}
    for trial in keys.values():
        pairs = pairs_by_query.setdefault(trial["query_id"], set())
        pair = tuple(sorted((trial["candidate_a"], trial["candidate_b"])))
        assert pair not in pairs
        pairs.add(pair)
        x, y = trial["encoder_x"], trial["encoder_y"]
        preferred_x, preferred_y = trial["preferred_x"], trial["preferred_y"]
        scores = trial["scores"]
        assert scores[x]["query_a"] != scores[x]["query_b"]
        # Ranking payload independently proves the canonical strict inversion.
        assert trial["ranking"]["x_gap"] > 0
        assert trial["ranking"]["y_gap"] > 0
