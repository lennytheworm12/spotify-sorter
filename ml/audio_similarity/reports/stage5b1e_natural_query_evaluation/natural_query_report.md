# Stage 5B.1E Natural YouTube Discovery Query Evaluation

## Status

`STAGE5B1E_DISCOVERY_COMPLETE_AWAITING_HUMAN_REVIEW`

No production query was activated. All resolver policies remained unchanged.

## Frozen resolver regression

The original candidate pools replay exactly at 42/50 AUTO_MATCH and 8/50 MATCH_UNCERTAIN.

## Discovery execution

- yt-dlp version(s): `2026.08.19`
- successful queries: 200/200
- request failures: 0
- zero-candidate query outcomes: 3
- provider warnings: 0
- unique candidate video IDs: 422
- media downloads: 0

## Strategy comparison

| Strategy | Human-safe R@1 | R@3 | R@5 | Resolver AUTO_MATCH | Coverage | Candidate-set failures* | Canonical/strong source |
|---|---:|---:|---:|---:|---:|---:|---:|
| Q0_CURRENT_CONTROL | 37.5% | 82.5% | 95.0% | 42/50 | 84.0% | 2 | 20/50 |
| Q1_NATURAL_SPOTIFY_TITLE | 40.0% | 67.5% | 82.5% | 40/50 | 80.0% | 7 | 15/50 |
| Q2_NATURAL_TITLE_PLUS_ARTIST | 35.0% | 77.5% | 92.5% | 40/50 | 80.0% | 3 | 16/50 |
| Q3_CORE_TITLE_ARTIST_VERSION | 32.5% | 72.5% | 85.0% | 40/50 | 80.0% | 6 | 15/50 |

*Candidate-set failure here means no previously human-confirmed SAFE video ID appeared in the top five for a human-evaluable track. New unlabeled candidates can reduce this count only after review.

## Taki Taki diagnostic

### Q0_CURRENT_CONTROL

Query: `"DJ Snake" "Taki Taki (with Selena Gomez, Ozuna & Cardi B)" official`

