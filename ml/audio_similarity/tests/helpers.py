from __future__ import annotations

import math
from pathlib import Path

import pytest
import torch
import torchaudio


def synth_waveform(
    seconds: float,
    sample_rate: int = 24000,
    channels: int = 1,
    freq: float = 440.0,
    amplitude: float = 0.5,
    seed: int | None = None,
) -> torch.Tensor:
    n = int(round(seconds * sample_rate))
    if seed is not None:
        gen = torch.Generator().manual_seed(seed)
        wav = amplitude * torch.rand(n, generator=gen) * 2 - 1
        return wav.unsqueeze(0).repeat(channels, 1)
    t = torch.arange(n, dtype=torch.float64) / sample_rate
    wav = amplitude * torch.sin(2 * math.pi * freq * t)
    wav = wav.to(torch.float32)
    if channels > 1:
        # distinct content per channel so stereo->mono averaging is observable
        wav = torch.stack([wav * (c + 1) / channels for c in range(channels)], dim=0)
        return wav
    return wav.unsqueeze(0)


def save_wav(path: Path | str, wav: torch.Tensor, sample_rate: int) -> Path:
    torchaudio.save(str(path), wav, sample_rate)
    return Path(path)


@pytest.fixture
def mono_24k_30s(tmp_path: Path) -> Path:
    return save_wav(tmp_path / "mono_24k_30s.wav", synth_waveform(30), 24000)


@pytest.fixture
def stereo_44k_10s(tmp_path: Path) -> Path:
    return save_wav(tmp_path / "stereo_44k_10s.wav", synth_waveform(10, sample_rate=44100, channels=2), 44100)


@pytest.fixture
def short_clip(tmp_path: Path) -> Path:
    return save_wav(tmp_path / "short.wav", synth_waveform(3), 24000)


@pytest.fixture
def long_clip(tmp_path: Path) -> Path:
    return save_wav(tmp_path / "long.wav", synth_waveform(45), 24000)


@pytest.fixture
def corrupt_file(tmp_path: Path) -> Path:
    p = tmp_path / "corrupt.mp3"
    p.write_bytes(bytes(range(256)) * 64)
    return p


# ---------------------------------------------------------------------------
# Fake MERT backbone / processor for fast encoder + batch tests
# ---------------------------------------------------------------------------

class FakeHiddenStates(list):
    pass


class FakeBackboneOutput:
    def __init__(self, seq_len: int = 100, dim: int = 1024, seed: int = 0):
        gen = torch.Generator().manual_seed(seed)
        self.hidden_states = FakeHiddenStates(
            torch.randn(1, seq_len, dim, generator=gen) for _ in range(24)
        )


class FakeBackbone(torch.nn.Module):
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
        import numpy as np

        tensor = torch.as_tensor(np.asarray(wav), dtype=torch.float32).unsqueeze(0)
        return {"input_values": tensor}


def make_fake_encoder(seed: int = 0):
    """Return (MeritEncoder with fakes, FakeBackbone)."""
    from audio_similarity.merit_encoder import (
        EXTRACT_LAYERS,
        MERIT_REPO_ID,
        MERT_MODEL_ID,
        PREPROCESSING_VERSION,
        MeritEncoder,
        ModelProvenance,
        ProjectionHead,
    )

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
    from audio_similarity.merit_encoder import MeritEncoder as _M  # noqa: F811

    encoder = _M(model=backbone, processor=FakeProcessor(), heads=heads, provenance=provenance)
    return encoder, backbone
