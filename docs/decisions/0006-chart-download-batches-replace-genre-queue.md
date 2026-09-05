# 0006: Chart Download Batches Replace the Genre-Search Queue

## Status

Accepted for local research. Supersedes ADR 0004's active queue/CLI routing,
not its historical execution evidence. No downloads launched during setup.

## Date

2026-09-05

## Context

The owner explicitly requested download batches for the chart-based popular-song
finder, replacing the older Spotify genre-search batches. The current chart
matching snapshot contains 534 matched recordings; the broader catalog is still
incomplete. Pending and ambiguous matches must not enter a runnable queue.

## Decision

Freeze the 534-recording matched subset as a versioned cohort. Hash-order Spotify
IDs with `chart-popular-download-order-v1`, then partition into 500 and 34 tracks.
Pin the exact matching snapshot, cohort, and batch contents. Later metadata
matches do not alter this cohort; expansion needs another versioned freeze.

The familiar `audio_similarity.cli.stage5d0a` command now delegates to
`audio_similarity.chart_download_batches`. It no longer collects or dispatches
the genre-search catalog. The old CLI remains reproducible from Git history;
old manifests, queue state, retained sources, and embeddings are preserved.

Reuse the existing SeedProcessor and ProviderGovernor through a single-batch
worker entry point. Each batch has its own selection/checkpoint state, but chart
batches share provider pacing, cooldown, and circuit state. Carry forward existing
genre-worker pacing deadlines and safety counters once; refuse to bypass an old
open circuit. One retained-media lock enforces serial execution across workers.

An explicit command runs one batch only. No automatic Batch 0002 start. A valid
existing source/representation is reused; other tracks run the current frozen
selector-aware discovery, exact-ID full source retention, and centered30_v1
materialization. No changes to encoders, weights, segments, query behavior, or
selector vetoes. Failed/manual-tail tracks remain in the denominator.

## Consequences

These are chart-supported metadata matches, not human-validated YouTube sources.
The selector still determines whether acquisition is allowed. The 534-track
subset is not comprehensive twenty-year/style coverage. Provider metrics span
all chart batches, while completion state remains per batch. Both batches remain
unstarted at setup completion; the owner starts the overnight run explicitly.

See `ml/audio_similarity/reports/chart_download_batches_v1/README.md` for commands.
