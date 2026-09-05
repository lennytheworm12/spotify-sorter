# Stage 5B.4C — Official YouTube Data API Fallback

**Verdict: `YOUTUBE_DATA_API_FALLBACK_FAILED`.**

## Architecture

```text
natural title + first 3 artists -> yt-dlp ytsearch3
    candidates -> existing selector
    zero       -> Data API search.list (same query, video, max 3)
               -> videos.list metadata hydration
               -> existing selector
    unresolved -> manual YouTube URL override
```

## Motivating evaluation

- exact query: `Girl, Interrupted 2xxx Miso`
- primary result count: **0**
- primary error: `null`
- primary warnings: `[]`
- primary elapsed: **1.072s**
- Data API triggered: **true**
- search video IDs: `[]`
- search elapsed: **0.2890832829871215s**
- search error: `{"category": "YOUTUBE_DATA_API_SEARCH_ZERO_RESULTS", "http_status": null, "message": "search.list returned no usable video IDs", "reason": null, "retryable": false}`
- diagnostic raw `items` count: **0**
- total bounded `search.list` requests: **2**
- hydrated candidates: **0**
- hydration elapsed: **not run; no video IDs**
- first human SAFE rank: **none; no candidate available**
- unresolved next step: `MANUAL_YOUTUBE_URL_OVERRIDE`

| Rank | Provider rank | Video ID | Title | Channel | Duration | Views |
|---:|---:|---|---|---|---:|---:|

## Criteria

- yt dlp remained primary: **true**
- data api only after zero: **true**
- same query used: **true**
- data api found candidate: **false**
- videos list hydrated candidate: **false**
- human safe top3: **false**
- selector and query untuned: **true**
- historical artifacts immutable: **true**
- tests passed: **true**

## Scope

- Alternate queries, query heuristics, and selector tuning: **0**.
- Playwright invocations: **0**.
- API credentials serialized: **0**.
- Audio/video downloads: **0**.
- Historical artifacts overwritten: **0**.
- Production activation: **false**.

## Reproduction

The deterministic adapter and artifact checks can be replayed without a key:

```bash
uv run pytest -q tests/test_stage5b4c_youtube_data_api.py
```

The live runner is fail-closed once evidence exists. The recorded requests should not be rerun merely to seek a different result.

## Decision

The official API fallback did not recover the motivating case. Keep the architecture unactivated and route this unresolved track to a manual YouTube URL override. Do not add query heuristics from this result.

Official references: [search.list](https://developers.google.com/youtube/v3/docs/search/list) and [videos.list](https://developers.google.com/youtube/v3/docs/videos/list).
