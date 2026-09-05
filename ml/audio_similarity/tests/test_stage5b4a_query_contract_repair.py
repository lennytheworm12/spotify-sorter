from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from audio_similarity.stage5b1a_models import (
    SpotifyTrack,
    Stage5B1AValidationError,
    file_sha256,
)
from audio_similarity.stage5b4a_query_contract_repair import (
    QUERY_CONTRACT_ID,
    REVIEW_COLUMNS,
    build_offline_replay,
    first_distinct_artists,
    natural_title_first3_artists_query,
    run_repaired_discovery,
    sanitize_query_text,
    validate_human_review,
    write_human_review,
)


def _track(title: str, artists: list[str]) -> SpotifyTrack:
    return SpotifyTrack.from_dict({
        "stable_track_id": "query-test",
        "title": title,
        "artists": artists,
    })


@pytest.mark.parametrize(
    ("artists", "expected"),
    [
        (["aespa"], "Whiplash aespa"),
        (["2xxx", "Miso"], "Whiplash 2xxx Miso"),
        (["A", "B", "C"], "Whiplash A B C"),
        (["A", "B", "C", "D"], "Whiplash A B C"),
    ],
)
def test_query_includes_up_to_first_three_artists(
    artists: list[str], expected: str
) -> None:
    assert natural_title_first3_artists_query(_track("Whiplash", artists)) == expected


def test_artist_deduplication_is_normalized_and_preserves_credited_order() -> None:
    track = _track("Title", ["Artist A", " artist a ", "Ｂ", "B", "C", "D"])
    assert first_distinct_artists(track.artists) == ("Artist A", "Ｂ", "C")
    assert natural_title_first3_artists_query(track) == "Title Artist A Ｂ C"


def test_quoted_soundtrack_title_is_sanitized_without_semantic_rewriting() -> None:
    track = _track(
        'All The Stars - From “Black Panther: The Album”',
        ["Kendrick Lamar", "SZA"],
    )
    query = natural_title_first3_artists_query(track)
    assert query == "All The Stars - From Black Panther: The Album Kendrick Lamar SZA"
    assert '"' not in query
    assert "From Black Panther: The Album" in query


@pytest.mark.parametrize(
    ("title", "artists", "expected"),
    [
        (
            "넘어와 (Feat. 백예린)",
            ["DEAN", "Yerin Baek"],
            "넘어와 (Feat. 백예린) DEAN Yerin Baek",
        ),
        ("夜に駆ける", ["YOASOBI"], "夜に駆ける YOASOBI"),
        ("光年之外", ["G.E.M."], "光年之外 G.E.M."),
        (
            "Scribble (feat. Wonstein)",
            ["Gyubin", "Wonstein"],
            "Scribble (feat. Wonstein) Gyubin Wonstein",
        ),
    ],
)
def test_unicode_and_parenthetical_title_information_is_preserved(
    title: str, artists: list[str], expected: str
) -> None:
    assert natural_title_first3_artists_query(_track(title, artists)) == expected


def test_query_has_no_forced_terms_or_exact_match_quoting() -> None:
    query = natural_title_first3_artists_query(_track("Ordinary Song", ["Artist One"]))
    assert query == "Ordinary Song Artist One"
    assert "official" not in query.casefold()
    assert not query.startswith(('"', "'"))
    assert not query.endswith(('"', "'"))


def test_sanitation_normalizes_controls_smart_quotes_and_whitespace() -> None:
    assert sanitize_query_text("  A\t‘single’\x00  \"double\"  ") == "A 'single' double"


def test_entire_frozen_v3_manifest_replays_offline() -> None:
    project_root = Path(__file__).resolve().parents[1]
    contract, replay = build_offline_replay(project_root)
    assert contract["query_contract_id"] == QUERY_CONTRACT_ID
    assert replay["summary"]["tracks_total"] == 100
    assert replay["summary"]["non_empty_query_count"] == 100
    assert replay["summary"]["query_construction_failure_count"] == 0
    assert replay["summary"]["maximum_artist_count"] == 3
    assert replay["summary"]["punctuation_rejection_count"] == 0
    assert replay["summary"]["live_searches_run"] == 0
    assert replay["summary"]["tracks_with_harmless_punctuation"] > 0
    assert all(1 <= row["artist_count_included"] <= 3 for row in replay["tracks"])
    assert all(row["repaired_query"] for row in replay["tracks"])
    girl = next(
        row
        for row in replay["tracks"]
        if row["raw_spotify_title"] == "Girl, Interrupted"
    )
    assert girl["repaired_query"] == "Girl, Interrupted 2xxx Miso"
    stars = next(
        row
        for row in replay["tracks"]
        if row["raw_spotify_title"].startswith("All The Stars")
    )
    assert stars["repaired_query"] == (
        "All The Stars (with SZA) - From Black Panther: The Album Kendrick Lamar SZA"
    )


