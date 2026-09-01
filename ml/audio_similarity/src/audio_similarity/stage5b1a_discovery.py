"""Deterministic Firecrawl Search discovery and YouTube candidate normalization."""
from __future__ import annotations

import json
import re
import socket
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen

from .stage5b1a_config import ProviderConfig, QueryConfig
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError


YOUTUBE_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_FEATURE_CLAUSE = re.compile(
    r"\s*[\(\[]\s*(?:feat(?:uring)?|ft)\.?\s+[^\)\]]+[\)\]]",
    re.IGNORECASE,
)
_TRAILING_FEATURE = re.compile(
    r"\s+(?:feat(?:uring)?|ft)\.?\s+(?:(?!\s[-–—]\s|[\(\[]).)+$",
    re.IGNORECASE,
)
_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
_MAX_RESPONSE_BYTES = 2_000_000


class FirecrawlTransport(Protocol):
    def search(self, payload: dict[str, Any]) -> "FirecrawlTransportResponse": ...


class FirecrawlRequestError(RuntimeError):
    """Sanitized provider failure that never contains authorization material."""

    def __init__(
        self,
        category: str,
        message: str,
        *,
        attempts: int,
        retryable: bool,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.attempts = attempts
        self.retryable = retryable
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "message": str(self),
            "attempts": self.attempts,
            "retryable": self.retryable,
            "status_code": self.status_code,
        }


@dataclass(frozen=True)
class FirecrawlTransportResponse:
    payload: dict[str, Any]
    attempts: int


@dataclass(frozen=True)
class NormalizedSearchResult:
    source_rank: int
    url: str | None
    youtube_video_id: str | None
    title: str | None
    description: str | None
    raw_source: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_rank": self.source_rank,
            "url": self.url,
            "youtube_video_id": self.youtube_video_id,
            "title": self.title,
            "description": self.description,
            "raw_source": self.raw_source,
        }


@dataclass(frozen=True)
class DiscoveryCandidate:
    rank: int
    firecrawl_rank: int
    url: str
    youtube_video_id: str
    title: str | None
    description: str | None
    query: str
    stable_track_id: str
    duplicate_occurrences: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "firecrawl_rank": self.firecrawl_rank,
            "url": self.url,
            "youtube_video_id": self.youtube_video_id,
            "title": self.title,
            "description": self.description,
            "query": self.query,
            "stable_track_id": self.stable_track_id,
            "duplicate_occurrences": [dict(value) for value in self.duplicate_occurrences],
        }


@dataclass(frozen=True)
class DiscoveryOutcome:
    track: SpotifyTrack
    query: str
    request: dict[str, Any]
    provider: dict[str, Any]
    normalized_results: tuple[NormalizedSearchResult, ...]
    candidates: tuple[DiscoveryCandidate, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "track": self.track.to_dict(),
            "query": self.query,
            "request": self.request,
            "provider": self.provider,
            "normalized_results": [result.to_dict() for result in self.normalized_results],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "candidate_video_ids": [candidate.youtube_video_id for candidate in self.candidates],
            "error": None,
        }


def normalize_search_title(title: str, *, remove_featured_artist_noise: bool = True) -> str:
    normalized = title
    if remove_featured_artist_noise:
        normalized = _FEATURE_CLAUSE.sub("", normalized)
        normalized = _TRAILING_FEATURE.sub("", normalized)
    normalized = normalized.replace('"', " ")
    normalized = " ".join(normalized.split())
    if not normalized:
        raise Stage5B1AValidationError("query title became empty after normalization")
    return normalized


def build_search_query(track: SpotifyTrack, config: QueryConfig) -> str:
    title = normalize_search_title(
        track.title,
        remove_featured_artist_noise=config.normalize_featured_artist_noise,
    )
    primary_artist = track.artists[0].replace('"', " ")
    primary_artist = " ".join(primary_artist.split())
    query = config.template.format(
        primary_artist=primary_artist,
        normalized_title=title,
    )
    query = " ".join(query.split())
    if len(query) > 500:
        raise Stage5B1AValidationError("generated Firecrawl query exceeds 500 characters")
    return query


def _valid_video_id(value: str | None) -> str | None:
    if value and YOUTUBE_VIDEO_ID.fullmatch(value):
        return value
    return None


