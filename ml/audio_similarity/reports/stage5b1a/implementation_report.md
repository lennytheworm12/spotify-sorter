# Stage 5B.1A — Firecrawl YouTube discovery feasibility

Status: **`DISCOVERY_COMPLETE_AWAITING_HUMAN_REVIEW`**

The frozen 25-track experiment ran through Firecrawl's keyless REST mode with `FIRECRAWL_API_KEY` explicitly absent. Candidate discovery is complete, no human labels were fabricated, and the feasibility verdict remains pending human review.

## Purpose and boundary

This slice answers one engineering question:

> Given Spotify-style track metadata, can Firecrawl Search place the intended YouTube recording somewhere in a small candidate set often enough to justify Firecrawl as the discovery layer?

The implementation follows the approved Obsidian design `Projects/Spotify Sorter/Spotify Audio Similarity Stage 5B — Popular Catalog Cold Start and Acquisition Worker Design.md` and stops at discovery. It does not call the YouTube Data API, use yt-dlp, download media, run CLAP/MuQ, integrate Stage 5A, access Spotify, or implement later Stage 5B matching/queue/acquisition work.

## Frozen manifest

- Artifact: `reports/stage5b1a/frozen_tracks.json`
- Schema: `stage5b1a-frozen-track-manifest-v1`
- Track count: 25
- SHA-256: `f3592bb8c8dea689959a22da222d8b7ce4911c1804392acb501cffe768700c57`
- Release range: 2001–2024
- Freeze declaration: `frozen_before_live_discovery=true`

The set is an engineering smoke set, not a statistical population sample. Every row records why it exists. Across the set, cases cover straightforward and older hits; multiple/featured artists; punctuation, symbols, diacritics, and long parenthetical titles; a named 2019 mix; explicit/clean ambiguity; common titles; electronic, hip-hop, rock/alternative, R&B, Latin, country, and K-pop/global recordings; official-video duration differences; many covers/remixes/unofficial uploads; an actual remix; and an actual live recording.

The normalized `SpotifyTrack` model is provider-independent and supports:

```text
stable_track_id
spotify_track_id (optional)
title
artists[]
album (optional)
duration_ms (optional)
release_year (optional)
isrc (optional)
```

## Frozen discovery configuration

- Config: `configs/stage5b1a_firecrawl.json`
- Config SHA-256: `e68dfd6ac2a20c6f6d6ee4c2ca6a9f506dc80ddfc9d1264997ee4b778ed57d1a`
- Provider version: `firecrawl-search-v2-youtube-v1`
- Endpoint: `POST https://api.firecrawl.dev/v2/search`
- Source: Firecrawl `web` only
- Included domains: `youtube.com`, `youtu.be`
- Raw provider result limit: 10
- Deduplicated review candidate limit: 5
- Country: `US`
- Highlights: disabled, retaining provider descriptions/snippets
- Concurrency: sequential
- Timeout: 30 seconds
- Retry attempts: at most 3 with bounded exponential backoff
- Authentication: `FIRECRAWL_API_KEY` when present; otherwise Firecrawl's official rate-limited keyless REST mode
- Secrets: never persisted

