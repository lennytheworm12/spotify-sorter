"""Artifacts and bounded live evaluation for the Stage 5B.4B fallback."""
from __future__ import annotations

import csv
import importlib.metadata
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
from .stage5b4b_browser import BrowserSearchConfig, PlaywrightYouTubeSearchAdapter
from .stage5b4b_playwright_fallback import (
    PLAYWRIGHT_FALLBACK,
    YtDlpExactUrlHydrator,
    discover_with_zero_result_fallback,
)


EXPERIMENT_ID = "STAGE5B4B_PLAYWRIGHT_FALLBACK_V1"
OUTPUT_DIRECTORY = "reports/stage5b4b_playwright_fallback"
SAFE_LABELS = frozenset({"IDEAL", "ACCEPTABLE"})
REVIEW_LABELS = frozenset({"", "IDEAL", "ACCEPTABLE", "WRONG", "UNCERTAIN"})
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
    "browser_rank",
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
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage5B1AValidationError(f"expected JSON object: {path}")
    return value


def _identity(path: Path, project_root: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(project_root)),
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _stage5b4a_paths(project_root: Path) -> dict[str, Path]:
    directory = project_root / "reports/stage5b4a_query_contract_repair"
    return {
        name: directory / name
        for name in (
            "repaired_query_contract.json",
            "v3_query_replay.json",
            "repaired_discovery.json",
            "human_review.csv",
            "query_contract_report.md",
            "artifact_manifest.json",
        )
    }


def verify_history_guards(project_root: str | Path) -> dict[str, Any]:
    """Fail closed unless the committed 5B.4A motivating evidence is intact."""

    project_root = Path(project_root).resolve()
    paths = _stage5b4a_paths(project_root)
    if not all(path.is_file() for path in paths.values()):
        raise Stage5B1AValidationError("Stage 5B.4A artifacts are incomplete")
    stage5b4a_manifest = _json(paths["artifact_manifest.json"])
    for name, expected in stage5b4a_manifest.get("artifacts", {}).items():
        path = paths.get(name)
        if path is None or file_sha256(path) != expected.get("sha256"):
            raise Stage5B1AValidationError(f"Stage 5B.4A artifact changed: {name}")
    for name, expected in stage5b4a_manifest.get("frozen_v3_inputs", {}).items():
        path = project_root / str(expected.get("path"))
        if not path.is_file() or file_sha256(path) != expected.get("sha256"):
            raise Stage5B1AValidationError(f"Representative V3 artifact changed: {name}")
    implementation = stage5b4a_manifest.get("implementation", {})
    implementation_path = project_root / str(implementation.get("path"))
    if (
        not implementation_path.is_file()
        or file_sha256(implementation_path) != implementation.get("sha256")
    ):
        raise Stage5B1AValidationError("Stage 5B.4A query implementation changed")
    contract = _json(paths["repaired_query_contract.json"])
    if contract.get("query_contract_id") != QUERY_CONTRACT_ID:
        raise Stage5B1AValidationError("Stage 5B.4A query contract identity changed")
    discovery = _json(paths["repaired_discovery.json"])
    motivating = [
        row
        for row in discovery.get("tracks", [])
        if row.get("outcome", {}).get("track", {}).get("title") == "Girl, Interrupted"
    ]
    if len(motivating) != 1:
        raise Stage5B1AValidationError("Stage 5B.4A motivating case is not unique")
    case = motivating[0]
    outcome = case.get("outcome", {})
    if (
        case.get("exact_generated_query") != "Girl, Interrupted 2xxx Miso"
        or outcome.get("query") != case.get("exact_generated_query")
        or outcome.get("candidates") != []
        or outcome.get("error") is not None
        or outcome.get("warnings") != []
        or outcome.get("request", {}).get("search_expression")
        != "ytsearch3:Girl, Interrupted 2xxx Miso"
    ):
        raise Stage5B1AValidationError("Stage 5B.4A zero-result evidence changed")
    v3_config_path = project_root / "reports/stage5b4_representative_v3/benchmark_config.json"
    v3_config = _json(v3_config_path)
    selector = v3_config.get("selector", {})
    selector_source = project_root / str(selector.get("implementation", {}).get("path"))
    if (
        not selector_source.is_file()
        or file_sha256(selector_source)
        != selector.get("implementation", {}).get("sha256")
        or selector.get("production_activated") is not False
        or v3_config.get("scope_guards", {}).get("production_activation") is not False
    ):
        raise Stage5B1AValidationError("Stage 5B.3 selector or production guard changed")
    return {
        "stage5b4a_artifacts": {
            name: _identity(path, project_root) for name, path in paths.items()
        },
        "representative_v3_artifacts": stage5b4a_manifest["frozen_v3_inputs"],
        "selector": _identity(selector_source, project_root),
        "production_activation": False,
        "motivating_case": case,
    }


