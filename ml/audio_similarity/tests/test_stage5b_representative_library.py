from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import Stage5B1AValidationError, file_sha256
from audio_similarity.stage5b_representative_library import (
    DEFAULT_SAMPLE_SEED,
    LibraryTrack,
    build_benchmark_manifest,
    canonical_json_bytes,
    historical_exclusion_identities,
    load_library_snapshot,
    manifest_sha256,
    verify_frozen_manifest,
)


def _spotify_id(index: int) -> str:
    return f"{index:022d}"


def _raw_track(index: int, title: str | None = None) -> dict:
    return {
        "id": _spotify_id(index),
        "name": title or f"Song {index}",
        "artists": [{"name": f"Artist {index}"}],
        "album": {"name": f"Album {index}", "release_date": "2024-02-03"},
        "duration_ms": 200_000 + index,
        "external_ids": {"isrc": f"USABC24{index:05d}"},
        "is_local": False,
    }


def _snapshot(path: Path, tracks: list[dict], duplicate_first: bool = False) -> Path:
    sources = [{"source_key": "LIKED", "tracks": tracks}]
    if duplicate_first:
        sources.append({"source_key": "PLAYLIST:owned", "tracks": [tracks[0]]})
    path.write_text(json.dumps({
        "schema_version": "stage5b-owner-library-snapshot-v1",
        "sources": sources,
    }))
    return path


def test_library_dedupe_preserves_union_membership(tmp_path: Path) -> None:
    path = _snapshot(tmp_path / "snapshot.json", [_raw_track(1), _raw_track(2)], True)
    library = load_library_snapshot(path)
    assert len(library) == 2
    first = next(row for row in library if row.track.spotify_track_id == _spotify_id(1))
    assert first.source_keys == ("LIKED", "PLAYLIST:owned")
    assert first.track.release_year == 2024


def test_local_tracks_are_excluded_and_spotify_ids_required(tmp_path: Path) -> None:
    local = _raw_track(1)
    local["is_local"] = True
    good = _raw_track(2)
    assert len(load_library_snapshot(_snapshot(tmp_path / "good.json", [local, good]))) == 1
    missing = _raw_track(3)
    missing["id"] = None
    with pytest.raises(Stage5B1AValidationError, match="require Spotify IDs"):
        load_library_snapshot(_snapshot(tmp_path / "bad.json", [missing]))


def test_nonstandard_isrc_is_treated_as_missing_metadata(tmp_path: Path) -> None:
    invalid = _raw_track(1)
    invalid["external_ids"]["isrc"] = "INVALID12345678"
    library = load_library_snapshot(_snapshot(tmp_path / "snapshot.json", [invalid]))

    assert library[0].track.isrc is None


def test_historical_exclusion_uses_spotify_and_semantic_identity(tmp_path: Path) -> None:
    historical = tmp_path / "historical.json"
    historical.write_text(json.dumps({"tracks": [{
        "stable_track_id": "old",
        "spotify_track_id": _spotify_id(1),
        "title": "Same Song - 2020 Remaster",
        "artists": ["The Artist"],
        "album": "Album",
        "duration_ms": 200_000,
        "release_year": 2020,
        "isrc": None,
    }]}))
    identities, provenance = historical_exclusion_identities([historical])
    assert f"spotify:{_spotify_id(1)}" in identities
    assert "semantic:same song 2020 remaster::the artist" in identities
    assert "core:same song::the artist" in identities
    assert provenance["sources"][0]["sha256"] == file_sha256(historical)


def test_sample_is_deterministic_exact_and_has_no_substitution(tmp_path: Path) -> None:
    library = load_library_snapshot(
        _snapshot(tmp_path / "snapshot.json", [_raw_track(i) for i in range(1, 121)])
    )
    excluded = {f"spotify:{_spotify_id(index)}" for index in range(1, 6)}
    kwargs = {
        "sample_size": 100,
        "seed": DEFAULT_SAMPLE_SEED,
        "snapshot_sha256": "a" * 64,
        "exclusion_provenance": {"sources": []},
    }
    first = build_benchmark_manifest(library, excluded, **kwargs)
    second = build_benchmark_manifest(list(reversed(library)), excluded, **kwargs)
    assert first == second
    assert first["sampled_track_count"] == 100
    assert first["historically_excluded_track_count"] == 5
    assert len({row["spotify_track_id"] for row in first["tracks"]}) == 100
    assert first["post_freeze_substitutions"] == 0

    manifest = tmp_path / "manifest.json"
    digest = tmp_path / "manifest.sha256"
    manifest.write_bytes(canonical_json_bytes(first))
    digest.write_text(manifest_sha256(first) + "\n")
    assert verify_frozen_manifest(manifest, digest) == first
    first["post_freeze_substitutions"] = 1
    manifest.write_bytes(canonical_json_bytes(first))
    digest.write_text(file_sha256(manifest) + "\n")
    with pytest.raises(Stage5B1AValidationError, match="substitution"):
        verify_frozen_manifest(manifest, digest)


def test_fewer_than_100_uses_all_eligible_tracks(tmp_path: Path) -> None:
    library = load_library_snapshot(
        _snapshot(tmp_path / "snapshot.json", [_raw_track(i) for i in range(1, 11)])
    )
    manifest = build_benchmark_manifest(
        library,
        set(),
        sample_size=100,
        seed="fixed",
        snapshot_sha256="b" * 64,
        exclusion_provenance={"sources": []},
    )
    assert manifest["sampled_track_count"] == 10
