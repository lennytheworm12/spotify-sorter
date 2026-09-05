from __future__ import annotations

import json
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5b4c_artist_decomposition import (
    FALLBACK_SUCCESS,
    PRIMARY_SUCCESS,
    QUERY_CONTRACT_ID,
)
from audio_similarity.stage5b4c_artist_decomposition_experiment import (
    EXPERIMENT_ID,
    REQUIRED_ARTIFACTS,
    build_v3_query_plan,
    config_document,
    run_live,
    verify_artist_decomposition_history,
    ytdlp_provider_config,
)


GIRL_Q0 = "Girl, Interrupted 2xxx Miso"
GIRL_Q1 = "Girl, Interrupted 2xxx"
GIRL_Q2 = "Girl, Interrupted Miso"
ALL_STARS_Q0 = (
    "All The Stars (with SZA) - From Black Panther: The Album Kendrick Lamar SZA"
)


def _candidate(video_id: str, rank: int, query: str) -> dict:
    return {
        "rank": rank,
        "provider_rank": rank,
        "youtube_video_id": video_id,
        "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": f"Title {video_id}",
        "uploader": "Test - Topic",
        "channel": "Test - Topic",
        "duration_seconds": 181.0,
        "view_count": 100,
        "description": "metadata",
        "availability": None,
        "live_status": None,
        "provider": "yt_dlp",
        "query": query,
        "duplicate_occurrences": [],
    }


class _Provider:
    def __init__(self):
        self.calls: list[str] = []

    def discover_query(self, track, query, *, limit):
        self.calls.append(query)
        responses = {
            GIRL_Q0: [],
            GIRL_Q1: [],
            GIRL_Q2: [_candidate("DpXA_N3jnvE", 1, query)],
            ALL_STARS_Q0: [_candidate("ju4KQT0wL0I", 1, query)],
        }
        return {
            "track": track.to_dict(),
            "query": query,
            "request": {"download": False},
            "provider": {"name": "yt_dlp", "attempts": 1},
            "candidates": responses[query],
            "warnings": [],
            "error": None,
        }


def test_history_guards_pin_all_preceding_supplements_and_selector() -> None:
    project_root = Path(__file__).resolve().parents[1]
    history = verify_artist_decomposition_history(project_root)
    assert history["production_activation"] is False
    assert history["motivating_case"]["outcome"]["query"] == GIRL_Q0
    assert history["motivating_case"]["outcome"]["candidates"] == []
    assert history["motivating_case"]["outcome"]["warnings"] == []
    assert history["motivating_case"]["outcome"]["error"] is None
    assert history["selector"]["sha256"] == (
        "262ac3d0d7459170fef81336ee6f54f5523f2d8300fedee8a51798ce8439160f"
    )


def test_config_is_metadata_only_and_has_no_forbidden_provider_or_query_behavior() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = config_document(project_root)
    provider = ytdlp_provider_config()
    assert config["query_contract_id"] == QUERY_CONTRACT_ID
    assert config["architecture"]["fallback_trigger"] == (
        "VALID_PRIMARY_SEARCH_WITH_ZERO_USABLE_CANDIDATES_ONLY"
    )
    assert config["architecture"]["merge_candidate_pools"] is False
    assert config["query_policy"] == {
        "semantic_title_rewriting": False,
        "title_only_fallback": False,
        "forced_terms": [],
        "query_permutations": False,
        "artist_aliases": False,
        "song_specific_rules": False,
    }
    assert provider.search_prefix == "ytsearch3:"
    assert provider.skip_download is True
    assert provider.simulate is True
    assert provider.metadata_only_options()["skip_download"] is True
    assert config["scope_guards"]["playwright_invocations"] == 0
    assert config["scope_guards"]["audio_downloads"] == 0


def test_frozen_v3_plan_is_offline_complete_bounded_and_non_rejecting() -> None:
    project_root = Path(__file__).resolve().parents[1]
    plan = build_v3_query_plan(project_root)
    summary = plan["summary"]
    assert len(plan["tracks"]) == 100
    assert summary["tracks_total"] == 100
    assert (
        summary["tracks_with_1_artist"]
        + summary["tracks_with_2_artists"]
        + summary["tracks_with_3_or_more_artists"]
        == 100
    )
    assert summary["maximum_fallback_requests_per_track"] <= 3
    assert summary["malformed_or_empty_query_count"] == 0
    assert summary["punctuation_rejection_count"] == 0
    assert summary["live_searches_run"] == 0
    girl = next(
        row for row in plan["tracks"] if row["spotify_track_id"] == "1cBNzkPsAdI7XJaKIsjKUk"
    )
    assert girl["queries"] == {
        "Q0": GIRL_Q0,
        "Q1": GIRL_Q1,
        "Q2": GIRL_Q2,
        "Q3": None,
    }


def test_mocked_targeted_run_falls_back_only_for_motivating_case(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    provider = _Provider()
    summary = run_live(project_root, tmp_path, provider=provider)
    assert provider.calls == [GIRL_Q0, GIRL_Q1, GIRL_Q2, ALL_STARS_Q0]
    assert summary["tracks"] == [
        {
            "benchmark_id": "stage5b4_representative_v3_010",
            "outcome": FALLBACK_SUCCESS,
            "successful_query": GIRL_Q2,
            "candidate_video_ids": ["DpXA_N3jnvE"],
            "total_provider_requests": 3,
        },
        {
            "benchmark_id": "stage5b4_representative_v3_073",
            "outcome": PRIMARY_SUCCESS,
            "successful_query": ALL_STARS_Q0,
            "candidate_video_ids": ["ju4KQT0wL0I"],
            "total_provider_requests": 1,
        },
    ]
    recorded = json.loads((tmp_path / "targeted_discovery.json").read_text())
    assert recorded["scope_guards"]["candidate_pool_merges"] == 0
    assert recorded["scope_guards"]["audio_downloads"] == 0
    assert recorded["tracks"][0]["fallback_triggered"] is True
    assert recorded["tracks"][1]["fallback_triggered"] is False


def test_recorded_supplement_is_complete_hash_locked_and_validated() -> None:
    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "reports/stage5b4c_artist_query_decomposition"
    assert set(REQUIRED_ARTIFACTS) | {"artifact_manifest.json"} == {
        path.name for path in output_dir.iterdir() if path.is_file()
    }
    manifest = json.loads((output_dir / "artifact_manifest.json").read_text())
    metrics = json.loads((output_dir / "decomposition_metrics.json").read_text())
    discovery = json.loads((output_dir / "targeted_discovery.json").read_text())
    assert manifest["experiment_id"] == EXPERIMENT_ID
    assert manifest["verdict"] == "ARTIST_DECOMPOSITION_FALLBACK_VALIDATED"
    assert metrics["verdict"] == "ARTIST_DECOMPOSITION_FALLBACK_VALIDATED"
    assert metrics["human_review"]["first_safe_rank"] == 1
    assert metrics["frozen_candidate_contract"] == QUERY_CONTRACT_ID
    assert discovery["scope_guards"]["live_track_count"] == 2
    for name, identity in manifest["artifacts"].items():
        assert identity["sha256"] == file_sha256(output_dir / name)
    for identity in manifest["implementation"].values():
        assert identity["sha256"] == file_sha256(project_root / identity["path"])
    for group in manifest["frozen_inputs"].values():
        if "path" in group:
            assert group["sha256"] == file_sha256(project_root / group["path"])
        else:
            for identity in group.values():
                assert identity["sha256"] == file_sha256(
                    project_root / identity["path"]
                )
