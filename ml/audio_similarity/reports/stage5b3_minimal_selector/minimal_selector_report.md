# Stage 5B.3 — YouTube-Prior Minimal Selector

## Contract

Native YouTube rank is trusted unless the raw candidate title explicitly presents an unrequested live/performance source or its duration delta is greater than 20 seconds. Missing positive identity, performer, provenance, source, album, year, or version evidence is not a veto.

- frozen input: Stage 5B.2 100-track native Top-3 dataset
- searches run: **0**
- existing resolver invocations: **0**
- additional veto families: **0**

## Results

- AUTO_SELECT: **99/100 (99.0%)**
- MATCH_UNCERTAIN: **1/100**
- selected ranks: `{'rank_1': 88, 'rank_2': 9, 'rank_3': 2, 'none': 1}`
- existing human SAFE: **89**
- existing human WRONG: **0**
- existing human UNCERTAIN: **1**
- selections awaiting review: **9**
- human SAFE precision: **pending review**

## Critical checks

1. `We got so much` live veto corrected rank 1: **True**
2. `A Little Bit Colder` duration veto corrected rank 1: **False**
3. `Goddess of the Hollow` duration veto corrected rank 1: **True**
4. Original SAFE rank-1 candidates vetoed: **10**
5. Known WRONG selections: **0**
6. Rank 2 selections: **9**
7. Rank 3 selections: **2**

## Changed selections

- `stage5b_youtube_prior_v1_015`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `yBy0vr-nYzg` (UNREVIEWED).
- `stage5b_youtube_prior_v1_017`: rank 1 vetoed by `['UNREQUESTED_LIVE_OR_PERFORMANCE', 'DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `Kw2faPNf00s` (IDEAL).
- `stage5b_youtube_prior_v1_021`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 3 `sWyZMFmTfQs` (UNREVIEWED).
- `stage5b_youtube_prior_v1_028`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `FeeVnBhQwZE` (UNREVIEWED).
- `stage5b_youtube_prior_v1_032`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `b5mhUs326BQ` (IDEAL).
- `stage5b_youtube_prior_v1_043`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `MunZpl35-p4` (UNREVIEWED).
- `stage5b_youtube_prior_v1_044`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `Kh3C_rEsVRQ` (UNREVIEWED).
- `stage5b_youtube_prior_v1_046`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 3 `f88WxriTKW0` (UNREVIEWED).
- `stage5b_youtube_prior_v1_047`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `9uypQGzzhns` (UNREVIEWED).
- `stage5b_youtube_prior_v1_055`: rank 1 vetoed by `['DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `Mm2PW9CZHJc` (UNREVIEWED).
- `stage5b_youtube_prior_v1_077`: rank 1 vetoed by `['UNREQUESTED_LIVE_OR_PERFORMANCE', 'DURATION_ANOMALY_GT_20_SECONDS']`; selected rank 2 `rquH4qEfRHA` (UNREVIEWED).

## Decision

**AWAITING TARGETED HUMAN REVIEW.** No architecture decision is frozen yet.

This is calibration on frozen Stage 5B.2 evidence. It is not production-activated and Representative Library V3 was not run.
