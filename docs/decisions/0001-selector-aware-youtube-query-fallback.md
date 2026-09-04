# 0001: Continue YouTube Query Fallback Until Selection Succeeds

## Status

Accepted for the next fresh benchmark; not production-active and not retroactive.

## Date

2026-09-04

## Context

Stage 5C.2 used a discovery-first stopping rule: any non-empty YouTube Top-3 candidate pool stopped query fallback. The unchanged Stage 5B.3 selector then abstained when every candidate was an unrequested live/performance result or differed from Spotify duration by more than 20 seconds.

Two representative tracks exposed the gap:

- `GANADARA (Feat. IU)` returned three candidates, but all three were vetoed during the frozen run. A duration-aligned official audio existed.
- `Love Always Leaves Me` returned three candidates for the multi-artist and individual-artist queries, but every pool was unselectable. A title-only search exposed the duration-exact Topic upload.

The search layer had therefore succeeded syntactically without producing a usable downstream result.

## Decision

Treat a query as successful only when the unchanged Stage 5B.3 selector accepts a candidate from that query's native Top-3.

Run these mechanically generated queries sequentially:

1. sanitized raw Spotify title plus the first three distinct credited artists;
2. the same title plus artist 1, artist 2, and artist 3 individually;
3. the same sanitized title alone.

Stop at the first query whose native Top-3 contains a selector-eligible candidate. Do not merge query pools, rerank candidates, alter selector vetoes, or retry provider errors as if they were valid empty/unselectable results.

## Alternatives Considered

### Stop at the first non-empty pool

Rejected because it strands tracks when all returned candidates are vetoed, even if a later deterministic query exposes an eligible source.

### Trigger only single-artist decomposition after zero results

Rejected because `Love Always Leaves Me` demonstrated non-empty but unusable pools for the primary and individual-artist forms.

### Add semantic title or artist heuristics

Rejected for this repair. The fallback remains bounded and song-agnostic.

### Merge candidates from every query

Rejected because it discards native YouTube ranking context and creates a cross-query scoring problem.

## Consequences

- Common successful searches retain their one-request path.
- Manual-tail recovery can cost up to five metadata-only searches for a three-artist track.
- Title-only search has less identity context and may increase false-positive risk for ambiguous titles; a fresh held-out benchmark is required before activation.
- Frozen Stage 5C.2 artifacts and metrics remain historical evidence and are not rewritten.
- Manual exact-URL override remains the final unresolved tail.
