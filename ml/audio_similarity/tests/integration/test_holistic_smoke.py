"""Stage 9 heavy smoke gate: 3 real FMA clips through every holistic encoder.

Downloads MuQ-MuLan-large and the CLAP checkpoint on first use.
Run deliberately:

    cd ml/audio_similarity && uv run pytest tests/integration/test_holistic_smoke.py -m heavy -o addopts=""
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from audio_similarity.audio import preprocess_file
from audio_similarity.sampling import sample_segments

pytestmark = pytest.mark.heavy

AUDIO_ROOT = Path(__file__).resolve().parents[2] / "data" / "fma" / "fma_small"
SMOKE_TRACKS = ["000/000002.mp3", "000/000005.mp3", "000/000010.mp3"]


def _excerpt(relative_path: str) -> np.ndarray:
    """Frozen center5_v1 excerpt at 24 kHz mono."""
    wav = preprocess_file(AUDIO_ROOT / relative_path)
    seg = sample_segments("smoke", 30.0, "center5")[0]
    start = int(seg.actual_start_sec * 24000)
    end = int(seg.actual_end_sec * 24000)
    excerpt = wav[start:end].numpy().astype(np.float64)
    assert excerpt.shape == (120000,)  # exactly 5 s @24 kHz
    return excerpt


def _validate(result, expected_dim: int) -> None:
    assert result.embedding.shape == (expected_dim,)
    assert np.isfinite(result.embedding).all()
    norm = float(np.linalg.norm(result.embedding))
    assert abs(norm - 1.0) <= 1e-3


@pytest.fixture(scope="module")
def excerpts():
    return [_excerpt(rel) for rel in SMOKE_TRACKS]


def _run_gate(encoder_id: str, make_encoder, dim: int, excerpts):
    timings = []
    results = []
    enc = make_encoder()
    for wav in excerpts:
        t0 = time.perf_counter()
        result = enc.encode_segment(wav, 24000)
        timings.append(time.perf_counter() - t0)
        _validate(result, dim)
        results.append(result)
    # determinism: re-encode first clip
    repeat = enc.encode_segment(excerpts[0], 24000)
    max_diff = float(np.abs(results[0].embedding - repeat.embedding).max())
    assert max_diff <= 1e-4, f"{encoder_id} not deterministic (max diff {max_diff})"
    print(f"\n{encoder_id}: dims={dim} p50={sorted(timings)[1]:.2f}s "
          f"times={[round(t, 2) for t in timings]} max_repeat_diff={max_diff:.2e}")
    return results, timings


def test_muq_mulan_smoke(excerpts):
    from audio_similarity.holistic_encoders import MuQMulanEncoder

    _run_gate("muq_mulan_large", MuQMulanEncoder, 512, excerpts)


def test_mert_5120_smoke(excerpts):
    from audio_similarity.holistic_encoders import mert_5120_encoder

    _run_gate("mert_5120", mert_5120_encoder, 5120, excerpts)


def test_mert_generic_smoke(excerpts):
    from audio_similarity.holistic_encoders import mert_generic_encoder

    _run_gate("mert_generic", mert_generic_encoder, 1024, excerpts)


def test_laion_clap_smoke(excerpts):
    from audio_similarity.holistic_encoders import LaionClapEncoder

    def make():
        ckpt = Path(__file__).resolve().parents[2] / "models" / "music_audioset_epoch_15_esc_90.14.pt"
        return LaionClapEncoder(checkpoint_path=str(ckpt) if ckpt.exists() else None)

    _run_gate("laion_clap", make, 512, excerpts)


# cross-encoder sanity on the same excerpt: different models must produce
# DIFFERENT geometries; identical geometry would suggest a wiring mistake
def test_cross_encoder_embeddings_differ(excerpts):
    from audio_similarity.holistic_encoders import (
        MuQMulanEncoder,
        mert_5120_encoder,
    )

    muq = MuQMulanEncoder().encode_segment(excerpts[0], 24000)
    mert = mert_5120_encoder().encode_segment(excerpts[0], 24000)
    assert muq.embedding.shape != mert.embedding.shape
