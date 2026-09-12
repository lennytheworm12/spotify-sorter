# 0007: Separate Offline Ranking, Descriptive Output and Admission Policy

## Status

Accepted for synthetic research scaffolding only. No ranker, representation,
threshold or production policy is selected.

## Context

Ranking v1.2 and output v1 are separate protocols. The active corpus worker
produces centered30 CLAP/MuQ; Method C is a different representation. Existing
playlist membership provides observed positives and unlabeled alternatives,
not candidate-playlist suitability labels. Mechanical PASS does not qualify an
output calibrator or admission policy.

## Decision

Add `audio_similarity.calibration` without changing the worker, frontend,
mapper, prompt or production scorer. Typed immutable source/query contracts and
hash-bound NPY bundles keep representation, source order and matrix provenance
explicit. Cache readiness uses read-only SQLite and full source-byte hashing;
it never instantiates a write-capable inference cache.

Separate inner selection from outer estimates and lockbox metadata. Curator and
duplicate-source components are indivisible; recording/version groups are purged
from all fitting-side appearances. The runnable search is synthetic-only. Save
all configurations, refitted ablations, scores and selection reasons. Keep exact
M3 as a supplied matrix, never an inferred mixture.

Keep raw pair F, playlist Q and equal-seed member-reference percentile distinct.
Suitability hooks have no installed fitting backend. Ordered policy fixtures are
synthetic; real policies require an independently validated manifest tied to one
ranker and candidate policy. No function writes playlists.

## Explicit engineering choices needing a real execution freeze

- The named “corresponding audio comparator” is not fully specified in the
  protocols. The synthetic selection adapter uses the same h/rho/audio base with
  genre terms zero. Choosing instead a separately tuned audio winner changes
  the recall gate. Confirm the comparator plan before real search is enabled.
- The curator-cluster SE estimator, mask seed and rounding, bootstrap count and
  categorical tie order are not fully specified. This scaffold uses deterministic
  cluster bootstrap, ceil(20%) hidden members, hash-order masks and stable
  numeric/representation-ID tie order. The demonstration freezes 32 bootstrap
  draws and one mask per playlist for speed, not statistical adequacy. Real
  execution must preregister these settings and adequate independent support.
- v1.2 also removes inactive h at rho=1: 880 nominal -> 792 eta-deduplicated ->
  756 unique joint configurations. Arm-specific labels preserve interpretation;
  equivalent MuQ-only definitions reuse the same evaluation.
- Existing acquisition requests are not fully adjudicated canonical recordings.
  The readiness denominator is explicitly requests; it does not manufacture
  recording equivalences, source permissions or independent curator identities.

## Consequences

The interfaces and synthetic tests can run while acquisition continues. Real
ranking needs source/identity/split freeze plus provenance-aligned feature parity.
Descriptive output needs a selected frozen ranker. Suitability fitting and policy
validation additionally need candidate-playlist labels and independent data roles.
An opened ranking lockbox cannot become a fresh final policy test. These gates are
reported separately rather than collapsed into a musical verdict.
