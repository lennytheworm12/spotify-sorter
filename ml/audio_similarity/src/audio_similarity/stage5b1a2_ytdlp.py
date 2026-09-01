"""Metadata-only yt-dlp YouTube search for Stage 5B.1A2."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import yt_dlp

from .stage5b1a2_config import YtDlpProviderConfig
from .stage5b1a_config import QueryConfig
from .stage5b1a_discovery import YOUTUBE_VIDEO_ID, build_search_query, parse_youtube_video_id
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError


_MAX_TEXT = 10_000
_MAX_LOG_MESSAGES = 100


def _text(value: Any, maximum: int = _MAX_TEXT) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized[:maximum] if normalized else None


def _duration(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0 else None


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return int(result) if math.isfinite(result) and result >= 0 else None


def _video_id(entry: dict[str, Any]) -> str | None:
    direct = entry.get("id")
    direct_id = direct if isinstance(direct, str) and YOUTUBE_VIDEO_ID.fullmatch(direct) else None
    parsed_ids = [
        parse_youtube_video_id(entry.get(key))
        for key in ("webpage_url", "original_url", "url")
    ]
    parsed = next((value for value in parsed_ids if value is not None), None)
    if direct_id and parsed and direct_id != parsed:
        return None
    candidate = direct_id or parsed
    extractor = " ".join(
        value for value in (entry.get("ie_key"), entry.get("extractor_key"), entry.get("extractor"))
        if isinstance(value, str)
    ).lower()
    if candidate and ("youtube" in extractor or parsed is not None):
        return candidate
    return None


def _raw_entry(entry: dict[str, Any]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for key in (
        "_type", "id", "url", "webpage_url", "original_url", "title", "description",
        "uploader", "uploader_id", "channel", "channel_id", "availability", "live_status",
        "ie_key", "extractor", "extractor_key",
    ):
        value = _text(entry.get(key), 4096 if key.endswith("url") or key == "url" else _MAX_TEXT)
        if value is not None:
            raw[key] = value
    duration = _duration(entry.get("duration"))
    if duration is not None:
        raw["duration"] = duration
    view_count = _count(entry.get("view_count"))
    if view_count is not None:
        raw["view_count"] = view_count
    return raw


@dataclass(frozen=True)
class YtDlpBackendResponse:
    info: dict[str, Any]
    warnings: tuple[str, ...]
    version: str


class YtDlpBackend(Protocol):
    version: str

    def search(self, expression: str) -> YtDlpBackendResponse: ...


class YtDlpSearchError(RuntimeError):
    def __init__(
        self,
        category: str,
        message: str,
        *,
        attempts: int,
        retryable: bool,
        warnings: tuple[str, ...] = (),
    ):
        super().__init__(message)
        self.category = category
        self.attempts = attempts
        self.retryable = retryable
        self.warnings = warnings

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "message": str(self),
            "attempts": self.attempts,
            "retryable": self.retryable,
            "warnings": list(self.warnings),
        }


class _CaptureLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def debug(self, _message: str) -> None:
        return None

    def info(self, _message: str) -> None:
        return None

    def warning(self, message: str) -> None:
        if len(self.warnings) < _MAX_LOG_MESSAGES:
            self.warnings.append(str(message)[:4000])

    def error(self, message: str) -> None:
        if len(self.errors) < _MAX_LOG_MESSAGES:
            self.errors.append(str(message)[:4000])


class YtDlpPythonBackend:
    """Pinned Python API boundary; never invokes yt-dlp's download method."""

    def __init__(
        self,
        provider: YtDlpProviderConfig,
        *,
        youtube_dl_factory: Callable[[dict[str, Any]], Any] = yt_dlp.YoutubeDL,
    ):
        self.provider = provider
        self.version = yt_dlp.version.__version__
        self._youtube_dl_factory = youtube_dl_factory

    def search(self, expression: str) -> YtDlpBackendResponse:
        logger = _CaptureLogger()
        options = self.provider.metadata_only_options() | {"logger": logger}
        try:
            with self._youtube_dl_factory(options) as ydl:
                info = ydl.extract_info(expression, download=False)
                sanitized = ydl.sanitize_info(info)
        except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError, OSError, TimeoutError) as exc:
            details = logger.errors[-1] if logger.errors else type(exc).__name__
            raise YtDlpSearchError(
                "YTDLP_EXTRACTION_ERROR",
                f"yt-dlp search failed: {details}",
                attempts=1,
                retryable=True,
                warnings=tuple(logger.warnings),
            ) from exc
        if not isinstance(sanitized, dict):
            raise YtDlpSearchError(
                "YTDLP_RESPONSE_INVALID",
                "yt-dlp search response root must be an object",
                attempts=1,
                retryable=False,
                warnings=tuple(logger.warnings),
            )
        return YtDlpBackendResponse(
            info=sanitized,
            warnings=tuple(logger.warnings),
            version=self.version,
        )


@dataclass(frozen=True)
class NormalizedYtDlpResult:
    source_rank: int
    youtube_video_id: str | None
    canonical_url: str | None
    title: str | None
    uploader: str | None
    channel: str | None
    duration_seconds: float | None
    view_count: int | None
    description: str | None
    availability: str | None
    live_status: str | None
    raw_source: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class YtDlpCandidate:
    rank: int
    provider_rank: int
    youtube_video_id: str
    canonical_url: str
    title: str | None
    uploader: str | None
    channel: str | None
    duration_seconds: float | None
    view_count: int | None
    description: str | None
    availability: str | None
    live_status: str | None
    provider: str
    query: str
    stable_track_id: str
    duplicate_occurrences: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        value = dict(self.__dict__)
        value["url"] = self.canonical_url
        value["duplicate_occurrences"] = [dict(item) for item in self.duplicate_occurrences]
        return value


