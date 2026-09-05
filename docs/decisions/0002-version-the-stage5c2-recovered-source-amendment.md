# 0002: Version the Stage 5C.2 Recovered-Source Amendment

## Status

Accepted for human similarity review; the original Stage 5C.2 execution remains frozen.

## Date

2026-09-04

## Context

The original Stage 5C.2 representative manifest contained 100 tracks, but the frozen zero-result-only query contract left `GANADARA (Feat. IU)` and `Love Always Leaves Me` in the manual tail. The run therefore materialized and presented 98 tracks.

The selector-aware query supplement later recovered both owner-confirmed sources with the unchanged Stage 5B.3 selector:

- `GANADARA (Feat. IU)` → YouTube video `v224EdAkZr8`;
- `Love Always Leaves Me` → YouTube video `i4YFngxyJ0k`.

The owner requested that successful query-optimization recoveries be included in the frozen set.

## Decision

Create a versioned amended source set, `STAGE5C2_REPRESENTATIVE_100_SELECTOR_AWARE_AMENDMENT_V2`, rather than modifying the original Stage 5C.2 artifacts.

The amendment:

1. reuses the original 100-track Spotify manifest and the 98 original representations byte-for-byte;
2. freezes the two recovered exact YouTube IDs in a separate two-track acquisition manifest;
3. materializes only those two sources using the frozen Stage 5A CLAP/MuQ contract;
4. combines the 98 base and two supplemental representations for derived 100-track similarity artifacts;
5. makes the amended 100-track queue the default Stage 5C.2 review-server dataset;
6. migrates any existing human labels by canonical unordered pair ID without overwriting conflicting labels.

The original report at `reports/stage5c2_representative_100` remains the immutable execution record. The amended report at `reports/stage5c2_representative_100_amended_v2` is the review dataset.

## Consequences

- Historical 98-track metrics remain reproducible and unchanged.
- The owner can review all 100 originally sampled tracks together.
- The two supplemental downloads and representations have their own rate-limit, cleanup, cache, and hash provenance.
- The amended review queue is derived evidence, not a claim that the original run selected 100 tracks under its then-frozen query contract.
- The selector-aware query contract still requires a fresh representative benchmark before production activation.