def parse_youtube_video_id(url: str | None) -> str | None:
    if not isinstance(url, str) or not url.strip() or len(url) > 4096:
        return None
    value = url.strip()
    if "://" not in value:
        value = "https://" + value
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower().rstrip(".")
    path_parts = [unquote(part) for part in parsed.path.split("/") if part]
    if host in {"youtu.be", "www.youtu.be"}:
        return _valid_video_id(path_parts[0] if path_parts else None)
    youtube_host = host == "youtube.com" or host.endswith(".youtube.com")
    youtube_nocookie = host == "youtube-nocookie.com" or host.endswith(".youtube-nocookie.com")
    if not youtube_host and not youtube_nocookie:
        return None
    if parsed.path.rstrip("/") == "/watch":
        return _valid_video_id(parse_qs(parsed.query).get("v", [None])[0])
    if len(path_parts) >= 2 and path_parts[0].lower() in {"shorts", "embed", "live"}:
        return _valid_video_id(path_parts[1])
    return None


def _optional_provider_text(value: Any, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:maximum] if value else None


def _raw_source(result: dict[str, Any]) -> dict[str, Any]:
    raw = {
        "url": _optional_provider_text(result.get("url"), 4096),
        "title": _optional_provider_text(result.get("title"), 2000),
        "description": _optional_provider_text(result.get("description"), 10_000),
    }
    category = _optional_provider_text(result.get("category"), 200)
    if category is not None:
        raw["category"] = category
    metadata = result.get("metadata")
    if isinstance(metadata, dict):
        bounded_metadata = {}
        for key in ("sourceURL", "url", "error"):
            text = _optional_provider_text(metadata.get(key), 4096 if key != "error" else 2000)
            if text is not None:
                bounded_metadata[key] = text
        status_code = metadata.get("statusCode")
        if isinstance(status_code, int) and not isinstance(status_code, bool):
            bounded_metadata["statusCode"] = status_code
        raw["metadata"] = bounded_metadata
    return raw


def normalize_firecrawl_web_results(
    web_results: Any,
) -> tuple[NormalizedSearchResult, ...]:
    if not isinstance(web_results, list):
        raise FirecrawlRequestError(
            "FIRECRAWL_RESPONSE_INVALID",
            "Firecrawl response data.web must be an array",
            attempts=1,
            retryable=False,
        )
    normalized = []
    for index, value in enumerate(web_results, start=1):
        result = value if isinstance(value, dict) else {}
        url = _optional_provider_text(result.get("url"), 4096)
        normalized.append(
            NormalizedSearchResult(
                source_rank=index,
                url=url,
                youtube_video_id=parse_youtube_video_id(url),
                title=_optional_provider_text(result.get("title"), 2000),
                description=_optional_provider_text(result.get("description"), 10_000),
                raw_source=_raw_source(result),
            )
        )
    return tuple(normalized)


def deduplicate_candidates(
    results: tuple[NormalizedSearchResult, ...],
    *,
    query: str,
    stable_track_id: str,
    limit: int,
) -> tuple[DiscoveryCandidate, ...]:
    if limit < 1:
        raise Stage5B1AValidationError("candidate limit must be positive")
    first: dict[str, NormalizedSearchResult] = {}
    duplicates: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        video_id = result.youtube_video_id
        if video_id is None:
            continue
        occurrence = {
            "source_rank": result.source_rank,
            "url": result.url,
            "title": result.title,
        }
        if video_id not in first:
            first[video_id] = result
            duplicates[video_id] = []
        else:
            duplicates[video_id].append(occurrence)
    candidates = []
    for result in sorted(first.values(), key=lambda value: value.source_rank)[:limit]:
        video_id = result.youtube_video_id
        assert video_id is not None
        candidates.append(
            DiscoveryCandidate(
                rank=len(candidates) + 1,
                firecrawl_rank=result.source_rank,
                url=f"https://www.youtube.com/watch?v={video_id}",
                youtube_video_id=video_id,
                title=result.title,
                description=result.description,
                query=query,
                stable_track_id=stable_track_id,
                duplicate_occurrences=tuple(duplicates[video_id]),
            )
        )
    return tuple(candidates)


