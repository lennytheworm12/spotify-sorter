# Stage 5B.4C — Credited-Artist Query Decomposition

**Verdict: `ARTIST_DECOMPOSITION_FALLBACK_VALIDATED`.**

## Frozen architecture

```text
Q0: sanitized title + first 3 distinct credited artists
    candidates -> stop; use native Top-3
    zero       -> title + artist 1
                  title + artist 2
                  title + artist 3
                  sequential; stop at first non-empty Top-3
    error      -> provider error; do not decompose
```

## Targeted evidence

- Motivating Q0: `Girl, Interrupted 2xxx Miso` -> **0** candidates.
- Q1: `Girl, Interrupted 2xxx` -> **0** candidates in 0.698s.
- Q2: `Girl, Interrupted Miso` -> **3** candidates in 0.743s.
- Successful candidate IDs: `['DpXA_N3jnvE', '3ldYv7cwom4', 'Bk0gP8ZXRsA']`.
- First human SAFE rank: **1**.
- Regression Q0: `All The Stars (with SZA) - From Black Panther: The Album Kendrick Lamar SZA` -> **3** candidates.
- Regression fallback count: **0**.

| Rank | Video ID | Title | Channel | Duration | Views |
|---:|---|---|---|---:|---:|
| 1 | `DpXA_N3jnvE` | Girl, Interrupted | 2xxx - Topic | 181.0 | 152221 |
| 2 | `3ldYv7cwom4` | 2xxx! - 02 Girl, Interrupted ft. Miso | Dan N | 183.0 | 101028 |
| 3 | `Bk0gP8ZXRsA` | Girl, Interrupted - 2xxx! (ft. Miso) | Club Eskimo - Vietnam Fanpage | 171.0 | 7898 |

## Offline Representative V3 analysis

- duplicate fallback queries removed: **63**
- live searches run: **0**
- malformed or empty query count: **0**
- maximum fallback requests per track: **3**
- maximum possible fallback requests across v3: **81**
- punctuation rejection count: **0**
- tracks total: **100**
- tracks with 1 artist: **63**
- tracks with 2 artists: **30**
- tracks with 3 or more artists: **7**
- tracks with harmless punctuation: **17**

No V3 YouTube searches were executed for this analysis; only the frozen metadata was transformed into potential query plans.

## Decision

Freeze `NATURAL_TITLE_FIRST3_ARTISTS_THEN_SINGLE_ARTIST_V1` as the candidate discovery contract for the next fresh representative benchmark. Do not reinterpret V3 and do not production-activate from this targeted repair.

## Scope

- Candidate-pool merges, title-only variants, song-specific rules: **0**.
- Playwright and Data API invocations: **0**.
- Audio/video downloads: **0**.
- Historical artifacts overwritten: **0**.
- Production activation: **false**.

## Reproduction

```bash
uv run pytest -q tests/test_stage5b4c_artist_decomposition.py tests/test_stage5b4c_artist_decomposition_experiment.py
```
