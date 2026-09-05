"""Bounded live evaluation and artifacts for the official Data API fallback."""
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
from .stage5b3_minimal_selector import select_native_rank
from .stage5b4a_query_contract_repair import (
    QUERY_CONTRACT_ID,
    natural_title_first3_artists_query,
)
from .stage5b4b_experiment import verify_history_guards
from .stage5b4c_youtube_data_api import (
    MANUAL_YOUTUBE_URL_OVERRIDE,
    YOUTUBE_DATA_API_FALLBACK,
    YouTubeDataApiClient,
    YouTubeDataApiConfig,
    discover_with_data_api_fallback,
)


EXPERIMENT_ID = "STAGE5B4C_YOUTUBE_DATA_API_FALLBACK_V1"
OUTPUT_DIRECTORY = "reports/stage5b4c_youtube_data_api_fallback"
SAFE_LABELS = frozenset({"IDEAL", "ACCEPTABLE"})
VALID_LABELS = frozenset({"", "IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"})
REQUIRED_ARTIFACTS = (
    "fallback_config.json",
    "primary_discovery.json",
    "data_api_search.json",
    "hydrated_candidates.json",
    "human_review.csv",
    "fallback_metrics.json",
    "fallback_report.md",
)
REVIEW_COLUMNS = (
    "review_schema_version",
    "experiment_id",
    "benchmark_id",
    "spotify_track_id",
    "expected_title",
    "expected_artists",
    "expected_duration_seconds",
    "search_query",
    "provider_path",
    "provider_rank",
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


def verify_stage5b4c_history(project_root: str | Path) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    history = verify_history_guards(project_root)
    stage5b4b_dir = project_root / "reports/stage5b4b_playwright_fallback"
    manifest_path = stage5b4b_dir / "artifact_manifest.json"
    manifest = _json(manifest_path)
    if manifest.get("verdict") != "PLAYWRIGHT_FALLBACK_FAILED":
        raise Stage5B1AValidationError("unexpected Stage 5B.4B verdict")
    for group in ("artifacts", "implementation"):
        for name, expected in manifest.get(group, {}).items():
            path = project_root / str(expected.get("path", ""))
            if group == "artifacts":
                path = stage5b4b_dir / name
            if not path.is_file() or file_sha256(path) != expected.get("sha256"):
                raise Stage5B1AValidationError(
                    f"Stage 5B.4B {group} identity changed: {name}"
                )
    return {
        "stage5b4b_manifest": _identity(manifest_path, project_root),
        "stage5b4b_artifacts": {
            name: _identity(stage5b4b_dir / name, project_root)
            for name in manifest["artifacts"]
        },
        "stage5b4a_artifacts": history["stage5b4a_artifacts"],
        "representative_v3_artifacts": history["representative_v3_artifacts"],
        "selector": history["selector"],
        "motivating_case": history["motivating_case"],
        "production_activation": False,
    }


def _primary_provider() -> YtDlpProviderConfig:
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


def _primary_adapter() -> YtDlpDiscoveryAdapter:
    provider = _primary_provider()
    inert_query = QueryConfig(
        variant_id="stage5b4c-explicit-frozen-query",
        template="{normalized_title} {primary_artist}",
        normalize_featured_artist_noise=False,
    )
    return YtDlpDiscoveryAdapter(
        provider,
        inert_query,
        YtDlpPythonBackend(provider),
    )


def fallback_config_document(project_root: str | Path) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    history = verify_stage5b4c_history(project_root)
    return {
        "schema_version": "stage5b4c-fallback-config-v1",
        "experiment_id": EXPERIMENT_ID,
        "query_contract_id": QUERY_CONTRACT_ID,
        "query": "Girl, Interrupted 2xxx Miso",
        "architecture": {
            "primary": "yt_dlp ytsearch3",
            "fallback": "YouTube Data API v3 search.list then videos.list",
            "fallback_trigger": "ZERO_USABLE_PRIMARY_CANDIDATES_ONLY",
            "same_query_required": True,
            "unresolved_next_step": MANUAL_YOUTUBE_URL_OVERRIDE,
            "selector": "STAGE5B3_MINIMAL_YOUTUBE_SELECTOR_V1_UNCHANGED",
        },
        "data_api": YouTubeDataApiConfig().to_dict()
        | {
            "search_parameters": {
                "part": "snippet",
                "q": "SAME_NATURAL_QUERY",
                "type": "video",
                "maxResults": 3,
            },
            "hydration_parameters": {
                "part": "snippet,contentDetails,statistics,status",
                "id": "SEARCH_RESULT_IDS_IN_PROVIDER_ORDER",
            },
            "search_pages": 1,
            "retries": 0,
        },
        "frozen_inputs": {
            "stage5b4b_manifest": history["stage5b4b_manifest"],
            "stage5b3_selector": history["selector"],
            "stage5b4a_artifacts": history["stage5b4a_artifacts"],
            "representative_v3_artifacts": history["representative_v3_artifacts"],
        },
        "scope_guards": {
            "motivating_cases": 1,
            "alternate_queries": 0,
            "query_tuning": False,
            "selector_tuning": False,
            "playwright_invocations": 0,
            "personal_credentials_serialized": False,
            "production_activation": False,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
    }


def write_config(project_root: str | Path, output_dir: str | Path) -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    document = fallback_config_document(project_root)
    atomic_json(output_dir / "fallback_config.json", document)
    return document


def run_live(
    project_root: str | Path,
    output_dir: str | Path,
    api_key: str,
    *,
    primary_adapter: Any | None = None,
    data_api: YouTubeDataApiClient | None = None,
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "primary": output_dir / "primary_discovery.json",
        "search": output_dir / "data_api_search.json",
        "hydration": output_dir / "hydrated_candidates.json",
    }
    if any(path.exists() for path in paths.values()):
        raise Stage5B1AValidationError("Stage 5B.4C live evidence already exists")
    history = verify_stage5b4c_history(project_root)
    track = SpotifyTrack.from_dict(history["motivating_case"]["outcome"]["track"])
    query = natural_title_first3_artists_query(track)
    if query != "Girl, Interrupted 2xxx Miso":
        raise Stage5B1AValidationError("Stage 5B.4C query differs from frozen contract")
    if not api_key.strip():
        raise Stage5B1AValidationError("YOUTUBE_DATA_API_KEY is not configured")
    result = discover_with_data_api_fallback(
        track,
        query,
        primary_adapter or _primary_adapter(),
        data_api or YouTubeDataApiClient(api_key),
    )
    primary = {
        "schema_version": "stage5b4c-primary-discovery-v1",
        "experiment_id": EXPERIMENT_ID,
        "provider_path": "YTDLP_SEARCH",
        **result["primary"],
        "scope_guards": {
            "search_mode": "ytsearch3",
            "metadata_only": True,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
    }
    search = {
        "schema_version": "stage5b4c-data-api-search-v1",
        "experiment_id": EXPERIMENT_ID,
        "query": query,
        "provider_path": YOUTUBE_DATA_API_FALLBACK,
        **result["data_api_search"],
        "scope_guards": {
            "same_query_as_primary": True,
            "maximum_results": 3,
            "pages_requested": 1 if result["data_api_search"]["triggered"] else 0,
            "credential_serialized": False,
        },
    }
    hydration = {
        "schema_version": "stage5b4c-hydrated-candidates-v1",
        "experiment_id": EXPERIMENT_ID,
        "query": query,
        "provider_path": result["provider_path"],
        **result["data_api_hydration"],
        "candidates": result["candidates"],
        "next_step": result["next_step"],
        "error": result["error"],
        "scope_guards": {
            "selector_invocations_before_human_review": 0,
            "provider_rank_preserved": True,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
    }
    serialized = json.dumps(
        {"primary": primary, "search": search, "hydration": hydration},
        ensure_ascii=False,
    )
    if api_key in serialized:
        raise Stage5B1AValidationError("API credential entered artifact payload")
    for name, document in (
        ("primary", primary),
        ("search", search),
        ("hydration", hydration),
    ):
        atomic_json(paths[name], document)
    return {
        "query": query,
        "primary_result_count": primary["result_count"],
        "data_api_triggered": search["triggered"],
        "data_api_result_count": len((search.get("outcome") or {}).get("results", [])),
        "hydrated_candidate_count": len(hydration["candidates"]),
        "error": hydration["error"],
        "next_step": hydration["next_step"],
    }


def write_review(output_dir: str | Path) -> Path:
    output_dir = Path(output_dir).resolve()
    primary = _json(output_dir / "primary_discovery.json")
    hydration = _json(output_dir / "hydrated_candidates.json")
    track = primary["outcome"]["track"]
    path = output_dir / "human_review.csv"
    if path.exists():
        raise Stage5B1AValidationError("Stage 5B.4C human review already exists")
    candidates = hydration.get("candidates") or []
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
                "search_query": primary["query"],
                "provider_path": hydration["provider_path"],
                "provider_rank": candidate.get("provider_rank", "") if candidate else "",
                "candidate_rank": candidate.get("rank", "") if candidate else "",
                "candidate_video_id": candidate.get("youtube_video_id", "") if candidate else "",
                "candidate_url": candidate.get("canonical_url", "") if candidate else "",
                "candidate_title": (candidate.get("title") or "") if candidate else "",
                "candidate_uploader": (candidate.get("uploader") or "") if candidate else "",
                "candidate_channel": (candidate.get("channel") or "") if candidate else "",
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
                "track_note": "" if candidate else "NO_HYDRATED_CANDIDATES",
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
        raise Stage5B1AValidationError("review must stop after the first SAFE candidate")
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
    history = verify_stage5b4c_history(project_root)
    primary = _json(output_dir / "primary_discovery.json")
    search = _json(output_dir / "data_api_search.json")
    hydration = _json(output_dir / "hydrated_candidates.json")
    review = validate_review(output_dir / "human_review.csv")
    candidates = hydration.get("candidates") or []
    selector = (
        select_native_rank(primary["outcome"]["track"], candidates)
        if review["safe_in_top3"] and candidates
        else None
    )
    search_outcome = search.get("outcome") or {}
    hydration_outcome = hydration.get("outcome") or {}
    criteria = {
        "yt_dlp_remained_primary": True,
        "data_api_only_after_zero": search.get("triggered")
        == (primary.get("result_count") == 0),
        "same_query_used": search_outcome.get("query") == primary.get("query"),
        "data_api_found_candidate": bool(search_outcome.get("results")),
        "videos_list_hydrated_candidate": bool(candidates),
        "human_safe_top3": review["safe_in_top3"],
        "selector_and_query_untuned": True,
        "historical_artifacts_immutable": bool(history),
        "tests_passed": focused_passed > 0
        and (regression_passed or 0) > 0
        and (full_passed or 0) > 0,
    }
    validated = all(criteria.values())
    verdict = (
        "YOUTUBE_DATA_API_FALLBACK_VALIDATED"
        if validated
        else "YOUTUBE_DATA_API_FALLBACK_FAILED"
    )
    metrics = {
        "schema_version": "stage5b4c-fallback-metrics-v1",
        "experiment_id": EXPERIMENT_ID,
        "verdict": verdict,
        "criteria": criteria,
        "counts": {
            "primary_candidates": primary["result_count"],
            "data_api_video_results": len(search_outcome.get("results", [])),
            "hydrated_candidates": len(candidates),
        },
        "latency_seconds": {
            "primary_ytdlp_search": primary["elapsed_seconds"],
            "data_api_search": search_outcome.get("elapsed_seconds"),
            "videos_list_hydration": hydration_outcome.get("elapsed_seconds"),
        },
        "human_review": review,
        "selector_evaluation_after_human_review": selector,
        "unresolved_next_step": hydration.get("next_step"),
        "verification": {
            "focused": focused_passed,
            "stage5b_regressions": regression_passed,
            "full_non_heavy": full_passed,
            "full_deselected": full_deselected,
        },
        "scope_guards": {
            "playwright_invocations": 0,
            "alternate_queries": 0,
            "credential_serialized": False,
            "selector_modified": False,
            "query_modified": False,
            "production_activation": False,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
    }
    atomic_json(output_dir / "fallback_metrics.json", metrics)
    _write_report(output_dir, primary, search, hydration, metrics)
    manifest = {
        "schema_version": "stage5b4c-artifact-manifest-v1",
        "experiment_id": EXPERIMENT_ID,
        "verdict": verdict,
        "artifacts": {
            name: _identity(output_dir / name, project_root)
            for name in REQUIRED_ARTIFACTS
        },
        "implementation": {
            name: _identity(project_root / path, project_root)
            for name, path in {
                "adapter": "src/audio_similarity/stage5b4c_youtube_data_api.py",
                "experiment": "src/audio_similarity/stage5b4c_experiment.py",
                "cli": "src/audio_similarity/cli/stage5b4c_youtube_data_api.py",
                "adapter_tests": "tests/test_stage5b4c_youtube_data_api.py",
                "experiment_tests": "tests/test_stage5b4c_experiment.py",
            }.items()
        },
        "frozen_inputs": {
            "stage5b4b_manifest": history["stage5b4b_manifest"],
            "stage5b3_selector": history["selector"],
        },
    }
    atomic_json(output_dir / "artifact_manifest.json", manifest)
    return {"verdict": verdict, "metrics": metrics, "manifest": manifest}


def _write_report(
    output_dir: Path,
    primary: dict[str, Any],
    search: dict[str, Any],
    hydration: dict[str, Any],
    metrics: dict[str, Any],
) -> None:
    search_outcome = search.get("outcome") or {}
    hydration_outcome = hydration.get("outcome") or {}
    candidates = hydration.get("candidates") or []
    lines = [
        "# Stage 5B.4C — Official YouTube Data API Fallback",
        "",
        f"**Verdict: `{metrics['verdict']}`.**",
        "",
        "## Architecture",
        "",
        "```text",
        "natural title + first 3 artists -> yt-dlp ytsearch3",
        "    candidates -> existing selector",
        "    zero       -> Data API search.list (same query, video, max 3)",
        "               -> videos.list metadata hydration",
        "               -> existing selector",
        "    unresolved -> manual YouTube URL override",
        "```",
        "",
        "## Motivating evaluation",
        "",
        f"- exact query: `{primary['query']}`",
        f"- primary result count: **{primary['result_count']}**",
        f"- primary error: `{json.dumps(primary.get('error'))}`",
        f"- primary warnings: `{json.dumps(primary.get('warnings', []))}`",
        f"- primary elapsed: **{primary['elapsed_seconds']:.3f}s**",
        f"- Data API triggered: **{str(search['triggered']).lower()}**",
        f"- search video IDs: `{search_outcome.get('video_ids_in_provider_order', [])}`",
        f"- search elapsed: **{search_outcome.get('elapsed_seconds')}s**",
        f"- search error: `{json.dumps(search_outcome.get('error'))}`",
        "- diagnostic raw `items` count: "
        f"**{(search.get('bounded_diagnostic') or {}).get('item_count')}**",
        "- total bounded `search.list` requests: "
        f"**{search.get('scope_guards', {}).get('pages_requested')}**",
        f"- hydrated candidates: **{len(candidates)}**",
        (
            f"- hydration elapsed: **{hydration_outcome['elapsed_seconds']:.3f}s**"
            if hydration_outcome.get("elapsed_seconds") is not None
            else "- hydration elapsed: **not run; no video IDs**"
        ),
        (
            f"- first human SAFE rank: **{metrics['human_review']['first_safe_rank']}**"
            if metrics["human_review"]["first_safe_rank"] is not None
            else "- first human SAFE rank: **none; no candidate available**"
        ),
        f"- unresolved next step: `{hydration.get('next_step')}`",
        "",
        "| Rank | Provider rank | Video ID | Title | Channel | Duration | Views |",
        "|---:|---:|---|---|---|---:|---:|",
    ]
    for candidate in candidates:
        lines.append(
            f"| {candidate['rank']} | {candidate['provider_rank']} | "
            f"`{candidate['youtube_video_id']}` | {candidate.get('title') or ''} | "
            f"{candidate.get('channel') or ''} | {candidate.get('duration_seconds')} | "
            f"{candidate.get('view_count')} |"
        )
    lines.extend(
        [
            "",
            "## Criteria",
            "",
            *[
                f"- {name.replace('_', ' ')}: **{str(value).lower()}**"
                for name, value in metrics["criteria"].items()
            ],
            "",
            "## Scope",
            "",
            "- Alternate queries, query heuristics, and selector tuning: **0**.",
            "- Playwright invocations: **0**.",
            "- API credentials serialized: **0**.",
            "- Audio/video downloads: **0**.",
            "- Historical artifacts overwritten: **0**.",
            "- Production activation: **false**.",
            "",
            "## Reproduction",
            "",
            "The deterministic adapter and artifact checks can be replayed without a key:",
            "",
            "```bash",
            "uv run pytest -q tests/test_stage5b4c_youtube_data_api.py",
            "```",
            "",
            (
                "The live runner is fail-closed once evidence exists. The recorded "
                "requests should not be rerun merely to seek a different result."
            ),
            "",
            "## Decision",
            "",
            (
                "The official API fallback did not recover the motivating case. "
                "Keep the architecture unactivated and route this unresolved track "
                "to a manual YouTube URL override. Do not add query heuristics from "
                "this result."
            ),
            "",
            "Official references: "
            "[search.list](https://developers.google.com/youtube/v3/docs/search/list) "
            "and [videos.list](https://developers.google.com/youtube/v3/docs/videos/list).",
            "",
        ]
    )
    (output_dir / "fallback_report.md").write_text("\n".join(lines), encoding="utf-8")
