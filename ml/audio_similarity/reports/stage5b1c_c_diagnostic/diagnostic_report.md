# Stage 5B.1C-C remaining-tail diagnostic

Status: `STAGE5B1C_C_DIAGNOSTIC_COMPLETE`

This is a frozen, offline diagnosis. It does not implement or activate a new
resolver policy. No discovery, Sol evaluation, human review, media download,
Stage 5A call, CLAP call, or MuQ call was performed.

## Answer

The final ten tracks are not one homogeneous resolver problem:

- **2 are strong metadata-only opportunities**: `012` is a structural title
  parser failure; `023` is an exact named-remix Official Audio blocked only by
  the global duration boundary.
- **2 are plausible but risky metadata opportunities**: `034` would require
  independently grounded release-edition equivalence, and `041` is an exact
  slowed/reverb text match whose duration still cannot establish the precise
  modified recording.
- **2 are metadata-insufficient**: `030` and `033` contain plausible recordings,
  but the supplied fields cannot establish the requested acoustic/master
  identity.
- **4 are candidate-set failures**: `021`, `029`, `032`, and `040` do not expose
  a safely correct requested recording in the frozen top five.

The defensible metadata-only opportunity is therefore **84% as a strong-only
diagnostic ceiling** and **88% if both risky possibilities eventually prove
safe**. These are hypothetical ceilings, not achieved coverage or validated
precision. The current measured coverage remains **40/50 = 80%**.

## Frozen evidence and regression replay

The diagnostic verifies file hashes before replaying the full cascade.

| Evidence | SHA-256 |
|---|---|
| 1C-B candidate features | `f319e4d5288405ba6abdd3c2bde65d56ab429410d2f2a41d185c4d0457a97596` |
| 1C-B decisions | `67caf7cd35574bb75271e7950f4b5a105c22425804692073f0c630caf68c5eb3` |
| Tier-2 human review | `2d98a42513d30fb3ce49f89e481698913fb4ff09b047a6341cbf952cdd7cf2f0` |
| Tier-2 human-audit results | `26fbfc59fc7617fd54377fde099cabf9170f2c55946bd3046839ea4e7e8edcb5` |

Exact replay result:

| Stage | AUTO_MATCH | MATCH_UNCERTAIN | Exact candidate replay |
|---|---:|---:|---|
| Balanced V1 | 29 | 21 | yes |
| 1C-A incremental | 6 | 15 remain | same six IDs |
| 1C-B incremental | 5 | 10 remain | same five IDs |
| Combined | 40 | 10 | yes |

The preceding Tier-2 human audit also remains frozen at 11/11 reviewed: 5
`IDEAL`, 6 `ACCEPTABLE`, 0 `WRONG`, and 0 `UNCERTAIN`. None of the final ten
tracks has a frozen human candidate label, so their recoverability assessment
must not be called human-validated.

The unresolved IDs are derived from the replay, then checked against the
expected frozen tail:

`012`, `021`, `023`, `029`, `030`, `032`, `033`, `034`, `040`, `041`.

## Blocker aggregates

Counts below use the strongest semantically plausible candidate for each track.
The machine-readable artifact separately preserves the resolver's mechanical
"fewest failed gates" candidate. This distinction matters: for `023`, the
mechanically closest candidate is the wrong original mix, whereas the strongest
recording candidate is the exact requested Official Audio with a larger
duration delta.

| Frozen failed gate | Tracks affected | Primary blocker |
|---|---:|---:|
| Exact title / parser normalization | 4 | 1 |
| Primary performer evidence | 0 | 0 |
| Missing/incomplete version evidence | 4 | 4 |
| Explicit version conflict | 1 | 1 |
| Duration threshold | 6 | 4 |
| Official Music Video duration restriction | 0 | 0 |
| `OTHER` source rejection | 0 | 0 |
| Missing provenance | 0 | 0 |
| Explicit performer/cover conflict | 0 | 0 |

The zero source/provenance counts are important: 1C-B successfully removed
unknown source as a negative gate. The remaining tail is now dominated by
recording identity, version, duration, and candidate availability.

Across any of the five candidates—not just the strongest—track counts are:

