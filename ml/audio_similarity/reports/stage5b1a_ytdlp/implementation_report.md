# Stage 5B.1A2 — yt-dlp YouTube search feasibility

Status: **`DISCOVERY_COMPLETE_AWAITING_HUMAN_REVIEW`**

The frozen 25-track metadata-only discovery run is complete. No human labels were fabricated, no Recall@K values were calculated, and no PASS/CONDITIONAL/FAIL verdict is claimed.

## Purpose and provider role

This bounded experiment asks whether yt-dlp YouTube search can place the intended recording in the first five results often enough to become the primary Stage 5B cold-start discovery mechanism. Firecrawl remains preserved as the historical Stage 5B.1A provider experiment; this yt-dlp experiment is the candidate active discovery provider.

This slice stops at search metadata and human-review preparation. It does not download media, score or select a final candidate, call the YouTube Data API, invoke Playwright, create a queue/worker, call Spotify, run CLAP/MuQ, or integrate Stage 5A.

## Frozen inputs and gate

- Manifest: `reports/stage5b1a/frozen_tracks.json`
- Manifest SHA-256: `f3592bb8c8dea689959a22da222d8b7ce4911c1804392acb501cffe768700c57`
- Track count/order: the exact existing 25 rows, unchanged
- Configuration: `configs/stage5b1a2_ytdlp.json`
- Configuration SHA-256: `476dfa9eaa3daec9961af627215fcd08b488463675e1563b2a350136ab2a752c`
- Query variant: `quoted-primary-artist-title-official-v1`
- Query template: `"{primary_artist}" "{normalized_title}" official`
- Featured-artist normalization: unchanged from Firecrawl (`feat.`, `ft.`, and `featuring` presentation clauses only)
- Gate: PASS at Recall@5 >= 90%; CONDITIONAL at >= 80% and < 90%; FAIL below 80%

Remix, live, remaster/mix, Taylor's Version, duration, and other target-version evidence remains in the query. No song-specific tuning or result-driven query revision occurred.

## yt-dlp implementation and search configuration

- Dependency/version: pinned `yt-dlp==2026.8.19`
- API: Python `YoutubeDL.extract_info(search_expression, download=False)`
- Search expression: `ytsearch5:<frozen query>`
- Candidate limit: first five yt-dlp search results, then exact video-ID deduplication without reordering
- Flat extraction: `extract_flat=in_playlist`
- Disk cache: disabled
- User CLI configuration: not loaded by the embedded Python API; `ignoreconfig=true` is also recorded
- Internal yt-dlp retries: 0
- Experiment attempts: at most 2 per track, with 2-second bounded backoff
- Socket timeout: 30 seconds
- Concurrency: none; searches are sequential
- Inter-track pacing: fixed 1.0 second between the 25 track searches

The implementation follows yt-dlp's official [embedding guidance](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp), including `download=False` and sanitizing the returned info dictionary. The pinned release is the official [2026.08.19 stable release](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19).

## Metadata-only guarantee

Every request records all of these safeguards:

```text
download = false
simulate = true
skip_download = true
extract_flat = in_playlist
cachedir = false
```

The validated run artifact records:

```text
audio downloads = 0
video downloads = 0
CLAP calls = 0
MuQ calls = 0
Stage 5A materializations = 0
```

No media or yt-dlp cache artifact was created or committed.

## Candidate normalization

Only validated 11-character YouTube video IDs from YouTube extractor/search entries enter the candidate list. Search/container/non-video entries remain distinguishable and cannot become candidates. Candidates are canonicalized to `https://www.youtube.com/watch?v=<id>`, deduplicated only by exact video ID, and retain original yt-dlp order. Distinct IDs are never merged.

Each candidate preserves, when supplied:

```text
rank and original provider rank
video ID and canonical URL
title
uploader
channel
duration_seconds
description
availability
live_status
provider = yt_dlp
exact frozen query
bounded raw source metadata
```

## Real run

