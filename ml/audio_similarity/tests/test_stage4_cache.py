from __future__ import annotations

import hashlib

import numpy as np
import pytest

from audio_similarity.stage4_cache import SegmentCache, SegmentCacheError, analysis_key, embedding_bytes, regenerate_aggregates


def geometry():
    return {"source_sha256":"a", "canonical_pcm_sha256":"b", "encoder_id":"laion_clap", "encoder_checkpoint_sha256":"c", "encoder_revision":"stage2b_frozen", "preprocessing_version":"full_mono_24khz_v1", "sampling_version":"five5_fractional_v1", "embedding_dtype":"float32", "embedding_dimension":8}


def row(track: str, index: int, vector, **overrides):
    values = geometry() | {"corpus":"musdb18", "track_id":track, "segment_index":index, "start_sample":index*10, "end_sample":index*10+120000, "start_sec":index/2400, "end_sec":index/2400+5, "normalized_segment_embedding":vector, "status":"ok", "failure":"", "encode_ms":1.0, "created_at":1}
    values.update(overrides)
    values["analysis_key"] = analysis_key(values)
    return values


def test_analysis_key_isolation():
    a = geometry(); b = geometry(); b["sampling_version"] = "other"
    assert analysis_key(a) != analysis_key(b)


def test_atomic_segment_resume_partial_not_complete(tmp_path):
    cache = SegmentCache(tmp_path / "segments.parquet")
    vectors = np.random.default_rng(1).normal(size=(5,8))
    cache.append([row("t", i, vectors[i]) for i in range(3)])
    key = analysis_key(geometry())
    assert cache.complete_tracks(key) == set()
    cache.append([row("t", i, vectors[i]) for i in range(3,5)])
    assert cache.complete_tracks(key) == {"t"}
    assert not list(tmp_path.glob("*.tmp"))


def test_duplicate_segment_rejected(tmp_path):
    cache = SegmentCache(tmp_path / "segments.parquet")
    item = row("t", 0, np.ones(8))
    cache.append([item])
    with pytest.raises(SegmentCacheError):
        cache.append([item])


def test_embedding_norm_dimension_and_hash(tmp_path):
    cache = SegmentCache(tmp_path / "segments.parquet")
    cache.append([row("t", 0, np.arange(1,9))])
    saved = cache.read().iloc[0]
    vector = np.asarray(saved.normalized_segment_embedding)
    assert np.linalg.norm(vector) == pytest.approx(1.0)
    assert saved.embedding_sha256 == hashlib.sha256(embedding_bytes(vector)).hexdigest()
    with pytest.raises(SegmentCacheError):
        cache.append([row("bad", 0, np.ones(7))])


def test_aggregate_exact_regeneration_from_raw_cache(tmp_path):
    cache = SegmentCache(tmp_path / "segments.parquet")
    vectors = np.random.default_rng(5).normal(size=(5,8))
    cache.append([row("t", i, vectors[i]) for i in range(5)])
    first = regenerate_aggregates(cache.read())
    second = regenerate_aggregates(cache.read())
    # created_at may differ; geometry bytes and hashes must not.
    assert [(x["aggregation_version"], x["global_embedding_sha256"], embedding_bytes(x["global_embedding"])) for x in first] == [(x["aggregation_version"], x["global_embedding_sha256"], embedding_bytes(x["global_embedding"])) for x in second]
    assert len(first) == 2
