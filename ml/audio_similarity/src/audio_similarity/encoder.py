"""Encoder boundary for Phase 2 (design section 10).

Sampling/aggregation never import MERIT. Encoders implement the small
`AudioEncoder` protocol; adapters wrap real encoders later. The FakeEncoder
keeps the fast test suite free of MERT/MERIT downloads, CUDA, and GPUs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class EncodedSegment:
    """Result of encoding one audio segment."""

    factor_embeddings: dict[str, np.ndarray]
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, vector in self.factor_embeddings.items():
            arr = np.asarray(vector)
            if arr.ndim != 1:
                raise ValueError(f"factor '{name}' embedding must be 1-D, got shape {arr.shape}")


@runtime_checkable
class AudioEncoder(Protocol):
    name: str
    max_window_seconds: float | None

    def encode(self, waveform: np.ndarray, sample_rate: int) -> EncodedSegment: ...


class FakeEncoder:
    """Deterministic hash-based encoder for tests and plumbing validation.

    Produces a fixed number of unit factors whose values derive stably from
    the waveform content — identical input gives identical output, different
    input gives different output, no models required.
    """

    def __init__(
        self,
        name: str = "fake",
        dim: int = 32,
        factors: tuple[str, ...] = ("signal",),
        max_window_seconds: float | None = 30.0,
        seed: int = 1234,
    ):
        self.name = name
        self.max_window_seconds = max_window_seconds
        self._dim = int(dim)
        self._factors = tuple(factors)
        self._seed = seed

    def encode(self, waveform: np.ndarray, sample_rate: int) -> EncodedSegment:
        import hashlib

        wav = np.ascontiguousarray(np.asarray(waveform, dtype=np.float64))
        if wav.ndim == 2:
            wav = wav.mean(axis=-1)
        digest_input = b"%d|%d|%s" % (sample_rate, wav.size, wav.tobytes())
        embeddings = {}
        for offset, factor in enumerate(self._factors):
            digest = hashlib.sha256(
                b"%d|%s|%s|%s" % (self._seed, factor.encode(), b"", digest_input)
            ).digest()
            gen = np.random.default_rng(int.from_bytes(digest[:8], "little"))
            vec = gen.normal(size=self._dim)
            embeddings[factor] = vec / np.linalg.norm(vec)
        return EncodedSegment(
            factor_embeddings=embeddings,
            metadata={"encoder": self.name, "samples": int(wav.size)},
        )
