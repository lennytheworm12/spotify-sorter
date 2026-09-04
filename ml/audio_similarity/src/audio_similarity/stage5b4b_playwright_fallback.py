"""Zero-only Playwright fallback plus exact-URL yt-dlp metadata hydration."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .stage5b1a2_config import YtDlpProviderConfig
from .stage5b1a2_ytdlp import (
    YtDlpBackend,
    YtDlpPythonBackend,
    YtDlpSearchError,
    normalize_ytdlp_entries,
)
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError
from .stage5b4b_browser import (
    BrowserSearchAdapter,
    BrowserSearchOutcome,
    BrowserVideoResult,
)


YTDLP_SEARCH = "YTDLP_SEARCH"
PLAYWRIGHT_FALLBACK = "PLAYWRIGHT_FALLBACK"
PRIMARY_ZERO_RESULTS = "PRIMARY_ZERO_RESULTS"
EXACT_URL_HYDRATION_FAILED = "EXACT_URL_HYDRATION_FAILED"


class PrimaryDiscoveryAdapter(Protocol):
    def discover_query(
        self, track: SpotifyTrack, query: str, *, limit: int
    ) -> Any: ...


class BrowserResultHydrator(Protocol):
    def hydrate(
        self,
        track: SpotifyTrack,
        query: str,
        results: tuple[BrowserVideoResult, ...],
    ) -> "ExactUrlHydrationOutcome": ...


@dataclass(frozen=True)
class ExactUrlHydrationOutcome:
    query: str
    requested_urls: tuple[str, ...]
    results: tuple[dict[str, Any], ...]
    candidates: tuple[dict[str, Any], ...]
    elapsed_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "exact_urls_requested": list(self.requested_urls),
            "results": [dict(result) for result in self.results],
            "candidates": [dict(candidate) for candidate in self.candidates],
            "candidate_video_ids": [
                candidate["youtube_video_id"] for candidate in self.candidates
            ],
            "elapsed_seconds": self.elapsed_seconds,
            "summary": {
                "requested_count": len(self.requested_urls),
                "hydration_success_count": len(self.candidates),
                "hydration_failure_count": sum(
                    result["status"] == "FAILED" for result in self.results
                ),
            },
            "scope_guards": {
                "ytsearch_queries": 0,
                "exact_url_requests_only": True,
                "audio_downloads": 0,
                "video_downloads": 0,
            },
        }


def exact_url_provider_config() -> YtDlpProviderConfig:
    """Return metadata-only options that fully resolve standalone watch URLs."""

    return YtDlpProviderConfig(
        candidate_limit=3,
        search_prefix="",
        extract_flat="discard_in_playlist",
        skip_download=True,
        simulate=True,
        ignore_user_config=True,
        cache_enabled=False,
        socket_timeout_seconds=30,
        max_attempts=1,
        retry_backoff_seconds=0.0,
        sleep_between_tracks_seconds=0.0,
    )


class YtDlpExactUrlHydrator:
    """Hydrate browser-ranked watch URLs without issuing another search query."""

    def __init__(
        self,
        backend: YtDlpBackend | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.provider = exact_url_provider_config()
        self.backend = backend or YtDlpPythonBackend(self.provider)
        self._clock = clock

    @staticmethod
    def _failure(
        browser_result: BrowserVideoResult,
        message: str,
        *,
        warnings: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        return {
            "browser_rank": browser_result.rank,
            "video_id": browser_result.video_id,
            "exact_url": browser_result.watch_url,
            "status": "FAILED",
            "warnings": list(warnings),
            "error": {
                "category": EXACT_URL_HYDRATION_FAILED,
                "message": message,
                "retryable": False,
            },
            "metadata": None,
        }

    def hydrate(
        self,
        track: SpotifyTrack,
        query: str,
        results: tuple[BrowserVideoResult, ...],
    ) -> ExactUrlHydrationOutcome:
        started = self._clock()
        records: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        for browser_result in results:
            try:
                response = self.backend.search(browser_result.watch_url)
                normalized_results = normalize_ytdlp_entries([response.info])
                normalized = normalized_results[0] if normalized_results else None
                if normalized is None or normalized.youtube_video_id != browser_result.video_id:
                    records.append(
                        self._failure(
                            browser_result,
                            "exact URL metadata did not resolve to the requested video ID",
                            warnings=response.warnings,
                        )
                    )
                    continue
            except YtDlpSearchError as exc:
                records.append(
                    self._failure(
                        browser_result,
                        str(exc),
                        warnings=exc.warnings,
                    )
                )
                continue
            candidate = {
                "rank": len(candidates) + 1,
                "provider_rank": browser_result.rank,
                "browser_rank": browser_result.rank,
                "youtube_video_id": browser_result.video_id,
                "canonical_url": browser_result.watch_url,
                "url": browser_result.watch_url,
                "title": normalized.title,
                "uploader": normalized.uploader,
                "channel": normalized.channel,
                "duration_seconds": normalized.duration_seconds,
                "view_count": normalized.view_count,
                "description": normalized.description,
                "availability": normalized.availability,
                "live_status": normalized.live_status,
                "provider": "yt_dlp",
                "discovery_source": PLAYWRIGHT_FALLBACK,
                "query": query,
                "stable_track_id": track.stable_track_id,
                "duplicate_occurrences": [],
            }
            candidates.append(candidate)
            records.append(
                {
                    "browser_rank": browser_result.rank,
                    "video_id": browser_result.video_id,
                    "exact_url": browser_result.watch_url,
                    "status": "HYDRATED",
                    "warnings": list(response.warnings),
                    "error": None,
                    "provider": {
                        "name": "yt_dlp",
                        "version": response.version,
                        "mode": "exact_watch_url",
                    },
                    "metadata": candidate,
                }
            )
        return ExactUrlHydrationOutcome(
            query=query,
            requested_urls=tuple(result.watch_url for result in results),
            results=tuple(records),
            candidates=tuple(candidates),
            elapsed_seconds=self._clock() - started,
        )


def _outcome_dict(outcome: Any) -> dict[str, Any]:
    value = outcome.to_dict() if hasattr(outcome, "to_dict") else outcome
    if not isinstance(value, dict):
        raise Stage5B1AValidationError("discovery adapter outcome must be an object")
    return value


def _primary_failure(
    track: SpotifyTrack, query: str, exc: YtDlpSearchError
) -> dict[str, Any]:
    return {
        "track": track.to_dict(),
        "query": query,
        "candidates": [],
        "candidate_video_ids": [],
        "warnings": list(exc.warnings),
        "error": exc.to_dict(),
    }


def discover_with_zero_result_fallback(
    track: SpotifyTrack,
    query: str,
    primary_adapter: PrimaryDiscoveryAdapter,
    browser_adapter: BrowserSearchAdapter,
    hydrator: BrowserResultHydrator,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Use Playwright only after primary ytsearch3 yields no usable candidates."""

    query = query.strip()
    if not query:
        raise Stage5B1AValidationError("fallback discovery query must be non-empty")
    primary_started = clock()
    try:
        primary = _outcome_dict(primary_adapter.discover_query(track, query, limit=3))
    except YtDlpSearchError as exc:
        primary = _primary_failure(track, query, exc)
    primary_elapsed = clock() - primary_started
    primary_candidates = list(primary.get("candidates") or [])
    primary_diagnostic = {
        "query": query,
        "result_count": len(primary_candidates),
        "error": primary.get("error"),
        "warnings": list(primary.get("warnings") or []),
        "elapsed_seconds": primary_elapsed,
        "outcome": primary,
    }
    if primary_candidates:
        return {
            "query": query,
            "provider_path": YTDLP_SEARCH,
            "trigger_reason": None,
            "primary": primary_diagnostic,
            "browser": {
                "triggered": False,
                "reason": "PRIMARY_RETURNED_USABLE_CANDIDATES",
                "outcome": None,
            },
            "hydration": {"triggered": False, "outcome": None},
            "candidates": primary_candidates,
            "error": None,
        }
    browser_outcome = browser_adapter.search(query, limit=3)
    browser_diagnostic = {
        "triggered": True,
        "reason": PRIMARY_ZERO_RESULTS,
        "outcome": browser_outcome.to_dict(),
    }
    if browser_outcome.error is not None or not browser_outcome.results:
        error = browser_outcome.error or {
            "category": "PLAYWRIGHT_NO_VIDEO_RESULTS",
            "message": "browser fallback returned no usable video results",
            "retryable": False,
        }
        return {
            "query": query,
            "provider_path": PLAYWRIGHT_FALLBACK,
            "trigger_reason": PRIMARY_ZERO_RESULTS,
            "primary": primary_diagnostic,
            "browser": browser_diagnostic,
            "hydration": {"triggered": False, "outcome": None},
            "candidates": [],
            "error": error,
        }
    hydration = hydrator.hydrate(track, query, browser_outcome.results)
    hydration_diagnostic = {"triggered": True, "outcome": hydration.to_dict()}
    candidates = [dict(candidate) for candidate in hydration.candidates]
    error = None
    if not candidates:
        error = {
            "category": EXACT_URL_HYDRATION_FAILED,
            "message": "all browser-discovered exact URLs failed metadata hydration",
            "retryable": False,
        }
    return {
        "query": query,
        "provider_path": PLAYWRIGHT_FALLBACK,
        "trigger_reason": PRIMARY_ZERO_RESULTS,
        "primary": primary_diagnostic,
        "browser": browser_diagnostic,
        "hydration": hydration_diagnostic,
        "candidates": candidates,
        "error": error,
    }
