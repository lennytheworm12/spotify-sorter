"""Shared fixtures for the audio_similarity test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import save_wav, synth_waveform


@pytest.fixture
def mono_24k_30s(tmp_path: Path) -> Path:
    return save_wav(tmp_path / "mono_24k_30s.wav", synth_waveform(30), 24000)


@pytest.fixture
def stereo_44k_10s(tmp_path: Path) -> Path:
    return save_wav(
        tmp_path / "stereo_44k_10s.wav",
        synth_waveform(10, sample_rate=44100, channels=2),
        44100,
    )


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