The request shape and default no-scrape `url`, `title`, and `description` result behavior were checked against the current official [Firecrawl Search API reference](https://docs.firecrawl.dev/api-reference/endpoint/search). Firecrawl documents keyless Search as free, per-IP/day rate-limited access in its [rate-limit reference](https://docs.firecrawl.dev/rate-limits#keyless-no-api-key). The adapter uses the Python standard library and adds no SDK or CLI dependency. The frozen configuration bytes and hash did not change; authentication selection is transport behavior and does not alter the query or request payload.

## Query strategy

One query form was declared before any live result:

```text
query_variant_id = quoted-primary-artist-title-official-v1
template = "{primary_artist}" "{normalized_title}" official
```

Only obvious `feat.`, `ft.`, and `featuring` presentation clauses are removed from the search title. Remix, live, remaster/mix, duration, Taylor's Version, and other semantically important target-version markers remain. Original metadata and the exact generated query are persisted together.

No per-track tuning and no second query form are used.

## Candidate normalization and provenance

The URL parser accepts validated 11-character video IDs from:

```text
youtube.com/watch?v=...
youtu.be/...
youtube.com/shorts/...
youtube.com/embed/...
youtube.com/live/...
youtube-nocookie.com/embed/...
```

Lookalike domains, channels, search pages, and invalid IDs are retained as bounded normalized raw results but do not become review candidates. Parseable videos are canonicalized as `https://www.youtube.com/watch?v=<id>`.

Candidates deduplicate only by exact YouTube video ID. The earliest Firecrawl rank wins, and later occurrences retain source rank, URL, and title in `duplicate_occurrences`. Distinct video IDs are never merged. Candidate ranks are contiguous after deduplication and preserve Firecrawl ordering.

A live run writes `reports/stage5b1a/firecrawl_discovery_results.json` atomically. For every frozen track it records original input metadata, case rationale, exact query, secret-free request configuration, provider version/job/credit/warning fields when supplied, all bounded normalized results, the five ordered candidates, errors, and operational timestamps. One request failure does not stop later tracks. Existing result artifacts are not silently overwritten.

## Human review workflow

Committed no-result template: `reports/stage5b1a/review_template.csv`

After a real run, the CLI generates `reports/stage5b1a/firecrawl_review.csv` with expected metadata and five candidate URL/video-ID/title/description slots. It never chooses a candidate automatically. The reviewer fills exactly one label:

```text
1 | 2 | 3 | 4 | 5
NOT_IN_TOP_5 (NOT_IN_TOP_K is accepted as an alias)
UNCERTAIN
```

An optional note remains free-form. Candidate rank labels exceeding the actual candidate count are rejected, and the CLI refuses to overwrite a review file that already contains human labels.

Commands from `ml/audio_similarity`:

```bash
uv run python -m audio_similarity.cli.stage5b1a verify
uv run python -m audio_similarity.cli.stage5b1a prepare-review
uv run python -m audio_similarity.cli.stage5b1a run
uv run python -m audio_similarity.cli.stage5b1a review
uv run python -m audio_similarity.cli.stage5b1a metrics
```

The `run` command prefers `FIRECRAWL_API_KEY` when present and otherwise omits the authorization header to use keyless Firecrawl. Each result row records `api_key` or `keyless` as secret-free provenance. The network-free `review` command can regenerate the candidate review CSV from an existing result artifact without repeating Firecrawl requests.

## Metrics and predeclared gate

Recall@K is:

> confirmed correct ranks at or below K divided by evaluable tracks.

Evaluable tracks are confirmed ranks plus `NOT_IN_TOP_5`. `UNCERTAIN` and unreviewed rows are reported separately and excluded from the recall denominator. Metric artifacts expose numerator, denominator, and value for Recall@1, Recall@3, and Recall@5, plus reviewed/evaluable/unreviewed counts, `NOT_IN_TOP_5`, `UNCERTAIN`, Firecrawl request failures, and zero-candidate tracks.

The frozen primary gate is:

```text
PASS:        Recall@5 >= 90%
CONDITIONAL: Recall@5 >= 80% and < 90%
FAIL:        Recall@5 < 80%
```

This is a small-project engineering gate, not a scientific population claim. Any unreviewed row keeps the verdict `PENDING_HUMAN_REVIEW`; the threshold is not applied to an incomplete review.

## Real-run status and artifacts

- Run status: `reports/stage5b1a/run_status.json`
- Status: `DISCOVERY_COMPLETE_AWAITING_HUMAN_REVIEW`
- Authentication mode: Firecrawl keyless REST; `FIRECRAWL_API_KEY` absent
- Run interval: `2026-09-01T06:31:22+00:00` to `2026-09-01T06:32:10+00:00`
- Firecrawl requests: 25 sequential requests; all succeeded on the first attempt
- Request failures: 0
- Normalized provider results: 165
- Deduplicated YouTube candidates: 76
- Tracks with at least one candidate: 21
- Tracks with zero candidates: 4 (`s5b1a_003`, `s5b1a_012`, `s5b1a_014`, `s5b1a_016`)
- Discovery results: `reports/stage5b1a/firecrawl_discovery_results.json` (SHA-256 `047f2ee493a1823cbd4355db8cbf4363b47c225e3a00b68b9cc86490bfee118a`)
- Human candidate review: `reports/stage5b1a/firecrawl_review.csv` (SHA-256 `98b9881877a3df7c4d6fb14b45e71ad2b40ed85d7df33a0213af2089dfe5a12c`)
- Review labels completed: 0 of 25
- Recall@1/@3/@5: pending human review
- Feasibility verdict: `PENDING_HUMAN_REVIEW`

## Tests and known limitations

Focused Stage 5B.1A tests cover track validation, hash locking, case coverage, query construction, YouTube ID parsing, normalization, deduplication, ordering, empty results, provider errors, bounded retries, API-key/keyless selection, authorization omission, secret handling, sequential failure isolation, atomic persistence, review generation/labels, Recall@1/@3/@5, `UNCERTAIN` denominator behavior, gate boundaries, and artifact identity binding.

Executed test gates:

- Focused Stage 5B.1A: 50 passed, 0 failed.
- Relevant Stage 5A regressions: 14 passed, 0 failed.
- Full non-heavy `ml/audio_similarity` suite: 511 passed, 12 heavy tests deselected by the repository default, 0 failed.

Known limitations are intentional at this gate:

- Search results supply no authoritative duration/channel/licensing metadata.
- Correctness requires human review; titles are not treated as truth.
- One fixed query may underperform for some recordings; its behavior must be measured before revision.
- Firecrawl/search results can vary by provider index, geography, and time despite frozen inputs/configuration.
- Three zero-candidate tracks returned no web results; the fourth returned only a YouTube playlist URL, which correctly remained a non-video result.
- Keyless access is subject to Firecrawl's per-IP daily request and credit caps. This run did not encounter either cap.
- The feasibility set is deliberately small and cannot support population-level claims.
- No fallback discovery provider was used; keyless mode is the same Firecrawl Search endpoint.
