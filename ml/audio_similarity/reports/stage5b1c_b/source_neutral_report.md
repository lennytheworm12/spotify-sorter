# Stage 5B.1C-B — Source-Neutral Candidate Resolution

## Status

`STAGE5B1C_B_SOURCE_NEUTRAL_EVALUATED`

Source neutrality recovered 5 of the 15 candidates left unresolved after
Stage 5B.1C-A. Combined deterministic coverage is 40/50 (80%). This is a
coverage result, not a human-validated precision claim: the five selections
have frozen Sol support but no targeted human labels.

No discovery, Sol evaluation, human review, media download, Stage 5A call,
CLAP call, or MuQ call was performed.

## Frozen regressions

The evaluator hash-locks the committed 1C-A artifacts and performs a live
deterministic replay before 1C-B runs.

| Layer | AUTO_MATCH | MATCH_UNCERTAIN | Selected IDs |
| --- | ---: | ---: | --- |
| `POLICY_BALANCED_V1` | 29 | 21 | Exact frozen replay |
| `POLICY_TIER2_METADATA_FUSION_V1` | 6 | 15 | Exact frozen replay: 015, 016, 017, 026, 027, 043 |

The Balanced selected video IDs and all six 1C-A selected video IDs are
unchanged.

## Source-neutral design

The 1C-B stage runs only on the 15 tracks that remain unresolved after 1C-A:

```text
Balanced V1
    → 1C-A normalization/evidence fusion
        → 1C-B source-neutral fallback
```

The policy changes only the interpretation of source absence:

- recognized Topic/distributor/release provenance remains positive evidence;
- matching artist uploader/channel evidence remains positive corroboration;
- unknown or `OTHER` provenance contributes neutral evidence;
- explicit performer, cover, version, modification, or recording conflicts
  remain hard blockers;
- important absent target-version evidence remains a blocker;
- the general duration boundary remains 7 seconds;
- the Official Music Video duration boundary remains 2 seconds;
- the frozen 1C-A ordering is retained, so the experiment changes eligibility
  rather than introducing a new ranking policy.

`OTHER` is not universally admissible. It can pass only when it was the sole
remaining rejection after all stronger gates pass. One compatibility case also
uses frozen Tier-1 exact-title evidence to corroborate a known 1C-A multi-artist
prefix split; neither frozen layer is modified.

## Incremental result

| Measure | Result |
| --- | ---: |
| 1C-B attempted | 15 |
| 1C-B AUTO_MATCH | 5 |
| Remaining MATCH_UNCERTAIN | 10 |
| Combined AUTO_MATCH | 40/50 |
| Combined coverage | 80% |
| Gain over Balanced V1 | +22 percentage points (58% → 80%) |
| Gain over 1C-A baseline | +10 percentage points (70% → 80%) |

The measured result is one recovery larger than the four-track hypothesis.
Track 044 (`Home`) was also eligible because its strongest `OTHER` candidate
already passed title, performer, version, and the unchanged 7-second duration
gate.

## Recovered candidates

| Track | Selected video | Identity/version evidence | Duration delta | Source/provenance | Prior blocker | Frozen evidence |
| --- | --- | --- | ---: | --- | --- | --- |
| 020 `You & Me — Flume Remix` | `OUkkaqSNduU` | Exact structural title; Disclosure performer; Flume remix `MATCH` | 1.013 s | `OTHER`; Flume uploader/channel is positive corroboration | `OTHER` rejection only | Sol `IDEAL`; no human label |
| 022 `I Follow Rivers — The Magician Remix` | `oS6wfWu0JvA` | Exact structural title; Lykke Li performer; Magician remix `MATCH` | 4.000 s | `OTHER`; Lykke Li uploader/channel is positive corroboration | `OTHER` rejection only | Sol `IDEAL`; no human label |
| 025 `Something Just Like This — Alesso Remix` | `9gnyYxEWgi4` | Frozen Tier-1 exact title corroborates 1C-A multi-artist split; primary performer present; Alesso remix `MATCH` | 1.000 s | `OTHER`; unknown source is neutral | 1C-A title split + `OTHER` rejection | Sol `ACCEPTABLE`; no human label |
| 028 `Hotel California — Live on MTV, 1994` | `k4HWjQNN1K8` | Exact structural title; Eagles performer; live MTV 1994 `MATCH` | 3.000 s | `OTHER`; unknown source is neutral | `OTHER` rejection only | Sol `ACCEPTABLE`; no human label |
| 044 `Home` | `DQJpFVzeNp8` | Exact structural title; Edward Sharpe & The Magnetic Zeros performer; no version conflict | 6.800 s | `OTHER`; unknown source is neutral | `OTHER` rejection only | Sol `ACCEPTABLE`; no human label |

