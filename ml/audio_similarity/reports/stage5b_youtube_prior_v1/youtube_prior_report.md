# Stage 5B.2 — Raw YouTube Search Prior Benchmark

## Frozen experiment

- held-out tracks: **100**
- manifest SHA-256: `3a967360ece50d3792f48c3bf857f5270965d09610d2601b517bd2a0e1c23396`
- private owner-library snapshot SHA-256: `0a31c8828a2a586008d78a0a6026a83a737db5e943cbd99847c1ae9005a43331`
- deterministic sample seed: `stage5b-youtube-prior-v1-seed-2026-09-02`
- library universe: **1256 unique / 110 excluded / 1146 eligible**
- overlap with DEV, calibration, adversarial challenge, query experiments, prior manual audits, and Representative Library V1: **0 tracks**
- starting source commit: `e3aa0f1`
- experiment branch: `ml/stage5b2-youtube-prior-benchmark`
- query: unquoted `<Spotify title> <primary artist>`
- retrieval: native `ytsearch3`, metadata only, rank preserved
- yt-dlp version: `2026.08.19`
- discovery: **100/100**, 300 candidates, zero search failures
- existing resolver invocations: **0**
- audio/video downloads: **0**

## Human-ground-truth results

- Top-1 SAFE: **97/100 (97.0%)**
- Top-1 IDEAL: **90/100 (90.0%)**
- Top-1 ACCEPTABLE: **7/100 (7.0%)**
- Top-1 WRONG: **2/100 (2.0%)**
- Top-1 UNCERTAIN: **1/100 (1.0%)**
- Top-2 SAFE Recall: **100/100 (100.0%)**
- Top-3 SAFE Recall: **100/100 (100.0%)**
- first SAFE rank: `{'rank_1': 97, 'rank_2': 3, 'rank_3': 0, 'none': 0}`
- H1 (Top-1 SAFE >= 90%): **PASS**
- H2 (Top-3 SAFE >= 99%): **PASS**

## Independent blinded Sol comparison

Sol reviewed all 300 shuffled candidates from raw metadata only. It did not see native rank, human labels, resolver evidence, or outcomes.
- model/configuration: `gpt-5.6-sol`, reasoning `high`
- prompt SHA-256: `7baeb8a888d6ff00a63d4e5ce93c6a52801d92a11b6a29334c8c6e358b75ede7`
- blinded payload SHA-256: `728aa8b5f3d06dbf60ac870942b683453ed86e569507c8ff8e4f91d2a855d9b3`
- Sol output SHA-256: `b3f2db435171ca9709f02698c88d14f5785e807d8ce34af6eedebea9d900dece`
- completed human review SHA-256: `e0a39ed88fe840982b4e3ece77102e667baaed83cebff49f7fee0f3f0ecdcef7`
- human-reviewed candidate comparisons: **103**
- exact-label agreement: **87.4%**
- SAFE/WRONG/UNCERTAIN agreement: **97.1%**
- Sol remains secondary evidence; human labels are ground truth.

## Failures

- Top-1 failures: **3**
- Top-3 misses: **0**
- categories: `{'LIVE_VS_STUDIO': 1, 'METADATA_INSUFFICIENT': 1, 'MULTI_TRACK_OR_NOT_ISOLATED': 1}`
- detailed cases and reviewer notes are frozen in `failure_analysis.json`.

| Target | Rank-1 result | Cause | First SAFE rank |
|---|---:|---|---:|
| We got so much | WRONG | LIVE_VS_STUDIO | 2 |
| A Little Bit Colder | UNCERTAIN | METADATA_INSUFFICIENT | 2 |
| Goddess of the Hollow | WRONG | MULTI_TRACK_OR_NOT_ISOLATED | 2 |

- **We got so much**: native rank 1 `LE SSERAFIM (르세라핌) 'We got so much' l Original Stage` was WRONG (LIVE_VS_STUDIO); rank 2 `LE SSERAFIM We got so much Lyrics (Color Coded Lyrics)` was the first human-SAFE result.
- **A Little Bit Colder**: native rank 1 `stream_error - a little bit colder` was UNCERTAIN (METADATA_INSUFFICIENT); rank 2 `stream_error - a little bit colder [lyrics]` was the first human-SAFE result.
- **Goddess of the Hollow**: native rank 1 `city girl | goddess of the hollow [full album]` was WRONG (MULTI_TRACK_OR_NOT_ISOLATED); rank 2 `Goddess of the Hollow` was the first human-SAFE result.
- There were no Top-3 misses requiring deeper miss analysis.

## Comparison with Representative Library V1

- prior deterministic resolver coverage: **81.0%** (81/100)
- prior reviewed AUTO_MATCH SAFE precision: **97.5%**
- raw native YouTube Top-1 SAFE rate: **97.0%**

Coverage and precision answer different questions: the resolver abstains, while raw Top-1 always makes a selection. This benchmark does not activate a new production architecture.

The native rank prior is nevertheless much stronger than the current proof-heavy architecture's coverage: all three Top-1 failures were recovered at rank 2, and no track missed within the top three. The evidence supports a future experiment built around native YouTube rank plus narrow explicit safety vetoes and source preference—not direct production trust in rank 1. That design must be tested on a fresh V3 sample.

## Decision

**YOUTUBE_TOP1_PRIOR_VALIDATED**

No query, label, rank, candidate, or resolver policy was changed after reveal. Any future ranking-plus-veto architecture requires a fresh validation sample.

## Validation

- focused Stage 5B.2 tests: **11 passed**
- complete Stage 5B regression suite: **435 passed**
- full non-heavy `ml/audio_similarity` suite: **909 passed, 12 deselected**

## Reproduction commands

```bash
uv run python -m audio_similarity.cli.stage5b2_youtube_prior freeze-manifest
uv run python -m audio_similarity.cli.stage5b2_youtube_prior discover
uv run python -m audio_similarity.cli.stage5b2_youtube_prior build-sol-payload
uv run python -m audio_similarity.cli.stage5b2_youtube_prior build-review
uv run python -m audio_similarity.cli.stage5b2_youtube_prior closeout
uv run pytest
```
