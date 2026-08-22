"""Deterministic audio-signal visualization for the 0x-alpha experiment.

Phase 2 design sections 46.4-46.6 and 48. Three versioned views:

    waveform_v1      amplitude vs time (ablation)
    linear_stft_v1   STFT magnitude in dB, LINEAR physical frequency axis
    log_mel_v1       mel filterbank + dB (perceptually motivated comparison)

All rendering is numpy-only with explicit frozen parameters — no plotting
library defaults. Output is a dependency-free deterministic grayscale PNG.
Images carry opaque identifiers only; callers must never embed artist,
title, album, genre, lyrics, or model scores.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass

import numpy as np

CANONICAL_SAMPLE_RATE = 24000
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class SignalRenderError(ValueError):
    """Raised for invalid render inputs or configurations."""


def sha256_audio(waveform: np.ndarray, sample_rate: int) -> str:
    wav = np.ascontiguousarray(np.asarray(waveform, dtype=np.float64))
    digest = hashlib.sha256(b"%d|%s" % (sample_rate, wav.tobytes())).hexdigest()
    return digest


# ---------------------------------------------------------------------------
# canonicalization: stereo -> mono, resample to the canonical rate
# ---------------------------------------------------------------------------


def canonicalize_waveform(
    waveform: np.ndarray,
    sample_rate: int,
    target_sample_rate: int = CANONICAL_SAMPLE_RATE,
) -> np.ndarray:
    """Return a 1-D float64 mono waveform at the target sample rate.

    Stereo/multichannel input is reduced by channel mean (the same rule as
    the MERIT preprocessing path). Resampling is linear interpolation —
    adequate and fully deterministic for visualization purposes; this is a
    renderer-local choice recorded in provenance.
    """
    wav = np.asarray(waveform, dtype=np.float64)
    if wav.ndim == 2:
        wav = wav.mean(axis=-1 if wav.shape[-1] <= 8 else 0)
    if wav.ndim != 1:
        raise SignalRenderError(f"expected 1-D or 2-D waveform, got shape {wav.shape}")
    if not np.isfinite(wav).all():
        raise SignalRenderError("waveform contains non-finite samples")
    if sample_rate <= 0:
        raise SignalRenderError(f"invalid sample rate {sample_rate}")
    if sample_rate == target_sample_rate:
        return wav
    n_target = max(1, int(round(len(wav) * target_sample_rate / sample_rate)))
    x_old = np.linspace(0.0, 1.0, num=len(wav), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_target, endpoint=False)
    return np.interp(x_new, x_old, wav)


# ---------------------------------------------------------------------------
# grayscale PNG writer (stdlib only; byte-deterministic given identical pixels)
# ---------------------------------------------------------------------------


def encode_png_grayscale(pixels: np.ndarray) -> bytes:
    """Encode a HxW uint8 array as a baseline grayscale PNG."""
    if pixels.dtype != np.uint8 or pixels.ndim != 2:
        raise SignalRenderError("PNG encoder expects a 2-D uint8 array")
    height, width = pixels.shape

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw = b"".join(b"\x00" + pixels[row].tobytes() for row in range(height))
    return _PNG_SIGNATURE + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, level=9)) + chunk(b"IEND", b"")


def _resize_bilinear(matrix: np.ndarray, height: int, width: int) -> np.ndarray:
    """Deterministic bilinear resize of a 2-D float array to (height, width)."""
    src_h, src_w = matrix.shape
    if src_h == height and src_w == width:
        return matrix
    row_positions = np.linspace(0, src_h - 1, num=height)
    col_positions = np.linspace(0, src_w - 1, num=width)
    r0 = np.clip(np.floor(row_positions).astype(np.int64), 0, src_h - 2)[:, None]   # (H,1)
    c0 = np.clip(np.floor(col_positions).astype(np.int64), 0, src_w - 2)[None, :]   # (1,W)
    rf = (row_positions - r0[:, 0])[:, None]                                        # (H,1)
    cf = (col_positions - c0[0, :])[None, :]                                        # (1,W)
    top_left = matrix[r0, c0]
    top_right = matrix[r0, c0 + 1]
    bottom_left = matrix[r0 + 1, c0]
    bottom_right = matrix[r0 + 1, c0 + 1]
    top = top_left * (1 - cf) + top_right * cf
    bottom = bottom_left * (1 - cf) + bottom_right * cf
    return top * (1 - rf) + bottom * rf


def _to_uint8_image(normalized: np.ndarray, height: int, width: int) -> np.ndarray:
    resized = _resize_bilinear(np.clip(normalized, 0.0, 1.0), height, width)
    return np.round(resized * 255.0).astype(np.uint8)


def _db_scale(magnitude: np.ndarray, top_db: float) -> np.ndarray:
    power = magnitude**2
    log_power = 10.0 * np.log10(power + 1e-12)
    floor = log_power.max() - top_db
    return np.clip(log_power, floor, None)


def _stft_magnitude(wav: np.ndarray, n_fft: int, hop_length: int) -> np.ndarray:
    """Deterministic numpy STFT magnitude (freq bins x time frames).

    Short inputs are zero-padded to one window so silent/short segments still
    produce a valid finite image.
    """
    if len(wav) < n_fft:
        wav = np.pad(wav, (0, n_fft - len(wav)))
    n_frames = 1 + (len(wav) - n_fft) // hop_length
    frames = np.lib.stride_tricks.sliding_window_view(wav, n_fft)[::hop_length]
    windowed = frames[:n_frames] * np.hanning(n_fft)
    spectrum = np.fft.rfft(windowed, axis=-1)
    return np.abs(spectrum.T)  # (freq bins, frames)


def _mel_filterbank(n_mels: int, n_freq_bins: int, sample_rate: int, fmin: float, fmax: float) -> np.ndarray:
    def hz_to_mel(freq):
        return 2595.0 * np.log10(1.0 + np.asarray(freq) / 700.0)

    def mel_to_hz(mel):
        return 700.0 * (10 ** (np.asarray(mel) / 2595.0) - 1.0)

    freqs = np.linspace(0.0, sample_rate / 2.0, n_freq_bins)
    mel_points = np.linspace(hz_to_mel(fmin), hz_to_mel(min(fmax, sample_rate / 2.0)), n_mels + 2)
    hz_points = mel_to_hz(mel_points)
    filterbank = np.zeros((n_mels, n_freq_bins))
    for m in range(n_mels):
        left, center, right = hz_points[m], hz_points[m + 1], hz_points[m + 2]
        up = (freqs - left) / max(center - left, 1e-9)
        down = (right - freqs) / max(right - center, 1e-9)
        filterbank[m] = np.clip(np.minimum(up, down), 0.0, None)
    # normalize each filter so peak response is 1 (explicit, versioned choice)
    peaks = filterbank.max(axis=1, keepdims=True)
    peaks[peaks == 0] = 1.0
    return filterbank / peaks


@dataclass(frozen=True)
class RendererConfig:
    sample_rate: int = CANONICAL_SAMPLE_RATE
    n_fft: int = 2048
    hop_length: int = 512
    n_mels: int = 128
    fmin: float = 20.0
    fmax: float = 12000.0
    top_db: float = 80.0
    image_width: int = 1024
    image_height: int = 512

    def __post_init__(self) -> None:
        if self.n_fft < 2 or self.hop_length < 1:
            raise SignalRenderError("n_fft must be >=2 and hop_length >=1")
        if self.image_width < 1 or self.image_height < 1:
            raise SignalRenderError("image dimensions must be positive")


@dataclass(frozen=True)
class RenderResult:
    view_name: str
    view_version: int
    image_png: bytes
    image_sha256: str
    provenance: dict

    @property
    def identity(self) -> str:
        return f"{self.view_name}_v{self.view_version}"


def _base_provenance(cfg: RendererConfig, source_audio_hash: str, segment_start_sec: float | None, segment_end_sec: float | None) -> dict:
    prov = {
        "sample_rate": cfg.sample_rate,
        "n_fft": cfg.n_fft,
        "hop_length": cfg.hop_length,
        "top_db": cfg.top_db,
        "image_width": cfg.image_width,
        "image_height": cfg.image_height,
        "frequency_scale": None,
        "amplitude_scale": "dB",
        "source_audio_hash": source_audio_hash,
        "segment_start_sec": segment_start_sec,
        "segment_end_sec": segment_end_sec,
        "resampler": f"linear_interp_v1@{cfg.sample_rate}Hz",
    }
    return prov


def _finish(view_name: str, view_version: int, normalized: np.ndarray, prov: dict) -> RenderResult:
    pixels = _to_uint8_image(normalized, prov["image_height"], prov["image_width"])
    png = encode_png_grayscale(pixels)
    prov["pixel_sha256"] = hashlib.sha256(pixels.tobytes()).hexdigest()
    return RenderResult(
        view_name=view_name,
        view_version=view_version,
        image_png=png,
        image_sha256=hashlib.sha256(png).hexdigest(),
        provenance=prov,
    )


def render_waveform_v1(
    waveform: np.ndarray,
    sample_rate: int,
    config: RendererConfig | None = None,
    segment_start_sec: float | None = None,
    segment_end_sec: float | None = None,
    source_audio_hash: str | None = None,
) -> RenderResult:
    """OX-V0: amplitude vs time envelope. Ablation view."""
    cfg = config or RendererConfig()
    wav = canonicalize_waveform(waveform, sample_rate, cfg.sample_rate)
    audio_hash = source_audio_hash or sha256_audio(wav, cfg.sample_rate)
    prov = _base_provenance(cfg, audio_hash, segment_start_sec, segment_end_sec)
    prov["frequency_scale"] = "none"
    prov["amplitude_scale"] = "linear_amplitude_envelope"

    columns = min(cfg.image_width, max(1, len(wav)))
    edges = np.linspace(0, len(wav), num=columns + 1).astype(np.int64)
    envelope = np.zeros(columns)
    for i in range(columns):
        bucket = wav[edges[i] : max(edges[i] + 1, edges[i + 1])]
        envelope[i] = np.abs(bucket).max() if bucket.size else 0.0

    peak = envelope.max()
    normalized = envelope / peak if peak > 0 else envelope  # silence -> uniform zero
    return _finish("waveform", 1, normalized[None, :], prov)


def render_linear_stft_v1(
    waveform: np.ndarray,
    sample_rate: int,
    config: RendererConfig | None = None,
    segment_start_sec: float | None = None,
    segment_end_sec: float | None = None,
    source_audio_hash: str | None = None,
) -> RenderResult:
    """OX-V1: STFT dB magnitude on a LINEAR physical frequency axis.

    Rows map linearly from 0 Hz to Nyquist — no mel warping.
    """
    cfg = config or RendererConfig()
    wav = canonicalize_waveform(waveform, sample_rate, cfg.sample_rate)
    audio_hash = source_audio_hash or sha256_audio(wav, cfg.sample_rate)
    prov = _base_provenance(cfg, audio_hash, segment_start_sec, segment_end_sec)
    prov["frequency_scale"] = "linear"

    magnitude = _stft_magnitude(wav, cfg.n_fft, cfg.hop_length)
    db = _db_scale(magnitude, cfg.top_db)
    normalized = (db - db.min()) / max(db.max() - db.min(), 1e-12)
    return _finish("linear_stft", 1, normalized, prov)


def render_log_mel_v1(
    waveform: np.ndarray,
    sample_rate: int,
    config: RendererConfig | None = None,
    segment_start_sec: float | None = None,
    segment_end_sec: float | None = None,
    source_audio_hash: str | None = None,
) -> RenderResult:
    """OX-V2: mel filterbank + dB, perceptually motivated comparison view."""
    cfg = config or RendererConfig()
    wav = canonicalize_waveform(waveform, sample_rate, cfg.sample_rate)
    audio_hash = source_audio_hash or sha256_audio(wav, cfg.sample_rate)
    prov = _base_provenance(cfg, audio_hash, segment_start_sec, segment_end_sec)
    prov["frequency_scale"] = "mel"
    prov["n_mels"] = cfg.n_mels
    prov["fmin"] = cfg.fmin
    prov["fmax"] = cfg.fmax
    prov["mel_formula"] = "htk_2595_log10_v1"

    magnitude = _stft_magnitude(wav, cfg.n_fft, cfg.hop_length)
    power = magnitude**2
    n_freq_bins = power.shape[0]
    filterbank = _mel_filterbank(cfg.n_mels, n_freq_bins, cfg.sample_rate, cfg.fmin, cfg.fmax)
    mel_power = filterbank @ power
    db = _db_scale(np.sqrt(mel_power), cfg.top_db)
    normalized = (db - db.min()) / max(db.max() - db.min(), 1e-12)
    return _finish("log_mel", 1, normalized, prov)


RENDERERS = {
    "waveform": render_waveform_v1,
    "linear_stft": render_linear_stft_v1,
    "log_mel": render_log_mel_v1,
}

DEFAULT_VIEW_PARAMS = {
    "waveform": {"sample_rate": CANONICAL_SAMPLE_RATE},
    "linear_stft": {"sample_rate": CANONICAL_SAMPLE_RATE, "frequency_axis": "linear"},
    "log_mel": {"sample_rate": CANONICAL_SAMPLE_RATE},
}


def get_renderer(name: str) -> callable:
    if name not in RENDERERS:
        raise KeyError(f"unknown renderer '{name}'; known: {sorted(RENDERERS)}")
    return RENDERERS[name]
