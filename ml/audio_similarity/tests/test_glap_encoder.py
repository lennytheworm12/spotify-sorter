from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import torch

from audio_similarity.glap_encoder import GLAP_DIMENSION, GlapAudioEncoder
from audio_similarity.holistic_encoders import EncoderContractError


class FakeGlapModel(torch.nn.Module):
    def __init__(self, *, dimension: int = GLAP_DIMENSION, nonfinite: bool = False):
        super().__init__()
        self.dimension = dimension
        self.nonfinite = nonfinite
        self.last_audio_shape = None

    def encode_audio(self, audio):
        self.last_audio_shape = tuple(audio.shape)
        base = audio.mean(dim=1, keepdim=True)
        output = base.repeat(1, self.dimension)
        output[:, 0] += 1.0
        if self.nonfinite:
            output[:, 0] = float("nan")
        return output


def _files(tmp_path: Path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    payload = b"fake frozen weights"
    hashes = {}
    for filename, contents in {
        "model.safetensors": payload,
        "modeling_glap.py": b"model code",
        "config.json": b"{}",
        "configuration_glap.py": b"configuration code",
        "sentencepiece.source.256000.model": b"tokenizer",
    }.items():
        (model_dir / filename).write_bytes(contents)
        hashes[filename] = hashlib.sha256(contents).hexdigest()
    return model_dir, hashes


def _encoder(tmp_path: Path, model: FakeGlapModel | None = None):
    model_dir, hashes = _files(tmp_path)
    calls = []

    def loader(*args, **kwargs):
        calls.append((args, kwargs))
        return model or FakeGlapModel()

    encoder = GlapAudioEncoder(
        model_dir,
        model_revision="frozen-test-revision",
        model_sha256=hashes["model.safetensors"],
        model_code_sha256=hashes["modeling_glap.py"],
        model_config_sha256=hashes["config.json"],
        configuration_code_sha256=hashes["configuration_glap.py"],
        tokenizer_sha256=hashes["sentencepiece.source.256000.model"],
        device="cpu",
        model_loader=loader,
    )
    return encoder, calls


def test_model_loading_is_local_revision_bound_and_eval(tmp_path):
    encoder, calls = _encoder(tmp_path)
    assert len(calls) == 1
    assert calls[0][1] == {"trust_remote_code": True, "local_files_only": True}
    assert encoder.model.training is False
    assert encoder.model_revision == "frozen-test-revision"


def test_embedding_shape_finite_normalized_and_resampled(tmp_path):
    encoder, _ = _encoder(tmp_path)
    waveform = np.linspace(-1, 1, 120000, dtype=np.float32)
    result = encoder.encode_segment(waveform, 24000)
    assert result.embedding.shape == (GLAP_DIMENSION,)
    assert np.isfinite(result.embedding).all()
    assert np.linalg.norm(result.embedding) == pytest.approx(1.0, abs=1e-6)
    assert encoder.model.last_audio_shape == (1, 80000)
    assert result.provenance["model_sample_rate"] == 16000
    assert result.provenance["resampling"] == "torchaudio_functional_resample_2.6.0_v1"


def test_deterministic_repeated_inference_and_batch_support(tmp_path):
    encoder, _ = _encoder(tmp_path)
    waveform = np.random.default_rng(4).normal(size=120000).astype(np.float32)
    first = encoder.encode_batch([waveform, waveform], 24000)
    second = encoder.encode_batch([waveform, waveform], 24000)
    np.testing.assert_array_equal(first[0].embedding, second[0].embedding)
    np.testing.assert_array_equal(first[0].embedding, first[1].embedding)


def test_invalid_output_and_wrong_input_are_rejected(tmp_path):
    encoder, _ = _encoder(tmp_path, FakeGlapModel(dimension=8))
    with pytest.raises(EncoderContractError, match="returned"):
        encoder.encode_segment(np.zeros(120000, dtype=np.float32), 24000)

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    bad, _ = _encoder(other_dir, FakeGlapModel(nonfinite=True))
    with pytest.raises(EncoderContractError, match="non-finite"):
        bad.encode_segment(np.zeros(120000, dtype=np.float32), 24000)
    with pytest.raises(EncoderContractError, match="24 kHz"):
        bad.encode_segment(np.zeros(80000, dtype=np.float32), 16000)


def test_checkpoint_hash_mismatch_fails_before_model_load(tmp_path):
    model_dir, hashes = _files(tmp_path)
    with pytest.raises(EncoderContractError, match="SHA-256 mismatch"):
        GlapAudioEncoder(
            model_dir,
            model_revision="r",
            model_sha256="0" * 64,
            model_code_sha256=hashes["modeling_glap.py"],
            model_config_sha256=hashes["config.json"],
            configuration_code_sha256=hashes["configuration_glap.py"],
            tokenizer_sha256=hashes["sentencepiece.source.256000.model"],
            device="cpu",
            model_loader=lambda *args, **kwargs: FakeGlapModel(),
        )
