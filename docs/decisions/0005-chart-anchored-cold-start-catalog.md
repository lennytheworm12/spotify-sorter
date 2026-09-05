# 0005: Chart-Anchored Cold-Start Catalog

## Status

Accepted direction; resumable metadata collection/matching runner implemented.
Final source coverage, recording allocation, catalog size, and acquisition
manifest are not frozen.

## Date

2026-09-05

## Context

The owner wants meaningful cold-start library coverage of popular music over
roughly the last twenty years (2006–2026), not equal annual genre quotas.
Spotify genre-search relevance did not reliably establish popularity or style
membership in the Stage 5D.0A V1 seed set. V1 remains historical evidence;
this decision does not rewrite ADR 0004's executed catalog or Batch 0001.

## Decision

Anchor the replacement candidate catalog in identifiable song-chart appearances.
Preserve source URL, chart period, territory, rank, retrieval timestamp, and
source hash. Treat chart period as popularity evidence, not release year, and
territory as a listening market, not artist nationality or language.

Use the 2006–2026 window for popularity evidence; older recordings that were
popular during that window need not be automatically excluded. Treat 2026 as
partial, using dated weekly/current evidence rather than a fictional annual chart.
Annual archives are a collection convenience, not a requirement for equal quotas.

Resolve chart entries to Spotify recording identities before final deduplication.
Do not equate identical display names with proven recording identity. Keep
version distinctions and all chart provenance when consolidating appearances.
Do not compare raw ranks from different markets as a universal popularity score.

Audit coverage across eras, markets, styles, and artist concentration. Broad
mainstream charts alone cannot establish adequate coverage of R&B, electronic,
rock, Latin, country, Korean/Japanese music, or other regional scenes. Supplement
identified gaps with verified relevant chart sources before freezing a full
catalog. Exact source roster and allocation remain pending feasibility work.

Prefer adding missing musical coverage over acquiring a popular artist's complete
discography. Reuse valid existing sources and representations by identity. Do not
discard the original acquired corpus merely because its sampling recipe changes.

## Alternatives Considered

- Spotify genre-search rank as popularity: insufficient evidence for this goal.
- Every song from top artists: risks album-track volume and artist concentration
  without demonstrating individual song popularity or additional coverage.
- Equal year/bucket quotas: not required by the owner and can force weak entries.
- Current charts alone: cannot establish twenty-year coverage.

## Consequences

The pilot is metadata-only, with no Spotify audio, YouTube discovery, acquisition,
encoder inference, or Batch 0002 activation. Its chart entries are not eligible
for acquisition. Collection rejects incomplete rank sequences, missing identity
fields, unexpected redirects, and displayed-period mismatches.

The current pilot validates six annual chart pages (600 appearances), not 600
unique recordings or a representative library. Australian 2006 HTML is quarantined
because its displayed year is 2005 despite the requested URL. Korean and broader
regional coverage, early-window coverage, current-year evidence, Spotify matching,
and recording deduplication remain unvalidated.

## Implementation follow-up

The separate `chart_catalog` command expands collection to 60 candidate archive
pages. Forty-eight validated pages yielded 4,800 appearances and 3,429 literal
song candidates. Existing Spotify metadata supplied 511 conservative matches;
50 additional searches supplied 23 more, with 24 unmatched and three ambiguous.
These 534 metadata matches are not audio-validated sources or a frozen final
acquisition catalog. The remaining 2,868 queries are checkpoint-resumable work.
See `ml/audio_similarity/reports/stage5d_chart_catalog_v1/README.md` for commands,
limitations, source failures, and test evidence. This supplements rather than
replaces the initial pilot snapshots.
