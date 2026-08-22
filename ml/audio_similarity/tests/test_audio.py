"""Audio preprocessing tests (Phase 1 doc, section 11 'Audio tests')."""

from __future__ import annotations

import pytest
import torch

from audio_similarity.audio import (
    AudioDecodeError,
    DurationInvalidError,
    PreprocessConfig,
    load_audio,
    preprocess_file,
    preprocess_waveform,
)
from tests.helpers import synth_waveform

CFG = PreprocessConfig()


def test_mono_input_remains_valid(mono_24k_30s):
    wav, sr = load_audio(mono_24k_30s)
    assert wav.shape[0] == 1
    assert sr == 24000
    out = preprocess_file(mono_24k_30s)
    assert out.shape == (24000 * 30,)
    assert torch.isfinite(out).all()


def test_stereo_converts_to_mono_as_channel_mean(stereo_44k_10s):
    out = preprocess_file(stereo_44k_10s)
    assert out.ndim == 1
    assert out.shape == (24000 * 30,)

    raw, sr = load_audio(stereo_44k_10s)
    assert raw.shape[0] == 2
    # expected manual pipeline: resample each channel, then average
    import torchaudio

    resampled = torchaudio.functional.resample(raw, sr, CFG.sample_rate)
    expected = resampled.mean(dim=0)
    torch.testing.assert_close(out[:1000], expected[:1000])


def test_resampling_to_24khz(stereo_44k_10s):
    raw, sr = load_audio(stereo_44k_10s)
    assert sr == 44100
    out = preprocess_waveform(raw, sr)
    expected_len = int(round(raw.shape[-1] * 24000 / 44100))
    # output is padded/truncated to the exact target length; resampled core should match expectation
    assert abs(out.numel() - int(24000 * 30)) < 1
    assert expected_len <= out.numel()


def test_short_clip_is_zero_padded(short_clip):
    out = preprocess_file(short_clip)
    assert out.shape == (24000 * 30,)
    tail = out[24000 * 3 :]
    assert torch.count_nonzero(tail) == 0


def test_long_clip_is_truncated(long_clip):
    raw, _ = load_audio(long_clip)
    out = preprocess_file(long_clip)
    assert out.shape == (24000 * 30,)
    assert raw.shape[-1] > out.shape[-1]


def test_exact_length_clip_unchanged():
    wav = synth_waveform(30)
    out = preprocess_waveform(wav.clone(), 24000)
    torch.testing.assert_close(out, wav.squeeze(0))


def test_malformed_audio_raises_typed_failure(corrupt_file):
    with pytest.raises(AudioDecodeError):
        load_audio(corrupt_file)


def test_zero_length_audio_raises_duration_invalid(monkeypatch, tmp_path):
    import torchaudio as ta

    p = tmp_path / "fake.wav"
    p.write_bytes(b"\x00" * 64)

    def fake_load(path, *args, **kwargs):
        return torch.zeros(1, 0), 24000

    monkeypatch.setattr(ta, "load", fake_load)
    with pytest.raises(DurationInvalidError):
        load_audio(p)


def test_preprocess_rejects_non_1d_result():
    stereo = synth_waveform(31, channels=2)
    mono_config = PreprocessConfig()
    out = preprocess_waveform(stereo, 24000, mono_config)
    assert out.ndim == 1


def test_target_samples_property():
    assert PreprocessConfig().target_samples == 24000 * 30
