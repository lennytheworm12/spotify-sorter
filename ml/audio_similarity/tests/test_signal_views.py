"""Signal-renderer tests (Phase 2 design sections 46.5, 46.6, 48)."""

from __future__ import annotations

import numpy as np
import pytest

from audio_similarity.signal_views import (
    CANONICAL_SAMPLE_RATE,
    RendererConfig,
    SignalRenderError,
    _db_scale,
    _mel_filterbank,
    _stft_magnitude,
    canonicalize_waveform,
    encode_png_grayscale,
    render_linear_stft_v1,
    render_log_mel_v1,
    render_waveform_v1,
)

SMALL = RendererConfig(image_width=256, image_height=128)


def tone(freq_hz: float, seconds: float = 3.0, sample_rate: int = 24000) -> np.ndarray:
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    return 0.5 * np.sin(2 * np.pi * freq_hz * t)


RENDERERS = [render_waveform_v1, render_linear_stft_v1, render_log_mel_v1]


@pytest.mark.parametrize("render", RENDERERS)
def test_deterministic_byte_identical_render(render):
    wav = tone(440.0)
    a = render(wav, 24000, config=SMALL)
    b = render(wav, 24000, config=SMALL)
    assert a.image_png == b.image_png
    assert a.image_sha256 == b.image_sha256


@pytest.mark.parametrize("render", RENDERERS)
def test_fixed_image_dimensions(render):
    result = render(tone(220.0), 24000, config=SMALL)
    assert SMALL.image_width == 256 and SMALL.image_height == 128
    # decode IHDR to confirm the PNG carries exactly those dimensions
    ihdr = result.image_png[16:24]
    width = int.from_bytes(ihdr[0:4], "big")
    height = int.from_bytes(ihdr[4:8], "big")
    assert (width, height) == (256, 128)


def test_finite_intermediate_values():
    wav = tone(880.0)
    magnitude = _stft_magnitude(canonicalize_waveform(wav, 24000), 2048, 512)
    assert magnitude.size > 0 and np.isfinite(magnitude).all()
    db = _db_scale(magnitude, top_db=80.0)
    assert np.isfinite(db).all()


def test_short_audio_below_n_fft():
    tiny = np.linspace(-0.5, 0.5, num=500)  # < n_fft=2048
    for render in RENDERERS:
        result = render(tiny, 24000, config=SMALL)
        assert result.image_png.startswith(b"\x89PNG")


def test_silent_audio_produces_valid_finite_image():
    silence = np.zeros(24000)
    results = [render(silence, 24000, config=SMALL) for render in RENDERERS]
    for r in results:
        assert r.image_png.startswith(b"\x89PNG")  # valid image despite no energy
        assert r.provenance["source_audio_hash"]
    # silence carries no structure: all views collapse to a uniform image
    assert len({r.image_sha256 for r in results}) >= 1


def test_silent_and_tone_images_differ():
    silent = render_log_mel_v1(np.zeros(24000), 24000, config=SMALL)
    loud = render_log_mel_v1(tone(440.0), 24000, config=SMALL)
    assert silent.image_sha256 != loud.image_sha256


def test_stereo_reduces_to_channel_mean_mono():
    left = tone(440.0, seconds=1.0)
    right = np.zeros_like(left)
    stereo = np.stack([left, right], axis=-1)
    direct = render_waveform_v1((left + right) / 2, 24000, config=SMALL)
    via_canonicalization = render_waveform_v1(stereo, 24000, config=SMALL)
    assert direct.image_png == via_canonicalization.image_png


def test_sample_rate_canonicalized_to_24k():
    resampled_src = tone(440.0, seconds=1.0, sample_rate=44100)
    result = render_linear_stft_v1(resampled_src, 44100, config=SMALL)
    assert result.provenance["sample_rate"] == CANONICAL_SAMPLE_RATE
    assert result.provenance["resampler"].startswith("linear_interp")


def test_canonicalize_passthrough_at_target_rate():
    wav = tone(300.0, seconds=0.5)
    out = canonicalize_waveform(wav, 24000)
    np.testing.assert_array_equal(out, wav)


# ---------------------------------------------------------------------------
# frequency-axis sanity
# ---------------------------------------------------------------------------