@dataclass(frozen=True)
class YtDlpDiscoveryOutcome:
    track: SpotifyTrack
    query: str
    request: dict[str, Any]
    provider: dict[str, Any]
    normalized_results: tuple[NormalizedYtDlpResult, ...]
    candidates: tuple[YtDlpCandidate, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "track": self.track.to_dict(),
            "query": self.query,
            "request": self.request,
            "provider": self.provider,
            "normalized_results": [item.to_dict() for item in self.normalized_results],
            "candidates": [item.to_dict() for item in self.candidates],
            "candidate_video_ids": [item.youtube_video_id for item in self.candidates],
            "warnings": list(self.warnings),
            "error": None,
        }


def normalize_ytdlp_entries(entries: Any) -> tuple[NormalizedYtDlpResult, ...]:
    if entries is None:
        return ()
    if not isinstance(entries, list):
        raise YtDlpSearchError(
            "YTDLP_RESPONSE_INVALID",
            "yt-dlp search entries must be an array",
            attempts=1,
            retryable=False,
        )
    output = []
    for rank, value in enumerate(entries, start=1):
        entry = value if isinstance(value, dict) else {}
        video_id = _video_id(entry)
        output.append(
            NormalizedYtDlpResult(
                source_rank=rank,
                youtube_video_id=video_id,
                canonical_url=(
                    f"https://www.youtube.com/watch?v={video_id}" if video_id else None
                ),
                title=_text(entry.get("title"), 2000),
                uploader=_text(entry.get("uploader"), 1000),
                channel=_text(entry.get("channel"), 1000),
                duration_seconds=_duration(entry.get("duration")),
                view_count=_count(entry.get("view_count")),
                description=_text(entry.get("description")),
                availability=_text(entry.get("availability"), 200),
                live_status=_text(entry.get("live_status"), 200),
                raw_source=_raw_entry(entry),
            )
        )
    return tuple(output)


def deduplicate_ytdlp_candidates(
    results: tuple[NormalizedYtDlpResult, ...],
    *,
    query: str,
    stable_track_id: str,
    limit: int,
) -> tuple[YtDlpCandidate, ...]:
    first: dict[str, NormalizedYtDlpResult] = {}
    duplicates: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        video_id = result.youtube_video_id
        if video_id is None:
            continue
        occurrence = {
            "source_rank": result.source_rank,
            "title": result.title,
            "canonical_url": result.canonical_url,
        }
        if video_id not in first:
            first[video_id] = result
            duplicates[video_id] = []
        else:
            duplicates[video_id].append(occurrence)
    candidates = []
    for result in sorted(first.values(), key=lambda item: item.source_rank)[:limit]:
        assert result.youtube_video_id is not None and result.canonical_url is not None
        candidates.append(
            YtDlpCandidate(
                rank=len(candidates) + 1,
                provider_rank=result.source_rank,
                youtube_video_id=result.youtube_video_id,
                canonical_url=result.canonical_url,
                title=result.title,
                uploader=result.uploader,
                channel=result.channel,
                duration_seconds=result.duration_seconds,
                view_count=result.view_count,
                description=result.description,
                availability=result.availability,
                live_status=result.live_status,
                provider="yt_dlp",
                query=query,
                stable_track_id=stable_track_id,
                duplicate_occurrences=tuple(duplicates[result.youtube_video_id]),
            )
        )
    return tuple(candidates)


class YtDlpDiscoveryAdapter:
    def __init__(
        self,
        provider: YtDlpProviderConfig,
        query: QueryConfig,
        backend: YtDlpBackend,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.provider = provider
        self.query_config = query
        self.backend = backend
        self._sleep = sleep

    def discover(self, track: SpotifyTrack, limit: int | None = None) -> YtDlpDiscoveryOutcome:
        candidate_limit = self.provider.candidate_limit if limit is None else limit
        if not 1 <= candidate_limit <= self.provider.candidate_limit:
            raise Stage5B1AValidationError("candidate limit must be between 1 and 5")
        query = build_search_query(track, self.query_config)
        expression = self.provider.search_expression(query)
        accumulated_warnings: list[str] = []
        response = None
        for attempt in range(1, self.provider.max_attempts + 1):
            try:
                response = self.backend.search(expression)
                accumulated_warnings.extend(response.warnings)
                break
            except YtDlpSearchError as exc:
                accumulated_warnings.extend(exc.warnings)
                if not exc.retryable or attempt == self.provider.max_attempts:
                    raise YtDlpSearchError(
                        exc.category,
                        str(exc),
                        attempts=attempt,
                        retryable=exc.retryable,
                        warnings=tuple(accumulated_warnings),
                    ) from exc
                self._sleep(self.provider.retry_backoff_seconds * (2 ** (attempt - 1)))
        assert response is not None
        normalized = normalize_ytdlp_entries(response.info.get("entries"))
        candidates = deduplicate_ytdlp_candidates(
            normalized,
            query=query,
            stable_track_id=track.stable_track_id,
            limit=candidate_limit,
        )
        return YtDlpDiscoveryOutcome(
            track=track,
            query=query,
            request={
                "search_expression": expression,
                "options": self.provider.metadata_only_options(),
                "download": False,
            },
            provider={
                "name": "yt_dlp",
                "version": response.version,
                "attempts": attempt,
            },
            normalized_results=normalized,
            candidates=candidates,
            warnings=tuple(accumulated_warnings),
        )
