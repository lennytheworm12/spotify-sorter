"""Mechanical contract tests for the holistic encoder adapters.

Heavy models are mocked; no downloads, no GPU required (Stage 7).
Real-model smokes live in tests/integration/test_holistic_smoke.py.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from audio_similarity.holistic_encoders import (
    AdapterSpec,
    LaionClapEncoder,
    MertVariantEncoder,
    MuQMulanEncoder,
    EncoderContractError,
)
from audio_similarity.encoder import HolisticAudioEncoder


# ---------------------------------------------------------------------------
# helpers: build adapters without running __init__ (no model load)
# ---------------------------------------------------------------------------


def muq_with_fake_model(dim=512):
    enc = object.__new__(MuQMulanEncoder)
    enc.spec = AdapterSpec("muq_mulan_large", hf_repo="OpenMuQ/MuQ-MuLan-large", declared_dim=dim)
    enc.encoder_id = "muq_mulan_large"
    enc.embedding_dim = dim
    enc.device = "cpu"
    enc.revision = "test"

    class FakeOut(dict):
        pass

    class FakeModel:
        """Always emits a FIXED 512-D vector derived from input content,
        independent of the declared dimension — mismatch detection relies on it."""

        def __call__(self, wavs=None, **kw):
            gen = torch.Generator().manual_seed(int(wavs.sum().item() * 1000) % (2**31))
            v = torch.randn(wavs.shape[0], 512, generator=gen)
            return FakeOut(output=v)

    enc.model = FakeModel()
    return enc


class FakeMert(torch.nn.Module):
    def __init__(self, layers=25, frames=30, dim=1024):
        super().__init__()
        self.dummy = torch.nn.Parameter(torch.zeros(1))
        self._layers = layers
        self._frames = frames
        self._dim = dim

    def forward(self, **kwargs):
        hidden = [torch.randn(1, self._frames, self._dim) for _ in range(self._layers)]
        out = type("Out", (), {})()
        out.hidden_states = hidden
        return out


def mert_with_fake_model(variant):
    enc = object.__new__(MertVariantEncoder)
    enc.variant = variant
    enc.layers, enc.embedding_dim = enc.VARIANTS[variant]
    enc.encoder_id = f"mert_{variant}"
    enc.backbone_id = "m-a-p/MERT-v1-330M"
    enc.device = "cpu"
    enc.model = FakeMert()
    return enc


def clap_with_fake_output(vec_dim=512):
    enc = object.__new__(LaionClapEncoder)
    enc.spec = AdapterSpec("laion_clap", checkpoint="630k-audioset-best.pt", declared_dim=vec_dim)
    enc.encoder_id = "laion_clap"
    enc.embedding_dim = vec_dim

    class FakeClap:
        def get_audio_embedding_from_data(self, x, use_tensor):
            assert use_tensor is False
            arr = np.asarray(x)
            # accept any length; library quantizes internally to 10 s @48 kHz
            return np.ones((arr.shape[0], vec_dim)) * 0.01

    enc.model = FakeClap()
    return enc


# ---------------------------------------------------------------------------
# protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "adapter,dim",
    [
        (muq_with_fake_model(), 512),
        (mert_with_fake_model("layers_3_4_5_6_23_concat_meanpool"), 5120),
        (mert_with_fake_model("last_layer_meanpool"), 1024),
        (clap_with_fake_output(), 512),
    ],
)
def test_adapters_satisfy_holistic_protocol_and_contract(adapter, dim):
    assert isinstance(adapter, HolisticAudioEncoder)
    wav = np.random.default_rng(0).normal(size=24000).astype(np.float32)
    result = adapter.encode_segment(wav, 24000)
    assert result.embedding.shape == (dim,)
    assert np.isfinite(result.embedding).all()
    assert abs(float(np.linalg.norm(result.embedding)) - 1.0) <= 1e-6
    assert result.encoder_id == adapter.encoder_id
    assert result.provenance


# ---------------------------------------------------------------------------
# per-encoder behavior
# ---------------------------------------------------------------------------


def test_muq_rejects_wrong_sample_rate():
    enc = muq_with_fake_model()
    with pytest.raises(EncoderContractError, match="24 kHz"):
        enc.encode_segment(np.zeros(120000), 44100)


def test_muq_detects_dimension_mismatch():
    enc = muq_with_fake_model(dim=513)  # declared != produced(512)
    with pytest.raises(EncoderContractError, match="expected"):
        enc.encode_segment(np.zeros(24000), 24000)


def test_mert_variant_dimensions_and_layers():
    enc_concat = mert_with_fake_model("layers_3_4_5_6_23_concat_meanpool")
    out = enc_concat.encode_segment(np.zeros(24000), 24000)
    assert out.embedding.shape == (5120,)
    assert out.provenance["layers"] == [3, 4, 5, 6, 23]

    enc_last = mert_with_fake_model("last_layer_meanpool")
    out2 = enc_last.encode_segment(np.zeros(24000), 24000)
    assert out2.embedding.shape == (1024,)
    assert out2.provenance["layers"] == [24]


def test_unknown_mert_variant_rejected():
    with pytest.raises(ValueError, match="unknown MERT variant"):
        MertVariantEncoder("layer_42")


def test_clap_records_windowing_provenance_and_resamples():
    enc = clap_with_fake_output()
    wav = np.random.default_rng(0).normal(size=120000).astype(np.float32)  # 5 s @24 k
    result = enc.encode_segment(wav, 24000)
    assert result.provenance["model_input_sr"] == 48000
    assert result.provenance["excerpt_resampled_from"] == 24000
    assert result.provenance["window_seconds"] == 10


def test_clap_accepts_any_input_length_via_library_quantization():
    enc = clap_with_fake_output()
    short = np.random.default_rng(0).normal(size=1000).astype(np.float32)
    result = enc.encode_segment(short, 24000)
    assert result.embedding.shape == (512,)


# ---------------------------------------------------------------------------
# determinism at the adapter level (mocked weights are fixed per instance)
# ---------------------------------------------------------------------------


def test_muq_deterministic_per_instance():
    enc = muq_with_fake_model()
    torch.manual_seed(7)
    a = enc.encode_segment(np.linspace(-1, 1, 24000), 24000)
    b = enc.encode_segment(np.linspace(-1, 1, 24000), 24000)
    # same input through same weights -> identical
    np.testing.assert_array_equal(a.embedding, b.embedding)
