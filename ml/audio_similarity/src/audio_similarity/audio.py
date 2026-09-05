"""Audio loading and preprocessing for MERIT inference.

Implements the published MERIT preprocessing path:

    decode -> resample to 24 kHz -> stereo to mono -> truncate/pad to 30 s

Design reference: Phase 1 doc, section 7 ("Model contract").
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch
import torchaudio

SAMPLE_RATE = 24000
TARGET_SECONDS = 30
PREPROCESSING_VERSION = "pp-v1"  # 24 kHz mono 30 s, published MERIT path


class AudioDecodeError(RuntimeError):
    """Raised when audio cannot be decoded or is not usable."""


class DurationInvalidError(AudioDecodeError):
    """Raised when decoded audio has a nonsensical duration."""


@dataclass(frozen=True)
class PreprocessConfig:
    sample_rate: int = SAMPLE_RATE
    target_seconds: int = TARGET_SECONDS
    mono: bool = True

    @property
    def target_samples(self) -> int:
        return self.sample_rate * self.target_seconds


DEFAULT_PREPROCESS = PreprocessConfig()


def load_audio(path: str | Path) -> tuple[torch.Tensor, int]:
    """Decode an audio file to a float tensor of shape (channels, samples).

    Raises AudioDecodeError on any decode failure.
    """
    try:
        wav, sample_rate = torchaudio.load(str(path))
    except Exception as exc:
        raise AudioDecodeError(f"failed to decode {path}: {exc}") from exc
    if wav.ndim != 2 or wav.shape[0] < 1:
        raise AudioDecodeError(f"unexpected waveform shape {tuple(wav.shape)} for {path}")
    if wav.numel() == 0 or wav.shape[1] == 0:
        raise DurationInvalidError(f"decoded zero-length audio from {path}")
    if not torch.isfinite(wav).all():
        raise AudioDecodeError(f"non-finite samples decoded from {path}")
    return wav, sample_rate


def preprocess_file(
    path: str | Path,
    config: PreprocessConfig = DEFAULT_PREPROCESS,
) -> torch.Tensor:
    """Load and preprocess an audio file to a fixed-size 1-D waveform."""
    wav, original_sr = load_audio(path)
    return preprocess_waveform(wav, original_sr, config)


def preprocess_waveform(
    wav: torch.Tensor,
    original_sr: int,
    config: PreprocessConfig = DEFAULT_PREPROCESS,
) -> torch.Tensor:
    """Resample to 24 kHz, collapse to mono, truncate/pad to exactly 30 s."""
    if wav.ndim == 1:
        wav = wav.unsqueeze(0)
    if original_sr != config.sample_rate:
        wav = torchaudio.functional.resample(wav, original_sr, config.sample_rate)

    if config.mono and wav.shape[0] > 1:
        wav = wav.mean(dim=0)
    else:
        wav = wav.squeeze(0)

    target = config.target_samples
    if wav.numel() > target:
        wav = wav[:target]
    elif wav.numel() < target:
        wav = torch.nn.functional.pad(wav, (0, target - wav.numel()))

    assert wav.shape == (target,), f"expected ({target},) got {tuple(wav.shape)}"
    return wav
