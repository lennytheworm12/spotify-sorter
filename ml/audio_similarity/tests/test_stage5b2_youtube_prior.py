from __future__ import annotations

import json
import csv
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from audio_similarity.stage5b1a_models import SpotifyTrack, Stage5B1AValidationError
from audio_similarity.stage5b2_youtube_prior import (
    BENCHMARK_ID,
    SAMPLE_SIZE,
    freeze_youtube_prior_manifest,
    build_blinded_sol_payload,
    historical_manifest_paths,
    load_youtube_prior_config,
    natural_title_artist_query,
    run_top3_discovery,
)
from audio_similarity.stage5b2_youtube_prior_review import (
    SAFE_LABELS,
    YoutubePriorReviewStore,
    first_safe_rank,
    required_rank,
    write_human_review_artifacts,
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


class _FakeAdapter:
    def discover_query(self, track, query, *, limit):
        assert query == natural_title_artist_query(track)
        assert limit == 3
        candidates = [
            {
                "rank": rank,
                "provider_rank": rank,
                "youtube_video_id": f"vid{rank:08d}",
                "canonical_url": f"https://www.youtube.com/watch?v=vid{rank:08d}",
                "title": f"Candidate {rank}",
                "uploader": "Uploader",
                "channel": "Channel",
                "duration_seconds": 180.0,
                "view_count": 100,
                "description": "Raw metadata",
            }
            for rank in (1, 2, 3)
        ]
        return SimpleNamespace(to_dict=lambda: {
            "track": track.to_dict(),
            "query": query,
            "provider": {"name": "yt_dlp", "version": "test"},
            "candidates": candidates,
            "candidate_video_ids": [row["youtube_video_id"] for row in candidates],
            "warnings": [],
            "error": None,
        })


def test_top_three_order_and_blinded_sol_payload_exclude_rank(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    config = load_youtube_prior_config(
        root / "reports/stage5b_youtube_prior_v1/benchmark_config.json"
    )
    config = replace(config, output_dir=tmp_path)
    discovery = run_top3_discovery(config, _FakeAdapter(), sleep=lambda _seconds: None)

    assert discovery["summary"]["tracks_completed"] == 100
    assert discovery["summary"]["candidate_count"] == 300
    assert discovery["scope_guards"]["existing_resolver_invocations"] == 0
    assert [row["rank"] for row in discovery["tracks"][0]["outcome"]["candidates"]] == [1, 2, 3]
    payload = build_blinded_sol_payload(config)
    assert payload["candidate_count"] == 300
    assert payload["search_rank_visible"] is False
    assert all("rank" not in candidate for row in payload["tracks"] for candidate in row["candidates"])
    assert all("human" not in json.dumps(candidate).lower() for row in payload["tracks"] for candidate in row["candidates"])

    with pytest.raises(Stage5B1AValidationError, match="already frozen"):
        run_top3_discovery(config, _FakeAdapter(), sleep=lambda _seconds: None)


def test_adaptive_review_protocol_and_autosave_store(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    config = load_youtube_prior_config(
        root / "reports/stage5b_youtube_prior_v1/benchmark_config.json"
    )
    config = replace(config, output_dir=tmp_path)
    run_top3_discovery(config, _FakeAdapter(), sleep=lambda _seconds: None)
    queue, review_path = write_human_review_artifacts(config)

    with review_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert queue["protocol"] == "REVIEW_NATIVE_RANKS_UNTIL_FIRST_SAFE"
    assert len(rows) == 300
    assert set(queue["safe_labels"]) == SAFE_LABELS
    assert required_rank(rows[:3]) == 1
    assert first_safe_rank(rows[:3]) is None

    store = YoutubePriorReviewStore(review_path)
    session = store.session()
    first = session["cases"][0]
    assert session["mode"] == "stage5b2_youtube_prior_review"
    assert [row["rank"] for row in first["candidates"]] == [1]
    with pytest.raises(Stage5B1AValidationError, match="earlier YouTube ranks"):
        store.submit(first["stable_track_id"], "vid00000002", "IDEAL")

    store.submit(first["stable_track_id"], "vid00000001", "WRONG", "wrong version")
    first = store.session()["cases"][0]
    assert first["next_required_rank"] == 2
    assert [row["rank"] for row in first["candidates"]] == [1, 2]

    store.submit(first["stable_track_id"], "vid00000002", "ACCEPTABLE")
    first = store.session()["cases"][0]
    assert first["review_complete"] is True
    assert first["next_required_rank"] is None
    assert [row["rank"] for row in first["candidates"]] == [1, 2]


def test_rank_three_is_requested_only_after_two_non_safe_labels(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    config = load_youtube_prior_config(
        root / "reports/stage5b_youtube_prior_v1/benchmark_config.json"
    )
    config = replace(config, output_dir=tmp_path)
    run_top3_discovery(config, _FakeAdapter(), sleep=lambda _seconds: None)
    _, review_path = write_human_review_artifacts(config)
    store = YoutubePriorReviewStore(review_path)
    first = store.session()["cases"][0]

    store.submit(first["stable_track_id"], "vid00000001", "UNCERTAIN")
    store.submit(first["stable_track_id"], "vid00000002", "WRONG")
    first = store.session()["cases"][0]
    assert first["next_required_rank"] == 3
    assert [row["rank"] for row in first["candidates"]] == [1, 2, 3]

    store.submit(first["stable_track_id"], "vid00000003", "WRONG")
    first = store.session()["cases"][0]
    assert first["review_complete"] is True
    assert first_safe_rank([
        {
            "youtube_rank": str(candidate["rank"]),
            "candidate_review_label": candidate["review"]["label"],
        }
        for candidate in first["candidates"]
    ]) is None
