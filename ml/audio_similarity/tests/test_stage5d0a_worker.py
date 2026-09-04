import json

import pytest

from audio_similarity.stage5d0a_manifest import freeze_catalog_and_batch_one, REPORT_DIRECTORY
from audio_similarity.stage5d0a_worker import run_worker, validate_freeze
from audio_similarity.stage5d0a_reporting import summarize
from tests.test_stage5d0a_manifest import catalog
from tests.test_stage5d0a_network import Clock, governor


def freeze(root, count):
    source = catalog(count)
    source["catalog_design"]["design_id"] = "POPULAR_COMMERCIAL_2000_2026_SPOTIFY_SEARCH_V1"
    path = root / "catalog.json"
    path.write_text(json.dumps(source))
    return freeze_catalog_and_batch_one(path, root / REPORT_DIRECTORY)[1]


class Processor:
    def __init__(self, root, directory, network, *, stop_after=None, cache=False):
        self.root, self.directory, self.network = root, directory, network
        self.processed = []
        self.stop_after = stop_after
        self.cache = cache

    def inspect(self, track):
        state = json.loads((self.directory / "state.json").read_text())
        cached = self.cache or state["tracks"][track["spotify_track_id"]]["state"] == "COMPLETE"
        return {"source": self.root if cached else None,
                "representation": {} if cached else None, "network_required": not cached,
                "selection": {"youtube_video_id": "abcdefghijk"}}

    def process(self, track, inspected, checkpoint):
        key = track["spotify_track_id"]
        self.processed.append(key)
        checkpoint("RESOLVED", selected_video_id="abcdefghijk")
        if self.stop_after and len(self.processed) == self.stop_after:
            self.network.stop_path.write_text("stop")
        return {"state": "MANUAL_TAIL" if int(key) == 1 else "COMPLETE",
                "result": {"source_retained": int(key) != 1, "representation_complete": int(key) != 1}}


def test_batch_500_boundary_and_cache_skips_without_batch_two(tmp_path, monkeypatch):
    batch = freeze(tmp_path, 502)
    monkeypatch.setattr("audio_similarity.stage5d0a_worker.media_git_audit", lambda root: {})
    instances = []
    def factory(*args):
        instance = Processor(*args, cache=True)
        instances.append(instance)
        return instance
    clock = Clock()
    status = run_worker(tmp_path, processor_factory=factory, governor_factory=lambda directory: governor(directory, clock))
    assert status["status"] == "FINISHED"
    assert status["network_jobs"] == 0
    assert len(instances[0].processed) == 500
    assert set(instances[0].processed) == {row["spotify_track_id"] for row in batch["tracks"]}
    assert not list((tmp_path / REPORT_DIRECTORY).glob("batch_0002*"))
    status = run_worker(tmp_path, processor_factory=factory, governor_factory=lambda directory: governor(directory, clock))
    assert not instances[-1].processed


def test_stop_resume_preserves_completed_and_manual_tail_continues(tmp_path, monkeypatch):
    freeze(tmp_path, 4)
    monkeypatch.setattr("audio_similarity.stage5d0a_worker.media_git_audit", lambda root: {})
    instances = []
    def factory(*args):
        instance = Processor(*args, stop_after=1 if not instances else None)
        instances.append(instance)
        return instance
    clock = Clock()
    kwargs = {"processor_factory": factory, "governor_factory": lambda directory: governor(directory, clock)}
    status = run_worker(tmp_path, **kwargs)
    assert status["status"] == "STOPPED"
    status = run_worker(tmp_path, resume=True, **kwargs)
    assert status["status"] == "FINISHED"
    assert status["states"] == {"COMPLETE": 3, "MANUAL_TAIL": 1}
    assert len(set(instances[0].processed + instances[1].processed)) == 4
    network = json.loads((instances[1].directory / "network_state.json").read_text())
    assert all(row["previous_start_delta_seconds"] >= 30 for row in network["jobs"][1:])


def test_mutated_freeze_prevents_worker_construction(tmp_path):
    freeze(tmp_path, 1)
    path = tmp_path / REPORT_DIRECTORY / "batch_0001_manifest.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_freeze(tmp_path)


def test_health_never_calls_all_failures_healthy():
    state = {"status": "FINISHED", "started_at_unix": 0, "updated_at_unix": 1,
             "tracks": {"one": {"state": "ACQUISITION_FAILED"}}}
    assert summarize(state, {})["verdict"] == "BATCH_500_PIPELINE_FAILED"
    state["tracks"]["one"]["state"] = "MANUAL_TAIL"
    assert summarize(state, {})["verdict"] == "BATCH_500_PIPELINE_FAILED"
