"""Embedding-contract tests with fake backbone + real projection heads.

Verifies: one shared MERT forward pass per waveform, 128-D unit-norm factor
vectors, 5120-D general baseline, finite outputs, checkpoint loading.
No model downloads (Phase 1 doc, sections 7-8, 11).
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from audio_similarity.audio import PreprocessConfig
from audio_similarity.merit_encoder import (
    BACKBONE_DIM,
    EMBEDDING_DIM,
    EXTRACT_LAYERS,
    MERIT_REPO_ID,
    MERT_MODEL_ID,
    PREPROCESSING_VERSION,
    EmbeddingResult,
    MeritEncoder,
    ModelOutputInvalidError,
    ModelProvenance,
    ProjectionHead,
    load_head_from_checkpoint,
    load_head_state,
    validate_factor_vector,
)


class FakeHiddenStates(list):
    pass


class FakeBackboneOutput:
    def __init__(self, seq_len: int = 100, dim: int = 1024, seed: int = 0):
        gen = torch.Generator().manual_seed(seed)
        # hidden_states[0] is the CNN output; layers 1..24 are transformer layers
        self.hidden_states = FakeHiddenStates(
            torch.randn(1, seq_len, dim, generator=gen) for _ in range(max(EXTRACT_LAYERS) + 1)
        )


class FakeBackbone(torch.nn.Module):
    """Stands in for frozen MERT; returns deterministic hidden states."""

    def __init__(self, seed: int = 0):
        super().__init__()
        self.seed = seed
        self.calls = 0
        self.dummy = torch.nn.Parameter(torch.zeros(1))

    def forward(self, **kwargs):
        self.calls += 1
        return FakeBackboneOutput(seed=self.seed + self.calls)


class FakeProcessor:
    sampling_rate = 24000

    def __call__(self, wav, sampling_rate, return_tensors):
        assert return_tensors == "pt"
        tensor = torch.as_tensor(np.asarray(wav), dtype=torch.float32).unsqueeze(0)
        return {"input_values": tensor}


def make_encoder(seed: int = 0) -> tuple[MeritEncoder, FakeBackbone]:
    torch.manual_seed(1234)
    backbone = FakeBackbone(seed=seed)
    heads = {name: ProjectionHead() for name in ("melody", "rhythm", "timbre")}
    provenance = ModelProvenance(
        backbone_id=MERT_MODEL_ID,
        backbone_revision="test",
        merit_repo_id=MERIT_REPO_ID,
        merit_revision="test",
        preprocessing_version=PREPROCESSING_VERSION,
        extract_layers=EXTRACT_LAYERS,
        head_sha256={name: "deadbeef" for name in heads},
    )
    encoder = MeritEncoder(model=backbone, processor=FakeProcessor(), heads=heads, provenance=provenance)
    return encoder, backbone


def sample_waveform() -> torch.Tensor:
    return torch.linspace(-1.0, 1.0, steps=PreprocessConfig().target_samples)


def test_factor_embeddings_have_contract_shape_and_norm():
    encoder, _ = make_encoder()
    result = encoder.encode_waveform(sample_waveform())
    assert isinstance(result, EmbeddingResult)
    for name in ("melody", "rhythm", "timbre"):
        vec = getattr(result, name)
        assert vec.shape == (EMBEDDING_DIM,)
        assert np.isfinite(vec).all()
        assert abs(float(np.linalg.norm(vec)) - 1.0) <= 1e-3


def test_general_mert_baseline_is_5120_and_normalized():
    encoder, _ = make_encoder()
    result = encoder.encode_waveform(sample_waveform())
    assert result.mert_general.shape == (BACKBONE_DIM,)
    assert np.isfinite(result.mert_general).all()
    assert abs(float(np.linalg.norm(result.mert_general)) - 1.0) <= 1e-3


def test_one_shared_forward_pass_per_waveform():
    encoder, backbone = make_encoder()
    wav = sample_waveform()
    encoder.encode_waveform(wav)
    assert backbone.calls == 1
    encoder.encode_waveform(wav)
    encoder.encode_waveform(wav)
    assert backbone.calls == 3  # one per waveform, not per factor/head


def test_extract_layers_are_pulled_from_hidden_states():
    encoder, backbone = make_encoder()
    result = encoder.encode_waveform(sample_waveform())

    # recompute expected backbone from the same deterministic fake
    out = FakeBackboneOutput(seed=backbone.seed + 1)
    parts = [out.hidden_states[layer].mean(dim=1) for layer in EXTRACT_LAYERS]
    expected = torch.cat(parts, dim=-1)[0].numpy()
    expected_normed = expected / np.linalg.norm(expected)

    np.testing.assert_allclose(result.mert_general, expected_normed, rtol=1e-4, atol=1e-6)


def test_deterministic_for_identical_input():
    encoder_a, _ = make_encoder(seed=0)
    encoder_b, _ = make_encoder(seed=0)
    wav = sample_waveform()
    a = encoder_a.encode_waveform(wav)
    b = encoder_b.encode_waveform(wav)
    for name in ("melody", "rhythm", "timbre"):
        np.testing.assert_allclose(getattr(a, name), getattr(b, name), rtol=0, atol=1e-6)


def test_different_inputs_give_different_embeddings():
    encoder, _ = make_encoder()
    r1 = encoder.encode_waveform(sample_waveform())
    other = torch.flip(sample_waveform(), dims=[0])
    r2 = encoder.encode_waveform(other)
    for name in ("melody", "rhythm", "timbre"):
        assert not np.allclose(getattr(r1, name), getattr(r2, name))


def test_projection_head_normalizes_output():
    torch.manual_seed(0)
    head = ProjectionHead(in_dim=64, hidden_dim=16, out_dim=8)
    x = torch.randn(5, 64) * 10
    out = head(x)
    assert out.shape == (5, 8)
    torch.testing.assert_close(out.norm(dim=-1), torch.ones(5), atol=1e-5, rtol=1e-5)


def test_head_checkpoint_roundtrip(tmp_path):
    torch.manual_seed(0)
    head = ProjectionHead(in_dim=32, hidden_dim=8, out_dim=4)
    ckpt = {
        "in_dim": 32,
        "hidden_dim": 8,
        "out_dim": 4,
        "state_dict": head.state_dict(),
    }
    path = tmp_path / "head.pt"
    torch.save(ckpt, path)
    restored = load_head_from_checkpoint(load_head_state(path))
    x = torch.randn(3, 32)
    torch.testing.assert_close(restored(x), head(x))


def test_missing_head_rejected():
    make = make_encoder()[0]
    make.heads.pop("timbre")
    with pytest.raises(ValueError, match="missing projection heads"):
        MeritEncoder(
            model=make.model,
            processor=make.processor,
            heads=make.heads,
            provenance=make.provenance,
        )


def test_validate_factor_vector_rejects_bad_outputs():
    with pytest.raises(ModelOutputInvalidError):
        validate_factor_vector("melody", np.zeros(EMBEDDING_DIM - 1))
    bad_norm = np.full(EMBEDDING_DIM, 2.0)
    with pytest.raises(ModelOutputInvalidError):
        validate_factor_vector("melody", bad_norm)
    non_finite = np.ones(EMBEDDING_DIM)
    non_finite[0] = np.nan
    with pytest.raises(ModelOutputInvalidError):
        validate_factor_vector("melody", non_finite)


def test_encode_rejects_non_1d_input():
    encoder, _ = make_encoder()
    with pytest.raises(ValueError, match="1-D"):
        encoder.encode_waveform(sample_waveform().unsqueeze(0))
