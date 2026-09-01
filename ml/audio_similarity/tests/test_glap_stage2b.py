from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from audio_similarity.encoder import HolisticEmbedding
from audio_similarity.glap_stage2b import (
    GlapCacheError,
    GlapEmbeddingCache,
    EvidenceTrack,
    analysis_identity,
    encode_historical_evidence,
    load_glap_contract,
)


def _contract():
    return {
        "experiment_id": "glap_stage2b_challenger_v1",
        "contract_status": "FROZEN_PRE_OUTCOME",
        "historical_evidence": {
            "trial_manifest": {"unique_audio_track_count": 3},
        },
        "audio_evidence": {
            "canonical_preprocessing": "pp-v1",
            "historical_excerpt": "center5_v1",
            "excerpt_start_sample_at_24000_hz": 300000,
            "excerpt_end_sample_at_24000_hz": 420000,
        },
        "challenger": {
            "representation_namespace": "glap_stage2b_challenger_v1",
            "model_identifier": "mispeech/GLAP",
            "model_revision": "frozen-revision",
            "model_file_sha256": "a" * 64,
            "stored_dtype": "float32",
            "embedding_dimensions": 1024,
        },
    }


def _unit_vector(index=0):
    vector = np.zeros(1024, dtype=np.float32)
    vector[index] = 1.0
    return vector


def test_real_frozen_contract_loads_and_enforces_center5():
    root = Path(__file__).parents[1]
    contract = load_glap_contract(
        root / "reports/glap_stage2b_challenger_v1/experiment_contract.json", root
    )
    assert contract["audio_evidence"]["historical_excerpt"] == "center5_v1"
    assert contract["challenger"]["model_identifier"] == "mispeech/GLAP"
    assert contract["challenger"]["embedding_dimensions"] == 1024


def test_cache_identity_invalidates_model_and_pcm_changes():
    contract = _contract()
    first = analysis_identity(contract, source_sha256="s", center5_pcm_sha256="p")
    changed = _contract()
    changed["challenger"]["model_revision"] = "new"
    assert analysis_identity(changed, source_sha256="s", center5_pcm_sha256="p") != first
    assert analysis_identity(contract, source_sha256="s", center5_pcm_sha256="new") != first


def test_cache_success_failure_and_corruption_are_explicit(tmp_path):
    cache = GlapEmbeddingCache(tmp_path / "cache.sqlite")
    contract = _contract()
    key = analysis_identity(contract, source_sha256="s", center5_pcm_sha256="p")
    cache.put_success(
        track_id=1,
        analysis_key=key,
        source_sha256="s",
        center5_pcm_sha256="p",
        contract=contract,
        vector=_unit_vector(),
        encode_ms=4.0,
    )
    np.testing.assert_array_equal(cache.valid_embedding(1, key), _unit_vector())
    cache.put_failure(
        track_id=2,
        analysis_key=key,
        source_sha256="s",
        center5_pcm_sha256="p",
        contract=contract,
        exc=ValueError("decode failed"),
        encode_ms=1.0,
    )
    assert cache.valid_embedding(2, key) is None
    row = cache.db.execute(
        "SELECT status, embedding, failure_code, error_message FROM embeddings WHERE track_id=2"
    ).fetchone()
    assert row == ("FAILED", None, "ValueError", "decode failed")
    cache.db.execute("UPDATE embeddings SET embedding=? WHERE track_id=1", (b"corrupt",))
    cache.db.commit()
    with pytest.raises(GlapCacheError, match="corrupt"):
        cache.valid_embedding(1, key)
    cache.close()


class FakeBatchEncoder:
    instances = []

    def __init__(self, *args, **kwargs):
        self.calls = []
        self.load_seconds = 0.01
        self.instances.append(self)

    def encode_batch(self, waveforms, sample_rate):
        self.calls.append(len(waveforms))
        return [
            HolisticEmbedding(
                embedding=_unit_vector(index % 1024),
                encoder_id="glap_stage2b_challenger_v1",
                embedding_dim=1024,
            )
            for index, _ in enumerate(waveforms)
        ]

    def peak_vram_bytes(self):
        return None


def _tracks():
    return [
        EvidenceTrack(index, f"{index}.wav", f"source-{index}", f"pcm-{index}")
        for index in (1, 2, 3)
    ]


def test_resume_and_idempotency_skip_valid_work(monkeypatch, tmp_path):
    import audio_similarity.glap_stage2b as module

    FakeBatchEncoder.instances.clear()
    monkeypatch.setattr(module, "load_glap_contract", lambda *args, **kwargs: _contract())
    monkeypatch.setattr(module, "load_evidence_tracks", lambda *args, **kwargs: _tracks())
    monkeypatch.setattr(
        module,
        "_prepare_excerpt",
        lambda track, audio_root: np.full(120000, track.track_id, dtype=np.float32),
    )
    common = dict(
        contract_path=tmp_path / "contract.json",
        root=tmp_path,
        model_dir=tmp_path / "model",
        cache_path=tmp_path / "cache.sqlite",
        device="cpu",
        encoder_factory=FakeBatchEncoder,
    )
    first = encode_historical_evidence(**common, limit=1)
    assert first["inference_attempted"] == 1
    resumed = encode_historical_evidence(**common, batch_size=2)
    assert resumed["skipped_valid_success"] == 1
    assert resumed["inference_attempted"] == 2
    repeat = encode_historical_evidence(**common)
    assert repeat["skipped_valid_success"] == 3
    assert repeat["inference_attempted"] == 0
    assert repeat["success_count"] == 3


def test_missing_audio_failure_is_isolated_and_retryable(monkeypatch, tmp_path):
    import audio_similarity.glap_stage2b as module

    monkeypatch.setattr(module, "load_glap_contract", lambda *args, **kwargs: _contract())
    monkeypatch.setattr(module, "load_evidence_tracks", lambda *args, **kwargs: _tracks()[:2])

    def prepare(track, audio_root):
        if track.track_id == 2:
            raise FileNotFoundError("missing source")
        return np.ones(120000, dtype=np.float32)

    monkeypatch.setattr(module, "_prepare_excerpt", prepare)
    result = encode_historical_evidence(
        contract_path=tmp_path / "contract.json",
        root=tmp_path,
        model_dir=tmp_path / "model",
        cache_path=tmp_path / "cache.sqlite",
        device="cpu",
        encoder_factory=FakeBatchEncoder,
    )
    assert result["success_count"] == 1
    assert result["failure_count"] == 1
    with sqlite3.connect(tmp_path / "cache.sqlite") as db:
        assert db.execute("SELECT status FROM embeddings WHERE track_id=2").fetchone()[0] == "FAILED"
