"""Stage 1A contract tests: excerpt strategy + holistic encoder protocol."""

from __future__ import annotations

import numpy as np
import pytest

from audio_similarity.encoder import (
    FakeHolisticEncoder,
    HolisticAudioEncoder,
    HolisticEmbedding,
)
from audio_similarity.sampling import get_strategy, sample_segments


# ---------------------------------------------------------------------------
# Stage 2 — centered 5-second excerpt contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "duration,expected",
    [
        (30.0, [(12.5, 17.5)]),   # FMA clip: exact center
        (600.0, [(297.5, 302.5)]),
        (10.0, [(2.5, 7.5)]),
        (5.0, [(0.0, 5.0)]),
        (3.0, [(0.0, 3.0)]),      # shorter than window -> whole track
    ],
)
def test_center5_exact_intervals(duration, expected):
    segs = sample_segments("t", duration, "center5")
    assert [(s.actual_start_sec, s.actual_end_sec) for s in segs] == expected


def test_center5_is_identical_across_calls():
    a = sample_segments("q", 30.0, "center5")
    b = sample_segments("q", 30.0, "center5")
    assert a == b


def test_center5_identity_stable():
    assert get_strategy("center5").identity == "center5_v1"


# ---------------------------------------------------------------------------
# Stage 3 — holistic encoder protocol
# ---------------------------------------------------------------------------


def test_fake_encoder_satisfies_protocol():
    enc = FakeHolisticEncoder()
    assert isinstance(enc, HolisticAudioEncoder)


def test_arbitrary_embedding_dimensions():
    for dim in (8, 64, 512, 5120, 777):
        enc = FakeHolisticEncoder(embedding_dim=dim)
        result = enc.encode_segment(np.linspace(-1, 1, 120000), 24000)
        assert result.embedding.shape == (dim,)
        assert result.embedding_dim == dim


def test_output_finite_normalized_nonzero():
    enc = FakeHolisticEncoder(embedding_dim=128)
    out = enc.encode_segment(np.random.default_rng(0).normal(size=24000), 24000)
    assert np.isfinite(out.embedding).all()
    assert abs(float(np.linalg.norm(out.embedding)) - 1.0) <= 1e-6


def test_deterministic_same_input_same_output():
    enc = FakeHolisticEncoder()
    wav = np.random.default_rng(1).normal(size=120000)
    a = enc.encode_segment(wav, 24000)
    b = enc.encode_segment(wav, 24000)
    np.testing.assert_array_equal(a.embedding, b.embedding)


def test_different_inputs_differ():
    enc = FakeHolisticEncoder()
    a = enc.encode_segment(np.ones(120000), 24000)
    b = enc.encode_segment(-np.ones(120000), 24000)
    assert not np.allclose(a.embedding, b.embedding)


def test_provenance_records_sample_rate_not_metadata():
    enc = FakeHolisticEncoder()
    out = enc.encode_segment(np.zeros(100), 44100)
    assert out.provenance["sample_rate"] == 44100
    # no leakage-prone fields exist in the provenance contract
    forbidden = {"title", "artist", "genre", "merit_melody", "model_score"}
    assert not (set(out.provenance) & forbidden)


def test_holistic_embedding_validation():
    with pytest.raises(ValueError, match="shape"):
        HolisticEmbedding(np.ones(10), "e", 128)
    with pytest.raises(ValueError, match="non-finite"):
        v = np.full(128, np.nan)
        HolisticEmbedding(v, "e", 128)
    with pytest.raises(ValueError, match="zero norm"):
        HolisticEmbedding(np.zeros(128), "e", 128)
