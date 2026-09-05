# Stage 5B.1H — Canonical Source Recognition + Video-Padding Semantics

Status: `STAGE5B1H_CANONICAL_SOURCE_SEMANTICS_COMPLETE`

## Outcome

The frozen Stage 5B.1G control reproduced exactly at **42/50 AUTO_MATCH and 8/50 MATCH_UNCERTAIN**. Stage 5B.1H preserves all 50 decisions and all selected candidate IDs, so coverage remains **42/50 (84%)**.

Among the 42 selected candidates, frozen human evidence now records **39 SAFE**, **0 WRONG**, and **1 UNCERTAIN**; two selections remain without human evidence. These are evidence-availability counts, not a population precision estimate.

## Architectural decision

Stage 5B.1H records three orthogonal dimensions:

1. **Recording identity** — compatible, incomplete, or explicitly conflicting.
2. **Source canonicality** — strong, supported, or unknown. Recognized artist, label/distributor, Topic, and structured-release provenance is positive; unknown provenance remains neutral.
3. **Audio cleanliness / video-padding risk** — likely clean audio, low padding, possible padding, elevated/unknown padding, or outside the frozen 20-second limit.

This is a separate evidence layer. Frozen Stage 5B.1G remains responsible for eligibility and global ordering; source terminology cannot rescue a recording, performer, version, or unrequested-modification conflict.

## Source vocabulary

The parser uses a small explicit vocabulary: `Official Audio`, `Official Video`, `Official Music Video`, `Official MV`, `M/V`, `MV`, `Official Lyric Video`, `Lyric Video`, `Audio`, French `clip officiel` / `vidéo officielle`, and Spanish `video oficial` / `vídeo oficial`. Bare `Audio`, bare `M/V`, and bare lyric wording require provenance corroboration before becoming canonical.

Negation is evaluated first. `Not a MV`, `Not an MV`, `Unofficial Video`, `Not Official`, and `Fan Made Official Style` cannot create positive video-source evidence. No translation model, language detector, or external NLP dependency is used.

## Metrics

- legacy source classifications refined: 7
- selected canonicality: `{'CANONICAL_STRONG': 29, 'CANONICAL_SUPPORTED': 1, 'CANONICAL_UNKNOWN': 12}`
- selected padding/cleanliness: `{'CLEAN_AUDIO_LIKELY': 6, 'VIDEO_PADDING_HIGH_OR_UNKNOWN': 22, 'VIDEO_PADDING_LOW': 12, 'VIDEO_PADDING_POSSIBLE': 2}`
- selected normalized sources: `{'ART_TRACK_TOPIC': 1, 'LYRIC_VIDEO': 8, 'NEGATED_VIDEO_PRESENTATION': 1, 'OFFICIAL_AUDIO': 6, 'OFFICIAL_LYRIC_VIDEO': 11, 'OFFICIAL_MUSIC_VIDEO': 5, 'OTHER': 10}`
- selected IDs changed: 0
- known human WRONG introduced: 0

The source-classification count describes semantic refinements relative to the legacy broad source enum; it does not imply that 55 historical selections were wrong.

## Reviewed diagnostic cases

| Track | Recognized phrase | Normalized source | Canonicality | Duration delta | Padding risk | Selected | Human |
|---|---|---|---|---:|---|---:|---|
| `s5b1c_013` | `M/V` | `OFFICIAL_MUSIC_VIDEO` | `CANONICAL_STRONG` | 2.053s | `VIDEO_PADDING_LOW` | yes | `IDEAL` |
| `s5b1c_017` | `Official Lyric Video`, `Lyric Video`, `Lyric` | `OFFICIAL_LYRIC_VIDEO` | `CANONICAL_STRONG` | 5.747s | `VIDEO_PADDING_POSSIBLE` | yes | `IDEAL` |
| `s5b1c_025` | `Audio` | `OFFICIAL_AUDIO` | `CANONICAL_STRONG` | 3.000s | `CLEAN_AUDIO_LIKELY` | yes | `IDEAL` |
| `s5b1c_048` | `Official Video` | `OFFICIAL_MUSIC_VIDEO` | `CANONICAL_STRONG` | 16.800s | `VIDEO_PADDING_HIGH_OR_UNKNOWN` | yes | `IDEAL` |
| `s5b1c_049` | `Not a MV` | `NEGATED_VIDEO_PRESENTATION` | `CANONICAL_STRONG` | 6.427s | `VIDEO_PADDING_HIGH_OR_UNKNOWN` | yes | `IDEAL` |
| `s5b1c_050` | `clip officiel` | `OFFICIAL_MUSIC_VIDEO` | `CANONICAL_STRONG` | 5.773s | `VIDEO_PADDING_POSSIBLE` | yes | `IDEAL` |

`s5b1c_048` (PROVENZA) is interpreted as a compatible recording from a strongly canonical artist-controlled Official Video, while its 16.8-second difference is retained as elevated/unknown video-padding risk. The candidate remains eligible because frozen 1G already admitted it—not because 1H ignores duration.

`s5b1c_049` (Shinunoga E-Wa) records `Not a MV` as negated presentation evidence. Its artist-channel provenance may still be canonical, but `MV` does not generate a positive music-video classification.

## Padding-risk distribution

| Risk | Candidates | Selected | Selected human labels |
|---|---:|---:|---|
| `CLEAN_AUDIO_LIKELY` | 11 | 6 | `{'IDEAL': 5, 'UNREVIEWED': 1}` |
| `VIDEO_PADDING_LOW` | 24 | 12 | `{'IDEAL': 12}` |
| `VIDEO_PADDING_POSSIBLE` | 2 | 2 | `{'IDEAL': 2}` |
| `VIDEO_PADDING_HIGH_OR_UNKNOWN` | 126 | 22 | `{'ACCEPTABLE': 9, 'IDEAL': 11, 'UNCERTAIN': 1, 'UNREVIEWED': 1}` |
| `OUTSIDE_EXPERIMENTAL_DURATION_LIMIT` | 72 | 0 | `{}` |

## Selection and safety

- selections changed from Stage 5B.1G: **0**
- additional AUTO_MATCH decisions: **0**
- known negative controls newly eligible: **0** (1H preserves frozen eligibility)
- human-review queue: **0 candidates** (`NO_REVIEW_REQUIRED`)

The five newly reviewed 1G selections are all human `IDEAL`. The semantics explain them through generalized phrase and provenance rules; no artist, track, or video ID is present in runtime classification logic.

## Scope and recommendation

The refinement succeeds as an interpretation layer: obvious canonical sources are recognized consistently, while canonicality is no longer conflated with guaranteed clean audio. It should remain attached to downstream acquisition evidence so a later audio-validation/trimming stage can treat padding risk explicitly. This experiment does not justify broader eligibility, new searches, or real-library validation.

Scope guards: Q0 unchanged; searches 0; media downloads 0; Sol reruns 0; Stage 5A, CLAP, and MuQ calls 0; historical resolver policies unchanged.

## Verification

- focused Stage 5B.1H tests: `37 passed`
- resolver regression suite: `138 passed`
- full non-heavy suite: `836 passed, 12 deselected, 11 warnings`