def _track(value: dict[str, Any]) -> SpotifyTrack:
    return SpotifyTrack.from_dict(value)


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
        variant_id="stage5b4b-explicit-frozen-query",
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
    history = verify_history_guards(project_root)
    browser = BrowserSearchConfig()
    return {
        "schema_version": "stage5b4b-fallback-config-v1",
        "experiment_id": EXPERIMENT_ID,
        "query_contract_id": QUERY_CONTRACT_ID,
        "query": "Girl, Interrupted 2xxx Miso",
        "architecture": {
            "primary": "yt_dlp ytsearch3",
            "fallback": "Playwright browser search then yt-dlp exact-URL hydration",
            "fallback_trigger": "ZERO_USABLE_PRIMARY_CANDIDATES_ONLY",
            "same_query_required": True,
            "selector": "STAGE5B3_MINIMAL_YOUTUBE_SELECTOR_V1_UNCHANGED",
        },
        "browser": browser.to_dict()
        | {
            "persistent_profile": False,
            "personal_cookies": False,
            "scroll_count": 0,
            "captcha_solving": False,
            "stealth_plugins": False,
        },
        "hydration": {
            "provider": "yt_dlp",
            "mode": "exact_watch_url",
            "search_queries": 0,
            "metadata_only": True,
            "sequential": True,
            "maximum_urls": 3,
        },
        "playwright_version": importlib.metadata.version("playwright"),
        "frozen_inputs": {
            "stage5b4a_artifact_manifest": _identity(
                _stage5b4a_paths(project_root)["artifact_manifest.json"], project_root
            ),
            "stage5b4a_query_contract": _identity(
                _stage5b4a_paths(project_root)["repaired_query_contract.json"],
                project_root,
            ),
            "stage5b4a_discovery": _identity(
                _stage5b4a_paths(project_root)["repaired_discovery.json"],
                project_root,
            ),
            "stage5b3_selector": history["selector"],
            "representative_v3_artifacts": history["representative_v3_artifacts"],
        },
        "scope_guards": {
            "motivating_cases": 1,
            "alternate_queries": 0,
            "query_tuning": False,
            "selector_tuning": False,
            "production_activation": False,
            "proof_heavy_resolver_invocations": 0,
            "sol_runs": 0,
            "clap_calls": 0,
            "muq_calls": 0,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
    }


def write_fallback_config(project_root: str | Path, output_dir: str | Path) -> dict[str, Any]:
    document = fallback_config_document(project_root)
    atomic_json(Path(output_dir).resolve() / "fallback_config.json", document)
    return document


def run_live_evaluation(
    project_root: str | Path,
    output_dir: str | Path,
    *,
    primary_adapter: Any | None = None,
    browser_adapter: Any | None = None,
    hydrator: Any | None = None,
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    output_dir = Path(output_dir).resolve()
    output_paths = {
        "primary": output_dir / "primary_discovery.json",
        "browser": output_dir / "playwright_discovery.json",
        "hydration": output_dir / "hydrated_candidates.json",
    }
    if any(path.exists() for path in output_paths.values()):
        raise Stage5B1AValidationError("Stage 5B.4B live evidence is already recorded")
    history = verify_history_guards(project_root)
    historical = history["motivating_case"]
    track = _track(historical["outcome"]["track"])
    query = natural_title_first3_artists_query(track)
    if query != historical["exact_generated_query"]:
        raise Stage5B1AValidationError("fallback query differs from Stage 5B.4A")
    primary_adapter = primary_adapter or _primary_adapter()
    browser_adapter = browser_adapter or PlaywrightYouTubeSearchAdapter()
    hydrator = hydrator or YtDlpExactUrlHydrator()
    result = discover_with_zero_result_fallback(
        track,
        query,
        primary_adapter,
        browser_adapter,
        hydrator,
    )
    primary_document = {
        "schema_version": "stage5b4b-primary-discovery-v1",
        "experiment_id": EXPERIMENT_ID,
        "provider_path": "YTDLP_SEARCH",
        "query": query,
        **result["primary"],
        "scope_guards": {
            "search_mode": "ytsearch3",
            "metadata_only": True,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
    }
    browser_document = {
        "schema_version": "stage5b4b-playwright-discovery-v1",
        "experiment_id": EXPERIMENT_ID,
        "query": query,
        **result["browser"],
        "scope_guards": {
            "same_query_as_primary": True,
            "maximum_results": 3,
            "scroll_count": 0,
            "personal_profile_loaded": False,
            "personal_cookies_loaded": False,
        },
    }
    hydration_document = {
        "schema_version": "stage5b4b-hydrated-candidates-v1",
        "experiment_id": EXPERIMENT_ID,
        "query": query,
        "provider_path": result["provider_path"],
        "trigger_reason": result["trigger_reason"],
        "triggered": result["hydration"]["triggered"],
        "outcome": result["hydration"]["outcome"],
        "candidates": result["candidates"],
        "error": result["error"],
        "scope_guards": {
            "selector_invocations_before_human_review": 0,
            "candidate_reranking": False,
            "provider_source_used_as_quality_evidence": False,
            "audio_downloads": 0,
            "video_downloads": 0,
        },
    }
    for name, document in (
        ("primary", primary_document),
        ("browser", browser_document),
        ("hydration", hydration_document),
    ):
        atomic_json(output_paths[name], document)
    return {
        "provider_path": result["provider_path"],
        "primary_result_count": primary_document["result_count"],
        "playwright_triggered": browser_document["triggered"],
        "browser_result_count": len(
            (browser_document.get("outcome") or {}).get("results", [])
        ),
        "hydrated_candidate_count": len(hydration_document["candidates"]),
        "error": hydration_document["error"],
    }


def run_bounded_browser_diagnostic(
    output_dir: str | Path,
    *,
    browser_adapter: Any | None = None,
    hydrator: Any | None = None,
) -> dict[str, Any]:
    """Run one post-fix browser-only check while preserving the initial outcome."""

    output_dir = Path(output_dir).resolve()
    primary = _json(output_dir / "primary_discovery.json")
    browser_path = output_dir / "playwright_discovery.json"
    hydration_path = output_dir / "hydrated_candidates.json"
    browser = _json(browser_path)
    hydration = _json(hydration_path)
    if browser.get("bounded_diagnostics"):
        raise Stage5B1AValidationError("bounded browser diagnostic is already recorded")
    if (
        primary.get("result_count") != 0
        or browser.get("triggered") is not True
        or browser.get("outcome", {}).get("error", {}).get("category")
        != "PLAYWRIGHT_NAVIGATION_TIMEOUT"
    ):
        raise Stage5B1AValidationError("post-fix diagnostic requires the initial timeout state")
    query = primary["query"]
    track = _track(primary["outcome"]["track"])
    browser_adapter = browser_adapter or PlaywrightYouTubeSearchAdapter()
    hydrator = hydrator or YtDlpExactUrlHydrator()
    initial_outcome = browser["outcome"]
    final_outcome = browser_adapter.search(query, limit=3)
    if final_outcome.query != query:
        raise Stage5B1AValidationError("browser diagnostic changed the frozen query")
    browser["outcome"] = final_outcome.to_dict()
    browser["bounded_diagnostics"] = [
        {
            "kind": "INITIAL_INTEGRATED_ATTEMPT",
            "outcome": initial_outcome,
        },
        {
            "kind": "MINIMAL_DOM_INSPECTION",
            "query_unchanged": True,
            "navigation_succeeded": True,
            "page_title": "Girl, Interrupted 2xxx Miso - YouTube",
            "observed_page_state": "AGE_CONFIRMATION_SIGN_IN_WALL",
            "valid_watch_link_count": 0,
            "scroll_count": 0,
            "personal_profile_loaded": False,
            "personal_cookies_loaded": False,
        },
        {
            "kind": "POST_FIX_CLASSIFICATION_RUN",
            "outcome": final_outcome.to_dict(),
        },
    ]
    browser["live_browser_navigation_count"] = 3
    if final_outcome.error is None and final_outcome.results:
        hydrated = hydrator.hydrate(track, query, final_outcome.results)
        hydration["triggered"] = True
        hydration["outcome"] = hydrated.to_dict()
        hydration["candidates"] = [dict(candidate) for candidate in hydrated.candidates]
        hydration["error"] = None if hydrated.candidates else {
            "category": "EXACT_URL_HYDRATION_FAILED",
            "message": "all browser-discovered exact URLs failed metadata hydration",
            "retryable": False,
        }
    else:
        hydration["triggered"] = False
        hydration["outcome"] = None
        hydration["candidates"] = []
        hydration["error"] = final_outcome.error
    atomic_json(browser_path, browser)
    atomic_json(hydration_path, hydration)
    return {
        "query": query,
        "error": final_outcome.error,
        "browser_result_count": len(final_outcome.results),
        "hydrated_candidate_count": len(hydration["candidates"]),
        "live_browser_navigation_count": 3,
    }


def write_human_review(output_dir: str | Path) -> Path:
    output_dir = Path(output_dir).resolve()
    primary = _json(output_dir / "primary_discovery.json")
    hydration = _json(output_dir / "hydrated_candidates.json")
    track = primary["outcome"]["track"]
    review_path = output_dir / "human_review.csv"
    existing: dict[str, dict[str, str]] = {}
    if review_path.exists():
        with review_path.open(encoding="utf-8", newline="") as handle:
            existing = {
                row["candidate_video_id"]: row for row in csv.DictReader(handle)
            }
    candidates = hydration.get("candidates", [])
    rows = []
    for candidate in candidates or [None]:
        video_id = candidate["youtube_video_id"] if candidate else ""
        old = existing.get(video_id, {})
        rows.append(
            {
                "review_schema_version": "stage5b4b-human-review-v1",
                "experiment_id": EXPERIMENT_ID,
                "benchmark_id": track["stable_track_id"],
                "spotify_track_id": track.get("spotify_track_id") or "",
                "expected_title": track["title"],
                "expected_artists": " | ".join(track["artists"]),
                "expected_duration_seconds": track["duration_ms"] / 1000,
                "search_query": primary["query"],
                "provider_path": hydration["provider_path"],
                "browser_rank": candidate.get("browser_rank", "") if candidate else "",
                "candidate_rank": candidate.get("rank", "") if candidate else "",
                "candidate_video_id": video_id,
                "candidate_url": candidate.get("canonical_url", "") if candidate else "",
                "candidate_title": (candidate.get("title") or "") if candidate else "",
                "candidate_uploader": (
                    candidate.get("uploader") or ""
                ) if candidate else "",
                "candidate_channel": (
                    candidate.get("channel") or ""
                ) if candidate else "",
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
                "candidate_review_label": old.get("candidate_review_label", ""),
                "candidate_note": old.get("candidate_note", ""),
                "track_note": old.get(
                    "track_note",
                    "NO_HYDRATED_CANDIDATES" if not candidate else "",
                ),
            }
        )
    review_path.parent.mkdir(parents=True, exist_ok=True)
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return review_path


def validate_human_review(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise Stage5B1AValidationError("unexpected Stage 5B.4B review columns")
        rows = list(reader)
    if not rows:
        raise Stage5B1AValidationError("Stage 5B.4B review is empty")
    labels = [row["candidate_review_label"].strip().upper() for row in rows]
    if any(label not in REVIEW_LABELS for label in labels):
        raise Stage5B1AValidationError("invalid Stage 5B.4B human label")
    if not rows[0]["candidate_video_id"]:
        if len(rows) != 1 or labels[0]:
            raise Stage5B1AValidationError("invalid no-candidate review record")
        return {
            "first_safe_rank": None,
            "safe_in_top3": False,
            "candidate_unavailable": True,
            "labels": [],
        }
    first_safe = None
    required_rank = 1
    final_labels = []
    for row, label in zip(rows, labels):
        rank = int(row["candidate_rank"])
        if first_safe is not None:
            if label:
                raise Stage5B1AValidationError("labels continue after first SAFE")
            continue
        if rank != required_rank or not label:
            raise Stage5B1AValidationError(f"candidate rank {required_rank} requires a label")
        final_labels.append({"rank": rank, "label": label, "note": row["candidate_note"]})
        if label in SAFE_LABELS:
            first_safe = rank
        else:
            required_rank += 1
    if first_safe is None and required_rank <= len(rows):
        raise Stage5B1AValidationError("sequential Stage 5B.4B review is incomplete")
    return {
        "first_safe_rank": first_safe,
        "safe_in_top3": first_safe is not None,
        "candidate_unavailable": False,
        "labels": final_labels,
    }


def _verification_passed(verification: dict[str, Any]) -> bool:
    return all(
        verification.get(name, {}).get("passed") is True
        for name in ("focused", "stage5b_regressions", "full_non_heavy")
    )


def write_closeout(
    project_root: str | Path,
    output_dir: str | Path,
    verification: dict[str, Any],
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    output_dir = Path(output_dir).resolve()
    verify_history_guards(project_root)
    config = _json(output_dir / "fallback_config.json")
    primary = _json(output_dir / "primary_discovery.json")
    browser = _json(output_dir / "playwright_discovery.json")
    hydration = _json(output_dir / "hydrated_candidates.json")
    review = validate_human_review(output_dir / "human_review.csv")
    browser_outcome = browser.get("outcome") or {}
    hydration_outcome = hydration.get("outcome") or {}
    selector_result = None
    if hydration.get("candidates"):
        selector_result = select_native_rank(
            primary["outcome"]["track"], hydration["candidates"]
        )
    criteria = {
        "yt_dlp_remained_primary": primary["provider_path"] == "YTDLP_SEARCH",
        "playwright_only_after_zero": (
            browser["triggered"] is True and primary["result_count"] == 0
        ),
        "same_query_used": (
            primary["query"] == browser.get("query") == browser_outcome.get("query")
        ),
        "browser_found_candidate": bool(browser_outcome.get("results")),
        "exact_url_hydration_succeeded": bool(hydration.get("candidates")),
        "human_safe_top3": review["safe_in_top3"],
        "selector_and_query_untuned": (
            config["scope_guards"]["selector_tuning"] is False
            and config["scope_guards"]["query_tuning"] is False
        ),
        "historical_artifacts_immutable": True,
        "tests_passed": _verification_passed(verification),
    }
    if all(criteria.values()):
        verdict = "PLAYWRIGHT_FALLBACK_VALIDATED"
    elif any(
        (
            criteria["browser_found_candidate"],
            criteria["exact_url_hydration_succeeded"],
            criteria["human_safe_top3"],
        )
    ):
        verdict = "PLAYWRIGHT_FALLBACK_PARTIALLY_VALIDATED"
    else:
        verdict = "PLAYWRIGHT_FALLBACK_FAILED"
    metrics = {
        "schema_version": "stage5b4b-fallback-metrics-v1",
        "experiment_id": EXPERIMENT_ID,
        "verdict": verdict,
        "criteria": criteria,
        "latency_seconds": {
            "primary_ytdlp_search": primary["elapsed_seconds"],
            "playwright_fallback": browser_outcome.get("elapsed_seconds"),
            "exact_url_hydration": hydration_outcome.get("elapsed_seconds"),
        },
        "counts": {
            "primary_candidates": primary["result_count"],
            "browser_navigations": browser.get("live_browser_navigation_count", 1),
            "browser_video_results": len(browser_outcome.get("results", [])),
            "hydrated_candidates": len(hydration.get("candidates", [])),
            "hydration_failures": hydration_outcome.get("summary", {}).get(
                "hydration_failure_count", 0
            ),
        },
        "human_review": review,
        "selector_evaluation_after_human_review": selector_result,
        "verification": verification,
        "scope_guards": {
            "selector_modified": False,
            "query_modified": False,
            "production_activation": False,
            "audio_downloads": 0,
            "video_downloads": 0,
            "proof_heavy_resolver_invocations": 0,
            "sol_runs": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
    }
    atomic_json(output_dir / "fallback_metrics.json", metrics)
    _write_report(output_dir, primary, browser, hydration, metrics)
    manifest = _write_artifact_manifest(project_root, output_dir, verdict)
    return {"verdict": verdict, "metrics": metrics, "manifest": manifest}


def _write_report(
    output_dir: Path,
    primary: dict[str, Any],
    browser: dict[str, Any],
    hydration: dict[str, Any],
    metrics: dict[str, Any],
) -> None:
    browser_outcome = browser.get("outcome") or {}
    hydration_outcome = hydration.get("outcome") or {}
    lines = [
        "# Stage 5B.4B — Playwright Fallback for Empty YouTube Search Results",
        "",
        f"**Verdict: `{metrics['verdict']}`.**",
        "",
        "## Answer",
        "",
        (
            "A clean, bounded Playwright search recovered ordinary YouTube watch "
            "results for the exact query after primary `ytsearch3` returned zero. "
            "Exact-URL yt-dlp hydration produced a human-SAFE candidate without any "
            "query or selector heuristic."
            if metrics["verdict"] == "PLAYWRIGHT_FALLBACK_VALIDATED"
            else (
                "No. The clean anonymous browser reached YouTube with the exact query, "
                "but YouTube replaced results with an age-confirmation/sign-in wall. "
                "The browser correctly returned `PLAYWRIGHT_CHALLENGE_BLOCKED`; no IDs "
                "were available to hydrate or review."
                if metrics["verdict"] == "PLAYWRIGHT_FALLBACK_FAILED"
                else "The bounded evaluation satisfied only part of the validation "
                "contract, so the architecture remains partially validated."
            )
        ),
        "",
        "## Evaluated architecture",
        "",
        "```text",
        "natural Spotify query -> yt-dlp ytsearch3",
        "    candidates present -> stop; existing Stage 5B.3 selector",
        "    zero candidates    -> clean Playwright YouTube search (same query)",
        "                       -> first 3 unique /watch video IDs",
        "                       -> yt-dlp exact-URL metadata hydration",
        "                       -> existing candidate format and selector",
        "```",
        "",
        (
            "Playwright is not a normal discovery provider and is not triggered by "
            "selector vetoes or `MATCH_UNCERTAIN`."
        ),
        "",
        "## Motivating live evaluation",
        "",
        f"- exact query: `{primary['query']}`",
        f"- primary candidates: **{primary['result_count']}**",
        f"- primary error: `{json.dumps(primary['error'], ensure_ascii=False)}`",
        f"- primary warnings: `{json.dumps(primary['warnings'], ensure_ascii=False)}`",
        f"- primary elapsed: **{primary['elapsed_seconds']:.3f}s**",
        f"- Playwright triggered: **{str(browser['triggered']).lower()}**",
        "- browser navigation succeeded: "
        f"**{str(browser_outcome.get('navigation_succeeded')).lower()}**",
        f"- browser results: **{len(browser_outcome.get('results', []))}**",
        f"- browser IDs: `{browser_outcome.get('video_ids_in_displayed_order', [])}`",
        f"- browser elapsed: **{browser_outcome.get('elapsed_seconds')}s**",
        f"- browser warnings: `{browser_outcome.get('warnings', [])}`",
        f"- browser error: `{json.dumps(browser_outcome.get('error'), ensure_ascii=False)}`",
        f"- bounded browser navigations: **{browser.get('live_browser_navigation_count', 1)}**",
        "- observed blocking state: **anonymous age-confirmation/sign-in wall**",
        f"- exact URLs requested: `{hydration_outcome.get('exact_urls_requested', [])}`",
        f"- hydrated candidates: **{len(hydration.get('candidates', []))}**",
        (
            f"- hydration elapsed: **{hydration_outcome['elapsed_seconds']:.3f}s**"
            if hydration_outcome.get("elapsed_seconds") is not None
            else "- hydration elapsed: **not run**"
        ),
        (
            f"- first human SAFE rank: "
            f"**{metrics['human_review']['first_safe_rank']}**"
            if metrics["human_review"]["first_safe_rank"] is not None
            else "- first human SAFE rank: **none; no candidate available**"
        ),
        "",
        "### Hydrated candidates",
        "",
        "| Rank | Browser rank | Video ID | Title | Channel | Duration | Views |",
        "|---:|---:|---|---|---|---:|---:|",
    ]
    for candidate in hydration.get("candidates", []):
        lines.append(
            f"| {candidate['rank']} | {candidate['browser_rank']} | "
            f"`{candidate['youtube_video_id']}` | {candidate.get('title') or ''} | "
            f"{candidate.get('channel') or ''} | {candidate.get('duration_seconds')} | "
            f"{candidate.get('view_count')} |"
        )
    lines.extend(
        [
            "",
            "## Validation criteria",
            "",
            *[
                f"- {name.replace('_', ' ')}: **{str(passed).lower()}**"
                for name, passed in metrics["criteria"].items()
            ],
            "",
            "## History and scope",
            "",
            "- Stage 5B.4A and Representative V3 artifacts overwritten: **0**.",
            "- Stage 5B.3 selector modifications: **0**.",
            "- Alternate queries, semantic query changes, and forced terms: **0**.",
            "- Personal cookies/profiles, stealth, CAPTCHA solving, and scrolling: **0**.",
            "- Audio/video downloads, proof-heavy resolver, Sol, CLAP, and MuQ: **0**.",
            "- Production activation: **false**.",
            "",
            "## Reproduction",
            "",
            "From `ml/audio_similarity`, synchronize the locked environment and install "
            "the matching Chromium binary before running the bounded commands:",
            "",
            "```bash",
            "uv sync",
            "uv run playwright install chromium",
            "uv run python -m audio_similarity.cli.stage5b4b_playwright_fallback config",
            "uv run python -m audio_similarity.cli.stage5b4b_playwright_fallback live",
            "```",
            "",
            (
                "The recorded live run was intentionally limited to the motivating "
                "query. Do not rerun it merely to seek a different ranking or page state."
            ),
            "",
            "## Decision",
            "",
            (
                "Freeze this architecture for evaluation on fresh representative "
                "traffic: primary `ytsearch3`, with Playwright plus exact-URL hydration "
                "only after zero usable primary candidates. Do not make Playwright the "
                "normal provider."
                if metrics["verdict"] == "PLAYWRIGHT_FALLBACK_VALIDATED"
                else "Do not freeze or production-activate this fallback architecture."
            ),
            "",
        ]
    )
    (output_dir / "fallback_report.md").write_text("\n".join(lines), encoding="utf-8")


def _write_artifact_manifest(
    project_root: Path, output_dir: Path, verdict: str
) -> dict[str, Any]:
    artifact_names = (
        "fallback_config.json",
        "primary_discovery.json",
        "playwright_discovery.json",
        "hydrated_candidates.json",
        "human_review.csv",
        "fallback_metrics.json",
        "fallback_report.md",
    )
    history = verify_history_guards(project_root)
    manifest = {
        "schema_version": "stage5b4b-artifact-manifest-v1",
        "experiment_id": EXPERIMENT_ID,
        "verdict": verdict,
        "artifacts": {
            name: {
                "sha256": file_sha256(output_dir / name),
                "size_bytes": (output_dir / name).stat().st_size,
            }
            for name in artifact_names
        },
        "frozen_inputs": {
            "stage5b4a": history["stage5b4a_artifacts"],
            "representative_v3": history["representative_v3_artifacts"],
            "stage5b3_selector": history["selector"],
        },
        "implementation": {
            name: _identity(project_root / path, project_root)
            for name, path in {
                "browser_adapter": "src/audio_similarity/stage5b4b_browser.py",
                "fallback": "src/audio_similarity/stage5b4b_playwright_fallback.py",
                "experiment": "src/audio_similarity/stage5b4b_experiment.py",
                "cli": "src/audio_similarity/cli/stage5b4b_playwright_fallback.py",
                "tests": "tests/test_stage5b4b_playwright_fallback.py",
                "project": "pyproject.toml",
                "lockfile": "uv.lock",
            }.items()
        },
        "scope_guards": {
            "historical_artifacts_overwritten": False,
            "selector_modified": False,
            "query_modified": False,
            "normal_provider_replaced": False,
            "production_activation": False,
            "motivating_cases": 1,
            "audio_downloads": 0,
            "video_downloads": 0,
            "proof_heavy_resolver_invocations": 0,
            "sol_runs": 0,
            "clap_calls": 0,
            "muq_calls": 0,
        },
    }
    atomic_json(output_dir / "artifact_manifest.json", manifest)
    return manifest
