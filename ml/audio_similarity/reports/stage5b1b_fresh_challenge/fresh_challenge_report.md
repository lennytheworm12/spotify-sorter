# Stage 5B.1B Part C — Fresh Challenge Validation

## Status

`STAGE5B1B_CONSERVATIVE_POLICY_VALIDATED`

The implementation, frozen discovery, unchanged feature extraction, dual-policy
execution, blinded Sol review, and all 41 targeted human judgments are complete.
The frozen pre-label evaluator selects `POLICY_CONSERVATIVE_V1` as the candidate
policy for a later acquisition smoke. Production AUTO_MATCH remains inactive.

## Starting point and freeze boundary

- Starting branch: `ml/stage5b1b-policy-calibration`
- Starting commit: `88b71b4724e43ab37e3d6417a99deccfd1b802a7`
- Validation branch: `ml/stage5b1b-fresh-challenge`
- Policy-freeze checkpoint: `dd27855`
- Manifest-freeze checkpoint: `cffd5d9`
- Harness checkpoint: `d868ce6`
- Pre-Sol evidence checkpoint: `b65dabe`

The exact Part B definitions were committed before the challenge manifest was
created. Both policy identities below are canonical SHA-256 hashes over the
policy definition plus their shared frozen duration boundaries, derived from
the pre-challenge policy bundle:

- `POLICY_CONSERVATIVE_V1`: `f73d936432dae977cc8cff70706e5c41427411d2ebb1db15e55a2dc710eab65c`
- `POLICY_BALANCED_V1`: `90be177c35160ef5cf6d59f69c0fffd3ec2f228d7e1a3630105f4bb5b723035b`
- Frozen policy bundle: `bbc527aa9a734b0aebbfafcb2775b479541a5e0248503627c14b8f429f708d5a`
- Part B selected-policy artifact preserved unchanged:
  `80ef018df79eefea10a3e336968027bc64bdd89c334548a500453a7947f1cbea`

The unchanged empirical duration bands remain 2/7/48 seconds. No thresholds,
version semantics, provenance rules, source ordering, or text parsing were
modified after challenge data became available.

## Fresh manifest

- Path: `reports/stage5b1b_fresh_challenge/challenge_tracks.json`
- SHA-256: `e2e9a1ab43f568dd9de853c2964f341ee0d0e2631ca87f732d0d4326ab990f79`
- Tracks: 50
- Prior DEV tracks checked: 25
- Prior calibration tracks checked: 50
- Normalized title + primary-artist overlap with DEV: 0
- Normalized title + primary-artist overlap with calibration: 0
- Exact normalized title overlap with either prior set: 0

The intentionally difficult set contains 61 distinct case tags. Its larger
groups include nine many-cover cases, seven multiple-artist cases, seven named
remixes, six straightforward studio baselines, five common titles, five K-pop
tracks, five featured-artist cases, five original-version competition cases,
four live tracks, four remasters, four explicit/clean ambiguity cases, and
international, diacritic, rerecording, acoustic, slowed, sped-up, reverb,
label-hosted, lyric, and music-video cases.

This is an engineering challenge set, not a population sample.

## yt-dlp discovery

- yt-dlp: `2026.08.19`
- Query: frozen `ytsearch5:` / quoted primary artist + normalized title +
  `official`
- Execution: sequential, one-second inter-track pacing
- Mode: `simulate=true`, `skip_download=true`, `download=false`
- Tracks attempted: 50
- Tracks with candidates: 50
- Tracks with zero candidates: 0
- Deduplicated candidates: 250
- Search failures: 0
- Tracks with warnings: 0
- Warning count: 0
- Elapsed discovery time: 107.58 seconds
- Discovery SHA-256:
  `95bb1ca905a05fcc4167da10e3dfd6cf267600a4dfb1898b491d28ba855e6fb4`

## Frozen policy outcomes before human review

| Policy | AUTO_MATCH | Coverage | MATCH_UNCERTAIN | Incremental over Conservative |
|---|---:|---:|---:|---:|
| Conservative | 8 | 16% | 42 | — |
| Balanced | 29 | 58% | 21 | 21 tracks / 42 points |

Conservative selected four Art Track/Topic and four Official Audio sources.
Balanced selected five Art Track/Topic, three Official Audio, nineteen Lyric
Video, and two Official Music Video sources. One track (`s5b1c_002`) was
AUTO_MATCHed by both policies but to different candidate IDs.

These are mechanical coverage results only. They are not a correctness verdict.

## Blinded Sol evaluation

- Model: `gpt-5.6-sol`
- Reasoning effort: high
- Codex CLI: `0.151.0`
- Tracks: 50/50
- Candidates: 250/250
- Evaluation errors: 0
- Forbidden tool/web events: 0
- Sol evaluation SHA-256:
  `b00ecb7c9ffb668b581e571065235676d62832c868fe6bed26812fbbd30f50ea`

Sol candidate labels were 48 IDEAL, 82 ACCEPTABLE, 99 WRONG, and 21
UNCERTAIN. Sol selected a candidate for 42 tracks (39 IDEAL and 3 ACCEPTABLE),
returned `NO_SAFE_CANDIDATE` for four tracks, and returned
`SOL_MATCH_UNCERTAIN` for four tracks.

Sol received only raw target/candidate metadata in deterministic shuffled
order. Search rank, YouTube video IDs, queries, case tags/rationale, feature
records, version parsing, source types, eligibility, policy definitions,
policy outcomes, and human labels were absent. The private candidate mapping
was stored separately. Sol is evaluation evidence, not human ground truth.

