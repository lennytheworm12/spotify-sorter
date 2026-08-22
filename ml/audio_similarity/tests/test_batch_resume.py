"""Batch pipeline, resume, and failure-classification tests.

Covers Phase 1 doc section 12 (resumable batch) and 24 (data-quality
behavior) using a fake encoder — no model downloads.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from audio_similarity.batch import (
    BatchInterrupted,
    classify_failure,
    run_batch,
)
from audio_similarity.audio import AudioDecodeError, DurationInvalidError
from audio_similarity.merit_encoder import ModelOutputInvalidError
from audio_similarity.storage import (
    EmbeddingStore,
    FailureStore,
    analysis_key,
)
from tests.helpers import make_fake_encoder, save_wav, synth_waveform


@pytest.fixture
def tiny_manifest(tmp_path: Path) -> tuple[Path, list[dict]]:
    """8 decodable wav tracks in an FMA-like layout + manifest rows."""
    audio_root = tmp_path / "audio"
    rows = []
    for tid in range(1, 9):
        sub = audio_root / f"{tid:03d}"
        sub.mkdir(parents=True)
        path = save_wav(sub / f"{tid:06d}.wav", synth_waveform(1, seed=tid), 24000)
        import hashlib

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(
            {
                "track_id": tid,
                "relative_audio_path": str(path.relative_to(audio_root)),
                "audio_sha256": digest,
            }
        )
    return audio_root, rows


def fresh_stores(tmp_path: Path) -> tuple[EmbeddingStore, FailureStore]:
    return (
        EmbeddingStore(tmp_path / "embeddings.parquet"),
        FailureStore(tmp_path / "failures.parquet"),
    )


def stored_vectors(store: EmbeddingStore, key: str) -> dict[int, dict]:
    out = {}
    for row in store.table().to_pylist():
        if row["analysis_key"] == key:
            out[row["track_id"]] = row
    return out


# ---------------------------------------------------------------------------
# analysis identity
# ---------------------------------------------------------------------------


def test_analysis_key_is_stable_and_order_independent():
    prov = {"backbone_id": "x", "head_sha256": {"melody": "a", "rhythm": "b"}, "layers": [3, 4]}
    assert analysis_key(prov) == analysis_key(dict(reversed(list(prov.items()))))
    assert analysis_key(prov) != analysis_key({**prov, "backbone_id": "y"})


# ---------------------------------------------------------------------------
# basic run
# ---------------------------------------------------------------------------


def test_batch_encodes_all_tracks(tmp_path, tiny_manifest):
    audio_root, rows = tiny_manifest
    encoder, _ = make_fake_encoder()
    emb, fail = fresh_stores(tmp_path)

    summary = run_batch(rows, encoder, emb, fail, audio_root)

    assert summary.attempted == 8
    assert summary.succeeded == 8
    assert summary.failed == 0
    assert emb.count() == 8
    assert fail.to_dicts() == []


def test_embeddings_roundtrip_through_store(tmp_path, tiny_manifest):
    audio_root, rows = tiny_manifest
    encoder, _ = make_fake_encoder()
    emb, fail = fresh_stores(tmp_path)
    run_batch(rows, encoder, emb, fail, audio_root)

    for row in emb.table().to_pylist():
        for factor in ("melody", "rhythm", "timbre"):
            vec = np.asarray(row[factor], dtype=np.float32)
            assert vec.shape == (128,)
            assert abs(float(np.linalg.norm(vec)) - 1.0) <= 2e-3  # f32 storage tolerance
        general = np.asarray(row["mert_general"], dtype=np.float32)
        assert general.shape == (5120,)
        assert row["device"]
        assert row["encoded_at"] is not None


# ---------------------------------------------------------------------------
# resume behavior
# ---------------------------------------------------------------------------


def test_rerun_skips_completed_without_duplicates(tmp_path, tiny_manifest):
    audio_root, rows = tiny_manifest
    encoder, backbone = make_fake_encoder()
    emb, fail = fresh_stores(tmp_path)

    first = run_batch(rows, encoder, emb, fail, audio_root)
    calls_after_first = backbone.calls
    second = run_batch(rows, encoder, emb, fail, audio_root)

    assert first.succeeded == 8
    assert second.attempted == 0
    assert second.skipped_completed == 8
    assert backbone.calls == calls_after_first  # no recompute
    assert emb.count() == 8  # no duplicate rows


def test_interruption_then_resume_preserves_and_completes(tmp_path, tiny_manifest):
    audio_root, rows = tiny_manifest
    encoder, _ = make_fake_encoder()
    emb, fail = fresh_stores(tmp_path)

    with pytest.raises(BatchInterrupted):
        run_batch(rows, encoder, emb, fail, audio_root, checkpoint_every=1, fail_after=4)

    key = analysis_key(encoder.provenance.to_dict())
    partial = stored_vectors(emb, key)
    assert len(partial) == 4  # checkpointed before the fault
    snapshot = {tid: {k: list(v[k]) for k in ("melody",)} for tid, v in partial.items()}

    # resume with a fresh store instance pointing at the same files
    emb2 = EmbeddingStore(tmp_path / "embeddings.parquet")
    fail2 = FailureStore(tmp_path / "failures.parquet")
    summary = run_batch(rows, encoder, emb2, fail2, audio_root)

    assert summary.skipped_completed == 4
    assert summary.succeeded == 4
    final = stored_vectors(emb2, key)
    assert len(final) == 8
    assert emb2.count(key) == 8  # no duplicates
    for tid, vectors in snapshot.items():
        np.testing.assert_array_equal(np.asarray(final[tid]["melody"]), np.asarray(vectors["melody"]))


def test_resume_encodes_only_missing_tracks(tmp_path, tiny_manifest):
    audio_root, rows = tiny_manifest
    encoder, _ = make_fake_encoder()
    emb, fail = fresh_stores(tmp_path)
    run_batch(rows[:5], encoder, emb, fail, audio_root)

    summary = run_batch(rows, encoder, emb, fail, audio_root)
    assert summary.skipped_completed == 5
    assert summary.succeeded == 3
    assert emb.count() == 8


def test_model_change_reencodes_under_new_key(tmp_path, tiny_manifest):
    import dataclasses

    audio_root, rows = tiny_manifest
    encoder_a, _ = make_fake_encoder(seed=0)
    emb, fail = fresh_stores(tmp_path)
    run_batch(rows[:3], encoder_a, emb, fail, audio_root)

    encoder_b, _ = make_fake_encoder(seed=0)  # same weights...
    encoder_b.provenance = dataclasses.replace(  # ...but a different model revision
        encoder_b.provenance, backbone_revision="test-v2"
    )
    summary = run_batch(rows[:3], encoder_b, emb, fail, audio_root)
    assert summary.skipped_completed == 0
    assert summary.succeeded == 3
    assert emb.count() == 6  # both keys retained; current-key count is 3


# ---------------------------------------------------------------------------
# failure handling
# ---------------------------------------------------------------------------


def test_corrupt_track_recorded_and_batch_continues(tmp_path, tiny_manifest):
    audio_root, rows = tiny_manifest
    bad = audio_root / "099"
    bad.mkdir()
    (bad / "000099.wav").write_bytes(b"garbage")
    rows = rows + [
        {"track_id": 99, "relative_audio_path": "099/000099.wav", "audio_sha256": "x"}
    ]

    encoder, _ = make_fake_encoder()
    emb, fail = fresh_stores(tmp_path)
    summary = run_batch(rows, encoder, emb, fail, audio_root)

    assert summary.succeeded == 8
    assert summary.failed == 1
    failures = fail.to_dicts()
    assert len(failures) == 1
    record = failures[0]
    assert record["track_id"] == 99
    assert record["failure_code"] == "DECODE_FAILED"
    assert record["retryable"] is False
    assert record["exception_class"]


def test_failure_classification_mapping():
    assert classify_failure(DurationInvalidError("short")) == "DURATION_INVALID"
    assert classify_failure(AudioDecodeError("bad")) == "DECODE_FAILED"
    assert classify_failure(ModelOutputInvalidError("nan")) == "OUTPUT_INVALID"
    assert classify_failure(RuntimeError("oom")) == "MODEL_FAILED"


class ExplodingEncoder:
    """Fake that raises MODEL_FAILED on call 3 and OUTPUT_INVALID on call 6."""

    def __init__(self, inner):
        self._inner = inner
        self.provenance = inner.provenance
        self.forward_call_count = 0
        self._calls = 0

    def encode_waveform(self, wav):
        import torch

        self._calls += 1
        if self._calls == 3:
            raise RuntimeError("simulated model crash")
        if self._calls == 6:
            raise ModelOutputInvalidError("simulated invalid output")
        return self._inner.encode_waveform(wav)


def test_model_and_output_failures_are_typed(tmp_path, tiny_manifest):
    audio_root, rows = tiny_manifest
    inner, _ = make_fake_encoder(seed=3)
    encoder = ExplodingEncoder(inner)
    emb, fail = fresh_stores(tmp_path)

    summary = run_batch(rows, encoder, emb, fail, audio_root)

    codes = {f["track_id"]: f["failure_code"] for f in fail.to_dicts()}
    assert set(codes.values()) == {"MODEL_FAILED", "OUTPUT_INVALID"}
    assert len(codes) == 2
    assert summary.succeeded + summary.failed == summary.attempted
    # failed tracks are not written to embeddings
    failed_ids = set(codes)
    written = {r["track_id"] for r in emb.table().to_pylist()}
    assert failed_ids.isdisjoint(written)


def test_retryable_flag_matches_design_taxonomy(tmp_path, tiny_manifest):
    from audio_similarity.batch import FAILURE_RETRYABLE

    assert FAILURE_RETRYABLE["MODEL_FAILED"] is True
    assert FAILURE_RETRYABLE["DECODE_FAILED"] is False
    assert FAILURE_RETRYABLE["DURATION_INVALID"] is False
    assert FAILURE_RETRYABLE["OUTPUT_INVALID"] is False


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


def test_same_waveform_same_embedding_across_runs(tmp_path, tiny_manifest):
    audio_root, rows = tiny_manifest
    encoder_one, _ = make_fake_encoder(seed=7)
    encoder_two, _ = make_fake_encoder(seed=7)
    emb, fail = fresh_stores(tmp_path)
    run_batch(rows[:2], encoder_one, emb, fail, audio_root)

    emb2 = EmbeddingStore(tmp_path / "second.parquet")
    fail2 = FailureStore(tmp_path / "second_failures.parquet")
    run_batch(rows[:2], encoder_two, emb2, fail2, audio_root)

    key = analysis_key(encoder_two.provenance.to_dict())
    a = {r["track_id"]: r for r in emb.table().to_pylist()}
    b = {r["track_id"]: r for r in emb2.table().to_pylist()}
    for tid in a:
        np.testing.assert_allclose(
            np.asarray(a[tid]["melody"], dtype=np.float64),
            np.asarray(b[tid]["melody"], dtype=np.float64),
            atol=1e-6,
        )
