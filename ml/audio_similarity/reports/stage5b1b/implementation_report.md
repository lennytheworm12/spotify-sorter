# Stage 5B.1B Part A — hierarchical candidate-resolution features

Status: **`STAGE5B1B_HELDOUT_READY_FOR_HUMAN_REVIEW`**

No final AUTO_MATCH threshold has been selected. Held-out labels are required before calibration.

## Evidence checkpoint and scope

- Work began from pushed Stage 5B.1A2 implementation commit `6ca3c99` plus the completed reviewer evidence present in the working tree.
- The verified Stage 5B.1A2 human-review PASS was committed and pushed first as `09f8347`.
- That checkpoint preserves the original 25-track manifest SHA-256 `f3592bb8c8dea689959a22da222d8b7ce4911c1804392acb501cffe768700c57` and reports Recall@1 44%, Recall@3 92%, Recall@5 100%, zero NOT_IN_TOP_5, and zero UNCERTAIN.
- The original 25 songs are used only as **DEV** data. They do not establish held-out match precision and were not used to select a production threshold.
- The governing design is `Projects/Spotify Sorter/Spotify Audio Similarity Stage 5B.1B — Candidate Resolution Design.md` in the project Obsidian vault.

This stage performs metadata discovery and feature materialization only. It downloads no media and does not call Stage 5A, CLAP, or MuQ.

## Architecture and decision rationale

The implementation reuses the source-independent `SpotifyTrack`, frozen query builder, yt-dlp metadata-only adapter, top-five deduplication, bounded retry behavior, artifact hashing, and sequential pacing from Stage 5B.1A2. New Stage 5B.1B modules add only the target/candidate parsers, hierarchical feature records, a 50-track manifest contract, held-out orchestration, and candidate-level review schema.

Evidence remains componentized in this order:

1. core target identity;
2. explicit target-relative version compatibility;
3. title and performer agreement;
4. numeric duration evidence;
5. source provenance and quality;
6. description, album, and release evidence;
7. weak relative-view and search-rank evidence;
8. a future empirically calibrated acceptance policy.

This structure was chosen so a lower-level signal cannot compensate for an explicit higher-level recording conflict. The implementation intentionally has no arbitrary point score, confidence probability, or acceptance cutoff.

## Identity and version parsing

Raw target title, artists, album, duration, year, Spotify ID, and ISRC remain preserved. Derived identity exposes core/normalized title, primary and credited artists, normalized artists, duration seconds, version families, raw version text, and qualifiers.

Implemented deterministic version families include remix and named remix, live and named live location/event, remaster, generic mix, radio edit, extended mix/version, acoustic, instrumental, karaoke, slowed, sped up, nightcore, reverb, clean/explicit, Taylor's Version/re-recording, duration-specific version, edit, and selected obvious named versions such as angrier/chill/demo/B-side/From The Vault/duet.

Each target-relative family relation is `MATCH`, `ABSENT`, or `CONFLICT`:

- `MATCH`: observed evidence is compatible with the target descriptor/qualifier;
- `ABSENT`: target detail is not supplied by the candidate metadata, so it remains weak missing evidence;
- `CONFLICT`: candidate metadata explicitly names an incompatible version or adds a version to a plain target.

An explicit version conflict, explicit cover/different title performer, or strict zero-overlap core-title contradiction makes `recording_eligible=false` for normal automatic selection while preserving the candidate and reason. The zero-overlap check is deliberately conservative and is not a tunable similarity threshold. Uploader/channel is provenance only: a label, distributor, Topic, VEVO-style, or K-pop company channel is never treated as the performer solely because it differs from the Spotify artist.

## Duration, source, and weak evidence

Duration stores target seconds, candidate seconds, absolute delta, and relative delta. No hard duration cutoff is present.

Source classification supports `ART_TRACK_TOPIC`, `OFFICIAL_AUDIO`, `LYRIC_VIDEO`, `OFFICIAL_MUSIC_VIDEO`, and `OTHER`. The approved source preference is encoded separately as Art Track/Topic > Official Audio > lyric video > Official Music Video > other, and is consulted only after recording compatibility. Official Music Video is therefore neither globally preferred nor globally rejected.

View count remains nullable. When supplied, relative count, log-relative strength, and rank are calculated only among recording-eligible candidates. Search rank remains a separate weak feature. Neither can rescue an explicit version or performer conflict.

## DEV feature analysis

Artifacts:

- `reports/stage5b1b/dev_candidate_features.json`
- `reports/stage5b1b/dev_feature_analysis.json`

All 25 tracks × 5 candidates = 125 candidate pairs have inspectable feature records. Human labels were joined only after feature calculation for diagnostics, and every original review note is preserved verbatim.

