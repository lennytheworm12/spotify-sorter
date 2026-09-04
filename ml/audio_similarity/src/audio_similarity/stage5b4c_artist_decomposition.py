"""Zero-result-only decomposition of a natural multi-artist YouTube query."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .stage5b1a2_ytdlp import YtDlpSearchError
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError
from .stage5b4a_query_contract_repair import (
    first_distinct_artists,
    natural_title_first3_artists_query,
    sanitize_query_text,
)


QUERY_CONTRACT_ID = "NATURAL_TITLE_FIRST3_ARTISTS_THEN_SINGLE_ARTIST_V1"
PRIMARY_MULTI_ARTIST = "PRIMARY_MULTI_ARTIST"
SINGLE_ARTIST_ZERO_RESULT_FALLBACK = "SINGLE_ARTIST_ZERO_RESULT_FALLBACK"
PRIMARY_SUCCESS = "PRIMARY_SUCCESS"
FALLBACK_SUCCESS = "FALLBACK_SUCCESS"
ALL_QUERY_VARIANTS_EMPTY = "ALL_QUERY_VARIANTS_EMPTY"
PROVIDER_ERROR = "PROVIDER_ERROR"


class QuerySearchProvider(Protocol):
    """Small provider boundary used by the decomposition orchestrator."""

    def discover_query(
        self, track: SpotifyTrack, query: str, *, limit: int
    ) -> Any: ...


@dataclass(frozen=True)
class QueryVariant:
    index: int
    query: str
    artist: str | None
    discovery_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_variant_index": self.index,
            "query": self.query,
            "query_artist": self.artist,
            "discovery_mode": self.discovery_mode,
        }


@dataclass(frozen=True)
class ArtistDecompositionPlan:
    title: str
    artists: tuple[str, ...]
    primary: QueryVariant
    fallbacks: tuple[QueryVariant, ...]
    duplicate_fallback_queries_removed: int

    @property
    def variants(self) -> tuple[QueryVariant, ...]:
        return (self.primary, *self.fallbacks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_contract_id": QUERY_CONTRACT_ID,
            "sanitized_spotify_title": self.title,
            "included_artists": list(self.artists),
            "primary": self.primary.to_dict(),
            "fallbacks": [variant.to_dict() for variant in self.fallbacks],
            "maximum_provider_requests": len(self.variants),
            "duplicate_fallback_queries_removed": (
                self.duplicate_fallback_queries_removed
            ),
        }


def build_artist_decomposition_plan(track: SpotifyTrack) -> ArtistDecompositionPlan:
    """Build Q0 and unique title-plus-one-artist fallbacks without semantics."""

    title = sanitize_query_text(track.title)
    artists = first_distinct_artists(track.artists, limit=3)
    primary_query = natural_title_first3_artists_query(track)
    primary = QueryVariant(
        index=0,
        query=primary_query,
        artist=None,
        discovery_mode=PRIMARY_MULTI_ARTIST,
    )
    seen = {primary_query}
    fallbacks: list[QueryVariant] = []
    duplicates_removed = 0
    for index, artist in enumerate(artists, start=1):
        query = " ".join((title, artist))
        if query in seen:
            duplicates_removed += 1
            continue
        seen.add(query)
        fallbacks.append(
            QueryVariant(
                index=index,
                query=query,
                artist=artist,
                discovery_mode=SINGLE_ARTIST_ZERO_RESULT_FALLBACK,
            )
        )
    return ArtistDecompositionPlan(
        title=title,
        artists=artists,
        primary=primary,
        fallbacks=tuple(fallbacks),
        duplicate_fallback_queries_removed=duplicates_removed,
    )


def _outcome_dict(outcome: Any) -> dict[str, Any]:
    value = outcome.to_dict() if hasattr(outcome, "to_dict") else outcome
    if not isinstance(value, dict):
        raise Stage5B1AValidationError("discovery adapter outcome must be an object")
    candidates = value.get("candidates")
    if not isinstance(candidates, (list, tuple)):
        raise Stage5B1AValidationError("discovery outcome candidates must be an array")
    if value.get("error") is not None:
        raise Stage5B1AValidationError(
            "provider errors must be raised rather than returned as discovery success"
        )
    return value


def _provider_error(exc: YtDlpSearchError) -> dict[str, Any]:
    return exc.to_dict()


def _attempt(
    variant: QueryVariant,
    *,
    started: float,
    ended: float,
    outcome: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = [] if outcome is None else list(outcome["candidates"])
    warnings = (
        list(error.get("warnings", []))
        if error is not None
        else list((outcome or {}).get("warnings", []))
    )
    return {
        **variant.to_dict(),
        "result_count": len(candidates),
        "candidate_video_ids": [
            candidate.get("youtube_video_id")
            for candidate in candidates
            if isinstance(candidate, dict)
        ],
        "warnings": warnings,
        "error": error,
        "elapsed_seconds": ended - started,
    }


def _with_provenance(
    candidates: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    variant: QueryVariant,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for candidate in candidates[:3]:
        if not isinstance(candidate, dict):
            raise Stage5B1AValidationError("discovery candidates must be objects")
        normalized.append(
            dict(candidate)
            | {
                "discovery_mode": variant.discovery_mode,
                "query_variant_index": variant.index,
                "query_artist": variant.artist,
            }
        )
    return normalized


def discover_with_artist_decomposition(
    track: SpotifyTrack,
    provider: QuerySearchProvider,
    *,
    limit: int = 3,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Search Q0, then unique single-artist variants only after valid zero results."""

    if limit != 3:
        raise Stage5B1AValidationError("artist decomposition uses a frozen Top-3 limit")
    plan = build_artist_decomposition_plan(track)
    run_started = clock()
    attempts: list[dict[str, Any]] = []

    for variant in plan.variants:
        started = clock()
        try:
            outcome = _outcome_dict(
                provider.discover_query(track, variant.query, limit=limit)
            )
        except YtDlpSearchError as exc:
            ended = clock()
            error = _provider_error(exc)
            attempts.append(
                _attempt(variant, started=started, ended=ended, error=error)
            )
            return {
                "track": track.to_dict(),
                "query_plan": plan.to_dict(),
                "outcome": PROVIDER_ERROR,
                "discovery_mode": variant.discovery_mode,
                "query_variant_index": variant.index,
                "query_artist": variant.artist,
                "successful_query": None,
                "candidates": [],
                "candidate_video_ids": [],
                "attempts": attempts,
                "total_provider_requests": len(attempts),
                "elapsed_seconds": ended - run_started,
                "error": error,
            }
        ended = clock()
        attempts.append(
            _attempt(variant, started=started, ended=ended, outcome=outcome)
        )
        raw_candidates = outcome["candidates"]
        if raw_candidates:
            candidates = _with_provenance(raw_candidates, variant)
            result = PRIMARY_SUCCESS if variant.index == 0 else FALLBACK_SUCCESS
            return {
                "track": track.to_dict(),
                "query_plan": plan.to_dict(),
                "outcome": result,
                "discovery_mode": variant.discovery_mode,
                "query_variant_index": variant.index,
                "query_artist": variant.artist,
                "successful_query": variant.query,
                "candidates": candidates,
                "candidate_video_ids": [
                    candidate.get("youtube_video_id") for candidate in candidates
                ],
                "attempts": attempts,
                "total_provider_requests": len(attempts),
                "elapsed_seconds": ended - run_started,
                "error": None,
            }

    ended = clock()
    return {
        "track": track.to_dict(),
        "query_plan": plan.to_dict(),
        "outcome": ALL_QUERY_VARIANTS_EMPTY,
        "discovery_mode": None,
        "query_variant_index": None,
        "query_artist": None,
        "successful_query": None,
        "candidates": [],
        "candidate_video_ids": [],
        "attempts": attempts,
        "total_provider_requests": len(attempts),
        "elapsed_seconds": ended - run_started,
        "error": None,
    }
