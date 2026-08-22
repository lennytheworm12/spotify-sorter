"""Stage A/B gate: encode real FMA Small files end-to-end.

Run deliberately (downloads MERT if not cached):

    uv run pytest tests/integration/test_fma_smoke.py -m heavy -o addopts=""
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from audio_similarity.audio import preprocess_file
from audio_similarity.manifest import load_manifest
from audio_similarity.merit_encoder import BACKBONE_DIM, EMBEDDING_DIM, MeritEncoder

pytestmark = pytest.mark.heavy


def _manifest_root() -> Path:
    root = Path(__file__).resolve().parents[2] / "data" / "fma"
    if not (root / "fma_small").exists():
        pytest.skip("FMA Small audio not downloaded")
    return root


@pytest.fixture(scope="module")
def encoder() -> MeritEncoder:
    return MeritEncoder.from_pretrained()


@pytest.fixture(scope="module")
def three_manifest_rows():
    manifest = load_manifest(_manifest_root().parent / "manifests" / "fma_small.parquet")
    ok = manifest[manifest["decode_status"] == "SUCCESS"].head(3)
    assert len(ok) == 3
    return ok


def test_three_real_fma_tracks_encode(encoder: MeritEncoder, three_manifest_rows):
    root = _manifest_root()
    for _, row in three_manifest_rows.iterrows():
        wav = preprocess_file(root / "fma_small" / row["relative_audio_path"])
        result = encoder.encode_waveform(wav)
        for name in ("melody", "rhythm", "timbre"):
            vec = getattr(result, name)
            assert vec.shape == (EMBEDDING_DIM,)
            assert np.isfinite(vec).all()
            assert abs(float(np.linalg.norm(vec)) - 1.0) <= 1e-3
        assert result.mert_general.shape == (BACKBONE_DIM,)
    assert encoder.forward_call_count == 3


def test_real_tracks_are_mutually_distinguishable(encoder: MeritEncoder, three_manifest_rows):
    root = _manifest_root()
    results = [
        encoder.encode_waveform(preprocess_file(root / "fma_small" / row["relative_audio_path"]))
        for _, row in three_manifest_rows.iterrows()
    ]
    for factor in ("melody", "rhythm", "timbre"):
        off_diag = [
            float(np.dot(getattr(results[i], factor), getattr(results[j], factor)))
            for i in range(3)
            for j in range(i + 1, 3)
        ]
        # distinct songs should not be perfect duplicates of each other
        assert max(off_diag) < 0.9999, f"{factor}: suspiciously identical tracks {off_diag}"