1. `JiHRCg1s1_U` — DJ Snake - Taki Taki ft. Selena Gomez, Ozuna, Cardi B(roblox music video) (`OFFICIAL_MUSIC_VIDEO`)
2. `1vr1UADWgY4` — DJ Snake - Taki Taki ft. Selena Gomez, Ozuna, Cardi B (2x Speed)(Fast Music 4 Fun) (`OTHER`)
3. `kxZYxojih3E` — Dj snake feat selena gomez  Ozuna & CARDI B  - TAKi TAKI ( LETRA VIDEO OFICIAL (`OTHER`)
4. `NzLieaKgBII` — DJ Snake -Taki Taki ft. Selena Gomez,Ozuna,Cardi B (NCS Bass Boosted). (`OTHER`)
5. `CXeIpfUdW0w` — DJ Snake - Taki Taki (ft. Cardi B, Selena Gomez, Ozuna) (Letra) (Lyrics) - Video (`LYRIC_VIDEO`)

Resolver: `AUTO_MATCH`; selected `kxZYxojih3E`; source `OTHER`.

### Q1_NATURAL_SPOTIFY_TITLE

Query: `Taki Taki (with Selena Gomez, Ozuna & Cardi B)`

1. `ixkoVwKQaJg` — DJ Snake - Taki Taki ft. Selena Gomez, Ozuna, Cardi B (Official Music Video) (`OFFICIAL_MUSIC_VIDEO`)
2. `tHzbQfgU6eE` — DJ Snake, Selena Gomez, Ozuna, Cardi B - Taki Taki (Letra/Lyrics) (`LYRIC_VIDEO`)
3. `anfOF0KP4JE` — DJ Snake - Taki Taki ft. Selena Gomez, Ozuna, Cardi B (`OTHER`)
4. `UC8uGV2kmMw` — DJ Snake - Taki Taki ft.Selena gomez , Ozuna, Cardi B (`OTHER`)
5. `yNsNFW9lrzI` — Taki Taki - DJ Snake ft. Selena Gomez, Ozuna & Cardi B (`OTHER`)

Resolver: `AUTO_MATCH`; selected `tHzbQfgU6eE`; source `LYRIC_VIDEO`.

### Q2_NATURAL_TITLE_PLUS_ARTIST

Query: `Taki Taki (with Selena Gomez, Ozuna & Cardi B) DJ Snake`

1. `ixkoVwKQaJg` — DJ Snake - Taki Taki ft. Selena Gomez, Ozuna, Cardi B (Official Music Video) (`OFFICIAL_MUSIC_VIDEO`)
2. `tHzbQfgU6eE` — DJ Snake, Selena Gomez, Ozuna, Cardi B - Taki Taki (Letra/Lyrics) (`LYRIC_VIDEO`)
3. `IoQQAOXaW0Q` — DJ Snake - Taki Taki (Official Music Video) ft. Selena Gomez, Ozuna, Cardi B (`OFFICIAL_MUSIC_VIDEO`)
4. `5oDAUf4DZmk` — DJ Snake, Selena Gomez, Ozuna, Cardi B - Taki Taki (Just Dance Fanmade) with Kelvin Jaeder (`OTHER`)
5. `xZWUo9nMXuA` — Taki Taki- DJ Snake ft.Selena Gomez, Ozuna, Cardi B (`OTHER`)

Resolver: `AUTO_MATCH`; selected `tHzbQfgU6eE`; source `LYRIC_VIDEO`.

### Q3_CORE_TITLE_ARTIST_VERSION

Query: `DJ Snake Taki Taki with Selena Gomez, Ozuna & Cardi B`

1. `ixkoVwKQaJg` — DJ Snake - Taki Taki ft. Selena Gomez, Ozuna, Cardi B (Official Music Video) (`OFFICIAL_MUSIC_VIDEO`)
2. `tHzbQfgU6eE` — DJ Snake, Selena Gomez, Ozuna, Cardi B - Taki Taki (Letra/Lyrics) (`LYRIC_VIDEO`)
3. `IoQQAOXaW0Q` — DJ Snake - Taki Taki (Official Music Video) ft. Selena Gomez, Ozuna, Cardi B (`OFFICIAL_MUSIC_VIDEO`)
4. `UC8uGV2kmMw` — DJ Snake - Taki Taki ft.Selena gomez , Ozuna, Cardi B (`OTHER`)
5. `anfOF0KP4JE` — DJ Snake - Taki Taki ft. Selena Gomez, Ozuna, Cardi B (`OTHER`)

Resolver: `AUTO_MATCH`; selected `tHzbQfgU6eE`; source `LYRIC_VIDEO`.

## Evidence limitations

Human-safe recall only recognizes previously human-confirmed video IDs. A new candidate may be correct but remains unvalidated until reviewed.

Frozen Sol labels are reported diagnostically and are not ground truth. Candidate availability alone is not treated as useful discovery.

Q3 retained parenthetical `with …` credits where the frozen parser treated
them as part of `core_title`. For example, its Taki Taki query was
`DJ Snake Taki Taki with Selena Gomez, Ozuna & Cardi B`, not merely
`DJ Snake Taki Taki`. This limitation was discovered after the query contract
and live results were frozen; Q3 was not changed or rerun post hoc.

## Human review

Targeted judgments required: 10

Completed: 0; remaining: 10

Review artifact: `human_review.csv`.

## Decision

`NO_CLEAR_WINNER_PENDING_TARGETED_HUMAN_REVIEW`

A final KEEP/ADOPT decision is deferred until materially changed selections have human evidence.

## Validation

- Focused Stage 5B.1E tests: `17 passed`
- Frozen resolver regressions within focused suite: passed
- Full non-heavy `ml/audio_similarity` suite: `755 passed, 12 deselected`
- Existing librosa short-fixture warnings: 11; no test failures
- Completed-run resume check: zero repeated searches and zero pacing sleeps

## Scope guards

- audio/video downloads: 0
- Stage 5A calls: 0
- CLAP/MuQ calls: 0
- Sol reruns: 0
- resolver changes: 0
- production activation: false
