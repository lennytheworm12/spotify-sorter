"""Deterministic waveform and native-fusion view plans for Stage 5E.1."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np


SAMPLE_RATE = 48_000
CHUNK_SECONDS = 10
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_SECONDS
MEL_HOP_SAMPLES = 480
NATIVE_CHUNK_FRAMES = CHUNK_SAMPLES // MEL_HOP_SAMPLES + 1
SAMPLING_SEED = 20260905


@dataclass(frozen=True)
class Chunk:
    index: int
    start_sample: int
    end_sample: int
    padded_samples: int

    def as_dict(self) -> dict[str, int]:
        return vars(self)


def full_song_chunks(sample_count: int) -> list[Chunk]:
    """Cover every source sample once; repeat-pad only the final short chunk."""
    if sample_count <= 0:
        raise ValueError("full-song sampling requires a nonempty waveform")
    chunks = []
    for index, start in enumerate(range(0, sample_count, CHUNK_SAMPLES)):
        end = min(sample_count, start + CHUNK_SAMPLES)
        chunks.append(Chunk(index, start, end, CHUNK_SAMPLES - (end - start)))
    if chunks[0].start_sample != 0 or chunks[-1].end_sample != sample_count:
        raise AssertionError("full-song chunk plan does not cover the source")
    if any(left.end_sample != right.start_sample for left, right in zip(chunks, chunks[1:])):
        raise AssertionError("full-song chunk plan has a gap or overlap")
    return chunks


def track_seed(source_sha256: str, seed: int = SAMPLING_SEED) -> int:
    if len(source_sha256) != 64:
        raise ValueError("source SHA-256 is required for deterministic sampling")
    digest = hashlib.sha256(f"{seed}\0{source_sha256}".encode()).digest()
    return int.from_bytes(digest[:4], "big")


def native_fusion_plan(sample_count: int, source_sha256: str) -> dict[str, Any]:
    """Freeze LAION's global + front/middle/back mel selection distribution."""
    if sample_count <= CHUNK_SAMPLES:
        return {
            "sample_count_48khz": sample_count,
            "total_mel_frames": sample_count // MEL_HOP_SAMPLES + 1,
            "chunk_frames": NATIVE_CHUNK_FRAMES,
            "longer": False,
            "local_start_frames": [0, 0, 0],
            "compatibility_waveform_crop_start_sample": 0,
            "seed": track_seed(source_sha256),
        }
    total_frames = sample_count // MEL_HOP_SAMPLES + 1
    available = total_frames - NATIVE_CHUNK_FRAMES + 1
    if available <= 0:
        raise ValueError("invalid native fusion frame geometry")
    ranges = np.array_split(np.arange(available, dtype=np.int64), 3)
    if any(not len(values) for values in ranges):
        raise ValueError("native fusion thirds are empty")
    rng = np.random.RandomState(track_seed(source_sha256))
    starts = [int(rng.choice(values)) for values in ranges]
    crop_start = int(rng.randint(0, sample_count - CHUNK_SAMPLES + 1))
    return {
        "sample_count_48khz": sample_count,
        "total_mel_frames": total_frames,
        "chunk_frames": NATIVE_CHUNK_FRAMES,
        "longer": True,
        "local_start_frames": starts,
        "compatibility_waveform_crop_start_sample": crop_start,
        "seed": track_seed(source_sha256),
    }


def sampling_plan(sample_count: int, source_sha256: str) -> dict[str, Any]:
    chunks = full_song_chunks(sample_count)
    native = native_fusion_plan(sample_count, source_sha256)
    payload = {
        "schema_version": "stage5e1-track-sampling-plan-v1",
        "sample_rate_hz": SAMPLE_RATE,
        "full_song_chunks": [chunk.as_dict() for chunk in chunks],
        "full_song_chunk_weighting": "equal_per_chunk_including_final_repeat-padded_chunk",
        "native_fusion": native,
    }
    payload["sampling_plan_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


def normalized_mean(vectors: list[np.ndarray] | np.ndarray) -> np.ndarray:
    values = np.asarray(vectors, dtype=np.float64)
    if values.ndim != 2 or not len(values) or not np.isfinite(values).all():
        raise ValueError("invalid embedding matrix for normalized mean")
    norms = np.linalg.norm(values, axis=1)
    if np.any(norms <= 0):
        raise ValueError("cannot normalize a zero embedding")
    mean = np.mean(values / norms[:, None], axis=0)
    norm = float(np.linalg.norm(mean))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("pooled embedding is zero or non-finite")
    return (mean / norm).astype(np.float32)