All five selected candidates are classified `OTHER`. Two have positive
uploader/channel corroboration and three have unknown-neutral provenance. No
selected candidate has an explicit recording-identity conflict.

Frozen evaluation composition:

```text
Sol IDEAL:       2
Sol ACCEPTABLE:  3
Sol WRONG:       0
Sol UNCERTAIN:   0

Human labeled:   0
Human unreviewed: 5
```

Sol is diagnostic evidence, not ground truth. The coverage increase is
demonstrated; safe production precision is not human-validated by this phase.

## Remaining unresolved tracks

| Track | Strongest frozen candidate | Decisive blocker after source neutrality | Additional blocker |
| --- | --- | --- | --- |
| 012 `Taki Taki` | `kxZYxojih3E` | Structural title parser mismatch | — |
| 021 `Bad Habits — FISHER Remix` | `oqoqeD48BD0` | Explicit wrong named remix | Duration >7 s |
| 023 `The Business — Vintage Culture & Dubdogz Remix` | `wJS9eb6_o00` | Requested remix evidence absent | — |
| 029 `The Night We Met — Live at the Ryman` | `7QADmsRUGgg` | Requested live/Ryman evidence absent | Duration >7 s |
| 030 `Pompeii — Acoustic Version` | `YX7joA8OLXA` | Primary performer evidence absent | Duration >7 s |
| 032 `Landslide — 2015 Remaster` | `k4M53xndqiU` | Requested remaster evidence absent | — |
| 033 `Sweet Child O' Mine — 2022 Remaster` | `D2gWc5Sw75w` | Requested remaster evidence absent | — |
| 034 `I Wanna Dance with Somebody — 2000 Remaster` | `id2-K3daNRQ` | Requested remaster evidence absent | — |
| 040 `Another Love — Slowed Down` | `ILy2HYcstRQ` | Duration >7 s | — |
| 041 `Dandelions — slowed + reverb` | `fXbfBUNJ9mY` | Duration >7 s | — |

The seven required negative controls (021, 029, 030, 032, 033, 040, 041)
remain unresolved. Wrong remixes, covers/wrong performers, missing remasters,
live/studio conflicts, slowed/reverb conflicts, nightcore, mashups, and duration
failures remain rejected in focused tests.

## Remaining metadata-only leverage

The frozen rows suggest a limited next metadata ceiling:

- three candidates are blocked primarily by the unchanged duration rule (023's
  exact requested remix candidate, 040, and 041), but any later duration work
  must be isolated and source/version aware;
- one candidate (012) may be recoverable by additional title parsing;
- the other six lack required version or performer evidence, or present an
  explicit wrong version, so source neutrality cannot safely recover them.

If all four plausible metadata cases were independently validated and safely
recovered, the observed challenge ceiling would be 44/50 (88%). This is a
diagnostic upper-bound estimate, not a recommendation to loosen thresholds.
The remaining tail increasingly requires better discovery, human review, or
future audio comparison rather than weaker metadata gates.

## Answer and recommendation

On this frozen challenge, treating unknown uploader/source provenance as
neutral rather than disqualifying increased automated coverage from 70% to
80% while preserving every explicit conflict and negative control. The answer
to the source-neutrality experiment is therefore **yes for coverage**, with no
known Sol-flagged unsafe selection.

Because none of the five recoveries has a human label, the recommended next
validation action is a small targeted human audit of these five selections
before treating 1C-B as production-safe. A later, separately frozen phase may
investigate source-aware duration behavior. This report does not begin that
work.

## Artifacts and reproducibility

- `source_neutral_candidate_features.json`: all 15 attempted tracks / 75 frozen
  candidate pairs, including prior and remaining gate reasons.
- `source_neutral_decisions.json`: selected candidates, evidence summaries,
  unresolved decisive blockers, regression proofs, and scope guards.
- `artifact_manifest.json`: hashes for frozen inputs, implementation, tests,
  and closeout artifacts.

Reproduce without network access:

```bash
cd ml/audio_similarity
uv run python -m audio_similarity.cli.stage5b1c_source_neutral \
  --config configs/stage5b1b_fresh_challenge.json \
  --tier2a-dir reports/stage5b1c_a \
  --output-dir reports/stage5b1c_b
```

## Tests

```text
Focused 1C-B:             16 passed
Stage 5A/5B regressions: 246 passed
Full non-heavy suite:    693 passed, 12 deselected
```

The full suite emitted 11 existing librosa warnings from MIR/residual tests.
There were no failures.
