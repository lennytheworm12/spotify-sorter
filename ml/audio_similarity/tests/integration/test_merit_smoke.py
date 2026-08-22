"""Heavy end-to-end smoke test with the REAL frozen MERT + MERIT heads.

Downloads m-a-p/MERT-v1-330M (~1.3 GB) and the three MERIT heads (~33 MB).
Run deliberately, not in fast CI:

    uv run pytest -m heavy -v

This is the Stage A gate from the Phase 1 design (section 13, Stage A):
3/3 clips must decode + encode + persist successfully and satisfy the
embedding contract; a duplicate waveform must yield ~1.0 factor similarity.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from audio_similarity.audio import preprocess_waveform
from audio_similarity.merit_encoder import (
    BACKBONE_DIM,
    EMBEDDING_DIM,
    MeritEncoder,
)
from tests.helpers import synth_waveform

pytestmark = pytest.mark.heavy


@pytest.fixture(scope="module")
def encoder() -> MeritEncoder:
    return MeritEncoder.from_pretrained()


def test_three_clips_end_to_end(encoder: MeritEncoder):
    wavs = [
        preprocess_waveform(synth_waveform(30, freq=220), 24000),
        preprocess_waveform(synth_waveform(30, sample_rate=44100, channels=2, freq=440), 44100),
        preprocess_waveform(synth_waveform(12, freq=880), 24000),  # short -> padded
    ]
    for wav in wavs:
        result = encoder.encode_waveform(wav)
        for name in ("melody", "rhythm", "timbre"):
            vec = getattr(result, name)
            assert vec.shape == (EMBEDDING_DIM,)
            assert np.isfinite(vec).all()
            assert abs(float(np.linalg.norm(vec)) - 1.0) <= 1e-3
        assert result.mert_general.shape == (BACKBONE_DIM,)

    # one shared backbone pass per clip, not per head
    assert encoder.forward_call_count == 3


def test_provenance_recorded(encoder: MeritEncoder):
    p = encoder.provenance.to_dict()
    assert p["backbone_id"] == "m-a-p/MERT-v1-330M"
    assert p["backbone_revision"] not in ("", "unknown")
    assert set(p["head_sha256"]) == {"melody", "rhythm", "timbre"}
    assert all(len(h) == 64 for h in p["head_sha256"].values())
    assert p["preprocessing_version"] == "pp-v1"
    assert p["extract_layers"] == [3, 4, 5, 6, 23]


def test_repeatability_same_stack(encoder: MeritEncoder):
    wav = preprocess_waveform(synth_waveform(30, freq=330, seed=7), 24000)
    r1 = encoder.encode_waveform(wav)
    r2 = encoder.encode_waveform(wav)
    for name in ("melody", "rhythm", "timbre"):
        cosine = float(np.dot(getattr(r1, name), getattr(r2, name)))
        assert cosine > 0.9999, f"{name} repeatability cosine {cosine}"
        assert float(np.abs(getattr(r1, name) - getattr(r2, name)).max()) < 1e-4


def test_duplicate_waveform_scores_approx_one():
    enc_a = MeritEncoder.from_pretrained()
    wav = preprocess_waveform(synth_waveform(20, seed=11), 24000)
    a = enc_a.encode_waveform(wav)
    b = enc_a.encode_waveform(wav.clone())
    for name in ("melody", "rhythm", "timbre"):
        cosine = float(np.dot(getattr(a, name), getattr(b, name)))
        assert cosine > 0.9999, f"{name} duplicate-waveform cosine {cosine}"


def test_distinct_clips_do_not_collide(encoder: MeritEncoder):
    tones = [synth_waveform(30, freq=f) for f in (110, 220, 440, 880)]
    embs = [encoder.encode_waveform(preprocess_waveform(t, 24000)) for t in tones]
    sims = [
        float(np.dot(embs[i].melody, embs[j].melody))
        for i in range(len(tones))
        for j in range(i + 1, len(tones))
    ]
    # not a quality claim — just guard against degenerate constant embeddings
    assert max(sims) < 1.0 - 1e-6 or len(set(map(float, sims))) > 1
