import json

import pytest

from audio_similarity.chart_download_batches import (
    build_cohort, batch_document, freeze, validate_batch, run, RUNTIME,
)
from audio_similarity.stage5d0a_network import CircuitOpen
from tests.test_stage5d0a_worker import Processor
from tests.test_stage5d0a_network import Clock, governor


def snapshot(count=6):
    result = {"metrics": {"catalog_id": "CHART_ANCHORED_2006_2026_METADATA_V1"},
              "matches": [], "recordings": []}
    for index in range(count):
        raw = {"id": f"{index:022d}", "name": f"Track {index}",
               "artists": [{"name": "Artist"}], "duration_ms": 180000,
               "album": {"name": "Album", "release_date": "1990-01-01"}}
        result["matches"].append({"song": {"song_key": str(index)}, "spotify": raw,
                                  "status": "MATCHED_METADATA"})
        result["recordings"].append({"spotify": raw, "spotify_ids": [raw["id"]],
                                     "song_keys": [str(index)],
                                     "appearances": [{"chart_year": 2020, "territory": "US"}]})
    return result


def prepare(root, count=6, size=3):
    source = root / "reports/stage5d_chart_catalog_v1/matching_fixture.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(snapshot(count)))
    freeze(root, source, batch_size=size)
    return source


def test_deterministic_nonoverlapping_batches_and_older_hit_recordings():
    cohort = build_cohort(snapshot(534), "sha")
    assert cohort == build_cohort(snapshot(534), "sha")
    a, b = batch_document(cohort, 1), batch_document(cohort, 2)
    assert [len(a["tracks"]), len(b["tracks"])] == [500, 34]
    assert not {r["spotify_track_id"] for r in a["tracks"]} & {r["spotify_track_id"] for r in b["tracks"]}
    assert not a["automatic_next_batch"]
    assert cohort["tracks"][0]["release_year"] == 1990
    with pytest.raises(ValueError):
        batch_document(cohort, 3)


@pytest.mark.parametrize("size", [0, 501, True])
def test_batch_size_is_bounded(size):
    with pytest.raises(ValueError):
        build_cohort(snapshot(), "sha", batch_size=size)


def test_pending_or_ambiguous_cannot_enter_download_queue():
    data = snapshot()
    data["matches"][0]["status"] = "AMBIGUOUS_RECORDINGS"
    with pytest.raises(ValueError, match="unmatched or ambiguous"):
        build_cohort(data, "sha")


def test_snapshot_freeze_tamper_and_reprepare_guard(tmp_path):
    source = prepare(tmp_path)
    validate_batch(tmp_path, 1)
    with pytest.raises(ValueError):
        freeze(tmp_path, source, batch_size=2)
    source.write_text(source.read_text() + " ")
    with pytest.raises(ValueError, match="input changed"):
        validate_batch(tmp_path, 1)


def test_run_is_only_requested_batch_resume_and_shared_provider_state(tmp_path, monkeypatch):
    prepare(tmp_path)
    monkeypatch.setattr("audio_similarity.stage5d0a_worker.media_git_audit", lambda root: {})
    instances = []
    def factory(*args):
        item = Processor(*args, cache=True)
        instances.append(item)
        return item
    clock = Clock()
    options = {"processor_factory": factory, "governor_factory": lambda d: governor(d, clock)}
    result = run(tmp_path, 1, **options)
    assert result["status"] == "FINISHED"
    assert len(instances[0].processed) == 3
    assert not (tmp_path / RUNTIME / "batch_0002").exists()
    run(tmp_path, 1, resume=True, **options)
    assert not instances[-1].processed
    result = run(tmp_path, 2, **options)
    assert result["batch"] == "0002"
    assert instances[0].network.directory == instances[-1].network.directory


def test_old_open_circuit_cannot_be_bypassed_by_switching_catalog(tmp_path):
    prepare(tmp_path)
    path = tmp_path / ".research_audio/stage5d0a/batch_0001/network_state.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"circuit": "OPEN"}))
    with pytest.raises(CircuitOpen):
        run(tmp_path, 1, processor_factory=lambda *args: pytest.fail("must not start"))


def test_familiar_command_now_uses_chart_runner():
    from audio_similarity.cli.stage5d0a import main
    from audio_similarity.chart_download_batches import main as chart_main
    assert main is chart_main


def test_old_safety_state_carries_forward_and_new_circuit_survives_batch_change(tmp_path, monkeypatch):
    prepare(tmp_path)
    monkeypatch.setattr("audio_similarity.stage5d0a_worker.media_git_audit", lambda root: {})
    clock = Clock()
    monkeypatch.setattr("audio_similarity.chart_download_batches.ProviderGovernor", lambda d: governor(d, clock))
    old = tmp_path / ".research_audio/stage5d0a/batch_0001/network_state.json"
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps({"circuit": "CLOSED", "cooldown_deadline": 900,
                               "next_request_deadline": 90, "http_429_count": 1}))
    run(tmp_path, 1, processor_factory=lambda *args: Processor(*args, cache=True))
    path = tmp_path / RUNTIME / "provider/network_state.json"
    state = json.loads(path.read_text())
    assert state["cooldown_deadline"] == 900
    assert state["http_429_count"] == 1
    state.update(circuit="OPEN", circuit_reason="second 429")
    path.write_text(json.dumps(state))
    with pytest.raises(CircuitOpen):
        run(tmp_path, 2, resume=True, processor_factory=lambda *args: pytest.fail("circuit must stop worker"))