| Gate seen on at least one candidate | Tracks |
|---|---:|
| Duration | 10 |
| Title/parser | 9 |
| Missing version | 7 |
| Explicit version conflict | 5 |
| Primary performer evidence | 3 |
| Official Music Video duration | 2 |
| Lyric provenance/view support | 2 |

Qualitative secondary patterns are:

- candidate-set quality: 4 tracks (`021`, `029`, `032`, `040`);
- remaster/reissue ambiguity: 3 (`032`, `033`, `034`);
- modified-audio identity: 2 (`040`, `041`);
- venue/performance identity: 1 (`029`);
- acoustic/multi-recording ambiguity: 1 (`030`).

Common strongest-candidate gate combinations:

| Combination | Tracks |
|---|---:|
| Duration only | 3 |
| Missing version only | 2 |
| Title only | 1 |
| Title + duration | 1 |
| Title + missing version | 1 |
| Title + missing version + duration | 1 |
| Version conflict + duration | 1 |

## Per-track diagnosis

| Track | Strongest candidate | Failed gates | Frozen evidence | Classification |
|---|---|---|---|---|
| `012` Taki Taki | `kxZYxojih3E`, rank 3 | title/parser | Sol `ACCEPTABLE`; no human label | `STRONG_METADATA_RECOVERY` |
| `021` Bad Habits — FISHER Remix | `rqVg1PpPSj8`, rank 1 | wrong named remix; duration | Sol `WRONG`; no human label | `CANDIDATE_SET_FAILURE` |
| `023` The Business — Vintage Culture & Dubdogz Remix | `1UESu4eyalA`, rank 1 | duration +14.764 s | Sol `IDEAL`; no human label | `STRONG_METADATA_RECOVERY` |
| `029` The Night We Met — Live at the Ryman | `N2K1LUWlF-4`, rank 1 | title; live/version absent; duration +66 s | Sol `UNCERTAIN`; no human label | `CANDIDATE_SET_FAILURE` |
| `030` Pompeii — Acoustic Version | `5_KBkAjyCOg`, rank 3 | title/parser; duration +35 s | Sol `UNCERTAIN`; no human label | `METADATA_INSUFFICIENT` |
| `032` Landslide — 2015 Remaster | `k4M53xndqiU`, rank 1 | remaster absent | Sol `WRONG`; no human label | `CANDIDATE_SET_FAILURE` |
| `033` Sweet Child O' Mine — 2022 Remaster | `D2gWc5Sw75w`, rank 4 | remaster absent | Sol `UNCERTAIN`; no human label | `METADATA_INSUFFICIENT` |
| `034` I Wanna Dance with Somebody — 2000 Remaster | `2dzf4T3RbEc`, rank 3 | title/parser; remaster absent | Sol `ACCEPTABLE`; no human label | `POSSIBLE_METADATA_RECOVERY` |
| `040` Another Love — Slowed Down | `G-1IQJvNQLk`, rank 2 | duration +14 s | Sol `WRONG`; no human label | `CANDIDATE_SET_FAILURE` |
| `041` Dandelions — slowed + reverb | `fXbfBUNJ9mY`, rank 1 | duration +15 s | Sol `UNCERTAIN`; no human label | `POSSIBLE_METADATA_RECOVERY` |

### `012` — mechanical parser limitation

The rank-3 candidate contains the correct track and complete credited artist
lineup, matches duration within 0.5 seconds, and carries no recording-version
conflict. The parser fails to separate the artist/feature prefix and Spanish
lyric-video wording from the structural title. Sol's `ACCEPTABLE` judgment is a
contextual interpretation that a deterministic parser can plausibly reproduce.

### `021` — requested remix absent from candidate set

Every result is a different named remix or a mashup. All five Sol labels are
`WRONG`. The explicit version conflict is correct and must remain a hard gate.
A targeted second query is more appropriate than policy relaxation or audio
comparison of known-wrong candidates.

### `023` — exact identity loses to a global duration gate

Rank 1 is the exact named remix, an Official Audio on Tiësto's channel, with
exact title, performer, and version `MATCH` evidence and no conflicts. Its sole
failure is +14.764 seconds. Sol marked it `IDEAL`. This is qualitatively
different from a third-party modified upload with the same duration delta and
justifies a future isolated experiment in evidence-conditioned duration—not a
global threshold increase.

### `029` — performance identity is not established

