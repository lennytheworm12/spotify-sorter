# Stage 5B.1A — Firecrawl YouTube discovery feasibility

Status: **`IMPLEMENTED_BUT_REAL_DISCOVERY_NOT_RUN`**

No Firecrawl credential was available in the execution environment. No live Firecrawl requests were made, no candidate results or human labels were fabricated, and no feasibility verdict is claimed.

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
- Credential: environment variable `FIRECRAWL_API_KEY`; never persisted

The request shape and default no-scrape `url`, `title`, and `description` result behavior were checked against the current official [Firecrawl Search API reference](https://docs.firecrawl.dev/api-reference/endpoint/search). The adapter uses the Python standard library and adds no SDK dependency.

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

The `run` command fails clearly when `FIRECRAWL_API_KEY` is absent. The network-free `review` command can regenerate the candidate review CSV from an existing result artifact without repeating Firecrawl requests.

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
- Status: `IMPLEMENTED_BUT_REAL_DISCOVERY_NOT_RUN`
- Firecrawl requests: 0
- Request failures: not applicable because no request was attempted
- Discovery results: pending credential
- Human candidate review: pending discovery
- Recall@1/@3/@5: pending discovery and human review
- Feasibility verdict: `PENDING_REAL_DISCOVERY_AND_HUMAN_REVIEW`

## Tests and known limitations

Focused Stage 5B.1A tests cover track validation, hash locking, case coverage, query construction, YouTube ID parsing, normalization, deduplication, ordering, empty results, provider errors, bounded retries, secret handling, sequential failure isolation, atomic persistence, review generation/labels, Recall@1/@3/@5, `UNCERTAIN` denominator behavior, gate boundaries, CLI credential handling, and artifact identity binding.

Executed test gates:

- Focused Stage 5B.1A: 48 passed, 0 failed.
- Relevant Stage 5A regressions: 14 passed, 0 failed.
- Full non-heavy `ml/audio_similarity` suite: 509 passed, 12 heavy tests deselected by the repository default, 0 failed.

Known limitations are intentional at this gate:

- Search results supply no authoritative duration/channel/licensing metadata.
- Correctness requires human review; titles are not treated as truth.
- One fixed query may underperform for some recordings; its behavior must be measured before revision.
- Firecrawl/search results can vary by provider index, geography, and time despite frozen inputs/configuration.
- The feasibility set is deliberately small and cannot support population-level claims.
- No fallback provider is used when the Firecrawl credential is absent.
