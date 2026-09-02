# Stage 5B.1C-A — Tier-2 Metadata Normalization and Evidence Fusion

Status: `STAGE5B1C_A_NORMALIZATION_PROCEED`

This phase evaluates whether deterministic metadata interpretation can recover
mechanical failures after frozen `POLICY_BALANCED_V1`, without changing Tier 1,
allowing arbitrary `OTHER` sources, or relaxing duration gates.

## Frozen evidence and regression

The evaluation consumed only committed Stage 5B.1B fresh-challenge artifacts.
No yt-dlp discovery, Sol evaluation, human review, media download, Stage 5A
materialization, CLAP inference, or MuQ inference was run.

| Frozen input | SHA-256 |
|---|---|
| `challenge_tracks.json` | `e2e9a1ab43f568dd9de853c2964f341ee0d0e2631ca87f732d0d4326ab990f79` |
| `challenge_ytdlp_discovery.json` | `95bb1ca905a05fcc4167da10e3dfd6cf267600a4dfb1898b491d28ba855e6fb4` |
| `challenge_candidate_features.json` | `451e72e27c0b52c3b6109f57ea0f5c7a3421271f3283b1f1232082160c37a08c` |
| `challenge_policy_decisions.json` | `58181c40bd54a8d4fabbc8d627ddaee6ccf7b5812a17331fe9c8d6600357fe87` |
| `frozen_policy_definitions.json` | `bbc527aa9a734b0aebbfafcb2775b479541a5e0248503627c14b8f429f708d5a` |
| `sol_evaluations.json` | `b00ecb7c9ffb668b581e571065235676d62832c868fe6bed26812fbbd30f50ea` |
| `human_review.csv` | `0342c46d4506994c61cf0b3e422f34f6d466bf6297a6b8973fd75f711884b842` |

The original feature dataset was replayed through the hash-bound frozen
Balanced implementation. The replay was exactly equal to the saved decision
artifact, including selected candidate IDs:

```text
POLICY_BALANCED_V1
AUTO_MATCH       29
MATCH_UNCERTAIN  21
coverage         58%
```

Tier 2 is a separate compatibility path. The frozen Stage 5B.1B parser,
features, policy definition, resolver implementation, decisions, and artifacts
were not edited.

## Tier-2 feature architecture

Schema: `stage5b1c-tier2-candidate-features-v1`

Normalization version: `stage5b1c-tier2-normalization-v1`

Policy ID: `POLICY_TIER2_METADATA_FUSION_V1`

Tier 2 derives independent, raw-backed fields for:

- structural target and candidate core titles;
- harmless source/presentation descriptors;
- normalized target performer aliases and credited/featured performers;
- performer evidence from title, uploader, channel, and distributor metadata;
- target-relative version descriptors and `MATCH` / `ABSENT` / `CONFLICT`;
- provenance source for version evidence;
- original numeric duration and frozen duration boundaries;
- source type and raw Art Track provenance;
- relative-view evidence recomputed only after corrected identity eligibility.

Implemented normalization includes Unicode normalization, case, punctuation,
quotes, whitespace, leading articles, `feat.` / `ft.` / `featuring`, `&` / `and`,
source suffixes, non-Latin display additions, `Twin Ver.` / `TwinVer.` /
`Twin Version`, and exact venue/year formatting.

Material recording descriptors remain structured evidence rather than noise,
including remix, live, remaster, acoustic, slowed, reverb, instrumental,
karaoke, radio edit, extended versions, and named qualifiers.

Distributor evidence is used only when backed by Topic, `Provided to YouTube
by`, or structured release metadata. Missing version evidence remains missing;
it is never inferred merely because an upload looks canonical.

## Unchanged safety gates

Tier 2A retains these frozen Balanced limits:

```text
general duration maximum:       7 seconds
Official Music Video maximum:   2 seconds
lyric relative-view minimum:    0.001
arbitrary OTHER sources:        rejected
explicit performer conflict:    rejected
explicit version conflict:      rejected
important version ABSENT:       rejected
```

Corrected eligibility causes relative-view evidence to be recomputed from raw
committed view counts. This repairs the `Iris` lyric candidate's missing weak
evidence without changing the `0.001` threshold.

## Recovered tracks and before/after evidence