Among the 25 human-selected DEV candidates:

- 25 had no parsed explicit version conflict and remained recording-eligible;
- 22 had exact normalized core-title agreement and 22 tied for strongest title similarity in their candidate set;
- 12 tied for strongest explicit performer evidence;
- source types were 12 Art Track/Topic, 2 Official Audio, 6 Official Music Video, and 5 Other;
- closest-duration analysis was not evaluable because the historical 25-track manifest did not contain Spotify `duration_ms`.

These findings helped verify parser behavior only. They are not held-out resolver accuracy.

## Fresh held-out manifest

- Path: `reports/stage5b1b/heldout_tracks.json`
- Tracks: 50
- SHA-256: `39557ede8f07bde129ad23d2bc64a0faf0fff755356cd87f2054e14f91d81e5a`
- Freeze checkpoint: `ba57934`

The manifest was committed and pushed before held-out discovery. It includes straightforward studio baselines plus named/generic remixes, radio/extended edits, live recordings with named locations/events, remasters, Taylor's Version/re-recordings, acoustic and alternate arrangements, clean/explicit ambiguity, K-pop label-hosted candidates, theatrical music videos, covers and common titles, multilingual titles, punctuation/diacritics, and smaller artists with weaker canonical provenance. It is an engineering validation set, not a population sample.

## Held-out yt-dlp discovery

- Query: `"{primary_artist}" "{normalized_title}" official`
- Search: sequential `ytsearch5`
- Pacing: fixed 1.0 second between tracks
- yt-dlp: `2026.08.19`
- Elapsed wall time: 90.880 seconds
- Tracks attempted: 50
- Tracks with candidates: 50
- Zero-candidate tracks: 0
- Search failures: 0
- Captured warning count: 0
- Deduplicated candidate pairs: 248
- Candidate coverage: 49 tracks returned five candidates; `s5b1b_015` returned three
- Metadata coverage: duration/uploader/channel/view count 248/248; description 231/248

The result artifact records `download=false`, `simulate=true`, `skip_download=true`, flat playlist extraction, candidate IDs, titles, uploader/channel, duration, description, view count when surfaced, request timestamps, and operational errors/warnings. The run status records zero audio downloads, zero video downloads, zero CLAP calls, zero MuQ calls, and zero Stage 5A materializations.

Artifacts:

- `reports/stage5b1b/heldout_ytdlp_discovery.json`
- `reports/stage5b1b/heldout_candidate_features.json`
- `reports/stage5b1b/run_status.json`

Artifact hashes are recorded in `run_status.json`: discovery `2c318ac0853ffe3395c6a934265585afcb0a39a2f9ce73e5a00ba35276d056e4`, features `f4260fe01b95770ceb4c47f8298033a0b865e597780a488bca1dfaac22a604a6`, and review `35f5370c2017e7b5e8d6a66623fc7e83a027eb9d650e36a0202adb425fc9f75d`.

## Human-review contract

- Path: `reports/stage5b1b/heldout_review.csv`
- Rows: 248 candidate pairs
- Completed labels: 0
- Allowed per-candidate labels: `IDEAL`, `ACCEPTABLE`, `WRONG`, `UNCERTAIN`
- Optional per-candidate and per-track note columns are included.

The schema permits zero or multiple IDEAL candidates and multiple ACCEPTABLE candidates. No labels were fabricated, and no final precision, coverage, or AUTO_MATCH verdict is claimed.

## Tests

Focused Stage 5B.1B, Stage 5B.1A/1A2 historical, and Stage 5A regression result: **145 passed, 0 failed**.

Full non-heavy `ml/audio_similarity` result: **592 passed, 12 heavy tests deselected, 0 failed**. The 11 warnings are existing short-signal librosa warnings and one existing empty-frequency tuning warning.

All normal tests mock the yt-dlp boundary and require no network access.

## Known limitations

- Title/description parsing is deterministic and deliberately bounded; unusual language, aliases, punctuation, or unnamed versions can remain missing or ambiguous.
- `ABSENT` is intentionally not rejected. Later held-out calibration must determine how combinations of missing evidence affect safe coverage.
- Flat yt-dlp search metadata may omit view count, complete description, availability, or release provenance.
- Source classification describes upload type, not recording correctness or audio cleanliness.
- Metadata alone may be insufficient for some theatrical videos, edits, or uploads with misleading titles. Audio fallback is explicitly deferred.
- YouTube results and extraction behavior can change with time, geography, IP reputation, and extractor updates.

**NO FINAL AUTO_MATCH THRESHOLD HAS BEEN SELECTED.**

**HELD-OUT LABELS ARE REQUIRED BEFORE CALIBRATION.**
