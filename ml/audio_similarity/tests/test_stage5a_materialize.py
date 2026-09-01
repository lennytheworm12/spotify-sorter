import hashlib
from pathlib import Path

import numpy as np
import pytest
import torch

from audio_similarity.stage5a_cache import Stage5ACache
from audio_similarity.stage5a_contract import load_contract
from audio_similarity.stage5a_dataset import read_dataset
from audio_similarity.stage5a_materialize import TrackInput, materialize, source_sha256
from tests.helpers import save_wav


CONTRACT_PATH = Path(__file__).parents[1] / "reports/holistic_stage4a_dual/audio_representation_v1.json"


class FakeEncoder:
    embedding_dim = 512

    def __init__(self, encoder_id, fail_above=None):
        self.encoder_id = encoder_id
        self.fail_above = fail_above
        self.calls = 0

    def encode_segment(self, waveform, sample_rate):
        assert sample_rate == 24000
        self.calls += 1
        if self.fail_above is not None and float(np.mean(waveform)) > self.fail_above:
            raise RuntimeError("injected inference failure")
        digest = hashlib.sha256(self.encoder_id.encode() + np.asarray(waveform, dtype="<f4").tobytes()).digest()
        seed = int.from_bytes(digest[:8], "little")
        return np.random.default_rng(seed).normal(size=self.embedding_dim).astype(np.float32)


def track(tmp_path, track_id, level):
    path = save_wav(tmp_path / f"{track_id}.wav", torch.full((1, 720000), level), 24000)
    return TrackInput(track_id, path, source_sha256(path))


def encoders(failing_muq=False):
    clap = FakeEncoder("laion_clap")
    muq = FakeEncoder("muq_mulan_large", 0.4 if failing_muq else None)
    return {clap.encoder_id: clap, muq.encoder_id: muq}, clap, muq


def file_hashes(directory):
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def test_resume_then_idempotent_rerun_uses_no_unnecessary_inference(tmp_path):
    contract = load_contract(CONTRACT_PATH)
    input_track = track(tmp_path, "one", 0.2)
    adapters, clap, muq = encoders()
    cache_path = tmp_path / "work.sqlite"
    output = tmp_path / "dataset"
    saved = 0

    def interrupt(*_):
        nonlocal saved
        saved += 1
        if saved == 2:
            raise RuntimeError("interrupt")

    with Stage5ACache(cache_path) as cache:
        with pytest.raises(RuntimeError, match="interrupt"):
            materialize([input_track], corpus="fixture", corpus_version="v1", contract=contract, cache=cache, encoders=adapters, output_dir=output, on_segment_saved=interrupt)
    assert clap.calls == 2 and muq.calls == 0

    with Stage5ACache(cache_path) as cache:
        result = materialize([input_track], corpus="fixture", corpus_version="v1", contract=contract, cache=cache, encoders=adapters, output_dir=output)
    assert clap.calls == 3 and muq.calls == 3
    assert result.clap.reused_segments == 2
    assert result.successful_tracks == 1
    first_hashes = file_hashes(output)
    rows = read_dataset(output)
    assert len(rows) == 1
    assert rows[0]["segment_centers_sec"] == [5, 15, 25]
    assert rows[0]["clap_embedding"] != rows[0]["muq_embedding"]
    assert np.linalg.norm(rows[0]["clap_embedding"]) == pytest.approx(1, abs=1e-6)
    assert np.linalg.norm(rows[0]["muq_embedding"]) == pytest.approx(1, abs=1e-6)

    fresh, fresh_clap, fresh_muq = encoders()
    with Stage5ACache(cache_path) as cache:
        rerun = materialize([input_track], corpus="fixture", corpus_version="v1", contract=contract, cache=cache, encoders=fresh, output_dir=output)
    assert fresh_clap.calls == fresh_muq.calls == 0
    assert rerun.reused_complete_tracks == 1
    assert file_hashes(output) == first_hashes


def test_failure_isolation_explicit_failure_and_retry(tmp_path):
    contract = load_contract(CONTRACT_PATH)
    inputs = [track(tmp_path, "good", 0.2), track(tmp_path, "bad", 0.5)]
    adapters, _, _ = encoders(failing_muq=True)
    cache_path = tmp_path / "work.sqlite"
    output = tmp_path / "dataset"
    with Stage5ACache(cache_path) as cache:
        result = materialize(inputs, corpus="fixture", corpus_version="v1", contract=contract, cache=cache, encoders=adapters, output_dir=output)
        failed = cache.db.execute("SELECT * FROM tracks WHERE stable_track_id='bad'").fetchone()
        assert failed["status"] == "FAILED"
        assert failed["failure_category"] == "MUQ_INFERENCE_FAILURE"
        assert failed["retryable"] == 1
    assert result.successful_tracks == 1 and result.failed_tracks == 1
    assert [row["stable_track_id"] for row in read_dataset(output)] == ["good"]

    retry_adapters, retry_clap, retry_muq = encoders()
    with Stage5ACache(cache_path) as cache:
        retried = materialize(inputs, corpus="fixture", corpus_version="v1", contract=contract, cache=cache, encoders=retry_adapters, output_dir=output)
    assert retry_clap.calls == 0
    # The first attempt stops that encoder at its first deterministic failure;
    # retry computes the failed segment and the two segments never attempted.
    assert retry_muq.calls == 3
    assert retried.successful_tracks == 2
    assert len(read_dataset(output)) == 2


def test_duplicate_input_is_rejected_before_work(tmp_path):
    contract = load_contract(CONTRACT_PATH)
    item = track(tmp_path, "same", 0.2)
    adapters, _, _ = encoders()
    with Stage5ACache(tmp_path / "work.sqlite") as cache:
        with pytest.raises(ValueError, match="duplicate"):
            materialize([item, item], corpus="fixture", corpus_version="v1", contract=contract, cache=cache, encoders=adapters, output_dir=tmp_path / "dataset")
