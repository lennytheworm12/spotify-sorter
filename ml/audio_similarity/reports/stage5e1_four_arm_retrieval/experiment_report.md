# Stage 5E.1 four-arm retrieval comparison

**Status:** `REPRESENTATIONS_READY_HUMAN_REVIEW_PENDING`

## Controlled design

- A/C use the frozen music-specialized HTSAT-base checkpoint.
- B/D use the matched official general-audio HTSAT-tiny fusion checkpoint and identical frozen global/front/middle/back views.
- A versus C isolates centered-window versus full-song chunk-mean sampling within one checkpoint.
- B versus D isolates learned native AFF versus equal embedding mean within one checkpoint.
- Cross-pair comparisons retain a checkpoint and architecture confound and must not be described as pure aggregation effects.
- MuQ and the CLAP/MuQ weights are unchanged.

## Corpus and execution

- Frozen eligible tracks: 741
- Network downloads: 0
- First-run wall time: 2261.04 seconds
- Peak process RSS: 6.11 GiB
- Cache rerun: `PASSED`
- First-run ledger preserved by cache rerun: `True`
- Representation pathology detected: `False`
- Scratch cleanup: `PASSED`
- First-run ledger recovery: recorded transparently after the original cache-rerun helper replaced only the JSON ledger; SQLite vectors were unchanged, and the helper now hash-verifies ledger preservation.

| Representation | Successful vectors | Views | Recorded inference seconds |
| --- | ---: | ---: | ---: |
| A | 741 | 2223 | 13.22 |
| B | 741 | 2964 | 25.56 |
| C | 741 | 16539 | 693.10 |
| D | 741 | 2964 | 37.83 |
| MUQ | 741 | 2223 | 28.68 |

## Retrieval changes versus A

| Comparison | Mean shared Top-5 count | Mean Top-5 Jaccard |
| --- | ---: | ---: |
| B_CLAP_VS_A_CLAP | 0.429 | 0.052 |
| B_COMBINED_VS_A_COMBINED | 1.246 | 0.162 |
| C_CLAP_VS_A_CLAP | 1.174 | 0.150 |
| C_COMBINED_VS_A_COMBINED | 1.903 | 0.262 |
| D_CLAP_VS_A_CLAP | 0.695 | 0.086 |
| D_COMBINED_VS_A_COMBINED | 1.489 | 0.198 |
| A_CLAP_VS_A_COMBINED | 3.266 | 0.517 |

## Retrieval review

- Raw directional Top-5 relationships: 29640
- Unique unordered pairs: 11458
- Reused compatible owner labels: 219
- New judgments required: 11239
- Human status: `HUMAN_REVIEW_PENDING`

No arm is selected or production-activated by this experiment. Human review is evidence collection and no tuning is performed.