- Run interval: `2026-09-01T07:12:09+00:00` to `2026-09-01T07:12:55+00:00`
- Elapsed wall time: `45.8462` seconds
- Tracks attempted: 25
- Successful searches: 25
- Search failures: 0
- Attempts: every search succeeded on its first attempt
- Tracks with candidates: 25
- Tracks with zero candidates: 0
- Candidate distribution: all 25 tracks have exactly 5 deduplicated candidates
- Total deduplicated candidate video IDs: 125
- Captured warning count: 0

No throttling, HTTP 429, sign-in requirement, player-extraction change, bot check, or temporary block warning/error was observed in this run.

Metadata populated across the 125 candidates:

- Title/video ID/URL: 125
- Uploader: 125
- Channel: 125
- Duration: 125
- Description: 112
- Availability: 0 (not surfaced by this flat-search response)
- Live status: 0 (not surfaced by this flat-search response)

## Human review and metrics

- Review template: `reports/stage5b1a_ytdlp/review_template.csv`
- Candidate review: `reports/stage5b1a_ytdlp/ytdlp_review.csv`
- Completed labels: 0 of 25
- Allowed labels: `1`, `2`, `3`, `4`, `5`, `NOT_IN_TOP_5`, `UNCERTAIN`
- Recall@1/@3/@5: pending human review
- Feasibility verdict: `PENDING_HUMAN_REVIEW`
- Metrics artifact: intentionally absent until review labels are completed

The metric implementation reuses the Firecrawl denominator semantics: confirmed ranks plus `NOT_IN_TOP_5` are evaluable; `UNCERTAIN` and unreviewed rows are excluded. Any incomplete review keeps the verdict pending.

## Objective Firecrawl comparison

Artifact: `reports/stage5b1a_ytdlp/provider_comparison.json`

| Coverage measure | Firecrawl | yt-dlp |
|---|---:|---:|
| Tracks attempted | 25 | 25 |
| Request/search failures | 0 | 0 |
| Tracks with candidates | 21 | 25 |
| Tracks with zero candidates | 4 | 0 |
| Total deduplicated candidates | 76 | 125 |
| Mean candidates per track | 3.04 | 5.00 |

yt-dlp also supplied uploader/channel/duration for every candidate, fields Firecrawl Search did not supply. This is an operational coverage/metadata comparison only. Both reviews remain unlabeled, so provider correctness and Recall@1/@3/@5 are not compared.

## Artifacts and hashes

- Discovery results: `reports/stage5b1a_ytdlp/ytdlp_discovery_results.json` — SHA-256 `63344ac9228c1a2d22846e4cc2621fe717c5f619a21736a00bccf8476463c605`
- Human review: `reports/stage5b1a_ytdlp/ytdlp_review.csv` — SHA-256 `af6208ac1dd206434ff2f2b4ccdefd96f4ef65d0782e03004d80b77425958071`
- Provider comparison: `reports/stage5b1a_ytdlp/provider_comparison.json` — SHA-256 `3d3ed0863f64b1266b4f8254f2b7ae7ac187f161c067f6b85a07ceffe8bc7ee2`
- Run status: `reports/stage5b1a_ytdlp/run_status.json` — SHA-256 `393f31f324fbc7220441c4d19553aa857cb94c524184b9e0b7071ca396179219`

## Tests

- Focused Stage 5B.1A2: 17 passed, 0 failed
- Combined Stage 5B.1A2 + existing Stage 5B.1A provider tests: 67 passed, 0 failed
- Relevant Stage 5A regressions: 14 passed, 0 failed
- Full non-heavy `ml/audio_similarity` suite: 528 passed, 12 heavy tests deselected, 0 failed

All normal tests mock the yt-dlp boundary and require no YouTube access.

## Known limitations

- Correctness remains unknown until humans label the candidates; coverage is not Recall.
- YouTube search results and extraction behavior can vary over time, geography, and IP reputation despite frozen inputs.
- Flat search deliberately avoids per-video extraction, so availability/live status and some descriptions are absent.
- This run used no cookies, proxy rotation, browser impersonation, account logic, or Playwright.
- A successful 25-track run does not prove long-running cold-start reliability; the captured pacing/warning behavior is evidence for later worker design, not that worker itself.
