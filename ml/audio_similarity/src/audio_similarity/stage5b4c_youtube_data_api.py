"""Official YouTube Data API fallback for zero-result yt-dlp searches."""
from __future__ import annotations

import json
import re
import socket
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .stage5b1a2_ytdlp import YtDlpSearchError
from .stage5b1a_discovery import YOUTUBE_VIDEO_ID
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError


YTDLP_SEARCH = "YTDLP_SEARCH"
YOUTUBE_DATA_API_FALLBACK = "YOUTUBE_DATA_API_FALLBACK"
PRIMARY_ZERO_RESULTS = "PRIMARY_ZERO_RESULTS"
MANUAL_YOUTUBE_URL_OVERRIDE = "MANUAL_YOUTUBE_URL_OVERRIDE"

YOUTUBE_DATA_API_CREDENTIAL_MISSING = "YOUTUBE_DATA_API_CREDENTIAL_MISSING"
YOUTUBE_DATA_API_SEARCH_FAILED = "YOUTUBE_DATA_API_SEARCH_FAILED"
YOUTUBE_DATA_API_SEARCH_ZERO_RESULTS = "YOUTUBE_DATA_API_SEARCH_ZERO_RESULTS"
YOUTUBE_DATA_API_HYDRATION_FAILED = "YOUTUBE_DATA_API_HYDRATION_FAILED"
YOUTUBE_DATA_API_RESPONSE_INVALID = "YOUTUBE_DATA_API_RESPONSE_INVALID"
YOUTUBE_DATA_API_QUOTA_EXCEEDED = "YOUTUBE_DATA_API_QUOTA_EXCEEDED"
YOUTUBE_DATA_API_AUTH_FAILED = "YOUTUBE_DATA_API_AUTH_FAILED"

SEARCH_ENDPOINT = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_ENDPOINT = "https://www.googleapis.com/youtube/v3/videos"
_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


class PrimaryDiscoveryAdapter(Protocol):
    def discover_query(
        self, track: SpotifyTrack, query: str, *, limit: int
    ) -> Any: ...


