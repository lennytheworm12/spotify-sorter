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