| Track | Selected candidate | Frozen Tier-1 evidence | Tier-2 evidence allowing recovery | Sol | Human |
|---|---|---|---|---|---|
| `s5b1c_015` ANTIFRAGILE | `ZNEuWldWPD4`, rank 2 | exact title false | `antifragile = antifragile`; LE SSERAFIM from title and structured description; lyric Δ0.556s | ACCEPTABLE | unaudited |
| `s5b1c_016` Supernova | `WXx5-HGERcg`, rank 5 | exact title false | `supernova = supernova`; aespa from title and structured description; lyric Δ0.120s | ACCEPTABLE | unaudited |
| `s5b1c_017` Cupid – Twin Ver. | `62TrmUvQGjo`, rank 4 | exact title false; Twin version unparsed | `cupid = cupid`; `Twin Version = Twin Ver.`; explicit FIFTY FIFTY; lyric Δ1.747s | ACCEPTABLE | unaudited |
| `s5b1c_026` Free Fallin' – Nokia 2007 | `sKzoEwQaF7Y`, rank 1 | exact title false; live version ABSENT | `free fallin = free fallin`; exact live venue/year MATCH; John Mayer from uploader/channel/distributor metadata; Art Track Δ0.267s | IDEAL | unaudited |
| `s5b1c_027` Slow Dancing – Nokia 2007 | `aEi646akxko`, rank 1 | false performer conflict; exact title false; performer missing; live version ABSENT | corrected top-level title parsing; exact venue/year MATCH; John Mayer uploader/channel evidence; Art Track Δ0.853s | IDEAL | unaudited |
| `s5b1c_043` Iris | `zDOILKOOUCo`, rank 4 | false performer conflict from leading article; lyric views unavailable | `The Goo Goo Dolls = Goo Goo Dolls`; uploader/channel agreement; recomputed relative views `0.675477`; lyric Δ0.467s | IDEAL | unaudited |

Recovery mechanisms overlap:

```text
STRUCTURAL_TITLE_NORMALIZATION                 5 selections
PERFORMER_ALIAS_OR_PROVENANCE_FUSION           2 selections
VERSION_NORMALIZATION_OR_PROVENANCE_FUSION     2 selections
```

## Coverage result

```text
Tier-2 attempted tracks:       21
Tier-2 AUTO_MATCH:              6
Tier-2 MATCH_UNCERTAIN:        15

Tier 1 + Tier 2 AUTO_MATCH:    35 / 50
combined coverage:             70%
absolute coverage increase:   +12 percentage points
relative unresolved reduction: 6 / 21 = 28.6%
```

Frozen Sol labels on selected Tier-2 candidates were:

```text
IDEAL:       3
ACCEPTABLE:  3
WRONG:       0
UNCERTAIN:   0
```

Sol is diagnostic evidence, not ground truth. None of the six candidates has a
human label in the frozen targeted audit, so the recovery count is not a
validated precision estimate and is not production activation evidence.

## Cases intentionally still unresolved

| Tracks | Reason Tier 2A stops |
|---|---|
| `012` | normalized title remains noisy and closest candidate is noncanonical `OTHER` |
| `020`, `022`, `025`, `028` | plausible candidates require the explicitly deferred `OTHER` fallback |
| `023` | correct-looking Official Audio remains outside the frozen 7-second duration gate |
| `044` | Official Music Video remains outside the frozen 2-second video gate |
| `021` | candidates are wrong named remixes or mashups; explicit conflicts remain |
| `029` | requested Ryman live identity remains absent/ambiguous and durations conflict |
| `030` | acoustic candidates remain weakly sourced with substantial duration differences |
| `032`, `033`, `034` | requested remaster evidence remains absent; canonical provenance does not invent it |
| `040`, `041` | modified-audio candidates remain outside the frozen duration gate or metadata-ambiguous |

All required negative controls (`021`, `029`, `030`, `032`, `033`, `040`, and
`041`) remain `MATCH_UNCERTAIN`.

## Safety interpretation and recommendation

The result answers the bounded research question positively: deterministic
normalization and evidence fusion alone recover 6 of 21 Tier-1 uncertainties,
raising observed metadata resolver coverage from 58% to 70%, without relaxing
source or duration thresholds and without accepting any frozen Sol-WRONG or
Sol-UNCERTAIN selection.

Recommendation: **proceed** with this Tier-2 normalization candidate, subject to
targeted human validation before any production activation. Broader `OTHER`
fallback, duration relaxation, and audio-based Tier 3 remain separate future
experiments and were not implemented here.

## Verification

- Implementation checkpoint: `e3c9504` on
  `ml/stage5b1c-a-tier2-normalization`.
- Focused Tier-2 tests: 20 passed.
- Stage 5B.1B + Stage 5B.1C regressions: 140 passed.
- Full non-heavy `ml/audio_similarity` suite: 677 passed, 12 deselected,
  11 pre-existing numerical-library warnings, 0 failures, 0 errors.
- Deterministic evaluation is asserted by repeated in-memory equality of both
  feature and decision artifacts.
- Five-axis review covered correctness, readability, architecture, security,
  and bounded performance. The decision artifact was reduced to references and
  compact evidence summaries rather than duplicating the complete feature
  dataset. Explicit cover conflicts and featured-artist presentation received
  additional negative/normalization tests during review.
- No external dependency, network call, secret, runtime LLM, or production
  policy activation was introduced.

## Reproduction

From `ml/audio_similarity`:

```bash
uv run python -m audio_similarity.cli.stage5b1c_tier2
```

Machine-readable outputs:

- `reports/stage5b1c_a/tier2_candidate_features.json`
- `reports/stage5b1c_a/tier2_decisions.json`

Media/model activity remained zero:

```text
audio downloads = 0
video downloads = 0
Stage 5A calls = 0
CLAP calls = 0
MuQ calls = 0
production AUTO_MATCH activation = false
```
