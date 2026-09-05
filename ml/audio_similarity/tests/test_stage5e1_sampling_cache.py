from __future__ import annotations

import numpy as np
import pytest

from audio_similarity.stage5e1_cache import Stage5E1Cache, representation_identity
from audio_similarity.stage5e1_sampling import (
    CHUNK_SAMPLES,
    NATIVE_CHUNK_FRAMES,
    full_song_chunks,
    native_fusion_plan,
    normalized_mean,
)


def test_full_song_chunks_cover_source_and_repeat_pad_only_final_chunk() -> None:
    chunks = full_song_chunks(CHUNK_SAMPLES * 2 + 123)
    assert [(row.start_sample, row.end_sample) for row in chunks] == [
        (0, CHUNK_SAMPLES),
        (CHUNK_SAMPLES, CHUNK_SAMPLES * 2),
        (CHUNK_SAMPLES * 2, CHUNK_SAMPLES * 2 + 123),
    ]
    assert [row.padded_samples for row in chunks] == [0, 0, CHUNK_SAMPLES - 123]


def test_native_fusion_plan_is_deterministic_and_samples_each_third() -> None:
    sample_count = CHUNK_SAMPLES * 9
    digest = "a" * 64
    first = native_fusion_plan(sample_count, digest)
    assert first == native_fusion_plan(sample_count, digest)
    available = first["total_mel_frames"] - NATIVE_CHUNK_FRAMES + 1
    thirds = np.array_split(np.arange(available), 3)
    assert all(start in third for start, third in zip(first["local_start_frames"], thirds))
    assert first["longer"] is True


def test_normalized_mean_normalizes_inputs_and_output() -> None:
    result = normalized_mean([np.array([10.0, 0.0]), np.array([0.0, 2.0])])
    assert result == pytest.approx([2 ** -0.5, 2 ** -0.5])
    assert np.linalg.norm(result) == pytest.approx(1)


def test_vector_cache_resumes_views_and_validates_pooled_vector(tmp_path) -> None:
    fields = {
        "spotify_track_id": "spotify",
        "arm": "C_FULL_SONG_CHUNK_MEAN",
        "source_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "sampling_plan_sha256": "c" * 64,
        "checkpoint_sha256": "d" * 64,
    }
    identity = representation_identity(**fields)
    vector = np.arange(1, 513, dtype=np.float32)
    with Stage5E1Cache(tmp_path / "vectors.sqlite") as cache:
        cache.record_view(
            identity,
            view_index=0,
            view_kind="FULL_SONG_CHUNK",
            start_unit=0,
            end_unit=480000,
            embedding=vector,
            inference_seconds=0.1,
        )
        assert list(cache.views(identity)) == [0]
        cache.record_vector(
            identity,
            fields,
            status="SUCCESS",
            embedding=vector,
            view_count=1,
            inference_seconds=0.1,
        )
        assert np.linalg.norm(cache.vector(identity)) == pytest.approx(1)
        assert cache.summary()["vector_status_counts"] == {
            "C_FULL_SONG_CHUNK_MEAN:SUCCESS": 1
        }