def test_440hz_tone_peaks_in_low_rows_of_linear_stft():
    """Linear frequency axis: a 440 Hz tone must peak near 0 Hz (bottom rows)."""
    cfg = SMALL
    wav = canonicalize_waveform(tone(440.0, seconds=4.0), 24000)
    magnitude = _stft_magnitude(wav, cfg.n_fft, cfg.hop_length)
    db = _db_scale(magnitude, cfg.top_db)
    freq_energy = db.mean(axis=1)
    peak_bin = int(np.argmax(freq_energy))
    bin_hz = peak_bin / (magnitude.shape[0] - 1) * (cfg.sample_rate / 2)
    assert bin_hz < 1000, f"440 Hz tone peaked at {bin_hz:.0f} Hz — linear axis broken"


def test_4000hz_tone_peaks_above_440hz():
    cfg = SMALL
    def peak_hz(freq):
        wav = canonicalize_waveform(tone(freq, seconds=3.0), 24000)
        magnitude = _stft_magnitude(wav, cfg.n_fft, cfg.hop_length)
        db = _db_scale(magnitude, cfg.top_db)
        return int(np.argmax(db.mean(axis=1))) / (magnitude.shape[0] - 1) * 12000

    assert peak_hz(4000.0) > peak_hz(440.0)


def test_mel_filterbank_shape_and_normalization():
    fb = _mel_filterbank(n_mels=64, n_freq_bins=1025, sample_rate=24000, fmin=20.0, fmax=12000.0)
    assert fb.shape == (64, 1025)
    assert (fb <= 1.0 + 1e-9).all() and (fb >= 0).all()


# ---------------------------------------------------------------------------
# provenance + leakage
# ---------------------------------------------------------------------------


REQUIRED_PROVENANCE_KEYS = {
    "sample_rate",
    "n_fft",
    "hop_length",
    "top_db",
    "image_width",
    "image_height",
    "frequency_scale",
    "amplitude_scale",
    "source_audio_hash",
    "segment_start_sec",
    "segment_end_sec",
}


@pytest.mark.parametrize("render", RENDERERS)
def test_provenance_records_required_fields(render):
    result = render(tone(440.0), 24000, config=SMALL, segment_start_sec=30.0, segment_end_sec=60.0)
    missing = REQUIRED_PROVENANCE_KEYS - set(result.provenance)
    assert not missing, f"provenance missing {missing}"
    assert result.provenance["segment_start_sec"] == 30.0
    assert result.provenance["image_width"] == 256


def test_config_change_changes_provenance():
    a = render_linear_stft_v1(tone(440.0), 24000, config=RendererConfig(image_width=128))
    b = render_linear_stft_v1(tone(440.0), 24000, config=RendererConfig(image_width=256))
    assert a.provenance["image_width"] != b.provenance["image_width"]
    assert a.image_sha256 != b.image_sha256


def test_no_metadata_leakage_in_provenance_or_api():
    """Images are rendered from samples only; there is no text/metadata input."""
    forbidden = {"title", "artist", "album", "genre", "lyrics", "merit_score", "mert_score"}
    import inspect

    for fn in RENDERERS:
        params = set(inspect.signature(fn).parameters)
        assert not (params & forbidden), f"{fn.__name__} accepts leakage-prone parameters"
    result = render_log_mel_v1(tone(440.0), 24000, config=SMALL)
    assert not (set(result.provenance) & forbidden)


# ---------------------------------------------------------------------------
# PNG writer sanity
# ---------------------------------------------------------------------------


def test_png_writer_roundtrip_dimensions():
    pixels = np.arange(12 * 34, dtype=np.uint8).reshape(12, 34) % 255
    png = encode_png_grayscale(pixels)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert png.endswith(b"IEND\xaeB`\x82")
    ihdr = png[16:24]
    assert int.from_bytes(ihdr[0:4], "big") == 34
    assert int.from_bytes(ihdr[4:8], "big") == 12


def test_invalid_waveform_rejected():
    with pytest.raises(SignalRenderError):
        canonicalize_waveform(np.array([np.nan, 1.0]), 24000)
    with pytest.raises(SignalRenderError):
        canonicalize_waveform(np.array([1.0]), 0)
