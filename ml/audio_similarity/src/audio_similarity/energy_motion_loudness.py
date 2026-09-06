"""Original-channel EBU R128 measurement for Stage 5F.1."""

from __future__ import annotations

import math
import os
import re
import subprocess

import numpy as np
import torch

from .energy_motion_config import ExtractionConfig


SUMMARY_RE = re.compile(
    r"Summary:\s*.*?Integrated loudness:\s*I:\s*(?P<i>-?[\d.]+) LUFS"
    r".*?Loudness range:\s*LRA:\s*(?P<lra>-?[\d.]+) LU",
    re.DOTALL,
)


def parse_ebur128_summary(stderr: str) -> tuple[float, float]:
    matches = list(SUMMARY_RE.finditer(stderr))
    if not matches:
        raise ValueError("FFmpeg ebur128 final Summary block was not found")
    match = matches[-1]
    return float(match.group("i")), float(match.group("lra"))


def measure_source_level(
    waveform: torch.Tensor,
    sample_rate: int,
    config: ExtractionConfig,
    timeout_seconds: int = 180,
) -> dict[str, float | None]:
    array = waveform.detach().cpu().numpy().astype(np.float32, copy=False)
    if array.ndim != 2 or not np.isfinite(array).all():
        raise ValueError("loudness input must be finite channels-by-samples audio")
    channels = int(array.shape[0])
    interleaved = np.ascontiguousarray(array.T, dtype="<f4").tobytes()
    command = [
        "ffmpeg", "-hide_banner", "-nostats", "-loglevel", "info",
        "-f", "f32le", "-ar", str(sample_rate), "-ac", str(channels), "-i", "pipe:0",
        "-af", f"ebur128=peak=none:dualmono={'true' if config.loudness_dualmono else 'false'}:framelog=verbose",
        "-f", "null", "-",
    ]
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    completed = subprocess.run(
        command, input=interleaved, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        timeout=timeout_seconds, check=False, env=env,
    )
    stderr = completed.stderr.decode("utf-8", "replace")
    if completed.returncode != 0:
        raise RuntimeError(f"FFmpeg ebur128 failed with exit {completed.returncode}: {stderr[-500:]}")
    integrated, lra = parse_ebur128_summary(stderr)
    square_mean = float(np.mean(array.astype(np.float64) ** 2))
    peak = float(np.max(np.abs(array)))
    rms_dbfs = 10.0 * math.log10(square_mean) if square_mean > 0 else None
    peak_dbfs = 20.0 * math.log10(peak) if peak > 0 else None
    return {
        "integrated_loudness_lufs": integrated,
        "loudness_range_lu": lra,
        "source_rms_dbfs": rms_dbfs,
        "sample_peak_dbfs": peak_dbfs,
        "crest_factor_db": peak_dbfs - rms_dbfs if peak_dbfs is not None and rms_dbfs is not None else None,
        "clipped_sample_fraction": float(np.mean(np.abs(array) >= 0.999)),
    }
