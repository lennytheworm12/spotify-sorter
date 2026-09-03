# Stage 5B.3 — YouTube-Prior Minimal Selector

## Contract

Native YouTube rank is trusted unless the raw candidate title explicitly presents an unrequested live/performance source or its duration delta is greater than 20 seconds. Missing positive identity, performer, provenance, source, album, year, or version evidence is not a veto.

- frozen input: Stage 5B.2 100-track native Top-3 dataset
- searches run: **0**
- existing resolver invocations: **0**
- additional veto families: **0**
- Stage 5B.2 manifest SHA-256: `3a967360ece50d3792f48c3bf857f5270965d09610d2601b517bd2a0e1c23396`
- Stage 5B.2 discovery SHA-256: `3a90301a008824a3001b464aae0e348bc56649f508ccca6f11d88c171f31b9b8`
- Stage 5B.2 human review SHA-256: `e0a39ed88fe840982b4e3ece77102e667baaed83cebff49f7fee0f3f0ecdcef7`

## Results

- AUTO_SELECT: **99/100 (99.0%)**
- MATCH_UNCERTAIN: **1/100**
- selected ranks: `{'rank_1': 88, 'rank_2': 9, 'rank_3': 2, 'none': 1}`
- human IDEAL: **84**
- human ACCEPTABLE: **13**
- human SAFE: **97**
- human WRONG: **0**
- human UNCERTAIN: **2**
- selections awaiting review: **0**
- human SAFE precision: **97/99 (97.98%)**
- targeted changed-selection review: **2 IDEAL, 6 ACCEPTABLE, 0 WRONG, 1 UNCERTAIN**

## Critical checks

1. `We got so much` live veto corrected rank 1: **True**
2. `A Little Bit Colder` duration veto corrected rank 1: **False**
3. `Goddess of the Hollow` duration veto corrected rank 1: **True**
4. Original SAFE rank-1 candidates vetoed: **10**
5. Known WRONG selections: **0**
6. Rank 2 selections: **9**
7. Rank 3 selections: **2**

`A Little Bit Colder` has a frozen 19.0-second duration delta, so the predeclared strict `>20s` veto correctly does not fire; its rank-1 selection remains human `UNCERTAIN`. `HOT` becomes the sole `MATCH_UNCERTAIN` after all three results are vetoed, even though its rank-1 candidate was previously human `IDEAL`.

## Changed selections

- `stage5b_youtube_prior_v1_015`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `yBy0vr-nYzg` (ACCEPTABLE).
- `stage5b_youtube_prior_v1_017`: rank 1 vetoed by `['UNREQUESTED_LIVE_OR_PERFORMANCE', 'DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `Kw2faPNf00s` (IDEAL).
- `stage5b_youtube_prior_v1_021`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 3 `sWyZMFmTfQs` (ACCEPTABLE).
- `stage5b_youtube_prior_v1_028`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `FeeVnBhQwZE` (ACCEPTABLE).
- `stage5b_youtube_prior_v1_032`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `b5mhUs326BQ` (IDEAL).
- `stage5b_youtube_prior_v1_043`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `MunZpl35-p4` (IDEAL).
- `stage5b_youtube_prior_v1_044`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `Kh3C_rEsVRQ` (ACCEPTABLE).
- `stage5b_youtube_prior_v1_046`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 3 `f88WxriTKW0` (ACCEPTABLE).
- `stage5b_youtube_prior_v1_047`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `9uypQGzzhns` (UNCERTAIN).
- `stage5b_youtube_prior_v1_055`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `Mm2PW9CZHJc` (IDEAL).
- `stage5b_youtube_prior_v1_077`: rank 1 vetoed by `['UNREQUESTED_LIVE_OR_PERFORMANCE', 'DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `rquH4qEfRHA` (ACCEPTABLE).

## Decision

**PASS.** Test this unchanged minimal selector on a fresh Representative Library V3 benchmark; do not production-activate from calibration.

Relative to trusting rank 1 blindly, V1 removes both known WRONG automatic selections while retaining 97 human-SAFE automatic selections. The cost is one additional human-UNCERTAIN selection, one abstention, and ten vetoes of rank-1 candidates already known SAFE. The duration veto is therefore effective on the two gross anomalies but over-broad for source quality; that limitation must be measured unchanged on V3 rather than retuned on this calibration set.

## Validation

- focused Stage 5B.3 tests: **10 passed**
- complete Stage 5B regressions: **458 passed**
- full non-heavy suite: **919 passed, 12 deselected**

This is calibration on frozen Stage 5B.2 evidence. It is not production-activated and Representative Library V3 was not run.
