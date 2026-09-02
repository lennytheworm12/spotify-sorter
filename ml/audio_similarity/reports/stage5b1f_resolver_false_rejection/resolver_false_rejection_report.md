# Stage 5B.1F Resolver False-Rejection and Candidate-Preference Diagnostic

## Outcome

`STAGE5B1F_RESOLVER_FALSE_REJECTION_DIAGNOSTIC_COMPLETE`

The unchanged Q0 resolver replays exactly at 42 AUTO_MATCH / 8 MATCH_UNCERTAIN. No discovery, resolver, threshold, parser, label, or candidate artifact changed.

The headline diagnosis is that Q0's 97.6% human-safe Recall@5 is `40/41` human-evaluable tracks—not `49/50`. Q0 contains a known human-safe candidate on 40/50 tracks, and the resolver selects a known-safe candidate on 38/50.

## Counts

- Q0 tracks with a known human-safe top-five candidate: 40/50
- tracks selecting a known human-safe candidate: 38/50
- strict false rejections (MATCH_UNCERTAIN despite known SAFE in-pool): 0
- confirmed human-label downgrades: 4
- selected-candidate human-evidence gaps with a known SAFE alternative: 1

## Candidate-preference cases

| Track | Selected label | Better label | Primary cause |
|---|---|---|---|
| s5b1c_004 — Kill Bill | ACCEPTABLE (`sk6rMb8OsQY`) | IDEAL (`SQnc1QibapQ`) | DURATION_PRECEDES_PROVENANCE_AND_SOURCE_IN_ORDERING |
| s5b1c_024 — Makeba - Ian Asher Remix | ACCEPTABLE (`MYBN-XP2CUs`) | IDEAL (`VI9gIPBH_dM`) | FALLBACK_ONLY_CASCADE_PREVENTS_CROSS_TIER_RERANK |
| s5b1c_035 — Enchanted (Taylor's Version) | UNCERTAIN (`q5YJ9JREVRk`) | IDEAL (`igIfiqqVHtA`) | DURATION_PRECEDES_PROVENANCE_AND_SOURCE_IN_ORDERING |
| s5b1c_044 — Home | UNREVIEWED (`-zpEMkKJd0M`) | ACCEPTABLE (`DQJpFVzeNp8`) | FALLBACK_ONLY_CASCADE_PREVENTS_CROSS_TIER_RERANK |
| s5b1c_049 — Shinunoga E-Wa | ACCEPTABLE (`sABVNz31WA0`) | IDEAL (`dawrQnvwMTY`) | OFFICIAL_MUSIC_VIDEO_DURATION_RESTRICTION |

Four are confirmed human-label downgrades (`004`, `024`, `035`, `049`). Track `044` is an evidence gap: the selected Art Track is unreviewed while an alternative is human-ACCEPTABLE, so the selected source is not proven worse.

## Why the better candidate lost

- `004 Kill Bill`: both candidates pass Balanced V1. The lyric upload is one duration band closer, and duration is ordered before the official artist/channel and Official Audio source evidence.
- `024 Makeba — Ian Asher Remix`: the artist-channel upload is human-IDEAL but classified OTHER and rejected by Balanced. 1C-B later makes it eligible, but the cascade stops at Balanced's human-ACCEPTABLE lyric selection and never reranks it.
- `035 Enchanted (Taylor's Version)`: the official Taylor Swift lyric video is human-IDEAL, but a 739-view third-party upload whose description contains 'Provided to YouTube by' metadata is 3 seconds closer and wins. Duration and permissive provenance classification overpower the official channel.
- `044 Home`: the later source-neutral candidate is human-ACCEPTABLE, but the Tier-1 Art Track wins before cross-tier comparison. The selected Art Track lacks a human label, so this is not a confirmed resolver error.
- `049 Shinunoga E-Wa`: an official artist upload labeled human-IDEAL is parsed as an Official Music Video despite `(Not a MV)`, then rejected by the two-second music-video duration rule; a third-party lyric upload wins.

## Duration and hierarchy audit

Duration is over-dominant for candidate preference, not for strict Q0 false rejection. It defeats materially stronger official/artist provenance in three preference cases (`004`, `035`, `049`). In `004` and `035`, both candidates are otherwise eligible and duration is the first lexicographic discriminator. In `049`, the music-video-specific duration gate combines with a source-classification presentation error.

The implementation otherwise follows its documented order literally: duration is evaluated before provenance/source. The evidence suggests that this frozen order can conflict with the product goal of preferring canonical clean sources once recording identity and version are already established.

The John Mayer `20Ov0cDPZy8` example is cross-strategy context, not a Q0 false rejection: it appeared only under Q1/Q2/Q3. Q0 already selected human-IDEAL `sKzoEwQaF7Y`.

## Remaining 8-track tail

| Track | Classification | Decisive blocker | Route |
|---|---|---|---|
| s5b1c_021 — Bad Habits - FISHER Remix | TRUE_DISCOVERY_FAILURE | Q0 returned zero candidates | targeted_rediscovery |
| s5b1c_029 — The Night We Met - Live at the Ryman | TRUE_DISCOVERY_FAILURE | requested Ryman recording is not established | targeted_rediscovery |
| s5b1c_030 — Pompeii - Acoustic Version | METADATA_INSUFFICIENT | acoustic recording identity is unproven | audio_comparison_or_better_metadata |
| s5b1c_032 — Landslide - 2015 Remaster | TRUE_DISCOVERY_FAILURE | Q0 returned zero candidates | targeted_rediscovery |
| s5b1c_033 — Sweet Child O' Mine - 2022 Remaster | METADATA_INSUFFICIENT | 2022 remaster evidence is absent | structured_release_metadata_or_audio_comparison |
| s5b1c_034 — I Wanna Dance with Somebody (Who Loves Me) - 2000 Remaster | TRUE_DISCOVERY_FAILURE | Q0 returned zero candidates | targeted_rediscovery |
| s5b1c_040 — Another Love - Slowed Down | TRUE_DISCOVERY_FAILURE | no result establishes the released Slowed Down recording | targeted_rediscovery |
| s5b1c_041 — Dandelions - slowed + reverb | METADATA_INSUFFICIENT | modification rate/recording identity is unproven | tier3_audio_comparison |

- strong resolver-only recoveries supported by current human evidence: 0
- possible resolver-only recoveries supported by current human evidence: 0
- metadata-insufficient: 3
- true discovery failures: 5

No current MATCH_UNCERTAIN track contains a human-confirmed SAFE Q0 candidate. Three tails (`030`, `033`, `041`) have plausible but Sol-UNCERTAIN candidates whose exact recording identity is not proven by metadata. Five (`021`, `029`, `032`, `034`, `040`) are discovery failures in this frozen Q0 run, including three zero-result pools.

## Coverage ceiling

- current mechanical coverage: 42/50 = 84.0%
- if all strong resolver recoveries succeeded: 42/50 = 84.0%
- if all strong + possible resolver recoveries succeeded: 42/50 = 84.0%

These ceilings are diagnostic, not achieved coverage. With the present frozen human evidence, there is no defensible resolver-only path from 84% to 90%. The remaining coverage gap requires better candidate discovery, stronger release metadata, or audio comparison—not weaker identity gates.

## Highest-leverage next resolver experiment

If candidate-selection quality is the objective, test one isolated global preference stage that compares every conflict-free candidate made eligible by any tier, and places corroborated official/artist provenance ahead of small within-safe-band duration differences. It should also require Topic/Art Track provenance to be internally consistent rather than trusting copied `Provided to YouTube by` text.

This experiment is supported by multiple cases (`004`, `024`, `035`, `049`) but would improve source quality, not demonstrated 42/50 mechanical coverage. Negative controls must preserve wrong remix/remaster, cover, live/studio, slowed/reverb, sped-up, nightcore, bass-boosted, mashup, wrong-performer, and theatrical-edit rejections.

## Validation

- focused Stage 5B.1F tests: 5 passed
- resolver regression group: 62 passed
- full non-heavy `ml/audio_similarity` suite: 763 passed, 12 deselected
- expected warnings: 11 existing short-fixture librosa warnings
- Q0 replay: exact 42/8 with identical selected candidate IDs
- frozen input hash verification: passed

## Scope guards

- yt-dlp searches: 0
- Sol runs: 0
- human labels changed: 0
- audio/video downloads: 0
- resolver/query/parser/threshold changes: 0
- production activation: 0
