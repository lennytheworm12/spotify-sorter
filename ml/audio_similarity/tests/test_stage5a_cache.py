import json
import sqlite3

import numpy as np
import pytest

from audio_similarity.stage5a_cache import Stage5ACache, Stage5ACacheError


def identity(analysis="analysis-a", source="source-a"):
    return {
        "encoder_analysis_identity": analysis,
        "corpus": "corpus",
        "corpus_version": "v1",
        "stable_track_id": "track-1",
        "source_audio_sha256": source,
        "canonical_pcm_sha256": "pcm-a",
        "vector_contract_sha256": "contract-a",
        "representation_version": "representation-a",
        "preprocessing_version": "preprocessing-a",
        "sampling_version": "sampling-a",
        "centers_json": json.dumps([5, 15, 25]),
        "aggregation_version": "aggregation-a",
        "encoder_id": "laion_clap",
        "encoder_provenance_json": "{}",
        "encoder_provenance_sha256": "provenance-a",
        "embedding_dtype": "float32",
        "embedding_dimension": 4,
    }


def test_segment_cache_is_resumable_and_identity_isolated(tmp_path):
    with Stage5ACache(tmp_path / "cache.sqlite") as cache:
        first = identity()
        cache.record_segment(first, center_sec=5, start_sample=1, end_sample=2, status="SUCCESS", embedding=[1, 2, 3, 4])
        cache.record_segment(first, center_sec=15, start_sample=2, end_sample=3, status="FAILED", failure_category="CLAP_INFERENCE_FAILURE", failure_detail="expected")
        assert set(cache.successful_segments("analysis-a")) == {5}
        assert cache.segment_attempts("analysis-a", 15) == 1
        cache.record_segment(first, center_sec=15, start_sample=2, end_sample=3, status="SUCCESS", embedding=[4, 3, 2, 1])
        assert cache.segment_attempts("analysis-a", 15) == 2
        assert cache.successful_segments("analysis-b") == {}


def test_cache_rejects_invalid_vectors_and_persists_encoders_independently(tmp_path):
    with Stage5ACache(tmp_path / "cache.sqlite") as cache:
        with pytest.raises(Stage5ACacheError, match="shape"):
            cache.record_pooled(identity(), status="SUCCESS", embedding=np.ones(3))
        with pytest.raises(Stage5ACacheError, match="non-finite"):
            cache.record_pooled(identity(), status="SUCCESS", embedding=[1, 2, np.nan, 4])
        cache.record_pooled(identity("clap"), status="SUCCESS", embedding=[1, 0, 0, 0])
        cache.record_pooled(identity("muq") | {"encoder_id": "muq_mulan_large"}, status="SUCCESS", embedding=[0, 1, 0, 0])
        assert cache.pooled_vector("clap").tolist() == [1, 0, 0, 0]
        assert cache.pooled_vector("muq").tolist() == [0, 1, 0, 0]


def test_cache_rejects_incompatible_schema_version(tmp_path):
    path = tmp_path / "cache.sqlite"
    with Stage5ACache(path):
        pass
    db = sqlite3.connect(path)
    db.execute("UPDATE cache_metadata SET value='future' WHERE key='schema_version'")
    db.commit()
    db.close()
    with pytest.raises(Stage5ACacheError, match="schema"):
        Stage5ACache(path)
