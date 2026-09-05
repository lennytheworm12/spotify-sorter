# Chart-anchored cold-start metadata runner

Implemented commands (run from `ml/audio_similarity`):

```sh
.venv/bin/python -m audio_similarity.chart_catalog collect
.venv/bin/python -m audio_similarity.chart_catalog match --max-requests 50
.venv/bin/python -m audio_similarity.chart_catalog report
```

`collect` attempts the frozen 60-page source plan, preserving successful raw
snapshots locally. The current collected result is 4,800 validated appearances
from 48 pages. Twelve unavailable/invalid pages are recorded, not filled with
invented entries. Do not rerun collection to silently revise this frozen input;
an expanded source plan needs a new version.

`match` reuses exact-title/credited-artist matches from the existing Spotify
metadata pool, then performs at most the requested number of new Spotify Top-10
searches. Default 50, maximum 500 per explicit invocation. Repeated invocations
resume remaining work. A song's successful response is checkpointed before
matching, including empty searches. Provider exceptions stop the run; they are
not cached as empty results. Spotify's existing request limiter and persistent
429 cooldown are reused. Raw responses and credentials are never printed.

`report` makes no network requests. It reconstructs matching and recording
deduplication from existing metadata and successful response checkpoints. Reports
are content-addressed; earlier matching reports are never overwritten. A local
worker lock prevents simultaneous metadata jobs. The mutable summary is in
`.research_audio/chart_catalog_v1/status.json`.

## Identity and scope

Typography-normalized title/artist pairs only consolidate literal chart entries.
They do not establish recording identity. Spotify matching is deliberately
conservative: full title and joined artist credits must match. Different titles,
translations, featured-credit presentation, reordered artists, and ambiguous
recordings can remain unmatched; this is not a claim that Spotify lacks the song.
The existing complete-link recording comparator consolidates matched editions
without merging duration chains or qualified versions. All chart appearances
are retained as provenance. `MATCHED_METADATA` is not human audio validation.

Existing Spotify metadata reuse does not imply retained audio exists. Source
and representation cache identity validation remains the acquisition runner's
responsibility in a separately authorized future run.

No audio, YouTube discovery, selector calls, encoder inference, or batch execution
is implemented here. Every output recording has `acquisition_eligible: false`.
The old genre-search catalog, acquired sources, and owner ratings are untouched.

## Coverage limitations

Current valid observations span 2008–2025, concentrated in Australian, Japanese,
and US mainstream charts. This is not yet comprehensive 2006–2026 coverage.
2006–2007, early US coverage, dated 2026 charts, Korean domestic charts, and
broader regional/style sources remain gaps. Artist counts and market/year
counts are diagnostics, not evidence that genre coverage is adequate.

The 2006–2008 Australian pages displayed a different year; early US/Japan URLs
returned 404, and two Japanese pages supplied only 50 ranks against this adapter's
100-rank contract. These require source-specific verification, not relaxing
validation just to increase the count.

## Executed matching check

4,800 appearances consolidate to 3,429 literal song candidates. Existing cached
Spotify metadata yielded 511 matches. Fifty new serial Spotify searches yielded
23 further matches, 24 no-exact-match outcomes, and three ambiguous recordings.
Total matched recordings: 534; pending song queries: 2,868.

The live snapshot is
`matching_16f0ff2b91ea073f73ef099769b6f8b8104c15a4c8225b10d793ee32517c4266.json`.
The preceding `matching_cbf63f4f71ca94d5d0b62c6dff8ab80ea5a7782f04d272a084264849f02b45b5.json`
records the offline-only baseline. Neither is a final cold-start library.

## Verification and five-axis review

- Correctness: mocked provider tests cover exact matching, version/artist
  rejection, ambiguity, complete-link dedupe, request bounds, resume, and local
  metadata reuse; live source collection rejects malformed periods/ranks.
- Readability: chart parsing, Spotify matching, and the existing frozen resolver
  remain separate. The CLI exposes only metadata commands.
- Architecture: reuse existing Spotify credentials/pacing and recording comparator;
  no changes to Stage 5 query, selector, retention, or representation code.
- Security: parameter-encoded requests through the existing official Spotify
  helper; raw checkpoints ignored; no media path. Chart HTTP 403/429 persist a
  stop requiring inspection rather than automatic retries.
- Performance: serial bounded requests, resumable checkpoints, local metadata
  reuse, and no encoder/model loading. Matching prioritizes precision, not recall.

The non-heavy suite passed 1,152 tests (12 heavy tests deselected). Focused tests
are rerun after subsequent small hardening changes. No production activation.
