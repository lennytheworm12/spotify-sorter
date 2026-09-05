"""Artifacts and bounded evaluation for credited-artist query decomposition."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .stage5b1a2_config import YtDlpProviderConfig
from .stage5b1a2_ytdlp import YtDlpDiscoveryAdapter, YtDlpPythonBackend
from .stage5b1a_config import QueryConfig
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError, file_sha256
from .stage5b1b_artifacts import atomic_json
from .stage5b4c_artist_decomposition import (
    ALL_QUERY_VARIANTS_EMPTY,
    FALLBACK_SUCCESS,
    PRIMARY_SUCCESS,
    PROVIDER_ERROR,
    QUERY_CONTRACT_ID,
    build_artist_decomposition_plan,
    discover_with_artist_decomposition,
)
from .stage5b4c_experiment import verify_stage5b4c_history


EXPERIMENT_ID = "STAGE5B4C_ARTIST_QUERY_DECOMPOSITION_V1"
OUTPUT_DIRECTORY = "reports/stage5b4c_artist_query_decomposition"
V3_BENCHMARK_ID = "STAGE5B4_REPRESENTATIVE_V3"
SAFE_LABELS = frozenset({"IDEAL", "ACCEPTABLE"})
VALID_LABELS = frozenset({"", "IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"})
REQUIRED_ARTIFACTS = (
    "query_decomposition_config.json",
    "targeted_discovery.json",
    "query_plan_v3.json",
    "human_review.csv",
    "decomposition_metrics.json",
    "decomposition_report.md",
)
REVIEW_COLUMNS = (
    "review_schema_version",
    "experiment_id",
    "benchmark_id",
    "spotify_track_id",
    "expected_title",
    "expected_artists",
    "expected_duration_seconds",
    "successful_query",
    "discovery_mode",
    "query_variant_index",
    "query_artist",
    "candidate_rank",
    "candidate_video_id",
    "candidate_url",
    "candidate_title",
    "candidate_uploader",
    "candidate_channel",
    "candidate_duration_seconds",
    "candidate_view_count",
    "candidate_description",
    "candidate_review_label",
    "candidate_note",
    "track_note",
)


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return payload


def _identity(path: Path, project_root: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(project_root)),
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def verify_artist_decomposition_history(project_root: str | Path) -> dict[str, Any]:
    """Verify every preceding supplement plus the frozen V3 and selector evidence."""

    project_root = Path(project_root).resolve()
    history = verify_stage5b4c_history(project_root)
    prior_dir = project_root / "reports/stage5b4c_youtube_data_api_fallback"
    manifest_path = prior_dir / "artifact_manifest.json"
    manifest = _json(manifest_path)
    if manifest.get("verdict") != "YOUTUBE_DATA_API_FALLBACK_FAILED":
        raise Stage5B1AValidationError("unexpected official Data API supplement verdict")
    for group in ("artifacts", "implementation", "frozen_inputs"):
        for name, expected in manifest.get(group, {}).items():
            path = (
                prior_dir / name
                if group == "artifacts"
                else project_root / str(expected.get("path", ""))
            )
            if not path.is_file() or file_sha256(path) != expected.get("sha256"):
                raise Stage5B1AValidationError(
                    f"official Data API supplement {group} changed: {name}"
                )
    motivating = history["motivating_case"]
    outcome = motivating.get("outcome") or {}
    if (
        outcome.get("query") != "Girl, Interrupted 2xxx Miso"
        or outcome.get("candidates") != []
        or outcome.get("error") is not None
        or outcome.get("warnings") != []
    ):
        raise Stage5B1AValidationError("unexpected historical motivating-case evidence")
    return {
        **history,
        "official_data_api_manifest": _identity(manifest_path, project_root),
        "official_data_api_artifacts": {
            name: _identity(prior_dir / name, project_root)
            for name in manifest["artifacts"]
        },
        "production_activation": False,
    }


def ytdlp_provider_config() -> YtDlpProviderConfig:
    return YtDlpProviderConfig(
        candidate_limit=3,
        search_prefix="ytsearch3:",
        extract_flat="in_playlist",
        skip_download=True,
        simulate=True,
        ignore_user_config=True,
        cache_enabled=False,
        socket_timeout_seconds=30,
        max_attempts=2,
        retry_backoff_seconds=2.0,
        sleep_between_tracks_seconds=0.0,
    )


def ytdlp_adapter() -> YtDlpDiscoveryAdapter:
    provider = ytdlp_provider_config()
    inert_query = QueryConfig(
        variant_id="stage5b4c-explicit-decomposition-query",
        template="{normalized_title} {primary_artist}",
        normalize_featured_artist_noise=False,
    )
    return YtDlpDiscoveryAdapter(
        provider,
        inert_query,
        YtDlpPythonBackend(provider),
    )


def _v3_manifest(project_root: Path) -> dict[str, Any]:
    manifest = _json(
        project_root / "reports/stage5b4_representative_v3/benchmark_manifest.json"
    )
    tracks = manifest.get("tracks")
    if (
        manifest.get("benchmark_id") != V3_BENCHMARK_ID
        or manifest.get("sampled_track_count") != 100
        or not isinstance(tracks, list)
        or len(tracks) != 100
    ):
        raise Stage5B1AValidationError("unexpected frozen Representative V3 manifest")
    return manifest


def _track(row: dict[str, Any]) -> SpotifyTrack:
    return SpotifyTrack.from_dict(
        {
            "stable_track_id": row["benchmark_id"],
            "spotify_track_id": row.get("spotify_track_id"),
            "title": row["title"],
            "artists": row["artists"],
            "album": row.get("album"),
            "duration_ms": row.get("duration_ms"),
            "release_year": row.get("release_year"),
            "isrc": row.get("isrc"),
        }
    )


def build_v3_query_plan(project_root: str | Path) -> dict[str, Any]:
    """Build all potential query plans from frozen metadata without searches."""

    project_root = Path(project_root).resolve()
    manifest = _v3_manifest(project_root)
    rows: list[dict[str, Any]] = []
    artist_counts = {"one_artist": 0, "two_artists": 0, "three_or_more_artists": 0}
    punctuation_count = 0
    duplicate_removed = 0
    possible_fallbacks = 0
    for raw in manifest["tracks"]:
        track = _track(raw)
        plan = build_artist_decomposition_plan(track)
        count = len(plan.artists)
        bucket = (
            "one_artist"
            if count == 1
            else "two_artists"
            if count == 2
            else "three_or_more_artists"
        )
        artist_counts[bucket] += 1
        punctuation_count += int(
            any(character in track.title for character in "\"':()[]-&")
        )
        duplicate_removed += plan.duplicate_fallback_queries_removed
        possible_fallbacks += len(plan.fallbacks)
        queries = {"Q0": plan.primary.query, "Q1": None, "Q2": None, "Q3": None}
        for variant in plan.fallbacks:
            queries[f"Q{variant.index}"] = variant.query
        rows.append(
            {
                "benchmark_id": track.stable_track_id,
                "spotify_track_id": track.spotify_track_id,
                "raw_spotify_title": track.title,
                "credited_artists": list(track.artists),
                **plan.to_dict(),
                "queries": queries,
            }
        )
    return {
        "schema_version": "stage5b4c-v3-query-plan-v1",
        "experiment_id": EXPERIMENT_ID,
        "source_benchmark_id": V3_BENCHMARK_ID,
        "query_contract_id": QUERY_CONTRACT_ID,
        "analysis_mode": "OFFLINE_FROZEN_METADATA_ONLY",
        "summary": {
            "tracks_total": len(rows),
            "tracks_with_1_artist": artist_counts["one_artist"],
            "tracks_with_2_artists": artist_counts["two_artists"],
            "tracks_with_3_or_more_artists": artist_counts[
                "three_or_more_artists"
            ],
            "maximum_fallback_requests_per_track": max(
                len(row["fallbacks"]) for row in rows
            ),
            "maximum_possible_fallback_requests_across_v3": possible_fallbacks,
            "duplicate_fallback_queries_removed": duplicate_removed,
            "malformed_or_empty_query_count": 0,
            "tracks_with_harmless_punctuation": punctuation_count,
            "punctuation_rejection_count": 0,
            "live_searches_run": 0,
        },
        "tracks": rows,
    }


def config_document(project_root: str | Path) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    history = verify_artist_decomposition_history(project_root)
    provider = ytdlp_provider_config()
    return {
        "schema_version": "stage5b4c-query-decomposition-config-v1",
        "experiment_id": EXPERIMENT_ID,
        "query_contract_id": QUERY_CONTRACT_ID,
        "architecture": {
            "primary": "sanitized title + first up to 3 distinct credited artists",
            "fallback_trigger": "VALID_PRIMARY_SEARCH_WITH_ZERO_USABLE_CANDIDATES_ONLY",
            "fallback": "same title + one credited artist, sequential credited order",
            "maximum_distinct_artists": 3,
            "stop_at_first_non_empty_pool": True,
            "merge_candidate_pools": False,
            "selector": "STAGE5B3_MINIMAL_YOUTUBE_SELECTOR_V1_UNCHANGED",
        },
        "provider": {
            "name": "yt_dlp",
            "search_mode": "ytsearch3",
            "candidate_limit": provider.candidate_limit,
            "metadata_only_options": provider.metadata_only_options(),
            "sequential_requests": True,
        },
        "query_policy": {
            "semantic_title_rewriting": False,
            "title_only_fallback": False,
            "forced_terms": [],
            "query_permutations": False,
            "artist_aliases": False,
            "song_specific_rules": False,
        },
        "targeted_tracks": [
            "stage5b4_representative_v3_010",
            "stage5b4_representative_v3_073",
        ],
        "frozen_inputs": {
            "stage5b4a_artifacts": history["stage5b4a_artifacts"],
            "stage5b4b_manifest": history["stage5b4b_manifest"],
            "official_data_api_manifest": history["official_data_api_manifest"],
            "representative_v3_artifacts": history["representative_v3_artifacts"],
            "stage5b3_selector": history["selector"],
        },
        "scope_guards": {
            "targeted_live_tracks": 2,
            "broad_v3_searches": 0,
            "playwright_invocations": 0,
            "data_api_required": False,
            "production_activation": False,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
    }


def prepare(project_root: str | Path, output_dir: str | Path) -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = (
        output_dir / "query_decomposition_config.json",
        output_dir / "query_plan_v3.json",
    )
    if any(path.exists() for path in paths):
        raise Stage5B1AValidationError("Stage 5B.4C preparation artifacts already exist")
    config = config_document(project_root)
    plan = build_v3_query_plan(project_root)
    atomic_json(paths[0], config)
    atomic_json(paths[1], plan)
    return {"config": config, "query_plan_summary": plan["summary"]}


def run_live(
    project_root: str | Path,
    output_dir: str | Path,
    *,
    provider: Any | None = None,
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "targeted_discovery.json"
    if path.exists():
        raise Stage5B1AValidationError("Stage 5B.4C targeted live evidence already exists")
    history = verify_artist_decomposition_history(project_root)
    manifest = _v3_manifest(project_root)
    by_id = {row["benchmark_id"]: row for row in manifest["tracks"]}
    cases = (
        ("MOTIVATING_ZERO_RESULT_CASE", "stage5b4_representative_v3_010"),
        ("PRIMARY_SUCCESS_REGRESSION", "stage5b4_representative_v3_073"),
    )
    adapter = provider or ytdlp_adapter()
    results = []
    for purpose, benchmark_id in cases:
        track = _track(by_id[benchmark_id])
        result = discover_with_artist_decomposition(track, adapter)
        result["case_purpose"] = purpose
        result["Q0"] = result["query_plan"]["primary"]["query"]
        result["Q0_result_count"] = result["attempts"][0]["result_count"]
        result["fallback_triggered"] = len(result["attempts"]) > 1
        result["fallback_queries_attempted"] = [
            attempt
            for attempt in result["attempts"]
            if attempt["query_variant_index"] > 0
        ]
        results.append(result)
    document = {
        "schema_version": "stage5b4c-targeted-discovery-v1",
        "experiment_id": EXPERIMENT_ID,
        "query_contract_id": QUERY_CONTRACT_ID,
        "historical_primary_zero_result_evidence": history["motivating_case"],
        "tracks": results,
        "scope_guards": {
            "live_track_count": 2,
            "requests_are_sequential": True,
            "first_non_empty_pool_only": True,
            "candidate_pool_merges": 0,
            "playwright_invocations": 0,
            "data_api_invocations": 0,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
    }
    atomic_json(path, document)
    return {
        "tracks": [
            {
                "benchmark_id": result["track"]["stable_track_id"],
                "outcome": result["outcome"],
                "successful_query": result["successful_query"],
                "candidate_video_ids": result["candidate_video_ids"],
                "total_provider_requests": result["total_provider_requests"],
            }
            for result in results
        ]
    }


def write_review(output_dir: str | Path) -> Path:
    output_dir = Path(output_dir).resolve()
    discovery = _json(output_dir / "targeted_discovery.json")
    path = output_dir / "human_review.csv"
    if path.exists():
        raise Stage5B1AValidationError("Stage 5B.4C human review already exists")
    motivating = next(
        row
        for row in discovery["tracks"]
        if row["case_purpose"] == "MOTIVATING_ZERO_RESULT_CASE"
    )
    track = motivating["track"]
    candidates = motivating.get("candidates") or []
    rows = []
    for candidate in candidates or [None]:
        rows.append(
            {
                "review_schema_version": "stage5b4c-human-review-v1",
                "experiment_id": EXPERIMENT_ID,
                "benchmark_id": track["stable_track_id"],
                "spotify_track_id": track.get("spotify_track_id") or "",
                "expected_title": track["title"],
                "expected_artists": " | ".join(track["artists"]),
                "expected_duration_seconds": track["duration_ms"] / 1000,
                "successful_query": motivating.get("successful_query") or "",
                "discovery_mode": motivating.get("discovery_mode") or "",
                "query_variant_index": (
                    motivating.get("query_variant_index")
                    if motivating.get("query_variant_index") is not None
                    else ""
                ),
                "query_artist": motivating.get("query_artist") or "",
                "candidate_rank": candidate.get("rank", "") if candidate else "",
                "candidate_video_id": (
                    candidate.get("youtube_video_id", "") if candidate else ""
                ),
                "candidate_url": candidate.get("canonical_url", "") if candidate else "",
                "candidate_title": (candidate.get("title") or "") if candidate else "",
                "candidate_uploader": (
                    candidate.get("uploader") or "" if candidate else ""
                ),
                "candidate_channel": (
                    candidate.get("channel") or "" if candidate else ""
                ),
                "candidate_duration_seconds": (
                    candidate.get("duration_seconds")
                    if candidate and candidate.get("duration_seconds") is not None
                    else ""
                ),
                "candidate_view_count": (
                    candidate.get("view_count")
                    if candidate and candidate.get("view_count") is not None
                    else ""
                ),
                "candidate_description": (
                    candidate.get("description") or "" if candidate else ""
                ),
                "candidate_review_label": "",
                "candidate_note": "",
                "track_note": "" if candidate else "NO_RECOVERED_CANDIDATES",
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def validate_review(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise Stage5B1AValidationError("unexpected Stage 5B.4C review columns")
        rows = list(reader)
    if not rows:
        raise Stage5B1AValidationError("Stage 5B.4C review is empty")
    labels = [row["candidate_review_label"].strip().upper() for row in rows]
    if any(label not in VALID_LABELS for label in labels):
        raise Stage5B1AValidationError("invalid Stage 5B.4C human label")
    if not rows[0]["candidate_video_id"]:
        if len(rows) != 1 or labels[0]:
            raise Stage5B1AValidationError("invalid no-candidate review record")
        return {"first_safe_rank": None, "safe_in_top3": False, "labels": []}
    first_safe = next(
        (
            int(row["candidate_rank"])
            for row, label in zip(rows, labels)
            if label in SAFE_LABELS
        ),
        None,
    )
    required = first_safe or len(rows)
    if any(not label for label in labels[:required]):
        raise Stage5B1AValidationError("sequential review is incomplete")
    if first_safe is not None and any(labels[first_safe:]):
        raise Stage5B1AValidationError("review must stop after first SAFE candidate")
    return {
        "first_safe_rank": first_safe,
        "safe_in_top3": first_safe is not None,
        "labels": labels,
    }


def finalize(
    project_root: str | Path,
    output_dir: str | Path,
    *,
    focused_passed: int,
    regression_passed: int | None = None,
    full_passed: int | None = None,
    full_deselected: int | None = None,
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    output_dir = Path(output_dir).resolve()
    history = verify_artist_decomposition_history(project_root)
    config = _json(output_dir / "query_decomposition_config.json")
    query_plan = _json(output_dir / "query_plan_v3.json")
    discovery = _json(output_dir / "targeted_discovery.json")
    review = validate_review(output_dir / "human_review.csv")
    by_purpose = {row["case_purpose"]: row for row in discovery["tracks"]}
    motivating = by_purpose["MOTIVATING_ZERO_RESULT_CASE"]
    regression = by_purpose["PRIMARY_SUCCESS_REGRESSION"]
    history_or_reproduced = (
        motivating["Q0_result_count"] == 0
        or history["motivating_case"]["outcome"]["candidates"] == []
    )
    criteria = {
        "primary_zero_reproduced_or_historically_pinned": history_or_reproduced,
        "fallback_tried_individual_artists_deterministically": (
            motivating["fallback_triggered"]
            and [
                attempt["query_artist"]
                for attempt in motivating["fallback_queries_attempted"]
            ][:2]
            == ["2xxx", "Miso"]
        ),
        "girl_interrupted_miso_recovered_candidates": (
            motivating["outcome"] == FALLBACK_SUCCESS
            and motivating["successful_query"] == "Girl, Interrupted Miso"
            and bool(motivating["candidates"])
        ),
        "human_safe_top3": review["safe_in_top3"],
        "all_the_stars_primary_without_fallback": (
            regression["outcome"] == PRIMARY_SUCCESS
            and regression["fallback_triggered"] is False
            and regression["total_provider_requests"] == 1
        ),
        "native_rank_preserved_without_pooling": all(
            candidate.get("rank") == index
            for index, candidate in enumerate(motivating["candidates"], start=1)
        ),
        "song_agnostic_bounded_contract": (
            config["query_policy"]["song_specific_rules"] is False
            and query_plan["summary"]["maximum_fallback_requests_per_track"] <= 3
        ),
        "selector_and_historical_artifacts_immutable": bool(history),
        "tests_passed": focused_passed > 0
        and (regression_passed or 0) > 0
        and (full_passed or 0) > 0,
    }
    verdict = (
        "ARTIST_DECOMPOSITION_FALLBACK_VALIDATED"
        if all(criteria.values())
        else "ARTIST_DECOMPOSITION_FALLBACK_FAILED"
    )
    metrics = {
        "schema_version": "stage5b4c-decomposition-metrics-v1",
        "experiment_id": EXPERIMENT_ID,
        "verdict": verdict,
        "criteria": criteria,
        "targeted": {
            row["case_purpose"]: {
                "benchmark_id": row["track"]["stable_track_id"],
                "outcome": row["outcome"],
                "Q0": row["Q0"],
                "Q0_result_count": row["Q0_result_count"],
                "fallback_triggered": row["fallback_triggered"],
                "fallback_query_count": len(row["fallback_queries_attempted"]),
                "successful_query_index": row["query_variant_index"],
                "successful_query": row["successful_query"],
                "candidate_video_ids": row["candidate_video_ids"],
                "total_provider_requests": row["total_provider_requests"],
                "elapsed_seconds": row["elapsed_seconds"],
            }
            for row in discovery["tracks"]
        },
        "offline_v3": query_plan["summary"],
        "human_review": review,
        "verification": {
            "focused": focused_passed,
            "stage5b_regressions": regression_passed,
            "full_non_heavy": full_passed,
            "full_deselected": full_deselected,
        },
        "frozen_candidate_contract": (
            QUERY_CONTRACT_ID if verdict == "ARTIST_DECOMPOSITION_FALLBACK_VALIDATED" else None
        ),
        "scope_guards": {
            "candidate_pool_merges": 0,
            "song_specific_rules": 0,
            "title_only_queries": 0,
            "playwright_invocations": 0,
            "data_api_invocations": 0,
            "selector_modified": False,
            "historical_artifacts_overwritten": False,
            "production_activation": False,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
    }
    atomic_json(output_dir / "decomposition_metrics.json", metrics)
    _write_report(output_dir, discovery, metrics)
    manifest = {
        "schema_version": "stage5b4c-artist-decomposition-manifest-v1",
        "experiment_id": EXPERIMENT_ID,
        "verdict": verdict,
        "artifacts": {
            name: _identity(output_dir / name, project_root)
            for name in REQUIRED_ARTIFACTS
        },
        "implementation": {
            name: _identity(project_root / path, project_root)
            for name, path in {
                "orchestrator": "src/audio_similarity/stage5b4c_artist_decomposition.py",
                "experiment": "src/audio_similarity/stage5b4c_artist_decomposition_experiment.py",
                "cli": "src/audio_similarity/cli/stage5b4c_artist_decomposition.py",
                "orchestrator_tests": "tests/test_stage5b4c_artist_decomposition.py",
                "experiment_tests": "tests/test_stage5b4c_artist_decomposition_experiment.py",
            }.items()
        },
        "frozen_inputs": {
            "stage5b4a_artifacts": history["stage5b4a_artifacts"],
            "stage5b4b_manifest": history["stage5b4b_manifest"],
            "official_data_api_manifest": history["official_data_api_manifest"],
            "representative_v3_artifacts": history["representative_v3_artifacts"],
            "stage5b3_selector": history["selector"],
        },
    }
    atomic_json(output_dir / "artifact_manifest.json", manifest)
    return {"verdict": verdict, "metrics": metrics, "manifest": manifest}


def _write_report(
    output_dir: Path,
    discovery: dict[str, Any],
    metrics: dict[str, Any],
) -> None:
    motivating, regression = discovery["tracks"]
    lines = [
        "# Stage 5B.4C — Credited-Artist Query Decomposition",
        "",
        f"**Verdict: `{metrics['verdict']}`.**",
        "",
        "## Frozen architecture",
        "",
        "```text",
        "Q0: sanitized title + first 3 distinct credited artists",
        "    candidates -> stop; use native Top-3",
        "    zero       -> title + artist 1",
        "                  title + artist 2",
        "                  title + artist 3",
        "                  sequential; stop at first non-empty Top-3",
        "    error      -> provider error; do not decompose",
        "```",
        "",
        "## Targeted evidence",
        "",
        f"- Motivating Q0: `{motivating['Q0']}` -> **{motivating['Q0_result_count']}** candidates.",
    ]
    for attempt in motivating["fallback_queries_attempted"]:
        lines.append(
            f"- Q{attempt['query_variant_index']}: `{attempt['query']}` -> "
            f"**{attempt['result_count']}** candidates in {attempt['elapsed_seconds']:.3f}s."
        )
    lines.extend(
        [
            f"- Successful candidate IDs: `{motivating['candidate_video_ids']}`.",
            f"- First human SAFE rank: **{metrics['human_review']['first_safe_rank']}**.",
            f"- Regression Q0: `{regression['Q0']}` -> **{regression['Q0_result_count']}** candidates.",
            f"- Regression fallback count: **{len(regression['fallback_queries_attempted'])}**.",
            "",
            "| Rank | Video ID | Title | Channel | Duration | Views |",
            "|---:|---|---|---|---:|---:|",
        ]
    )
    for candidate in motivating["candidates"]:
        lines.append(
            f"| {candidate['rank']} | `{candidate['youtube_video_id']}` | "
            f"{candidate.get('title') or ''} | {candidate.get('channel') or ''} | "
            f"{candidate.get('duration_seconds')} | {candidate.get('view_count')} |"
        )
    lines.extend(
        [
            "",
            "## Offline Representative V3 analysis",
            "",
            *[
                f"- {name.replace('_', ' ')}: **{value}**"
                for name, value in metrics["offline_v3"].items()
            ],
            "",
            "No V3 YouTube searches were executed for this analysis; only the frozen metadata was transformed into potential query plans.",
            "",
            "## Decision",
            "",
            (
                f"Freeze `{QUERY_CONTRACT_ID}` as the candidate discovery contract for the next fresh representative benchmark. "
                "Do not reinterpret V3 and do not production-activate from this targeted repair."
                if metrics["verdict"] == "ARTIST_DECOMPOSITION_FALLBACK_VALIDATED"
                else "Do not freeze or activate the decomposition fallback from this result."
            ),
            "",
            "## Scope",
            "",
            "- Candidate-pool merges, title-only variants, song-specific rules: **0**.",
            "- Playwright and Data API invocations: **0**.",
            "- Audio/video downloads: **0**.",
            "- Historical artifacts overwritten: **0**.",
            "- Production activation: **false**.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "uv run pytest -q tests/test_stage5b4c_artist_decomposition.py tests/test_stage5b4c_artist_decomposition_experiment.py",
            "```",
            "",
        ]
    )
    (output_dir / "decomposition_report.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
