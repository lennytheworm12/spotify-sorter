from __future__ import annotations

import numpy as np
import pytest
import torch

from audio_similarity.stage4_sampling import (
    SAMPLE_RATE, Stage4AudioError, canonical_waveform, extract_windows,
    five_fractional_windows, pcm_sha256, round_half_up,
)


def bounds(seconds: float):
    return [(w.start_sample, w.end_sample) for w in five_fractional_windows(round(seconds * SAMPLE_RATE))]


@pytest.mark.parametrize("seconds,expected", [
    (5, [(0,120000)] * 5),
    (30, [(12000,132000),(156000,276000),(300000,420000),(444000,564000),(588000,708000)]),
    (60, [(84000,204000),(372000,492000),(660000,780000),(948000,1068000),(1236000,1356000)]),
    (180, [(372000,492000),(1236000,1356000),(2100000,2220000),(2964000,3084000),(3828000,3948000)]),
    (600, [(1380000,1500000),(4260000,4380000),(7140000,7260000),(10020000,10140000),(12900000,13020000)]),
])
def test_exact_five_windows(seconds, expected):
    assert bounds(seconds) == expected


def test_fractional_rounding_and_boundaries():
    assert round_half_up(2.5) == 3
    windows = five_fractional_windows(120005)
    assert len(windows) == 5
    assert all(w.end_sample - w.start_sample == 120000 for w in windows)
    assert windows[0].start_sample == 0 and windows[-1].end_sample == 120005


def test_short_audio_is_ineligible():
    with pytest.raises(Stage4AudioError):
        five_fractional_windows(119999)


def test_full_decode_downmix_resample_never_truncates_or_pads():
    stereo = torch.stack([torch.ones(882123), torch.zeros(882123)])
    mono = canonical_waveform(stereo, 44100)
    assert mono.ndim == 1
    assert abs(len(mono) - round(882123 * SAMPLE_RATE / 44100)) <= 1
    # Resampler edge transients may slightly perturb a constant signal.
    assert float(mono.mean()) == pytest.approx(0.5, abs=3e-4)


def test_window_bytes_and_pcm_hash_are_deterministic():
    wav = torch.arange(720000, dtype=torch.float32)
    clips = extract_windows(wav)
    assert len(clips) == 5 and all(len(clip) == 120000 for clip in clips)
    assert pcm_sha256(wav) == pcm_sha256(wav.clone())
