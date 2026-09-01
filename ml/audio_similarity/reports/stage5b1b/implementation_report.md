# Stage 5B.1B Part A — hierarchical candidate-resolution features

Status: **`STAGE5B1B_SOL_AUDIT_READY_FOR_TARGETED_HUMAN_REVIEW`**

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

### Local review workbench

Run `.venv/bin/python -m audio_similarity.cli.stage5b1b_review_server` from `ml/audio_similarity`, then open `http://127.0.0.1:8768`.

The responsive workbench groups the 248 candidate rows beneath their 50 Spotify targets and exposes direct YouTube links, title, uploader/channel, duration, view count, the four independent candidate labels, optional per-candidate notes, and an optional per-track note. Every label saves immediately; notes save after a short idle delay or blur. Persistence is atomic and keyed by the frozen `(stable_track_id, video_id)` identity. Track notes remain consistent across all candidate rows for that track. Progress reports saved candidate judgments rather than merely optimistic browser state, resumes from the CSV, and can be exported at any point.

Automatic title/version/source/eligibility features are deliberately absent from the browser API so the held-out labels are not biased by the resolver under evaluation. The workbench does not embed or download YouTube media.

## Tests

Focused Stage 5B.1B, Stage 5B.1A/1A2 historical, and Stage 5A regression result: **145 passed, 0 failed**.

Focused review-workbench persistence/API result: **11 passed, 0 failed**.

Full non-heavy `ml/audio_similarity` result after the review workbench: **603 passed, 12 heavy tests deselected, 0 failed**. The 11 warnings are existing short-signal librosa warnings and one existing empty-frequency tuning warning.

Isolated headless Chromium verification passed for desktop and 390 px mobile layouts, all four label states, immediate label autosave, candidate-note and track-note autosave, reload/resume persistence, saved progress accounting, direct YouTube links, CSV export, horizontal overflow, and console errors/warnings. Browser verification used a disposable `/tmp` CSV; the authoritative empty review artifact remained unchanged.

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

## Blinded Sol-assisted evaluator and targeted audit

The exhaustive 248-row manual workflow was superseded by a blinded semantic
triage protocol. This does not alter the frozen 50-track manifest, yt-dlp
candidate set, hierarchical resolver features, or future calibration target.
It changes only which held-out rows are prioritized for human judgment.

### Blind evaluator contract

- Config: `configs/stage5b1b_sol.json`
- Model: `gpt-5.6-sol`
- Codex CLI: `0.151.0`
- Reasoning effort: `high`
- Prompt: `stage5b1b-sol-blinded-candidate-review-v2`
- Structured output schema SHA-256:
  `1480ac0ff8ee672f6412760f12e4657c89f7b4bbaca906452a07759af333621c`
- Frozen manifest SHA-256:
  `39557ede8f07bde129ad23d2bc64a0faf0fff755356cd87f2054e14f91d81e5a`
- Frozen discovery SHA-256:
  `2c318ac0853ffe3395c6a934265585afcb0a39a2f9ce73e5a00ba35276d056e4`

Sol received only the Spotify-style target metadata, generated search query,
and raw yt-dlp candidate fields. Resolver features, resolver decisions, human
labels, case tags, and curator case rationales were excluded. Every batch ran
ephemerally from an isolated temporary directory with user config/rules
disabled and a read-only sandbox. The harness rejects a batch if the Codex JSONL
event stream contains command, file, MCP, or web-search activity.

An earlier preflight exposed that the v1 prompt still included curator case
tags/rationales. That output was rejected and overwritten before comparison.
The accepted v2 run used the stricter raw-evidence-only contract above.

The evaluator processed 50 tracks and 248 candidates in ten resumable
five-track batches. All ten batches completed, the summed model wall time was
740.065 seconds, request failures were zero, and forbidden tool/web events were
zero. Candidate labels were 33 `IDEAL`, 110 `ACCEPTABLE`, 93 `WRONG`, and 12
`UNCERTAIN`. Sol made a track-level selection for 49 tracks and abstained on one.

### Resolver comparison semantics

There still is no calibrated production resolver. For audit construction, the
code evaluates an explicitly uncalibrated hierarchical proposal
`stage5b1b-uncalibrated-hierarchical-proposal-v1`. It requires exact normalized
core title, explicit primary-performer evidence, no hard identity conflict, and
resolved target-version evidence before proposing a source. It then applies the
already documented evidence hierarchy lexicographically. It never enables
`AUTO_MATCH`.

The primary agreement metric asks whether Sol independently labeled the
proposal's selected source `IDEAL` or `ACCEPTABLE`. `WRONG` is a safety
disagreement. Sol uncertainty and resolver abstention are reported separately
and excluded from that denominator:

- safe-selection agreement: 41/43 = 95.35%;
- unsafe-selection disagreement: 2/43 = 4.65%;
- resolver-selected tracks: 45;
- resolver-uncertain tracks: 5;
- tracks containing Sol uncertainty: 9;
- exact preferred-source agreement: 26/41 = 63.41%;
- safe source-preference disagreements: 15.

The two safety disagreements are preserved as `s5b1b_004` and `s5b1b_047`.
These results are triage evidence, not precision estimates against human ground
truth. The lower exact-source agreement is also not a correctness failure: it
often means both choices were considered safe while Sol preferred a different
clean source.

### Targeted human audit

The audit union includes every safety/source disagreement, every Sol-uncertain
case, every resolver abstention, and a deterministic ten-track random sample of
clean exact agreements. Candidate filtering narrows the work from all 248 rows
to 80 relevant candidate judgments across 37 tracks. Resolver-abstention tracks
retain all candidates; disagreements retain the two compared selections;
uncertainty retains the uncertain candidate and selection context; random audit
tracks retain the proposed/selected candidate.

Run:

```bash
.venv/bin/python -m audio_similarity.cli.stage5b1b_review_server \
  --queue reports/stage5b1b/sol_manual_audit_queue.json
```

The UI hides Sol and resolver annotations and continues to autosave human labels
to the authoritative `heldout_review.csv`. This preserves blinded human audit
judgment while avoiding exhaustive labeling.

Artifacts:

- `reports/stage5b1b/sol_evaluations.json`
  (`cd895d762569dbaf1697c973f04de3a89273d9c1daf50edfdfede15326a45b57`)
- `reports/stage5b1b/sol_resolver_comparison.json`
  (`4fd4901e499cd53eca8e44ee26b44c2d8c39cec38132b08080305c875c0f14a9`)
- `reports/stage5b1b/sol_manual_audit.json`
  (`61e6716b6e5747119ba31d101be005619658dd2277e30ba5d0009238f158779b`)
- `reports/stage5b1b/sol_manual_audit_queue.json`
  (`3f3868c613099e50a976d83ef5dea343fda0cf06d1bb51662ef0772b3d3193a5`)

**SOL JUDGMENTS ARE NOT HUMAN GROUND TRUTH.**

**NO FINAL AUTO_MATCH THRESHOLD HAS BEEN SELECTED.**

**TARGETED HUMAN AUDIT IS REQUIRED BEFORE CALIBRATION.**
