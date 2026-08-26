"""Sample-exact Stage 4 full-song preprocessing and five-window geometry."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torchaudio

SAMPLE_RATE = 24_000
WINDOW_SAMPLES = 120_000
FRACTIONS = (0.10, 0.30, 0.50, 0.70, 0.90)
SAMPLING_VERSION = "five5_fractional_v1"
PREPROCESSING_VERSION = "full_mono_24khz_v1"


class Stage4AudioError(ValueError):
    pass


@dataclass(frozen=True)
class SampleWindow:
    segment_index: int
    start_sample: int
    end_sample: int

    @property
    def start_sec(self) -> float:
        return self.start_sample / SAMPLE_RATE

    @property
    def end_sec(self) -> float:
        return self.end_sample / SAMPLE_RATE


def round_half_up(value: float) -> int:
    """Frozen non-banker's rounding rule: floor(x + 0.5)."""
    if not math.isfinite(value):
        raise Stage4AudioError("non-finite sample boundary")
    return math.floor(value + 0.5)


def five_fractional_windows(sample_count: int) -> list[SampleWindow]:
    if isinstance(sample_count, bool) or not isinstance(sample_count, int):
        raise Stage4AudioError("sample_count must be an integer")
    if sample_count < WINDOW_SAMPLES:
        raise Stage4AudioError("track cannot yield five complete 120000-sample windows")
    windows = []
    for index, fraction in enumerate(FRACTIONS):
        center = round_half_up(sample_count * fraction)
        start = center - WINDOW_SAMPLES // 2
        start = min(max(start, 0), sample_count - WINDOW_SAMPLES)
        windows.append(SampleWindow(index, start, start + WINDOW_SAMPLES))
    assert len(windows) == 5 and all(w.end_sample - w.start_sample == WINDOW_SAMPLES for w in windows)
    return windows


def canonical_waveform(waveform: torch.Tensor, source_rate: int) -> torch.Tensor:
    """Downmix and resample the complete decode; never pad or truncate."""
    if source_rate <= 0 or waveform.ndim not in (1, 2):
        raise Stage4AudioError("invalid decoded waveform")
    wav = waveform.unsqueeze(0) if waveform.ndim == 1 else waveform
    if wav.shape[0] < 1 or wav.shape[1] < 1 or not torch.isfinite(wav).all():
        raise Stage4AudioError("empty or non-finite decoded waveform")
    wav = wav.to(torch.float32).mean(dim=0, keepdim=True)
    if source_rate != SAMPLE_RATE:
        wav = torchaudio.functional.resample(wav, source_rate, SAMPLE_RATE)
    mono = wav.squeeze(0).contiguous()
    if mono.numel() < 1:
        raise Stage4AudioError("canonical decode is empty")
    return mono


def decode_full_audio(path: str | Path) -> torch.Tensor:
    try:
        waveform, rate = torchaudio.load(str(path))
    except Exception as exc:
        raise Stage4AudioError(f"failed full decode of {path}: {exc}") from exc
    return canonical_waveform(waveform, rate)


def pcm_sha256(waveform: torch.Tensor) -> str:
    samples = np.asarray(waveform.detach().cpu(), dtype="<f4")
    return hashlib.sha256(samples.tobytes(order="C")).hexdigest()


def extract_windows(waveform: torch.Tensor) -> list[torch.Tensor]:
    windows = five_fractional_windows(int(waveform.numel()))
    return [waveform[w.start_sample:w.end_sample].clone() for w in windows]
