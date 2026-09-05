from __future__ import annotations

import json
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5c2_discovery import freeze_selected_sources, run_discovery
from audio_similarity.stage5c2_manifest import (
    MANIFEST_SCHEMA_VERSION,
    SAMPLE_SEED,
    SAMPLE_SIZE,
    freeze_representative_manifest,
    validate_manifest,
)


def _track(index: int) -> dict:
    return {
        "benchmark_id": f"legacy_{index:03d}",
        "stage5c2_track_id": f"stage5c2_{index:03d}",
        "manifest_index": index,
        "spotify_track_id": f"{index:022d}",
        "title": f"Representative Song {index}",
        "artists": [f"Artist {index}", f"Guest {index}"],
        "album": f"Album {index}",
        "duration_ms": 180_000,
        "release_year": 2026,
        "isrc": f"USABC26{index:05d}",
        "sample_seed": SAMPLE_SEED,
        "library_source_keys": ["LIKED"],
    }


def _write_manifest(report: Path) -> dict:
    report.mkdir(parents=True)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "experiment_id": "stage5c2_representative_100",
        "sampled_track_count": SAMPLE_SIZE,
        "post_freeze_substitutions": 0,
        "frozen_contracts": {"selector_source": {"sha256": "frozen-selector"}},
        "tracks": [_track(index) for index in range(1, SAMPLE_SIZE + 1)],
    }
    path = report / "representative_manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    path.with_suffix(".sha256").write_text(file_sha256(path) + "\n", encoding="utf-8")
    return manifest


def _candidate(index: int, rank: int, query: str) -> dict:
    video_id = f"v{index:07d}{rank:03d}"
    return {
        "rank": rank,
        "provider_rank": rank,
        "youtube_video_id": video_id,
        "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": f"Representative Song {index}",
        "uploader": f"Artist {index} - Topic",
        "channel": f"Artist {index} - Topic",
        "duration_seconds": 180.0,
        "view_count": 1_000,
        "description": "Provided to YouTube",
        "query": query,
    }


class _Provider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def discover_query(self, track, query, *, limit):
        self.calls.append(query)
        index = int(track.stable_track_id.rsplit("_", 1)[1])
        primary = f"Representative Song {index} Artist {index} Guest {index}"
        fallback = f"Representative Song {index} Artist {index}"
        candidates = []
        if index == 1 and query == fallback:
            candidates = [_candidate(index, rank, query) for rank in (1, 2, 3)]
        elif index != 1 and query == primary:
            candidates = [_candidate(index, rank, query) for rank in (1, 2, 3)]
        return {
            "track": track.to_dict(),
            "query": query,
            "candidates": candidates,
            "warnings": [],
            "error": None,
        }


def test_representative_manifest_contract_is_exactly_100_unique_tracks(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "reports/stage5c2_representative_100")
    validate_manifest(manifest)
    assert len(manifest["tracks"]) == 100
    assert len({row["spotify_track_id"] for row in manifest["tracks"]}) == 100


def test_sampling_is_deterministic_and_excludes_historical_tracks(
    tmp_path: Path, monkeypatch
) -> None:
    history = tmp_path / "history.json"
    history.write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "spotify_track_id": f"{1:022d}",
                        "title": "Representative Song 1",
                        "artists": ["Artist 1"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    snapshot = tmp_path / "library.private.json"
    snapshot.write_text(
        json.dumps(
            {
                "schema_version": "stage5b-owner-library-snapshot-v1",
                "sources": [
                    {
                        "source_key": "LIKED",
                        "tracks": [
                            {
                                "id": f"{index:022d}",
                                "name": f"Representative Song {index}",
                                "artists": [{"name": f"Artist {index}"}],
                                "album": {
                                    "name": f"Album {index}",
                                    "release_date": "2026-01-01",
                                },
                                "duration_ms": 180_000,
                                "is_local": False,
                            }
                            for index in range(1, 121)
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "audio_similarity.stage5c2_manifest._validate_contracts",
        lambda _root: {"selector_source": {"sha256": "frozen"}},
    )
    monkeypatch.setattr(
        "audio_similarity.stage5c2_manifest.stage5c2_exclusion_paths",
        lambda _root: (history,),
    )
    first, first_sha = freeze_representative_manifest(
        tmp_path, snapshot_path=snapshot, report_dir=tmp_path / "report"
    )
    second, second_sha = freeze_representative_manifest(
        tmp_path, snapshot_path=snapshot, report_dir=tmp_path / "report"
    )
    assert first == second
    assert first_sha == second_sha
    assert f"{1:022d}" not in {row["spotify_track_id"] for row in first["tracks"]}


def test_discovery_uses_frozen_decomposition_then_freezes_exact_selected_ids(
    tmp_path: Path,
) -> None:
    report = tmp_path / "reports/stage5c2_representative_100"
    _write_manifest(report)
    provider = _Provider()
    discovery = run_discovery(
        tmp_path, provider, report_dir=report, sleep=lambda _seconds: None
    )
    assert discovery["summary"]["tracks_completed"] == 100
    assert discovery["summary"]["fallback_trigger_count"] == 1
    assert discovery["summary"]["fallback_success_count"] == 1
    assert provider.calls[:3] == [
        "Representative Song 1 Artist 1 Guest 1",
        "Representative Song 1 Artist 1",
        "Representative Song 2 Artist 2 Guest 2",
    ]
    selected, digest = freeze_selected_sources(tmp_path, report_dir=report)
    assert selected["automated_selection_count"] == 100
    assert selected["manual_tail_count"] == 0
    assert selected["post_freeze_substitutions"] == 0
    assert selected["exact_id_acquisition_only"] is True
    assert all("ytsearch" not in row["selected_youtube_url"] for row in selected["tracks"])
    assert file_sha256(report / "selected_sources.json") == digest


def test_primary_candidates_prevent_decomposition_and_native_pool_is_not_merged(
    tmp_path: Path,
) -> None:
    report = tmp_path / "reports/stage5c2_representative_100"
    _write_manifest(report)
    provider = _Provider()
    discovery = run_discovery(
        tmp_path, provider, report_dir=report, sleep=lambda _seconds: None
    )
    second = discovery["tracks"][1]["discovery"]
    assert len(second["attempts"]) == 1
    assert [candidate["rank"] for candidate in second["candidates"]] == [1, 2, 3]
    assert discovery["scope_guards"]["candidate_pool_merges"] == 0
