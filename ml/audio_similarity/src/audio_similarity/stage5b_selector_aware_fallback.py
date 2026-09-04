"""Selector-aware, bounded query fallback for natural YouTube discovery.

This contract is additive. It does not change the frozen Stage 5B.4C
zero-result contract or the Stage 5B.3 selector. A query succeeds only when
that unchanged selector accepts a candidate from its native Top-3 pool.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from .stage5b1a2_ytdlp import YtDlpSearchError
from .stage5b1a_models import SpotifyTrack, Stage5B1AValidationError
from .stage5b3_minimal_selector import AUTO_SELECT, select_native_rank
from .stage5b4c_artist_decomposition import (
    PRIMARY_MULTI_ARTIST,
    QuerySearchProvider,
    build_artist_decomposition_plan,
)


QUERY_CONTRACT_ID = (
    "NATURAL_TITLE_FIRST3_THEN_SINGLE_ARTIST_THEN_TITLE_ONLY_ON_UNSELECTABLE_V2"
)
SINGLE_ARTIST_UNSELECTABLE_FALLBACK = "SINGLE_ARTIST_UNSELECTABLE_FALLBACK"
TITLE_ONLY_UNSELECTABLE_FALLBACK = "TITLE_ONLY_UNSELECTABLE_FALLBACK"
PRIMARY_SELECTED = "PRIMARY_SELECTED"
FALLBACK_SELECTED = "FALLBACK_SELECTED"
ALL_QUERY_VARIANTS_UNSELECTABLE = "ALL_QUERY_VARIANTS_UNSELECTABLE"
PROVIDER_ERROR = "PROVIDER_ERROR"
NO_CANDIDATES = "NO_CANDIDATES"
TITLE_ONLY_VARIANT_INDEX = 4


@dataclass(frozen=True)
class SelectionAwareQueryVariant:
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


def build_selection_aware_query_plan(
    track: SpotifyTrack,
) -> tuple[SelectionAwareQueryVariant, ...]:
    """Build Q0, unique single-artist queries, then one title-only query."""

    original = build_artist_decomposition_plan(track)
    variants = [
        SelectionAwareQueryVariant(
            index=0,
            query=original.primary.query,
            artist=None,
            discovery_mode=PRIMARY_MULTI_ARTIST,
        )
    ]
    seen = {original.primary.query}
    for fallback in original.fallbacks:
        if fallback.query in seen:
            continue
        seen.add(fallback.query)
        variants.append(
            SelectionAwareQueryVariant(
                index=fallback.index,
                query=fallback.query,
                artist=fallback.artist,
                discovery_mode=SINGLE_ARTIST_UNSELECTABLE_FALLBACK,
            )
        )
    if original.title not in seen:
        variants.append(
            SelectionAwareQueryVariant(
                index=TITLE_ONLY_VARIANT_INDEX,
                query=original.title,
                artist=None,
                discovery_mode=TITLE_ONLY_UNSELECTABLE_FALLBACK,
            )
        )
    return tuple(variants)


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


def _normalize_candidates(
    candidates: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    variant: SelectionAwareQueryVariant,
) -> list[dict[str, Any]]:
    normalized = []
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
    expected_ranks = list(range(1, len(normalized) + 1))
    if [candidate.get("rank") for candidate in normalized] != expected_ranks:
        raise Stage5B1AValidationError("native YouTube candidate order changed")
    return normalized


def discover_and_select_with_fallback(
    track: SpotifyTrack,
    provider: QuerySearchProvider,
    *,
    limit: int = 3,
    selector: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]] = (
        select_native_rank
    ),
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Search sequential variants until the selector accepts one native Top-3."""

    if limit != 3:
        raise Stage5B1AValidationError("selector-aware fallback uses a Top-3 limit")
    variants = build_selection_aware_query_plan(track)
    target = track.to_dict()
    started_run = clock()
    attempts: list[dict[str, Any]] = []

    for variant in variants:
        started = clock()
        try:
            outcome = _outcome_dict(
                provider.discover_query(track, variant.query, limit=limit)
            )
        except YtDlpSearchError as exc:
            ended = clock()
            attempts.append(
                {
                    **variant.to_dict(),
                    "result_count": 0,
                    "candidate_video_ids": [],
                    "candidates": [],
                    "selector_decision": None,
                    "selector_reason": None,
                    "warnings": list(exc.warnings),
                    "error": exc.to_dict(),
                    "elapsed_seconds": ended - started,
                }
            )
            return _result(
                track,
                variants,
                attempts,
                outcome=PROVIDER_ERROR,
                ended=ended,
                started=started_run,
                error=exc.to_dict(),
            )

        ended = clock()
        candidates = _normalize_candidates(outcome["candidates"], variant)
        decision = selector(target, candidates) if candidates else None
        attempts.append(
            {
                **variant.to_dict(),
                "result_count": len(candidates),
                "candidate_video_ids": [
                    candidate.get("youtube_video_id") for candidate in candidates
                ],
                "candidates": candidates,
                "selector_decision": (
                    decision["decision"] if decision else NO_CANDIDATES
                ),
                "selector_reason": decision.get("selection_reason") if decision else None,
                "selector_evaluations": (
                    decision.get("candidate_evaluations", []) if decision else []
                ),
                "warnings": list(outcome.get("warnings", [])),
                "error": None,
                "elapsed_seconds": ended - started,
            }
        )
        if decision and decision["decision"] == AUTO_SELECT:
            return _result(
                track,
                variants,
                attempts,
                outcome=PRIMARY_SELECTED if variant.index == 0 else FALLBACK_SELECTED,
                ended=ended,
                started=started_run,
                variant=variant,
                candidates=candidates,
                selector_decision=decision,
            )

    ended = clock()
    return _result(
        track,
        variants,
        attempts,
        outcome=ALL_QUERY_VARIANTS_UNSELECTABLE,
        ended=ended,
        started=started_run,
    )


def _result(
    track: SpotifyTrack,
    variants: tuple[SelectionAwareQueryVariant, ...],
    attempts: list[dict[str, Any]],
    *,
    outcome: str,
    ended: float,
    started: float,
    variant: SelectionAwareQueryVariant | None = None,
    candidates: list[dict[str, Any]] | None = None,
    selector_decision: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected = selector_decision or {}
    return {
        "schema_version": "selector-aware-query-fallback-result-v1",
        "query_contract_id": QUERY_CONTRACT_ID,
        "track": track.to_dict(),
        "query_plan": [item.to_dict() for item in variants],
        "outcome": outcome,
        "fallback_triggered": len(attempts) > 1,
        "successful_query": variant.query if variant else None,
        "query_variant_index": variant.index if variant else None,
        "query_artist": variant.artist if variant else None,
        "discovery_mode": variant.discovery_mode if variant else None,
        "candidates": candidates or [],
        "selected_candidate": selected.get("selected_candidate"),
        "selected_video_id": selected.get("selected_video_id"),
        "selected_rank": selected.get("selected_rank"),
        "selector_decision": selector_decision,
        "attempts": attempts,
        "total_provider_requests": len(attempts),
        "elapsed_seconds": ended - started,
        "error": error,
        "scope_guards": {
            "selector_id": "STAGE5B3_MINIMAL_YOUTUBE_SELECTOR_V1",
            "candidate_pool_merges": 0,
            "candidate_reranking": False,
            "maximum_provider_requests": len(variants),
            "title_only_is_last": bool(
                variants
                and variants[-1].discovery_mode
                == TITLE_ONLY_UNSELECTABLE_FALLBACK
            ),
        },
    }
