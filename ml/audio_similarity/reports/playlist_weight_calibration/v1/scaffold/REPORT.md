# Calibration scaffold: implemented and verified

This is an engineering closeout for ranking v1.2 and output v1. **No real weights,
CLAP representation, admission threshold or strictness policy were selected.**
Implementation commit: `6ee42ee` on `ml/stage5f1-energy-motion`.

## Delivered

The new `audio_similarity.calibration` package contains validated source,
recording/version, representation, candidate, query and data-role contracts;
immutable pair-feature bundles; F/Q scoring; reconstruction metrics; grouped
nested splits/purging; exhaustive synthetic search and refitted ablations;
descriptive output/reference percentiles; suitability and policy readiness hooks;
and a read-only cache inventory. The new CLI is
`audio_similarity.cli.playlist_calibration`.

The scorer combines complete pair features before choosing Top-3 support, excludes
self/duplicate recordings, preserves nonmembers as unlabeled, and rejects changed
catalogs or masks across comparisons. Exact M3 is supplied separately. Inner
selection rejects outer, lockbox and final-test result artifacts. Layer B/C cannot
select v1. Source/curator groups and version purges are checked on supplied splits,
not only generated ones.

The output helper keeps F, Q and descriptive u separate. Eight deterministic
size-matched subsets, minimum 20 distinct members, m=min(20,n-1), exact midrank
ties and null cases are exercised. Suitability labels require an explicit human
judgment target; no fitting backend is installed. Strictness leaves scores/order
and the seed snapshot unchanged; before validation it returns NOT_CALIBRATED.
Unsupported policy domains return needs_review.

## Validation and synthetic evidence

- Full non-heavy Python suite: **1,449 passed**, 12 heavy deselected, 11 existing
  numerical-fixture warnings, 295.08 seconds.
- Final focused/relevant suite: **48 passed**, 37.84 seconds. Includes 19 new
  scaffold tests plus mapper, cache, review-analysis and batching regressions.
- Python compile check and Git whitespace check passed. No Python linter is
  configured/installed; no dependency was added. Frontend/backend code was not
  touched, so frontend build/tests were not rerun.
- **880 nominal configurations -> 792 after eta dedup -> 756 after inactive h
  dedup.** The full refitted registry has 14 named arms and 792 unique evaluated
  definitions including the separate M3 controls.
- Invented 45-recording/9-source fixture: one source group reserved as unopened
  lockbox; three outer folds, two inner folds each; exhaustive inner search for
  every arm. Full scores, per-query/playlist/curator/stratum/fold metrics,
  bootstrap uncertainty and selected/rejected reasons are retained.
- First final synthetic run: 53.23 seconds; replay: 46.84 seconds.
  **All 2,393 artifact files replayed byte-for-byte.** No inference/API calls.
- **3,606 pre-existing historical/configuration/frontend/backend files unchanged.**

Synthetic proof cases cover independent CLAP representations, complete-F Top-3,
hand-calculated NDCG/recall, hidden-member recovery, unlabeled alternatives,
curator/duplicate grouping, version purges, lockbox guards, query-population
identity, conservative selection, percentile ties/nulls, hash failures, exact M3,
ordered strictness sets, and no network/playlist-write path.

## Current-corpus readiness snapshot

| Item | Captured result |
|---|---:|
| Distinct frozen recording requests | 3,201 |
| Queue COMPLETE | 605 |
| Verified centered30 CLAP | 604 |
| Verified fixed MuQ | 604 |
| Missing/unverified centered30 and MuQ | 2,597 each |
| Method C enrolled for exact source identities | 0; 3,201 unverified |
| Gemini/canonical enrolled | 0; 3,201 unverified |
| Hash disagreements | 1 |

These are request identities, not a completed global recording/alias adjudication.
Method C/profile counts mean **not enrolled through a verified calibration bundle**;
they do not claim no historical feature exists elsewhere. The live acquisition
worker advances independently after capture. The private inventory is stored at
`.research_audio/calibration_scaffold_v1/readiness/inventory.private.json`; its
hash binds this report and supports deterministic offline replay.

The disagreement is **Thirsty — aespa**: actual retained bytes, provenance and queue
source hash agree (`335d5c...`), but the reused embedding row references a different
source hash (`611eaf...`). The scaffold blocks that linkage. It neither declares
the source corrupt nor repairs historical artifacts.

Feature readiness: WAITING_FOR_FEATURES. Source, split, ranking and lockbox
readiness: SOURCE_NOT_READY. Output descriptive readiness: NOT_CALIBRATED until a
ranker is selected/frozen. Suitability calibration: LABELS_REQUIRED.

## Remaining gates and ambiguities

Processing must provide aligned feature manifests; retained full audio is not
Method C. Source provenance, curator grouping, version identities, catalogs,
purges and independent data roles need a reviewed freeze. Owner-authored lists
must not be counted as independent curators without evidence.

Before real selection, resolve the protocol's underspecified “corresponding audio
comparator.” The synthetic adapter uses the same h/rho/base with zero genre terms;
a separately tuned comparator is another interpretation. Bootstrap details,
mask seed/rounding and categorical tie order also need a real execution freeze.
Synthetic values are documented engineering fixtures, not a protocol amendment.

Suitability fitting/policy selection additionally need a defined candidate-playlist
target, representative adjudicated labels, an approved tradeoff, and independent
output-fit/policy/final roles. An opened ranking lockbox cannot be recycled as
untouched final policy evidence.

No downloads, new CLAP/MuQ/Gemini calls, real outcome selection, suitability-label
creation, mapper/prompt edits, production ranking changes or playlist writes were
performed by this task.
