# Stage 5B.5 — Representative Library V4 Final Validation

**Verdict: `REPRESENTATIVE_V4_FINAL_VALIDATION_PASSED`.**

## Frozen pipeline

```text
Spotify metadata
  -> Q0: raw sanitized title + first 3 credited artists
  -> zero only: title + artist 1, then 2, then 3
  -> first non-empty native Top-3
  -> Stage 5B.3 minimal selector
  -> automated selection or manual tail
```

- manifest SHA-256: `bd01a7e34742154475f2f0bc246b4e2b3551ecb68fa35436cdf23cfde6558c2b`
- sample seed: `stage5b5-representative-v4-seed-2026-09-03`
- library / excluded / eligible / sampled: **1256 / 317 / 939 / 100**
- overlap with V1/V2/V3/5B.4A-C: **0**
- post-freeze substitutions: **0**

## Discovery

- candidate discovery: **100/100 (100.00%)**
- Q0 success: **100/100 (100.00%)**
- fallback triggered / recovered: **0 / 0**
- fallback recovery when triggered: **n/a**
- provider errors / unresolved empty: **0 / 0**
- provider requests / amplification: **100 / 1.00x**

## Blinded human oracle

- Top-1 SAFE: **97/100 (97.00%)**
- Top-3 SAFE: **100/100 (100.00%)**
- first SAFE ranks: `{'rank_1': 97, 'rank_2': 2, 'rank_3': 1, 'none': 0}`
- reviewed candidates: **115**

## Frozen automated selector

- coverage: **99/100 (99.00%)**
- SAFE precision: **96/99 (96.97%)**
- end-to-end automated SAFE yield: **96/100 (96.00%)**
- WRONG selections: **0 (0.00%)**
- unresolved/manual tail: **4 (4.00%)**

## Failure audit

- noteworthy cases: **6**
- Top-3 misses: **0**
- automated WRONG: **0**

| Target | First SAFE | Selector rank | Selected label |
|---|---:|---:|---|
| jellyous | 1 | 2 | UNCERTAIN |
| Push (Feat. REI (IVE)) | 1 | 3 | UNCERTAIN |
| No Blueberries | 1 | none | none |
| I don't know why I feel ok right now, but it's nice | 2 | 2 | IDEAL |
| The Girl Next Door | 3 | 3 | IDEAL |
| CRY FOR ME | 2 | 1 | UNCERTAIN |

## Decision

The complete frozen discovery and selection stack passed its held-out gates. This report validates the candidate architecture; it does not production-activate it.

## Reproduction

```bash
uv run python -m audio_similarity.cli.stage5b5_representative_v4 freeze-manifest
uv run python -m audio_similarity.cli.stage5b5_representative_v4 discover
uv run python -m audio_similarity.cli.stage5b5_representative_v4 run-selector
uv run python -m audio_similarity.cli.stage5b5_representative_v4 build-review
uv run python -m audio_similarity.cli.stage5b5_representative_v4 closeout
```

No query or selector tuning, candidate substitution, media download, CLAP/MuQ run, or production activation occurred.
