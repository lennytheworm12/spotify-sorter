# Stage 5B.1C-C strong metadata recovery

Status: `STAGE5B1C_C_STRONG_METADATA_EVALUATED`

The isolated strong-metadata fallback recovered both diagnostic targets. The
measured frozen challenge result is **42/50 = 84% AUTO_MATCH coverage**, an
absolute gain of **4 percentage points** over the frozen 40/50 baseline.

These two selections have frozen Sol support but no human labels. They are
queued for human review and are not production-activated.

## Frozen regression

The implementation verifies all frozen inputs and replays the complete existing
stack before attempting 1C-C.

| Stage | AUTO_MATCH | Remaining | Result |
|---|---:|---:|---|
| Balanced V1 | 29 | 21 | exact decisions replayed |
| 1C-A incremental | 6 | 15 | same six candidate IDs |
| 1C-B incremental | 5 | 10 | same five candidate IDs |
| Combined before 1C-C | 40 | 10 | 80% |
| 1C-C incremental | 2 | 8 | measured |
| Combined after 1C-C | 42 | 8 | 84% |

No pre-existing selection changed.

## Generalized rules

### `STRONG_PRESENTATION_EQUIVALENCE_V1`

This rule removes a trailing parenthesized `with`/`feat` credit only when every
parsed name is already present in the target's credited artist list. It can
also recognize a reordered, explicitly delimited performer prefix when every
name is credited.

After removing those credits, existing structural parsing removes only known
source-presentation text such as `Lyrics` or `LETRA VIDEO OFICIAL`. The final
core title must match exactly after deterministic Unicode and punctuation
normalization.

The rule does not use fuzzy similarity and does not remove recording-version
terms. An unknown credited performer prevents the equivalence.

### `STRONG_OFFICIAL_AUDIO_VERSION_DURATION_V1`

The normal duration boundary remains exactly 7 seconds. A separate 15-second
experimental cap is available only when all of these conditions hold:

- exact structural core title;
- primary performer match;
- no performer or cover conflict;
- one or more explicit target-version relationships, all `MATCH`;
- no `ABSENT` or `CONFLICT` version evidence;
- source classified `OFFICIAL_AUDIO`;
- positive corroborated uploader/channel/release provenance;
- no unrequested modified-audio marker;
- no slowed, sped-up, reverb, live, acoustic, instrumental, karaoke, mashup,
  nightcore, or bass-boosted target family;
- duration is above 7 seconds but no more than 15 seconds.

The cap is evidence-bound:

- maximum delta among the 11 existing human-safe Tier-2 selections: 6.8 s;
- diagnosed strong Official Audio outlier: 14.764 s;
- experimental cap: `ceil(14.764) = 15 s`.

Thus the existing human-safe distribution continues to support the ordinary
7-second gate. The larger cap is not a global threshold change.

## Incremental selections

### `s5b1c_012` — Taki Taki

Selected candidate: `kxZYxojih3E`, rank 3

Frozen Sol label: `ACCEPTABLE`

Human label: unavailable

Before 1C-C:

- 1C-B rejection: `normalized structural core title does not match`;
- target core retained `(with Selena Gomez, Ozuna & Cardi B)` as title text;
- candidate expressed the same people in the performer prefix;
- candidate used `LETRA VIDEO OFICIAL` presentation text;
- duration delta: 0.5 s;
- source: `OTHER`, already neutral under frozen 1C-B;
- primary performer: matched;
- version conflicts: none;
- explicit modification conflicts: none.

After validated credit-presentation removal, both structural titles are exactly
`taki taki`. Only the title/parser gate is waived.

The sibling bass-boosted candidate is not admitted: the new feature extractor
records `bass_boosted` as an explicit unrequested modification and adds a hard
rejection reason.

### `s5b1c_023` — The Business — Vintage Culture & Dubdogz Remix

Selected candidate: `1UESu4eyalA`, rank 1

Frozen Sol label: `IDEAL`

Human label: unavailable

Before 1C-C:

- 1C-B rejection: duration exceeds the 7-second boundary;
- duration delta: 14.764 s;
- core title: exact;
- primary performer: exact;
- requested named remix: explicit `MATCH`;
- source: `OFFICIAL_AUDIO`;
- uploader/channel provenance: Tiësto, positively corroborated;
- version conflicts or missing evidence: none;
- modified-audio conflicts: none.

Only the duration gate is waived under the 15-second contextual cap. The
mechanically closer original mix remains rejected because its requested remix
evidence is `ABSENT`.

## Safety analysis

| Unsafe family | Can the new rule admit it? | Protection |
|---|---|---|
| Wrong remix | No | every target version must explicitly `MATCH`; conflict remains hard |
| Cover | No | explicit cover/performer evidence remains hard; cover marker is also a modification conflict |
| Different live performance | No | live/studio conflict remains; live is excluded from duration flexibility |
| Wrong remaster | No | missing evidence remains `ABSENT`; different remaster remains `CONFLICT` |
| Slowed/reverb edit | No | those families cannot receive contextual duration flexibility |
| Sped-up/nightcore/bass-boosted edit | No | explicit unrequested modification hard blocker |
| Mashup | No | mashup marker and structural title conflict remain hard |
| Different performer | No | primary performer match and no performer conflict are mandatory |

The tests exercise each of these paths. Weak/unknown-source candidates continue
to obey the ordinary 7-second duration gate. `OFFICIAL_AUDIO` alone is
insufficient.

## Required unresolved controls

All eight required controls remain `MATCH_UNCERTAIN`:

- `021` Bad Habits — FISHER Remix
- `029` The Night We Met — Live at the Ryman
- `030` Pompeii — Acoustic Version
- `032` Landslide — 2015 Remaster
- `033` Sweet Child O' Mine — 2022 Remaster
- `034` I Wanna Dance with Somebody — 2000 Remaster
- `040` Another Love — Slowed Down
- `041` Dandelions — slowed + reverb

This includes both `POSSIBLE_METADATA_RECOVERY` cases. No remaster equivalence,
targeted rediscovery, audio comparison, or broader duration behavior was added.

## Human review

The review queue contains exactly two blank judgments:

- `s5b1c_012` / `kxZYxojih3E`
- `s5b1c_023` / `1UESu4eyalA`

Review artifact: `strong_metadata_human_review.csv`.

The measured coverage gain is real resolver behavior, but its safety is not yet
human-validated. Sol is diagnostic evidence only.

## Validation

- Focused 1C-C tests: `13 passed`
- Stage 5B resolver regressions: `187 passed`
- Full non-heavy suite: `724 passed, 12 deselected`
- Five-axis review: no unresolved correctness, readability/architecture,
  security, performance, or test-quality findings

No network, yt-dlp, Sol, media download, Stage 5A, CLAP, or MuQ operation ran.

## Recommendation

Complete the two-row human audit before treating the additional 4 percentage
points as safety-validated. If both are `IDEAL` or `ACCEPTABLE`, preserve this
layer unchanged and design any targeted-rediscovery work as a separate stage.
Do not expand this policy toward `034` or `041` from the present evidence.

## Reproduction

From `ml/audio_similarity`:

```bash
uv run python -m audio_similarity.cli.stage5b1c_strong_metadata
uv run pytest tests/test_stage5b1c_strong_metadata.py -q
```