class FirecrawlHTTPTransport:
    """Small injectable REST client with bounded retries and response size."""

    def __init__(
        self,
        config: ProviderConfig,
        api_key: str,
        *,
        opener: Callable[..., Any] = urlopen,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not isinstance(api_key, str) or not api_key.strip():
            raise Stage5B1AValidationError("FIRECRAWL_API_KEY is required for real discovery")
        self.config = config
        self._api_key = api_key.strip()
        self._opener = opener
        self._sleep = sleep

    def search(self, payload: dict[str, Any]) -> FirecrawlTransportResponse:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        for attempt in range(1, self.config.max_attempts + 1):
            request = Request(
                self.config.endpoint,
                data=encoded,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "spotify-audio-similarity-stage5b1a/1",
                },
            )
            try:
                with self._opener(
                    request,
                    timeout=self.config.request_timeout_ms / 1000,
                ) as response:
                    body = response.read(_MAX_RESPONSE_BYTES + 1)
                if len(body) > _MAX_RESPONSE_BYTES:
                    raise FirecrawlRequestError(
                        "FIRECRAWL_RESPONSE_TOO_LARGE",
                        "Firecrawl response exceeded the 2 MB experiment bound",
                        attempts=attempt,
                        retryable=False,
                    )
                parsed = json.loads(body.decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise ValueError("response root must be an object")
                return FirecrawlTransportResponse(payload=parsed, attempts=attempt)
            except HTTPError as exc:
                retryable = exc.code in _RETRYABLE_STATUS
                if retryable and attempt < self.config.max_attempts:
                    self._sleep(self.config.retry_backoff_seconds * (2 ** (attempt - 1)))
                    continue
                raise FirecrawlRequestError(
                    f"FIRECRAWL_HTTP_{exc.code}",
                    f"Firecrawl returned HTTP {exc.code}",
                    attempts=attempt,
                    retryable=retryable,
                    status_code=exc.code,
                ) from exc
            except (URLError, TimeoutError, socket.timeout) as exc:
                if attempt < self.config.max_attempts:
                    self._sleep(self.config.retry_backoff_seconds * (2 ** (attempt - 1)))
                    continue
                raise FirecrawlRequestError(
                    "FIRECRAWL_NETWORK_ERROR",
                    f"Firecrawl request failed after {attempt} attempts: {type(exc).__name__}",
                    attempts=attempt,
                    retryable=True,
                ) from exc
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                raise FirecrawlRequestError(
                    "FIRECRAWL_RESPONSE_INVALID",
                    f"Firecrawl returned invalid JSON: {type(exc).__name__}",
                    attempts=attempt,
                    retryable=False,
                ) from exc
        raise AssertionError("bounded Firecrawl retry loop exhausted unexpectedly")


class FirecrawlDiscoveryAdapter:
    def __init__(
        self,
        provider: ProviderConfig,
        query: QueryConfig,
        transport: FirecrawlTransport,
    ):
        self.provider = provider
        self.query_config = query
        self.transport = transport

    def discover(self, track: SpotifyTrack, limit: int | None = None) -> DiscoveryOutcome:
        candidate_limit = self.provider.candidate_limit if limit is None else limit
        if not 1 <= candidate_limit <= self.provider.candidate_limit:
            raise Stage5B1AValidationError(
                f"candidate limit must be between 1 and {self.provider.candidate_limit}"
            )
        query = build_search_query(track, self.query_config)
        payload = self.provider.request_payload(query)
        response = self.transport.search(payload)
        root = response.payload
        if root.get("success") is not True:
            provider_error = _optional_provider_text(root.get("error"), 1000)
            raise FirecrawlRequestError(
                "FIRECRAWL_SEARCH_FAILED",
                "Firecrawl response reported success=false"
                + (f": {provider_error}" if provider_error else ""),
                attempts=response.attempts,
                retryable=False,
            )
        data = root.get("data")
        if not isinstance(data, dict):
            raise FirecrawlRequestError(
                "FIRECRAWL_RESPONSE_INVALID",
                "Firecrawl response data must be an object",
                attempts=response.attempts,
                retryable=False,
            )
        normalized = normalize_firecrawl_web_results(data.get("web"))
        candidates = deduplicate_candidates(
            normalized,
            query=query,
            stable_track_id=track.stable_track_id,
            limit=candidate_limit,
        )
        return DiscoveryOutcome(
            track=track,
            query=query,
            request={
                "endpoint": self.provider.endpoint,
                "payload": payload,
                "api_key_environment_variable": self.provider.api_key_environment_variable,
            },
            provider={
                "name": "firecrawl",
                "discovery_version": self.provider.discovery_version,
                "attempts": response.attempts,
                "job_id": root.get("id") if isinstance(root.get("id"), str) else None,
                "credits_used": root.get("creditsUsed") if isinstance(root.get("creditsUsed"), int) else None,
                "warning": _optional_provider_text(root.get("warning"), 2000),
            },
            normalized_results=normalized,
            candidates=candidates,
        )