Rank 1 names the Ryman, but is 66 seconds short and lacks a date/release
identity. The other candidates are generic or explicitly different venues and
dates. Sol is uncertain on the Ryman result and wrong on the known different
performances. The top five do not establish the 2023 album performance; use
targeted rediscovery.

### `030` — acoustic recording ambiguity

Three candidates say Bastille acoustic but are 35–41 seconds shorter and lack
canonical release metadata. The only Art Track is by `waybackwhen`, not
Bastille. Sol is uncertain on the three plausible candidates. Correcting the
title parser would still leave a material information gap. Better discovery,
then audio comparison if necessary, is more defensible.

### `032` — wrong release and performances

The closest Art Track identifies the 1975 album release rather than the 2015
remaster. The remaining candidates are live or otherwise different. Sol marked
all five wrong. This is a discovery failure, not a reason to treat absent
remaster evidence as a match.

### `033` — plausible studio audio, unknown master

Two candidates look like the studio recording and are duration-compatible, but
neither says 2022 remaster. Sol is uncertain on both; the other three are wrong
alternatives. Metadata cannot identify the mastering. Targeted search or audio
comparison is needed.

### `034` — contextual release-equivalence hypothesis

The official `Single Version` Art Track is 1.4 seconds from the target and Sol
calls it `ACCEPTABLE` in the Greatest Hits context. However, the frozen fields do
not establish that `Single Version` equals `2000 Remaster`; the closer Art Track
explicitly says Dolby Atmos, a different mix. A future experiment could consume
independently grounded release-edition metadata, but should not hard-code this
textual equivalence.

### `040` — no candidate establishes the released slowed version

All candidates are third-party slowed edits. Nominal matches are 14–19 seconds
short; close-duration alternatives add reverb or clean modification. Sol marked
all five wrong. Targeted rediscovery is the correct next step.

### `041` — exact descriptors, ambiguous modification rate

Rank 1 exactly names performer, title, slowed, and reverb, but is 15 seconds
longer and unofficial. Other nominally identical edits range widely in length.
Sol is uncertain on the two closest candidates. This may support a narrowly
defined version-aware duration experiment, but audio comparison is more likely
to resolve the actual modification rate safely.

## Sol comparison

Sol is diagnostic evidence, not ground truth. Over these ten tracks:

| Gap interpretation | Tracks |
|---|---:|
| Resolver could likely encode the same reasoning deterministically | 2 |
| Sol contextual evidence-weighting advantage | 1 |
| Metadata insufficient even for Sol | 3 |
| Candidate set itself inadequate | 4 |

The semantic advantage is narrow: Sol can connect `Single Version`, Greatest
Hits context, and duration for `034`, but the available fields still do not
prove master equivalence. In seven cases, Sol is also uncertain/wrong or the
candidate set is inadequate; there is no semantic shortcut around missing
information.

## Metadata ceiling and next work

| Scenario | Hypothetical AUTO_MATCH | Diagnostic ceiling |
|---|---:|---:|
| Current frozen resolver | 40/50 | 80% measured |
| Recover only strong opportunities (`012`, `023`) | 42/50 | 84% hypothetical |
| Also recover plausible/risky (`034`, `041`) | 44/50 | 88% hypothetical |

Recommended separation of future work:

1. A parser-only experiment for `012`-class artist-prefix/feature formatting.
2. A separate identity-first duration experiment limited to exact performer,
   exact named-version, no-conflict, recognized Official Audio evidence like
   `023`. Do not globally raise the duration threshold.
3. Independently grounded release metadata before considering `034`-style
   remaster/single-version equivalence.
4. Targeted second search for `021`, `029`, `032`, and `040`.
5. Better discovery and/or Tier-3 audio comparison for `030`, `033`, and `041`.

The safe metadata-only path from 80% is therefore credibly toward **84%**. The
path to **88%** exists only as a risky hypothesis and needs new evidence. Trying
to force the other six cases through broader metadata rules would weaken
recording-identity safety.

## Reproduction

From `ml/audio_similarity`:

```bash
uv run python -m audio_similarity.cli.stage5b1c_diagnostic
uv run pytest tests/test_stage5b1c_diagnostic.py -q
```

The complete 50-candidate evidence, raw gates, frozen Sol/human joins, and
aggregate calculations are in `remaining_tail_diagnostic.json`.
