from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_similarity.stage5b1a_models import SpotifyTrack, Stage5B1AValidationError
from audio_similarity.stage5b2_youtube_prior import (
    BENCHMARK_ID,
    SAMPLE_SIZE,
    freeze_youtube_prior_manifest,
    historical_manifest_paths,
    natural_title_artist_query,
)


def _track(index: int) -> dict:
    return {
        "id": f"{index:022d}",
        "name": f"Natural Song {index}",
        "artists": [{"name": f"Artist {index}"}],
        "album": {"name": f"Album {index}", "release_date": "2025-01-01"},
        "duration_ms": 180_000 + index,
        "external_ids": {"isrc": f"USABC25{index:05d}"},
        "is_local": False,
    }


def _project(tmp_path: Path) -> tuple[Path, Path]:
    for relative in (
        "reports/stage5b1a/frozen_tracks.json",
        "reports/stage5b1b/heldout_tracks.json",
        "reports/stage5b1b_fresh_challenge/challenge_tracks.json",
        "reports/stage5b_representative_library_v1/benchmark_manifest.json",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"tracks": []}))
    snapshot = tmp_path / "library.private.json"
    snapshot.write_text(json.dumps({
        "schema_version": "stage5b-owner-library-snapshot-v1",
        "sources": [{"source_key": "LIKED", "tracks": [_track(i) for i in range(1, 111)]}],
    }))
    return tmp_path, snapshot


def test_natural_query_is_unquoted_unrewritten_title_plus_primary_artist() -> None:
    track = SpotifyTrack(
        stable_track_id="track",
        spotify_track_id="0" * 22,
        title="Golden (with Guest)",
        artists=("HUNTR/X", "Guest"),
        album="Album",
        duration_ms=200_000,
        release_year=2025,
        isrc=None,
    )

    query = natural_title_artist_query(track)
    assert query == "Golden (with Guest) HUNTR/X"
    assert '"' not in query
    assert "official" not in query.lower()


def test_manifest_is_exact_fresh_deterministic_100_and_immutable(tmp_path: Path) -> None:
    project, snapshot = _project(tmp_path)
    output = project / "reports/stage5b_youtube_prior_v1"
    first = freeze_youtube_prior_manifest(project, snapshot, output)
    second = freeze_youtube_prior_manifest(project, snapshot, output)

    assert first == second
    assert first["manifest"]["benchmark_id"] == BENCHMARK_ID
    assert first["manifest"]["sampled_track_count"] == SAMPLE_SIZE
    assert len({row["spotify_track_id"] for row in first["manifest"]["tracks"]}) == 100
    assert first["manifest"]["post_freeze_substitutions"] == 0
    assert first["config"]["retrieval"]["candidate_limit"] == 3
    assert first["config"]["scope_guards"]["existing_resolver_invocations"] == 0

    value = json.loads((output / "benchmark_manifest.json").read_text())
    value["post_freeze_substitutions"] = 1
    (output / "benchmark_manifest.json").write_text(json.dumps(value))
    with pytest.raises(Stage5B1AValidationError, match="refusing to replace"):
        freeze_youtube_prior_manifest(project, snapshot, output)


def test_all_prior_benchmark_sources_are_explicit() -> None:
    root = Path("/project")
    assert [path.name for path in historical_manifest_paths(root)] == [
        "frozen_tracks.json",
        "heldout_tracks.json",
        "challenge_tracks.json",
        "benchmark_manifest.json",
    ]
