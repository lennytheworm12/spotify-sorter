# Stage 5B.1B Part B — Offline Candidate Resolver Calibration

Status: `STAGE5B1B_POLICY_READY_FOR_FRESH_CHALLENGE_VALIDATION`

Frozen policy status: `CANDIDATE_POLICY_ONLY / NOT_PRODUCTION_ACTIVATED`

## Research question and boundary

This calibration asks whether a deterministic hierarchy can automatically
choose a metadata-supported safe YouTube source while returning
`MATCH_UNCERTAIN` for the difficult tail. It does not validate generalization,
activate production matching, download media, call Stage 5A, or run CLAP/MuQ.
A new frozen challenge set is the mandatory next gate.

Starting checkpoint:

- branch: `ml/stage5b1b-human-audit-complete`
- commit: `553c2b476a9bd4b707afeea6f5a69ffb4039f2a6`

## Frozen evidence

| Artifact | SHA-256 |
|---|---|
| 50-track manifest | `39557ede8f07bde129ad23d2bc64a0faf0fff755356cd87f2054e14f91d81e5a` |
| 248-candidate yt-dlp discovery | `2c318ac0853ffe3395c6a934265585afcb0a39a2f9ce73e5a00ba35276d056e4` |
| original feature artifact | `f4260fe01b95770ceb4c47f8298033a0b865e597780a488bca1dfaac22a604a6` |
| completed targeted human review | `8e5282310ff44c9441e81a1cb538613f004b92361ec8b8c21172b4d40b69e97e` |
| targeted audit queue | `3f3868c613099e50a976d83ef5dea343fda0cf06d1bb51662ef0772b3d3193a5` |
| calibration feature v2 | `33efc17b110329627979c7db6e2bdc7576034ced205e0db28762101d951c82e5` |

All 80 required queue candidates remain labeled: 32 `IDEAL`, 28
`ACCEPTABLE`, 5 `WRONG`, and 15 `UNCERTAIN`. Fourteen candidate notes and one
track-level note are preserved verbatim. The other 168 rows remain unaudited by
design.

The 80 rows are a targeted audit assembled from prior disagreements,
uncertainty, resolver abstentions, and a ten-track random agreement audit. They
are not a representative sample of all candidates. Metrics below therefore use
the explicit terms *human-audited subset* and *unaudited* rather than claiming
full-universe human precision.

## Canonical-release provenance features

Feature schema `stage5b1b-candidate-features-v2` independently exposes:

- `topic_channel_signal`;
- `provided_to_youtube_by_signal`;
- `auto_generated_by_youtube_signal`;
- `structured_release_metadata_signal`;
- `description_album_match`;
- `description_release_year_match`;
- positive uploader/channel-to-artist support, without treating mismatch as a
  recording conflict;
- raw description/channel evidence for each triggered signal.

The targeted human cells were:

- broad `ART_TRACK_TOPIC`: 15 audited, 14 IDEAL, 1 ACCEPTABLE, 0 WRONG or
  UNCERTAIN;
- strong identity + “Provided to YouTube by” + close duration: 7 audited, all
  IDEAL;
- strong identity + Official Audio + close duration: 3 audited, all IDEAL;
- Topic-channel literal: 1 audited, IDEAL;
- structured-release literal: 2 audited, both safe;
- auto-generated literal: 0 audited occurrences in the retained yt-dlp text.

The last result is a metadata-availability limitation, not evidence against Art
Tracks: yt-dlp frequently retained an abbreviated “Provided to YouTube by”
description without the trailing auto-generated sentence. Small cells are
descriptive only.

## Duration calibration

Duration remains numeric in every feature record. Bands were derived only from
the 54 recording-eligible human `IDEAL`/`ACCEPTABLE` rows with available
duration:

| Safe-delta quantile | Raw seconds | Frozen ceiling |
|---|---:|---:|
| q50 | 1.6405 | 2 s (`DURATION_VERY_CLOSE`) |
| q75 | 6.7270 | 7 s (`DURATION_CLOSE`) |
| q90 | 47.3118 | 48 s (`DURATION_MODERATE`) |

These bands are combined with stronger identity/version evidence; duration
never rescues a wrong remix, live/studio conflict, cover, rerecording, or other
explicit contradiction. The selected conservative policy uses only the
2-second very-close band.

## Relative views

Views remain a late tiebreaker only. Among strong-identity, close-duration lyric
rows with relative view strength at least 0.001, the targeted audit contained
10 examples: 2 IDEAL, 7 ACCEPTABLE, 0 WRONG, and 1 UNCERTAIN. The one comparable
row below 0.001 was UNCERTAIN. This supports retaining relative views as weak
lyric-upload evidence but is too small to establish safety by itself. The
selected conservative policy does not use lyric fallback.

## Fresh blinded Sol review

The Part B Sol review used `gpt-5.6-sol`, high reasoning, through Codex CLI
0.151.0. Its prompt, schema, payload, and mapping were frozen before execution:

- prompt SHA-256: `e99ddc6ad63322c5404866bdcd407c351503e782bf11ba727f013fe41e0b4160`;
- output schema SHA-256: `d258dcf464b4be97e26ea8c799086e97f2ebc54aecfc270109e41747d199b178`;
- blinded payload SHA-256: `dc7c90f24d26b1f50cdb8868f22e7b3c041f0f49ceab16a439162b4916bb063c`;
- private mapping SHA-256: `f3760b9f5eb029bc608a3697e7b75088a4fff0be764442c3e06fbd4a9752ff84`;
- completed output SHA-256: `a24e11ba7fd73262a458b1a2f0cb067a82e23438e73f0f43f2cfc615e513e377`.

Candidates were deterministically shuffled and represented to Sol by opaque
keys. Search rank, video ID, query, case tags/rationale, human labels, derived
features, resolver eligibility, source classification, and resolver decisions
were not supplied. Evaluation ran in isolated ephemeral read-only working
directories with user config/rules ignored. All 10 batches completed, with 50
tracks, 248 candidate judgments, zero request failures, and zero tool/web
events. Total recorded evaluator wall time was 2,902.05 seconds.

Sol labels were 51 IDEAL, 89 ACCEPTABLE, 96 WRONG, and 12 UNCERTAIN. It selected
a source for 49 tracks and returned `SOL_MATCH_UNCERTAIN` for one.

Sol remains an independent metadata reviewer, not ground truth. On the targeted
80 human rows:

- exact four-label agreement: 49/80 = 61.25%;
- all-state SAFE/UNSAFE/UNRESOLVED agreement: 58/80 = 72.50%;
- SAFE/UNSAFE agreement where both reviewers resolved the row: 56/62 = 90.32%.

The full disagreement matrix and human notes are preserved in
`sol_human_agreement.json`.

## Policy variants

All policies first reject explicit recording/version conflicts. Lower-level
duration, provenance, views, and search rank cannot rescue them.

| Policy | AUTO_MATCH | Coverage | MATCH_UNCERTAIN | Human audited selection | Human WRONG | Human UNCERTAIN | Sol WRONG |
|---|---:|---:|---:|---:|---:|---:|---:|
| CONSERVATIVE | 14 | 28% | 36 | 6 | 0 | 0 | 0 |
| BALANCED | 30 | 60% | 20 | 17 | 0 | 1 | 1 |
| PERMISSIVE | 43 | 86% | 7 | 29 | 0 | 5 | 2 |

Human-audited selection labels were:

- conservative: 6 IDEAL; 8 additional selections unaudited;
- balanced: 8 IDEAL, 8 ACCEPTABLE, 1 UNCERTAIN; 13 unaudited;
- permissive: 13 IDEAL, 11 ACCEPTABLE, 5 UNCERTAIN; 14 unaudited.

No variant selected a human-labeled WRONG candidate in this targeted audit.
That fact is not a full-universe precision claim. Balanced selected one
human-UNCERTAIN candidate and one Sol-WRONG candidate. Permissive selected five
human-UNCERTAIN and two Sol-WRONG candidates.

## Selected candidate policy

The predeclared lexicographic selection procedure minimizes, in order:

1. known human WRONG automatic selections;
2. known human UNCERTAIN automatic selections;
3. Sol WRONG automatic selections;
4. Sol UNCERTAIN automatic selections;
5. then maximizes coverage.

This selects `POLICY_CONSERVATIVE_V1`.

Its automatic gate requires:

- recording eligibility and no explicit version conflict;
- exact normalized core title;
- explicit primary-performer match;
- no absent target-version evidence;
- `DURATION_VERY_CLOSE` (at most 2 seconds under this calibration);
- canonical provenance or Official Audio;
- no lyric, Official Music Video, or noncanonical OTHER fallback.

Among its 14 selections, all 14 were labeled IDEAL by blinded Sol. Six were
directly human-audited and all six were IDEAL; five of those six came from the
deterministic random-agreement audit and one from the disagreement audit. The
other eight are explicitly recorded as unaudited, not human-validated.

This produces 28% candidate-policy coverage and a 72% `MATCH_UNCERTAIN` rate.
That conservative abstention rate is intentional. The policy is frozen only as
a candidate for fresh challenge validation.

Policy artifact:

- `resolver_policy_candidate_v1.json`
- SHA-256: `80ef018df79eefea10a3e336968027bc64bdd89c334548a500453a7947f1cbea`
- status: `CANDIDATE_POLICY_ONLY`
- production status: `NOT_PRODUCTION_ACTIVATED`

## Limitations and next gate

- Calibration and duration boundaries use the same 50-track universe.
- Human coverage is targeted and incomplete; 8/14 selected conservative
  candidates lack direct human labels.
- Sol can share metadata-only failure modes and is not human ground truth.
- Some YouTube descriptions are abbreviated, limiting provenance fields.
- No audio-equivalence check was attempted.
- No new YouTube searches or media/model pipeline work occurred.

The required next goal is a separately frozen fresh challenge set on which the
already-frozen candidate policy is run without tuning, followed by blinded Sol
review and targeted human audit.

## Final boundary

`STAGE5B1B_POLICY_READY_FOR_FRESH_CHALLENGE_VALIDATION`

Audio downloads = 0. Video downloads = 0. New YouTube searches = 0. Stage 5A
calls = 0. CLAP calls = 0. MuQ calls = 0. Production AUTO_MATCH activation =
false.
