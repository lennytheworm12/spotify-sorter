# Stage 5B.4B — Playwright Fallback for Empty YouTube Search Results

**Verdict: `PLAYWRIGHT_FALLBACK_FAILED`.**

## Answer

No. The clean anonymous browser reached YouTube with the exact query, but YouTube replaced results with an age-confirmation/sign-in wall. The browser correctly returned `PLAYWRIGHT_CHALLENGE_BLOCKED`; no IDs were available to hydrate or review.

## Evaluated architecture

```text
natural Spotify query -> yt-dlp ytsearch3
    candidates present -> stop; existing Stage 5B.3 selector
    zero candidates    -> clean Playwright YouTube search (same query)
                       -> first 3 unique /watch video IDs
                       -> yt-dlp exact-URL metadata hydration
                       -> existing candidate format and selector
```

Playwright is not a normal discovery provider and is not triggered by selector vetoes or `MATCH_UNCERTAIN`.

## Motivating live evaluation

- exact query: `Girl, Interrupted 2xxx Miso`
- primary candidates: **0**
- primary error: `null`
- primary warnings: `[]`
- primary elapsed: **0.823s**
- Playwright triggered: **true**
- browser navigation succeeded: **true**
- browser results: **0**
- browser IDs: `[]`
- browser elapsed: **13.978548760991544s**
- browser warnings: `[]`
- browser error: `{"category": "PLAYWRIGHT_CHALLENGE_BLOCKED", "message": "YouTube challenge or sign-in wall blocked results", "retryable": false}`
- bounded browser navigations: **3**
- observed blocking state: **anonymous age-confirmation/sign-in wall**
- exact URLs requested: `[]`
- hydrated candidates: **0**
- hydration elapsed: **not run**
- first human SAFE rank: **none; no candidate available**

### Hydrated candidates

| Rank | Browser rank | Video ID | Title | Channel | Duration | Views |
|---:|---:|---|---|---|---:|---:|

## Validation criteria

- yt dlp remained primary: **true**
- playwright only after zero: **true**
- same query used: **true**
- browser found candidate: **false**
- exact url hydration succeeded: **false**
- human safe top3: **false**
- selector and query untuned: **true**
- historical artifacts immutable: **true**
- tests passed: **true**

## History and scope

- Stage 5B.4A and Representative V3 artifacts overwritten: **0**.
- Stage 5B.3 selector modifications: **0**.
- Alternate queries, semantic query changes, and forced terms: **0**.
- Personal cookies/profiles, stealth, CAPTCHA solving, and scrolling: **0**.
- Audio/video downloads, proof-heavy resolver, Sol, CLAP, and MuQ: **0**.
- Production activation: **false**.

## Reproduction

From `ml/audio_similarity`, synchronize the locked environment and install the matching Chromium binary before running the bounded commands:

```bash
uv sync
uv run playwright install chromium
uv run python -m audio_similarity.cli.stage5b4b_playwright_fallback config
uv run python -m audio_similarity.cli.stage5b4b_playwright_fallback live
```

The recorded live run was intentionally limited to the motivating query. Do not rerun it merely to seek a different ranking or page state.

## Decision

Do not freeze or production-activate this fallback architecture.
