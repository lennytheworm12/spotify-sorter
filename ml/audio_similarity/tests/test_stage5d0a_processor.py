from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from audio_similarity.stage5d0a_processor import SeedProcessor
from audio_similarity.stage5d0a_network import ProviderGovernor


SELECTION = {"youtube_video_id": "abcdefghijk", "source_url": "https://www.youtube.com/watch?v=abcdefghijk", "selected_rank": 2}
TRACK = {"spotify_track_id": "a" * 22, "title": "Song", "artists": ["Artist"],
         "release_year": 2000, "duration_ms": 180000, "stage5d0a_track_id": "stage5d0a_1"}


def processor(root, monkeypatch, *, fail_acquire=False):
    module = "audio_similarity.stage5d0a_processor"
    p = SeedProcessor.__new__(SeedProcessor)
    p.root = root
    p.directory = root / "runtime"
    p.media = root / ".research_audio"
    p.media.mkdir()
    p.governor = ProviderGovernor(p.directory)
    p.cache_file = root / "vectors/representations.sqlite"
    p.corpus, p.corpus_version = "test", "test-v1"
    p.contract = object()
    p.encoders = object()
    counts = {"acquisition": 0, "inference": 0}
    representation = {"identity": "unchanged"}
    def acquire(track, output):
        counts["acquisition"] += 1
        assert track["youtube_video_id"] == SELECTION["youtube_video_id"]
        assert track["source_url"] == SELECTION["source_url"]
        source = output / "source.webm"
        source.write_bytes(b"compressed full source fixture" * 100)
        if fail_acquire:
            (output / "fragment.part").write_bytes(b"partial")
            raise RuntimeError("Video unavailable")
        return {"downloaded_path": str(source), "acquisition_started_at": "2026-09-04T00:00:00Z"}
    p.acquirer = SimpleNamespace(acquire=acquire)
    monkeypatch.setattr(module + ".probe_and_validate", lambda path, **kwargs: {"duration_seconds": 180,
                        "full_decode_validated": True, "codec": "opus", "container": "webm"})
    monkeypatch.setattr(module + ".Stage5ACache", lambda path: nullcontext())
    def materialize(tracks, **kwargs):
        counts["inference"] += 1
        assert len(tracks) == 1 and tracks[0].stable_track_id == TRACK["spotify_track_id"]
        assert tracks[0].audio_path.is_file()
        assert kwargs["contract"] is p.contract
        return SimpleNamespace(clap=SimpleNamespace(inferred_segments=3), muq=SimpleNamespace(inferred_segments=3))
    monkeypatch.setattr(module + ".materialize", materialize)
    def no_discovery(*args, **kwargs):
        pytest.fail("exact frozen source must not be rediscovered")
    monkeypatch.setattr(module + ".discover_and_select_with_fallback", no_discovery)
    p.find_representation = lambda *args: representation
    return p, counts, representation


@pytest.mark.parametrize("has_source,has_representation", [(True, True), (True, False), (False, True), (False, False)])
def test_four_cache_conditions_exact_id_and_cleanup(tmp_path, monkeypatch, has_source, has_representation):
    p, counts, representation = processor(tmp_path, monkeypatch)
    source = p.media / TRACK["spotify_track_id"] / "source.webm"
    provenance = None
    if has_source:
        source.parent.mkdir()
        source.write_bytes(b"retained")
        provenance = {"source_sha256": "fixture", "retained_relative_path": str(source.relative_to(p.media))}
    inspected = {"selection": SELECTION, "source": source if has_source else None,
                 "provenance": provenance, "representation": representation if has_representation else None}
    stages = []
    outcome = p.process(TRACK, inspected, lambda stage, **details: stages.append(stage))
    assert outcome["state"] == "COMPLETE"
    assert counts == {"acquisition": int(not has_source), "inference": int(not has_representation)}
    assert source.is_file()
    assert not list(p.media.glob(".stage5d-scratch-*"))
    assert outcome["result"]["representation"] == representation


def test_failure_cleans_partial_without_source_substitution(tmp_path, monkeypatch):
    p, counts, representation = processor(tmp_path, monkeypatch, fail_acquire=True)
    outcome = p.process(TRACK, {"selection": SELECTION, "source": None, "provenance": None,
                              "representation": representation}, lambda *args, **kwargs: None)
    assert outcome["state"] == "ACQUISITION_FAILED"
    assert counts == {"acquisition": 1, "inference": 0}
    assert not list(p.media.rglob("*.part"))
    assert not list(p.media.rglob("*.webm"))


