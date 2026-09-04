import json

from audio_similarity.stage5d0a_catalog import allocate_catalog, same_recording
from audio_similarity.stage5d0a_spotify import collect_cell
from audio_similarity.stage5d0a_manifest import build_global_manifest


def track(index, name="Song", isrc=None, duration=180000):
    return {"id": f"{index:022d}", "name": name,
            "artists": [{"name": "Artist"}], "duration_ms": duration,
            "album": {"name": "Album", "release_date": "2000-01-01"},
            "external_ids": {"isrc": isrc} if isrc else {}}


def test_duplicate_recordings_and_qualified_versions():
    assert same_recording(track(1, isrc="USAAA0000001"), track(2, isrc="USAAA0000001"))
    assert same_recording(track(1, "Song - Clean"), track(2, "Song - Explicit"))
    assert same_recording(track(1), track(2, duration=183000))
    assert not same_recording(track(1), track(2, duration=183001))
    for label in ("Live", "Acoustic", "Sped Up", "Slowed", "Remix", "Rerecorded"):
        assert not same_recording(track(1, isrc="same"), track(2, f"Song - {label}", isrc="same"))
    assert not same_recording(track(1, "Song - Alpha Remix"), track(2, "Song - Beta Remix"))


def test_cell_limit_alias_provenance_and_checkpoint_resume(tmp_path):
    calls = []
    def search(query, offset):
        calls.append((query, offset))
        return {"tracks": {"items": [track(i, f"Song {i}") for i in range(offset, offset + 10)],
                           "next": "next" if offset < 90 else None}}
    cell = collect_cell(2000, "POP", search, tmp_path)
    assert len(cell["candidates"]) == 75
    assert len(cell["candidates"][f"{1:022d}"]["alias_ranks"]) == 4
    count = len(calls)
    assert collect_cell(2000, "POP", search, tmp_path) == cell
    assert len(calls) == count


def test_global_ownership_backfill_and_same_year_redistribution():
    cells = []
    for bucket, aliases, count in (("POP", {"pop": 1}, 30), ("RNB_SOUL", {"r&b": 1, "soul": 2}, 27)):
        cells.append({"year": 2000, "bucket": bucket, "candidates": {
            f"{i:022d}": {"spotify": track(i, f"Song {i}"),
                         "alias_ranks": {alias: rank + i for alias, rank in aliases.items()}}
            for i in range(count)}})
    result = allocate_catalog(cells)
    assert len(result["tracks"]) == 30
    assert len({row["recording_id"] for row in result["tracks"]}) == 30
    assert all(row["assigned_bucket"] == "RNB_SOUL" for row in result["tracks"] if int(row["spotify_track_id"]) < 27)
    assert next(row for row in result["allocation_audit"] if row["year"] == 2000 and row["bucket"] == "RNB_SOUL")["selected"] == 27
    manifest = build_global_manifest(result, catalog_input_sha256="a" * 64)
    assert all(row["all_occurrences"] and row["recording_id"] for row in manifest["tracks"])
    assert result == allocate_catalog(list(reversed(cells)))


def test_dedupe_does_not_chain_duration_tolerance():
    candidates = {str(i): {"spotify": track(i, duration=180000 + i * 3000), "alias_ranks": {"pop": i+1}} for i in range(3)}
    result = allocate_catalog([{"year": 2000, "bucket": "POP", "candidates": candidates}])
    assert result["unique_recording_candidates"] == 2