class _FakeAdapter:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def discover_query(self, track, query, *, limit):
        self.queries.append(query)
        assert limit == 3
        candidates = [
            {
                "rank": rank,
                "provider_rank": rank,
                "youtube_video_id": f"v{len(self.queries):07d}{rank:03d}",
                "canonical_url": f"https://www.youtube.com/watch?v=v{len(self.queries):07d}{rank:03d}",
                "title": f"Candidate {rank}",
                "uploader": "Uploader",
                "channel": "Channel",
                "duration_seconds": 180.0,
                "view_count": 100,
                "description": "Metadata only",
            }
            for rank in (1, 2, 3)
        ]
        return SimpleNamespace(to_dict=lambda: {
            "track": track.to_dict(),
            "query": query,
            "request": {"download": False, "search_expression": f"ytsearch3:{query}"},
            "provider": {"name": "yt_dlp", "version": "test", "attempts": 1},
            "normalized_results": [],
            "candidates": candidates,
            "candidate_video_ids": [row["youtube_video_id"] for row in candidates],
            "warnings": [],
            "error": None,
        })


def test_discovery_is_bounded_to_two_failed_v3_cases_and_metadata_only(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    adapter = _FakeAdapter()
    result = run_repaired_discovery(
        project_root,
        tmp_path,
        adapter,
        sleep=lambda _seconds: None,
    )
    assert adapter.queries == [
        "Girl, Interrupted 2xxx Miso",
        "All The Stars (with SZA) - From Black Panther: The Album Kendrick Lamar SZA",
    ]
    assert result["summary"]["searches_completed"] == 2
    assert result["scope_guards"]["full_v3_searches_rerun"] is False
    assert result["scope_guards"]["audio_downloads"] == 0
    assert all(
        row["outcome"]["request"]["download"] is False
        and row["outcome"]["request"]["search_expression"].startswith("ytsearch3:")
        for row in result["tracks"]
    )
    with pytest.raises(Stage5B1AValidationError, match="already recorded"):
        run_repaired_discovery(project_root, tmp_path, adapter)


def test_review_enforces_sequential_stop_at_first_safe(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    run_repaired_discovery(
        project_root, tmp_path, _FakeAdapter(), sleep=lambda _seconds: None
    )
    review_path = write_human_review(tmp_path)
    with review_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for index, row in enumerate(rows):
        rank = int(row["youtube_rank"])
        if index < 3:
            row["candidate_review_label"] = (
                "WRONG" if rank == 1 else "ACCEPTABLE" if rank == 2 else ""
            )
        else:
            row["candidate_review_label"] = "IDEAL" if rank == 1 else ""
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    result = validate_human_review(review_path)
    assert result["all_cases_safe"] is True
    assert sorted(case["first_safe_rank"] for case in result["cases"]) == [1, 2]
    rows[2]["candidate_review_label"] = "UNCERTAIN"
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(Stage5B1AValidationError, match="continue after first SAFE"):
        validate_human_review(review_path)


def test_committed_supplement_artifacts_preserve_v3_and_record_failed_gate() -> None:
    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "reports/stage5b4a_query_contract_repair"
    required = {
        "repaired_query_contract.json",
        "v3_query_replay.json",
        "repaired_discovery.json",
        "human_review.csv",
        "query_contract_report.md",
        "artifact_manifest.json",
    }
    assert required == {path.name for path in output_dir.iterdir() if path.is_file()}
    artifact_manifest = json.loads((output_dir / "artifact_manifest.json").read_text())
    discovery = json.loads((output_dir / "repaired_discovery.json").read_text())
    review = validate_human_review(output_dir / "human_review.csv")
    assert artifact_manifest["verdict"] == "FAIL"
    assert artifact_manifest["query_contract_id"] == QUERY_CONTRACT_ID
    assert discovery["summary"]["searches_completed"] == 2
    assert discovery["summary"]["valid_search_count"] == 2
    assert discovery["summary"]["tracks_with_candidates"] == 1
    assert discovery["summary"]["zero_candidate_tracks"] == 1
    assert review["safe_case_count"] == 1
    assert review["all_cases_safe"] is False
    for name, identity in artifact_manifest["artifacts"].items():
        assert identity["sha256"] == file_sha256(output_dir / name)
    for identity in artifact_manifest["frozen_v3_inputs"].values():
        assert identity["sha256"] == file_sha256(project_root / identity["path"])
    report = (output_dir / "query_contract_report.md").read_text()
    assert "Do not freeze the repaired contract" in report
    assert "Historical V3 artifacts overwritten: 0" in report