def test_selection_is_immutable_and_self_hash_checked(tmp_path, monkeypatch):
    import json
    p, _, _ = processor(tmp_path, monkeypatch)
    spotify_id = TRACK["spotify_track_id"]
    p.freeze_selection(spotify_id, SELECTION)
    original = p.selection_path(spotify_id).read_bytes()
    p.freeze_selection(spotify_id, SELECTION)
    assert p.selection_path(spotify_id).read_bytes() == original
    with pytest.raises(ValueError, match="refusing"):
        p.freeze_selection(spotify_id, SELECTION | {"youtube_video_id": "another1234"})
    frozen = json.loads(original)
    frozen["selection"]["selected_rank"] = 1
    p.selection_path(spotify_id).write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="digest mismatch"):
        p.inspect(TRACK)


def test_resolution_freezes_exact_source_before_acquisition(tmp_path, monkeypatch):
    import json
    p, counts, _ = processor(tmp_path, monkeypatch)
    p.provider = object()
    def discover(target, provider):
        assert provider is p.provider
        assert target.spotify_track_id == TRACK["spotify_track_id"]
        assert list(target.artists) == TRACK["artists"]
        return {"outcome": "FALLBACK_SUCCESS", "selected_video_id": "abcdefghijk", "selected_rank": 2}
    monkeypatch.setattr("audio_similarity.stage5d0a_processor.discover_and_select_with_fallback", discover)
    original = p.acquirer.acquire
    def acquire(track, directory):
        frozen = json.loads(p.selection_path(TRACK["spotify_track_id"]).read_text())
        assert frozen["selection"]["youtube_video_id"] == track["youtube_video_id"]
        assert frozen["selection"]["selected_rank"] == 2
        return original(track, directory)
    p.acquirer.acquire = acquire
    outcome = p.process(TRACK, {"selection": None, "source": None, "provenance": None,
                              "representation": None}, lambda *args, **kwargs: None)
    assert outcome["state"] == "COMPLETE"
    assert counts == {"acquisition": 1, "inference": 1}


@pytest.mark.parametrize("provider_outcome,expected", [("ALL_QUERY_VARIANTS_EMPTY", "MANUAL_TAIL"), ("PROVIDER_ERROR", "ACQUISITION_FAILED")])
def test_unresolved_and_provider_errors_are_distinct_without_download(tmp_path, monkeypatch, provider_outcome, expected):
    p, counts, _ = processor(tmp_path, monkeypatch)
    p.provider = object()
    monkeypatch.setattr("audio_similarity.stage5d0a_processor.discover_and_select_with_fallback",
                        lambda *args: {"outcome": provider_outcome, "selected_video_id": None})
    result = p.process(TRACK, {"selection": None, "source": None, "provenance": None,
                             "representation": None}, lambda *args, **kwargs: None)
    assert result["state"] == expected
    assert counts == {"acquisition": 0, "inference": 0}
    assert not p.selection_path(TRACK["spotify_track_id"]).exists()


def test_source_remains_indexed_when_frozen_windows_cannot_materialize(tmp_path, monkeypatch):
    import json
    p, _, _ = processor(tmp_path, monkeypatch)
    p.find_representation = lambda *args: None
    monkeypatch.setattr("audio_similarity.stage5d0a_processor.materialize", lambda *args, **kwargs:
        SimpleNamespace(clap=SimpleNamespace(inferred_segments=0), muq=SimpleNamespace(inferred_segments=0),
                        failure_categories={"INVALID_OR_TOO_SHORT_AUDIO": 1}))
    outcome = p.process(TRACK, {"selection": SELECTION, "source": None, "provenance": None,
                              "representation": None}, lambda *args, **kwargs: None)
    assert outcome["state"] == "MATERIALIZATION_FAILED"
    index = json.loads((p.directory / "source_index" / (TRACK["spotify_track_id"] + ".json")).read_text())
    assert (p.media / index["retained_relative_path"]).is_file()
    assert index["representation"] is None
    assert not list(p.media.glob(".stage5d-scratch-*"))
