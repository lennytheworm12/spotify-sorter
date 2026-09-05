# Stage 5C.2A — Persistent Research Audio

## Verdict

`PERSISTENT_100_RESEARCH_AUDIO_CACHE_READY`

The active input is the versioned amended Stage 5C.2 V2 corpus, not the historical 98-source execution. All acquisition consumes exact frozen YouTube IDs; discovery and selection call counts are zero.

## Corpus retention

- Expected / retained: 100 / 100
- Local retained bytes: 321231604
- Last-run retention cache hits: 100
- Last-run acquisition failures: 0
- Scratch artifacts after audit: 0
- Retained media tracked by Git: 0

Full compressed source audio and per-source provenance remain under the Git-ignored `.research_audio/` cache. Temporary downloads, partials, and decode products are not retained.

## Acquisition behavior

- Live attempts: 100
- Retry attempts: 0
- Minimum start spacing: 20.00011199398432 seconds
- Required minimum: 20 seconds
- Spacing audit: PASS
- HTTP 429 / 5xx: 0 / 0

## Representation reuse

Existing centered30_v1 CLAP and MuQ identities are linked in each provenance record. CLAP reruns: 0; MuQ reruns: 0.

## Local review playback

The unchanged amended queue contains 100 queries, 500 directional relationships, and 359 unique unordered pairs. The reviewer resolves Spotify IDs through the local index and supports ordinary responses plus HTTP 206 beginning, middle, near-end, and repeated seeks. Browser validation status: `PASS`.

From `ml/audio_similarity`, run:

```bash
.venv/bin/python -m audio_similarity.cli.stage5c2_review_server
```

The default is local retained-audio playback. `--playback-source youtube` remains an explicit compatibility mode.

## Historical integrity

The original 98-track Stage 5C.2 report and amended V2 evidence are hash-guarded and were not rewritten. Existing human labels are preserved by the canonical unordered pair identifier.
