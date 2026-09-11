# Mechanical gate: PASS

**Failing pair IDs: none.** The complete frozen-100 explorer passed the mechanical
checks. No scorer fix, mapper change or weight calibration was needed.

- **4,950 pairs:** Jc, residual mass, Jnr and G are correct, symmetric and bounded.
  Matched canonical mass is removed before neighborhood projection.
- **297,000 numeric components:** genre, force, delta and adjusted scores match
  the independent Python reference exactly across 15 fixed QA scenarios.
- **Alpha zero:** exact frozen audio scores and ranks are restored for every
  anchor; all Top-K prefixes were checked in every genre/polarity mode.
- **118,800 browser rows:** displayed scores and ranks match the reference.
  Another 1,200 inspector checks passed. Display rounding is intentional;
  exact reconstruction uses the unrounded components in the evidence files.
- **Graph:** off preserves coordinates exactly. All six adjusted layouts are
  deterministic, match browser-worker output exactly, and restore correctly.
- **Neutral evidence:** synthetic tests cover context-only, unresolved and
  broad-only profiles, alongside exact/partial matches, secondary weights,
  duplicate aliases, neighborhood-only relationships and no relationship.
- **Preservation:** frozen-run hashes and modification times are unchanged;
  2,036 historical artifacts still match their existing manifests.

Validation: **17 frontend tests, 1,425 non-heavy Python tests, build and lint
passed**. No Gemini calls, model inference, human-label evaluation, parameter
selection or production changes occurred.

This PASS establishes mechanical correctness, not genre usefulness or improved
playlist compatibility. [Reproduction commands and evidence details](README.md)
include source hashes, fixed QA scenarios, numeric outputs and failure ledgers.