class JsonTransport(Protocol):
    def get_json(
        self,
        endpoint: str,
        parameters: Mapping[str, str],
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


class YouTubeDataApiError(RuntimeError):
    def __init__(
        self,
        category: str,
        message: str,
        *,
        http_status: int | None = None,
        reason: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.http_status = http_status
        self.reason = reason
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "message": str(self),
            "http_status": self.http_status,
            "reason": self.reason,
            "retryable": self.retryable,
        }


def _google_error(body: bytes) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return None, None
    message = error.get("message")
    details = error.get("errors")
    reason = None
    if isinstance(details, list) and details and isinstance(details[0], dict):
        reason = details[0].get("reason")
    return (
        str(message)[:1000] if isinstance(message, str) else None,
        str(reason)[:200] if isinstance(reason, str) else None,
    )


def _http_failure(status: int, message: str | None, reason: str | None) -> YouTubeDataApiError:
    if status == 401 or (
        status == 403
        and reason in {"keyInvalid", "accessNotConfigured", "ipRefererBlocked"}
    ):
        category = YOUTUBE_DATA_API_AUTH_FAILED
    elif status in {403, 429} and reason in {
        "quotaExceeded",
        "dailyLimitExceeded",
        "rateLimitExceeded",
        "userRateLimitExceeded",
    }:
        category = YOUTUBE_DATA_API_QUOTA_EXCEEDED
    else:
        category = YOUTUBE_DATA_API_SEARCH_FAILED
    return YouTubeDataApiError(
        category,
        message or f"YouTube Data API request failed with HTTP {status}",
        http_status=status,
        reason=reason,
        retryable=status >= 500 or status == 429,
    )


class UrlLibJsonTransport:
    """Small GET-only JSON boundary that never exposes the API key."""

    def get_json(
        self,
        endpoint: str,
        parameters: Mapping[str, str],
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        query = urlencode(dict(parameters) | {"key": api_key})
        request = Request(
            f"{endpoint}?{query}",
            headers={
                "Accept": "application/json",
                "User-Agent": "spotify-sorter-youtube-data-api/1",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read(2_000_001)
        except HTTPError as exc:
            message, reason = _google_error(exc.read(100_000))
            if message:
                message = message.replace(api_key, "[REDACTED]")
            if reason:
                reason = reason.replace(api_key, "[REDACTED]")
            raise _http_failure(exc.code, message, reason) from None
        except (URLError, socket.timeout, TimeoutError, OSError) as exc:
            raise YouTubeDataApiError(
                YOUTUBE_DATA_API_SEARCH_FAILED,
                f"YouTube Data API transport failed: {type(exc).__name__}",
                retryable=True,
            ) from None
        if len(body) > 2_000_000:
            raise YouTubeDataApiError(
                YOUTUBE_DATA_API_RESPONSE_INVALID,
                "YouTube Data API response exceeded the size limit",
            )
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise YouTubeDataApiError(
                YOUTUBE_DATA_API_RESPONSE_INVALID,
                "YouTube Data API response was not valid UTF-8 JSON",
            ) from None
        if not isinstance(payload, dict):
            raise YouTubeDataApiError(
                YOUTUBE_DATA_API_RESPONSE_INVALID,
                "YouTube Data API response root was not an object",
            )
        return payload


@dataclass(frozen=True)
class YouTubeDataApiConfig:
    api_key_environment_variable: str = "YOUTUBE_DATA_API_KEY"
    search_endpoint: str = SEARCH_ENDPOINT
    videos_endpoint: str = VIDEOS_ENDPOINT
    maximum_results: int = 3
    timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        if self.maximum_results != 3:
            raise Stage5B1AValidationError("Data API fallback is fixed to three results")
        if not 1.0 <= self.timeout_seconds <= 60.0:
            raise Stage5B1AValidationError("Data API timeout is out of bounds")
        if not self.api_key_environment_variable.strip():
            raise Stage5B1AValidationError("Data API key environment variable is required")
        if self.search_endpoint != SEARCH_ENDPOINT or self.videos_endpoint != VIDEOS_ENDPOINT:
            raise Stage5B1AValidationError(
                "Data API credentials may only be sent to the official endpoints"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_key_environment_variable": self.api_key_environment_variable,
            "search_endpoint": self.search_endpoint,
            "videos_endpoint": self.videos_endpoint,
            "maximum_results": self.maximum_results,
            "timeout_seconds": self.timeout_seconds,
            "credential_persisted": False,
        }


@dataclass(frozen=True)
class DataApiVideoReference:
    rank: int
    video_id: str
    watch_url: str

    def __post_init__(self) -> None:
        expected_url = f"https://www.youtube.com/watch?v={self.video_id}"
        if not 1 <= self.rank <= 3:
            raise Stage5B1AValidationError("Data API provider rank must be 1–3")
        if not YOUTUBE_VIDEO_ID.fullmatch(self.video_id):
            raise Stage5B1AValidationError("invalid Data API YouTube video ID")
        if self.watch_url != expected_url:
            raise Stage5B1AValidationError("Data API watch URL does not match its video ID")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class DataApiSearchOutcome:
    query: str
    results: tuple[DataApiVideoReference, ...]
    error: dict[str, Any] | None
    elapsed_seconds: float
    request: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "results": [result.to_dict() for result in self.results],
            "video_ids_in_provider_order": [result.video_id for result in self.results],
            "error": self.error,
            "elapsed_seconds": self.elapsed_seconds,
            "request": dict(self.request),
        }


@dataclass(frozen=True)
class DataApiHydrationOutcome:
    query: str
    requested_video_ids: tuple[str, ...]
    records: tuple[dict[str, Any], ...]
    candidates: tuple[dict[str, Any], ...]
    error: dict[str, Any] | None
    elapsed_seconds: float
    request: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "requested_video_ids": list(self.requested_video_ids),
            "records": [dict(record) for record in self.records],
            "candidates": [dict(candidate) for candidate in self.candidates],
            "error": self.error,
            "elapsed_seconds": self.elapsed_seconds,
            "request": dict(self.request),
        }


def _video_references(payload: dict[str, Any]) -> tuple[DataApiVideoReference, ...]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise YouTubeDataApiError(
            YOUTUBE_DATA_API_RESPONSE_INVALID,
            "search.list response did not contain an items array",
        )
    results: list[DataApiVideoReference] = []
    seen: set[str] = set()
    for item in items:
        identity = item.get("id") if isinstance(item, dict) else None
        video_id = identity.get("videoId") if isinstance(identity, dict) else None
        kind = identity.get("kind") if isinstance(identity, dict) else None
        if (
            kind != "youtube#video"
            or not isinstance(video_id, str)
            or not YOUTUBE_VIDEO_ID.fullmatch(video_id)
            or video_id in seen
        ):
            continue
        seen.add(video_id)
        results.append(
            DataApiVideoReference(
                rank=len(results) + 1,
                video_id=video_id,
                watch_url=f"https://www.youtube.com/watch?v={video_id}",
            )
        )
        if len(results) == 3:
            break
    return tuple(results)


def _duration_seconds(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    match = _DURATION.fullmatch(value)
    if match is None or not any(match.groupdict().values()):
        return None
    parts = {name: int(number or 0) for name, number in match.groupdict().items()}
    return float(
        parts["days"] * 86_400
        + parts["hours"] * 3_600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


def _view_count(value: Any) -> int | None:
    if not isinstance(value, str) or not value.isdigit():
        return None
    count = int(value)
    return count if count >= 0 else None


def _limited_text(value: Any, maximum: int = 10_000) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:maximum] if value else None


class YouTubeDataApiClient:
    def __init__(
        self,
        api_key: str | None,
        config: YouTubeDataApiConfig | None = None,
        *,
        transport: JsonTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or YouTubeDataApiConfig()
        self._api_key = api_key.strip() if isinstance(api_key, str) else ""
        self._transport = transport or UrlLibJsonTransport()
        self._clock = clock

    def _credential_error(self) -> dict[str, Any] | None:
        if self._api_key:
            return None
        return YouTubeDataApiError(
            YOUTUBE_DATA_API_CREDENTIAL_MISSING,
            f"{self.config.api_key_environment_variable} is not configured",
        ).to_dict()

    def search(self, query: str, *, limit: int = 3) -> DataApiSearchOutcome:
        query = query.strip()
        if not query:
            raise Stage5B1AValidationError("Data API search query must be non-empty")
        if limit != self.config.maximum_results:
            raise Stage5B1AValidationError("Data API search limit must be exactly three")
        started = self._clock()
        request = {
            "endpoint": self.config.search_endpoint,
            "parameters": {
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": "3",
            },
            "credential_source": self.config.api_key_environment_variable,
            "credential_recorded": False,
        }
        credential_error = self._credential_error()
        if credential_error is not None:
            return DataApiSearchOutcome(
                query=query,
                results=(),
                error=credential_error,
                elapsed_seconds=self._clock() - started,
                request=request,
            )
        try:
            payload = self._transport.get_json(
                self.config.search_endpoint,
                request["parameters"],
                api_key=self._api_key,
                timeout_seconds=self.config.timeout_seconds,
            )
            results = _video_references(payload)
        except YouTubeDataApiError as exc:
            return DataApiSearchOutcome(
                query=query,
                results=(),
                error=exc.to_dict(),
                elapsed_seconds=self._clock() - started,
                request=request,
            )
        error = None
        if not results:
            error = YouTubeDataApiError(
                YOUTUBE_DATA_API_SEARCH_ZERO_RESULTS,
                "search.list returned no usable video IDs",
            ).to_dict()
        return DataApiSearchOutcome(
            query=query,
            results=results,
            error=error,
            elapsed_seconds=self._clock() - started,
            request=request,
        )

    def hydrate(
        self,
        track: SpotifyTrack,
        query: str,
        results: tuple[DataApiVideoReference, ...],
    ) -> DataApiHydrationOutcome:
        if not results or len(results) > 3:
            raise Stage5B1AValidationError("Data API hydration requires one to three IDs")
        query = query.strip()
        if not query:
            raise Stage5B1AValidationError("Data API hydration query must be non-empty")
        ranks = [result.rank for result in results]
        video_ids = [result.video_id for result in results]
        if ranks != list(range(1, len(results) + 1)):
            raise Stage5B1AValidationError("Data API hydration requires provider ranks in order")
        if len(video_ids) != len(set(video_ids)):
            raise Stage5B1AValidationError("Data API hydration video IDs must be unique")
        started = self._clock()
        requested_ids = tuple(result.video_id for result in results)
        request = {
            "endpoint": self.config.videos_endpoint,
            "parameters": {
                "part": "snippet,contentDetails,statistics,status",
                "id": ",".join(requested_ids),
            },
            "credential_source": self.config.api_key_environment_variable,
            "credential_recorded": False,
        }
        credential_error = self._credential_error()
        if credential_error is not None:
            return DataApiHydrationOutcome(
                query=query,
                requested_video_ids=requested_ids,
                records=(),
                candidates=(),
                error=credential_error,
                elapsed_seconds=self._clock() - started,
                request=request,
            )
        try:
            payload = self._transport.get_json(
                self.config.videos_endpoint,
                request["parameters"],
                api_key=self._api_key,
                timeout_seconds=self.config.timeout_seconds,
            )
            items = payload.get("items")
            if not isinstance(items, list):
                raise YouTubeDataApiError(
                    YOUTUBE_DATA_API_RESPONSE_INVALID,
                    "videos.list response did not contain an items array",
                )
        except YouTubeDataApiError as exc:
            return DataApiHydrationOutcome(
                query=query,
                requested_video_ids=requested_ids,
                records=(),
                candidates=(),
                error=exc.to_dict(),
                elapsed_seconds=self._clock() - started,
                request=request,
            )
        by_id = {
            item.get("id"): item
            for item in items
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and YOUTUBE_VIDEO_ID.fullmatch(item["id"])
        }
        records: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        for reference in results:
            item = by_id.get(reference.video_id)
            if item is None:
                records.append(
                    {
                        "provider_rank": reference.rank,
                        "video_id": reference.video_id,
                        "status": "FAILED",
                        "error": {
                            "category": YOUTUBE_DATA_API_HYDRATION_FAILED,
                            "message": "videos.list omitted the requested video ID",
                            "retryable": False,
                        },
                    }
                )
                continue
            snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
            content = (
                item.get("contentDetails")
                if isinstance(item.get("contentDetails"), dict)
                else {}
            )
            statistics = (
                item.get("statistics")
                if isinstance(item.get("statistics"), dict)
                else {}
            )
            status = item.get("status") if isinstance(item.get("status"), dict) else {}
            live = snippet.get("liveBroadcastContent")
            candidate = {
                "rank": len(candidates) + 1,
                "provider_rank": reference.rank,
                "youtube_video_id": reference.video_id,
                "canonical_url": reference.watch_url,
                "url": reference.watch_url,
                "title": _limited_text(snippet.get("title")),
                "uploader": _limited_text(snippet.get("channelTitle"), 500),
                "channel": _limited_text(snippet.get("channelTitle"), 500),
                "channel_id": _limited_text(snippet.get("channelId"), 100),
                "duration_seconds": _duration_seconds(content.get("duration")),
                "view_count": _view_count(statistics.get("viewCount")),
                "description": _limited_text(snippet.get("description")),
                "availability": _limited_text(status.get("privacyStatus"), 50),
                "live_status": "not_live" if live == "none" else _limited_text(live, 50),
                "provider": "youtube_data_api_v3",
                "discovery_source": YOUTUBE_DATA_API_FALLBACK,
                "query": query,
                "stable_track_id": track.stable_track_id,
                "duplicate_occurrences": [],
            }
            candidates.append(candidate)
            records.append(
                {
                    "provider_rank": reference.rank,
                    "video_id": reference.video_id,
                    "status": "HYDRATED",
                    "error": None,
                    "metadata": candidate,
                }
            )
        error = None
        if not candidates:
            error = YouTubeDataApiError(
                YOUTUBE_DATA_API_HYDRATION_FAILED,
                "videos.list hydrated none of the search result IDs",
            ).to_dict()
        return DataApiHydrationOutcome(
            query=query,
            requested_video_ids=requested_ids,
            records=tuple(records),
            candidates=tuple(candidates),
            error=error,
            elapsed_seconds=self._clock() - started,
            request=request,
        )


def _primary_outcome(value: Any) -> dict[str, Any]:
    outcome = value.to_dict() if hasattr(value, "to_dict") else value
    if not isinstance(outcome, dict):
        raise Stage5B1AValidationError("primary discovery outcome must be an object")
    return outcome


def discover_with_data_api_fallback(
    track: SpotifyTrack,
    query: str,
    primary_adapter: PrimaryDiscoveryAdapter,
    data_api: YouTubeDataApiClient,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Use the official Data API only after yt-dlp returns zero candidates."""

    query = query.strip()
    if not query:
        raise Stage5B1AValidationError("fallback discovery query must be non-empty")
    started = clock()
    try:
        primary = _primary_outcome(primary_adapter.discover_query(track, query, limit=3))
    except YtDlpSearchError as exc:
        primary = {
            "track": track.to_dict(),
            "query": query,
            "candidates": [],
            "warnings": list(exc.warnings),
            "error": exc.to_dict(),
        }
    primary_candidates = list(primary.get("candidates") or [])
    primary_diagnostic = {
        "query": query,
        "result_count": len(primary_candidates),
        "error": primary.get("error"),
        "warnings": list(primary.get("warnings") or []),
        "elapsed_seconds": clock() - started,
        "outcome": primary,
    }
    if primary_candidates:
        return {
            "query": query,
            "provider_path": YTDLP_SEARCH,
            "primary": primary_diagnostic,
            "data_api_search": {"triggered": False, "outcome": None},
            "data_api_hydration": {"triggered": False, "outcome": None},
            "candidates": primary_candidates,
            "next_step": None,
            "error": None,
        }
    search = data_api.search(query, limit=3)
    search_diagnostic = {
        "triggered": True,
        "reason": PRIMARY_ZERO_RESULTS,
        "outcome": search.to_dict(),
    }
    if search.error is not None or not search.results:
        return {
            "query": query,
            "provider_path": YOUTUBE_DATA_API_FALLBACK,
            "primary": primary_diagnostic,
            "data_api_search": search_diagnostic,
            "data_api_hydration": {"triggered": False, "outcome": None},
            "candidates": [],
            "next_step": MANUAL_YOUTUBE_URL_OVERRIDE,
            "error": search.error,
        }
    hydration = data_api.hydrate(track, query, search.results)
    candidates = [dict(candidate) for candidate in hydration.candidates]
    return {
        "query": query,
        "provider_path": YOUTUBE_DATA_API_FALLBACK,
        "primary": primary_diagnostic,
        "data_api_search": search_diagnostic,
        "data_api_hydration": {
            "triggered": True,
            "outcome": hydration.to_dict(),
        },
        "candidates": candidates,
        "next_step": None if candidates else MANUAL_YOUTUBE_URL_OVERRIDE,
        "error": hydration.error,
    }