Relative to Sol labels on selected candidates:

| Policy | IDEAL | ACCEPTABLE | WRONG | UNCERTAIN |
|---|---:|---:|---:|---:|
| Conservative | 6 | 2 | 0 | 0 |
| Balanced | 18 | 10 | 1 | 0 |

The single Balanced/Sol-WRONG case is `s5b1c_039` (`Bloody Mary - Sped Up`)
and is mandatory human audit evidence, not a final failure conclusion. There
are twelve Balanced/Sol preferred-source disagreements.

## Targeted human audit

- Queue path: `reports/stage5b1b_fresh_challenge/human_audit_queue.json`
- Queue SHA-256:
  `50fa774766f913786cc5d706d28f42d61a1f64afa76e2a806efcad9525f517d4`
- Tracks represented: 28
- Candidate judgments required: 41
- Completed: 41
- Review path: `reports/stage5b1b_fresh_challenge/human_review.csv`
- Completed review SHA-256:
  `0342c46d4506994c61cf0b3e422f34f6d466bf6297a6b8973fd75f711884b842`
- Initial empty-review SHA-256, preserved as historical provenance:
  `3014995a90570f7b61e9dce50d1a25b65fb25225b677acb107bd0ae2795cbe61`

Selection includes the Balanced/Sol-WRONG candidate, all twelve meaningful
Balanced/Sol preferred-source disagreements, the one Conservative/Balanced
candidate disagreement, all Balanced lyric/music-video or weak-provenance
fallback selections, a deterministic 25% sample of otherwise-confident
Balanced/Sol agreements, and three Conservative/Sol agreement tracks.

The review CSV is blinded. It contains only Spotify target metadata, raw
candidate title/channel/uploader/duration/views/description, YouTube URL/video
ID, and human label/note fields. It omits search rank, policies, features,
eligibility, Sol labels/reasons, audit reasons, and case rationale.

## Human evaluation and decision

`IDEAL` and `ACCEPTABLE` count as SAFE, `WRONG` as UNSAFE, and `UNCERTAIN` as
UNRESOLVED. The 41 candidate judgments contain 22 IDEAL, 18 ACCEPTABLE, zero
WRONG, and one UNCERTAIN. Four candidate notes are preserved verbatim in the
review CSV.

Human-audited selected-candidate outcomes were:

| Policy | IDEAL | ACCEPTABLE | WRONG | UNCERTAIN | Selected but unaudited |
|---|---:|---:|---:|---:|---:|
| Conservative | 5 | 1 | 0 | 1 | 1 |
| Balanced | 16 | 11 | 0 | 1 | 1 |

The 21 Balanced-only AUTO_MATCH tracks were all audited: 10 were IDEAL and 11
were ACCEPTABLE, with zero WRONG and zero UNCERTAIN. Thus the incremental
Balanced expansion itself produced no known unsafe or unresolved selection in
this targeted audit.

The sole human UNCERTAIN AUTO_MATCH is `s5b1c_035`, candidate `q5YJ9JREVRk`.
Both Conservative and Balanced select that same candidate. One additional
selection shared by both policies (`s5b1c_019`, candidate `kAt6H_JkVxQ`) was not
in the targeted human queue and remains explicitly unaudited.

The decision function was frozen in commit `d868ce6`, before challenge labels
were available. It emits the Conservative verdict whenever a Balanced-selected
candidate is human UNCERTAIN, while Conservative only fails on a human WRONG.
Applying that unchanged rule yields:

`STAGE5B1B_CONSERVATIVE_POLICY_VALIDATED`

This result is intentionally not post-reveal reinterpreted as Balanced
validation, even though the only uncertainty is shared and all Balanced-only
selections were human SAFE. Those facts remain important limitations for the
next acquisition-smoke design.

## Boundaries and limitations

- Candidate correctness remains metadata-only; no audio-equivalence validation
  was performed.
- Approximate Spotify-style target durations were frozen before discovery;
  any human-observed metadata issue is validation evidence and must not cause
  an in-place policy or manifest change.
- The audit is targeted plus deterministic random safety samples, not an
  exhaustive human review or population-precision estimate.
- One AUTO_MATCH shared by both policies was not included in the targeted human
  queue; one other shared AUTO_MATCH was human UNCERTAIN.
- Sol and deterministic policies may share metadata-only failure modes.
- No challenge-driven rule, threshold, duration band, parser, or source-order
  change is permitted in this validation iteration.

Audio downloads = 0. Video downloads = 0. Stage 5A calls = 0. CLAP calls = 0.
MuQ calls = 0. Production AUTO_MATCH activation = false.

## Verification

- Focused fresh-challenge and review-workbench tests: 17 passed.
- All Stage 5B.1B regressions: 120 passed.
- Full non-heavy `ml/audio_similarity` suite: 657 passed, 12 deselected,
  0 failures, 0 errors, and 11 pre-existing numerical-library warnings in
  58.23 seconds.
- Isolated Chromium verification covered desktop and 390-pixel mobile layouts,
  immediate label autosave, debounced note autosave, reload/resume persistence,
  progress accounting, deterministic candidate-order blinding, direct YouTube
  links, export behavior, horizontal overflow, and console errors/warnings.
- Five-axis review covered correctness, readability, architecture, security,
  and bounded performance. Required findings were resolved by binding the Sol
  runtime to its frozen feature/decision hashes and validating saved Sol and
  private-mapping track/candidate coverage fail-closed.
- No dependency, application runtime Sol integration, secret, media file, or
  production resolver activation was introduced.
