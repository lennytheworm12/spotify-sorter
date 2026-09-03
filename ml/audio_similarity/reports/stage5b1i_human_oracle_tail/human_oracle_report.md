# Stage 5B.1I — Human Oracle Audit of the Remaining Top-5 Tail

Status: `STAGE5B1I_AWAITING_HUMAN_REVIEW`

## Frozen baseline

Stage 5B.1H replayed exactly at **42/50 AUTO_MATCH and 8/50 MATCH_UNCERTAIN**. The audit universe is derived from those eight decisions; no track ID is hard-coded into resolver or audit selection logic.

- unresolved tracks: **8**
- tracks with frozen Q0 candidates: **5**
- explicit zero-candidate tracks: **3**
- candidate judgments: **25**
- Q0 searches rerun: **0**
- resolver behavior changed: **no**

## Human review

The reviewer labels every available candidate independently as `IDEAL`, `ACCEPTABLE`, `WRONG`, or `UNCERTAIN`. `SAFE` means `IDEAL` or `ACCEPTABLE`. Resolver evidence is hidden until a candidate receives a label; all rationales are preserved verbatim.

Review CSV: `reports/stage5b1i_human_oracle_tail/human_review.csv`

Completed: **0 / 25** candidate judgments.

Oracle Recall@K, resolver-gap taxonomy, ceiling estimates, and ranked rule hypotheses are intentionally deferred until every available candidate is reviewed. Zero-candidate tracks are already documented as unavailable and do not receive fabricated rows.

Run `python -m audio_similarity.cli.stage5b1i_artifacts` after review to freeze the completed analysis.

## Implementation verification

- focused Stage 5B.1I tests: `10 passed`
- Stage 5B.1G/1H/1I resolver replay tests: `83 passed`
- full non-heavy suite: `846 passed, 12 deselected, 11 warnings`
