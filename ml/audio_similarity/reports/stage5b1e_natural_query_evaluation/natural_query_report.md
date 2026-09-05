# Stage 5B.1E Natural YouTube Discovery Query Evaluation

## Status

`STAGE5B1E_QUERY_EVALUATION_COMPLETE`

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
| Q0_CURRENT_CONTROL | 36.6% | 87.8% | 97.6% | 42/50 | 84.0% | 1 | 20/50 |
| Q1_NATURAL_SPOTIFY_TITLE | 43.9% | 78.0% | 92.7% | 40/50 | 80.0% | 3 | 15/50 |
| Q2_NATURAL_TITLE_PLUS_ARTIST | 36.6% | 87.8% | 95.1% | 40/50 | 80.0% | 2 | 16/50 |
| Q3_CORE_TITLE_ARTIST_VERSION | 34.1% | 80.5% | 90.2% | 40/50 | 80.0% | 4 | 15/50 |

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

## John Mayer review clarification

The targeted review UI showed resolver-selected candidates, not every top-five search result. The official John Mayer upload `20Ov0cDPZy8` was rank 1 for Q1, Q2, and Q3.

Its frozen duration was 243 seconds versus 264.267 seconds for the Spotify target. The unchanged resolver rejected that 21.267-second delta, then selected the 264-second, 33-view upload `sVjv1UAmLRc`, which the human reviewer labeled `UNCERTAIN`.

This is evidence that natural discovery retrieved a materially stronger-looking candidate while the frozen resolver—not discovery—prevented its selection. The official upload remains unreviewed under the formal SAFE/WRONG rubric and is not silently counted as human-safe.

## Evidence limitations

Human-safe recall only recognizes previously human-confirmed video IDs. A new candidate may be correct but remains unvalidated until reviewed.

Frozen Sol labels are reported diagnostically and are not ground truth. Candidate availability alone is not treated as useful discovery.

## Human review

Targeted judgments required: 10

Completed: 10; remaining: 0

Labels: `{"ACCEPTABLE": 7, "IDEAL": 2, "UNCERTAIN": 1}`

Review artifact: `human_review.csv`.

## Decision

`KEEP_CURRENT_QUERY`

The completed targeted review does not support replacing the control: Q0 retains the highest human-safe Recall@5 and resolver coverage. This freezes the experimental recommendation only; production remains unchanged.

Q1 improved human-safe Recall@1 and produced materially stronger-looking pools for examples such as Taki Taki and Free Fallin', but it lost too much Recall@3/5 and resolver coverage elsewhere. Q2 came closest to the control at Recall@5, but still trailed it by 2.5 percentage points and resolved two fewer tracks. The product hypothesis is therefore not supported as a universal first-pass replacement on this adversarial challenge.

Q3 was evaluated exactly as frozen. Its then-current core-title parser retained some `(with Artist)` credit text, so it was not a perfectly minimal core-title query for every track. This limitation was discovered after the strategy contract and live run were frozen; no post-outcome query rewrite or rerun was performed.

## Validation

- focused Stage 5B.1E tests: 20 passed
- full non-heavy `ml/audio_similarity` suite: 758 passed, 12 deselected
- expected warnings: 11 existing short-fixture librosa warnings
- initial sandboxed full-suite attempt: 741 passed and 17 localhost tests received sandbox HTTP 403; the identical suite passed completely when localhost access was enabled
- review closeout replay: 10/10 labels retained with stable queue membership
- frozen original-pool resolver regression: 42 AUTO_MATCH / 8 MATCH_UNCERTAIN, with unchanged selected IDs

## Scope guards

- audio/video downloads: 0
- Stage 5A calls: 0
- CLAP/MuQ calls: 0
- Sol reruns: 0
- resolver changes: 0
- production activation: false
