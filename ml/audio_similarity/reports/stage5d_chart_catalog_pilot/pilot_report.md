# Chart-source feasibility pilot

## Result

PARTIAL_SOURCE_FEASIBILITY — 600 validated chart appearances from six pages.
These are not deduplicated recordings, Spotify matches, or an acquisition batch.

The authoritative pilot output is `chart_pilot_verified.json`. The earlier
`chart_pilot.json` is an initial extraction diagnostic, superseded for consumption
because it did not validate the displayed period. Do not use its 700-entry count.

Verified inputs: Australian annual singles charts for 2015 and 2025, Japanese
annual Hot 100 for 2015 and 2025, and US annual Hot 100 for 2015 and 2025 as
published by Billboard Japan. The US chart is not Japanese-market evidence.

Sources include [ARIA](https://www.aria.com.au/charts/2025/singles-chart),
[Japan Hot 100](https://www.billboard-japan.com/charts/detail?a=hot100_year&year=2025),
and [US Hot 100](https://www.billboard-japan.com/charts/detail?a=uhot100_year&year=2025).
Each accepted source has its own URL, timestamp, and HTML SHA-256 in the JSON.
Raw snapshots are local and Git-ignored.

## Quality gate

The Australian 2006 URL returned HTML displaying 2005. It is rejected rather
than assigned the requested year. The parser also requires contiguous ranks
1–100, nonempty titles/artists, and no unexpected redirect. A successful HTTP
response or a requested year somewhere in page navigation is insufficient.

## Cold-start direction

Target popular music across roughly 2006–2026, using chart evidence plus an
explicit coverage audit, not mandatory year/genre quotas. Collect recognized songs
before considering selective artist-catalog expansion. Recording identity must
be resolved separately from chart display text. Repeat appearances preserve
evidence but must not inflate the final unique-source count.

Remaining work: historical coverage near 2006, Korean and broader regional/style
sources, partial-2026 evidence, Spotify recording matching, recording deduplication,
artist concentration and coverage analysis, and a frozen replacement catalog.
The pilot does not establish licensing/access feasibility for every future source.

## Operational boundary

No new media downloads, YouTube calls, or inference. Existing Stage 5 evidence
and owner review labels are untouched. No new batch is started.

Run from `ml/audio_similarity`:

```sh
.venv/bin/python -m audio_similarity.chart_seed_pilot
.venv/bin/python -m pytest tests/test_chart_seed_pilot.py -q
```

Cached snapshots allow offline replay; changed output cannot replace the frozen
verified artifact. A later expanded experiment needs a new versioned output.
