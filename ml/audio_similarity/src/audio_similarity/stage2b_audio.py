"""Exact canonical PCM evidence and identity hashing for Stage 2B."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .audio import preprocess_file
from .holistic_batch import _excerpt_bounds

SAMPLE_RATE = 24000
CENTER5_SAMPLES = 5 * SAMPLE_RATE


@dataclass(frozen=True)
class PcmIdentity:
    track_id: int
    source_sha256: str
    canonical_30s_pcm_sha256: str
    center5_v1_pcm_sha256: str
    canonical_samples: int
    excerpt_start_sample: int
    excerpt_end_sample: int


def float32_le_bytes(samples: np.ndarray) -> bytes:
    array = np.asarray(samples, dtype="<f4")
    if not np.isfinite(array).all():
        raise ValueError("non-finite canonical PCM")
    return array.tobytes(order="C")


def canonical_pcm(path: str | Path) -> tuple[np.ndarray, np.ndarray, int, int]:
    canonical = np.asarray(preprocess_file(path), dtype=np.float32)
    start, end = _excerpt_bounds(canonical, "center5")
    excerpt = canonical[start:end]
    if canonical.shape != (30 * SAMPLE_RATE,):
        raise ValueError(f"canonical PCM shape changed: {canonical.shape}")
    if excerpt.shape != (CENTER5_SAMPLES,):
        raise ValueError(f"center5_v1 shape changed: {excerpt.shape}")
    return canonical, excerpt, start, end


def compute_pcm_identity(track_id: int, source_sha256: str, path: str | Path) -> PcmIdentity:
    canonical, excerpt, start, end = canonical_pcm(path)
    return PcmIdentity(
        track_id=int(track_id),
        source_sha256=str(source_sha256),
        canonical_30s_pcm_sha256=hashlib.sha256(float32_le_bytes(canonical)).hexdigest(),
        center5_v1_pcm_sha256=hashlib.sha256(float32_le_bytes(excerpt)).hexdigest(),
        canonical_samples=len(canonical),
        excerpt_start_sample=start,
        excerpt_end_sample=end,
    )


class PcmIdentityCache:
    """Atomic local cache keyed by source SHA plus frozen contract hash."""

    def __init__(self, path: str | Path, contract_hash: str):
        self.path = Path(path) / f"identities-{contract_hash}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self._rows = payload if isinstance(payload, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            self._rows: dict[str, dict] = {}

    def get_or_compute(self, track_id: int, source_sha256: str, path: str | Path) -> PcmIdentity:
        cached = self._rows.get(source_sha256)
        if cached is not None:
            # Track ID is provenance, not cache identity; preserve the requested ID.
            return PcmIdentity(track_id=int(track_id), **{k: v for k, v in cached.items() if k != "track_id"})
        identity = compute_pcm_identity(track_id, source_sha256, path)
        self._rows[source_sha256] = asdict(identity)
        self._write()
        return identity

    def _write(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._rows, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)
