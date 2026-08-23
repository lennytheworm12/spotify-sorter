"""Synthesize small example-audio pairs that TEACH the rating rubric.

Deliberately uses pure synthesized tones — none of these clips come from
FMA/MUSDB18 or any judged item, so showing them to reviewers cannot bias
the experiment.

    python evaluation/make_examples.py

Writes MP3s (via ffmpeg when available, otherwise WAV) into
evaluation/static/examples/. Committed to git so both the local server
and the GitHub Pages bundle can serve them.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import torch
import torchaudio

SR = 24000
OUT_DIR = Path(__file__).resolve().parent / "static" / "examples"


def _note(freq: float, dur: float, kind: str) -> np.ndarray:
    t = np.linspace(0.0, dur, int(SR * dur), endpoint=False)
    env = np.minimum(1.0, np.arange(len(t)) / (0.01 * SR)) * np.exp(-t * 2.0)
    if kind == "sine":
        return 0.5 * env * np.sin(2 * np.pi * freq * t)
    if kind == "warm":  # a few harmonics -> warmer tone color
        return 0.35 * env * (
            np.sin(2 * np.pi * freq * t)
            + 0.5 * np.sin(2 * np.pi * freq * 2 * t)
            + 0.25 * np.sin(2 * np.pi * freq * 3 * t)
        )
    if kind == "buzz":  # many harmonics -> bright/buzzy timbre
        return 0.22 * env * sum(
            np.sin(2 * np.pi * freq * k * t) / k for k in range(1, 9)
        )
    raise ValueError(kind)


def melody_sequence(notes: list[float], note_dur: float, kind: str) -> np.ndarray:
    parts = [_note(f, note_dur * 0.92, kind) for f in notes]
    gap = np.zeros(int(SR * 0.03))
    out = []
    for p in parts:
        out += [p, gap]
    return np.concatenate(out)


def rhythm_bed(pattern: list[tuple[float, str]], duration: float, seed: int) -> np.ndarray:
    """Kick/noise-burst groove independent of any melody."""
    rng = np.random.default_rng(seed)
    n = int(SR * duration)
    mix = 0.15 * rng.normal(size=n) * np.exp(-np.arange(n) / (SR * 0.02))
    for start, hit in pattern:
        idx = int(start * SR)
        length = int(0.12 * SR)
        if idx + length > n:
            continue
        t = np.linspace(0.0, 0.12, length)
        if hit == "kick":
            mix[idx : idx + length] += 0.7 * np.sin(2 * np.pi * 65 * t) * np.exp(-t * 30)
        elif hit == "snare":
            mix[idx : idx + length] += 0.4 * rng.normal(size=length) * np.exp(-t * 40)
    return mix


NOTE_FREQS = {"C": 523.25, "D": 587.33, "E": 659.25, "G": 783.99, "A": 880.0, "F": 698.46}


def seq(*names: str) -> list[float]:
    return [NOTE_FREQS[n[0]] * (2 if n.endswith("+") else 1) for n in names]


def _fit_length(wav: np.ndarray, length: int) -> np.ndarray:
    if len(wav) < length:
        wav = np.pad(wav, (0, length - len(wav)))
    return wav[:length]


def build_examples() -> dict[str, np.ndarray]:
    examples: dict[str, np.ndarray] = {}

    # MELODY: identical tune (contour/rhythm of notes), different instrument + tempo
    tune = seq("C", "E", "G", "E", "A", "G", "E", "C")
    melody_a = melody_sequence(tune, 0.34, "sine")
    melody_b = melody_sequence(tune, 0.44, "buzz")
    target = max(len(melody_a), len(melody_b))
    examples["melody_query"] = _fit_length(melody_a, target) + 0.05 * _fit_length(
        rhythm_bed([(i * 0.68, "kick") for i in range(7)], target / SR + 1, 11), target
    )
    examples["melody_neighbor"] = _fit_length(melody_b, target) + 0.05 * _fit_length(
        rhythm_bed([(i * 0.88, "snare") for i in range(6)], target / SR + 1, 12), target
    )

    # RHYTHM: identical groove pattern, completely different pitch content
    pattern = [(0.0, "kick"), (0.25, "snare"), (0.5, "kick"), (0.75, "kick"),
               (1.0, "snare"), (1.25, "kick"), (1.5, "snare"), (1.75, "snare")]
    def loop_pattern(times: float) -> list[tuple[float, str]]:
        out = []
        for rep in range(times):
            out += [(start + rep * 2.0, hit) for start, hit in pattern]
        return out

    bed_a = rhythm_bed(loop_pattern(2), 4.0, 21)
    bed_b = rhythm_bed(loop_pattern(2), 4.0, 22)
    t_a = np.linspace(0, 4.0, int(SR * 4.0), endpoint=False)
    t_b = np.linspace(0, 4.0, int(SR * 4.0), endpoint=False)
    examples["rhythm_query"] = bed_a + 0.18 * np.sin(2 * np.pi * 330.0 * t_a)
    examples["rhythm_neighbor"] = bed_b + 0.18 * np.sin(2 * np.pi * 660.0 * t_b)

    # TIMBRE: same buzzy tone color, entirely different tunes
    examples["timbre_query"] = melody_sequence(seq("G", "F", "E", "D", "E", "G"), 0.30, "warm")
    examples["timbre_neighbor"] = melody_sequence(seq("A", "G", "E", "C", "D", "C"), 0.38, "warm")

    return examples


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    has_ffmpeg = shutil.which("ffmpeg") is not None

    for name, wav in build_examples().items():
        assert np.isfinite(wav).all()
        peak = np.abs(wav).max()
        if peak > 0:
            wav = wav / peak * 0.85
        tensor = torch.from_numpy(wav.astype(np.float32)).unsqueeze(0)
        if has_ffmpeg:
            out_path = OUT_DIR / f"{name}.mp3"
            torchaudio.save(str(out_path), tensor, SR, format="mp3")
        else:
            out_path = OUT_DIR / f"{name}.wav"
            torchaudio.save(str(out_path), tensor, SR)
        print(f"{out_path.name}: {out_path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
