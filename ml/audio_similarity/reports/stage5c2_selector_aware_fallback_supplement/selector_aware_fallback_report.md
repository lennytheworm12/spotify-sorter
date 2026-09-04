# Stage 5C.2 Selector-Aware Query Fallback Supplement

Verdict: `SELECTOR_AWARE_FALLBACK_TARGETED_VALIDATED`

This post-benchmark supplement leaves the frozen Stage 5C.2 manifest, discovery, selector decisions, selected sources, and metrics unchanged.

## Decision

A discovery query is successful only when the unchanged Stage 5B.3 selector accepts a candidate. A non-empty but fully vetoed Top-3 therefore advances to the next single-artist query and finally one sanitized title-only query. Query pools remain separate and native rank remains authoritative within each pool.

## Targeted evidence

### GANADARA (Feat. IU)

- Historical result: `MATCH_UNCERTAIN`.
- Current result: `FALLBACK_SELECTED` via `GANADARA (Feat. IU) Jay Park`.
- Selected video: `v224EdAkZr8` at native rank 3.
- Owner-supplied reference recovered: `True`.
- Provider requests: 2.

### Love Always Leaves Me

- Historical result: `MATCH_UNCERTAIN`.
- Current result: `FALLBACK_SELECTED` via `Love Always Leaves Me`.
- Selected video: `i4YFngxyJ0k` at native rank 2.
- Owner-supplied reference recovered: `True`.
- Provider requests: 4.

## Boundary

This validates the repair on the two observed manual-tail cases only. It does not retroactively change Stage 5C.2 and does not establish representative title-only precision. The contract requires a fresh held-out benchmark before production activation.
