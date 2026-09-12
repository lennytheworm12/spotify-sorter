# Offline calibration scaffolding

This implements deterministic mechanics for ranking v1.2 and output v1. It does
not select real weights or CLAP representations, fit probabilities, create labels,
choose thresholds, or activate production behavior. All executable parameter
searches reject real evidence. Existing acquisition may continue independently;
these commands do not start or modify it.

## Run now

From `ml/audio_similarity`:

```bash
.venv/bin/python -m pytest tests/calibration -q
.venv/bin/python -m audio_similarity.cli.playlist_calibration synthetic \
  --output .research_audio/calibration_scaffold_v1/release_synthetic
.venv/bin/python -m audio_similarity.cli.playlist_calibration readiness \
  --output .research_audio/calibration_scaffold_v1/readiness_new_snapshot
```

The synthetic command freezes code hashes/configuration first, writes an immutable
45-recording invented feature bundle, reserves one source group as an unopened
lockbox, and executes three outer folds with two inner folds each. It exhaustively
refits all ablations inside each inner loop. It also exercises the equal-seed
reference helper using an explicitly unselected synthetic preset. No real labels
or real outcome matrices enter this command.

Repeating the synthetic command against the same output checks exact artifact
bytes and fails on changed code/config/results. NPY files disable pickle; JSON is
canonical and rejects NaN. Full score ledgers are retained, including unlabeled
candidates. The report describes engineering behavior only.

The read-only census defaults to the original and extension reference batches.
Use repeated `--run-dir` arguments to inventory a different set. It captures each
queue JSON once, checks immutable manifest hashes, reads SQLite with `mode=ro`
and `query_only`, and checks source/embedding bytes, ordering/contract identities,
segment completion and normalization. It does not decode audio or run encoders.
Because the corpus is live, use a new output directory for a fresh snapshot.
Replay the saved inventory without reading the live corpus:

```bash
.venv/bin/python -m audio_similarity.cli.playlist_calibration replay-readiness \
  --inventory .research_audio/calibration_scaffold_v1/readiness/inventory.private.json \
  --output .research_audio/calibration_scaffold_v1/readiness
```

A queue `COMPLETE` marker can coexist with a rejected cache hash linkage. Readiness
reports both counts. Missing Method C/canonical means not verified and enrolled for
these exact source identities, not a claim that no such features exist anywhere.
The scanner currently supports centered30 cache enrollment only; use the explicit
`PairFeatures` bundle interface for future complete C30/Method-C/M/genre artifacts.
No feature is inferred from a fused score or title match.

## Components and extension points

| Module | Contract |
|---|---|
| `contracts.py` | Frozen recording/version/source groups, Layer A/B/C playlists, candidates, masks and roles; strict JSON corpus loader |
| `features.py` | Ordered source/hash-bound float64 pair matrices, explicit representation identities, neutral missing-genre mask, deterministic save/load |
| `ranking.py` | Finite grid and refitted arm registry; F; complete-F Top-3 Q; observed-membership metrics |
| `splits.py` | Model-blind curator/duplicate components, grouped nested folds, record/version purges, 80/20 masks, lockbox metadata and output-role audit |
| `search.py` | Inner-only exhaustive synthetic ledger, cluster uncertainty, recall guard, one-SE simplicity, outer estimates; rejects outer/lockbox selection files |
| `output.py` | Ranker freeze, descriptive ledger/reference helper, explicit suitability labels/hooks, immutable-snapshot strictness preview |
| `readiness.py` | Read-only current-corpus census and deterministic replay from captured inventory |

Grid: two representations × 11 rho values × 8 canonical weights × 5 eta values.
After inactive eta/h deduplication there are **756 joint definitions**. Exact M3
and its 36 canonical/residual settings add **36 separate definitions**, for **792
unique evaluated definitions across the full ablation registry**. Repeated arm
membership reuses evaluations. M3 is a separate supplied cached matrix.

The bundle contains C_center30, C_method_c, M, Jc, Jnr, R and optional exact M3.
R must equal `(1-Jc)*Jnr`; missing genre contributes zero and stays visible in the
mask. Audio matrices must be complete on one common population. Representation,
checkpoint, preprocessing, environment, implementation, mapper/prompt/schema,
source/order and matrix hashes form the identity. Encoders and mapper algorithms
are not implemented or changed here.

Grouping uses transitive curator/duplicate-source components, including the
protocol Jaccard>=.8 / containment>=.9 duplicate tests. `version_group_id` is a
conservative exclusion/purge unit; source identity adjudication must establish it.
Masks don't create independent source evidence. Metrics average queries within
playlist, playlists within curator/stratum, then strata; plain playlist macro and
per-curator results are also reported. Candidate support excludes matching version
groups and uses deterministic recording-ID tie breaking.

The reference helper requires 20 unique usable recordings, m=min(20,n-1), eight
hash-seeded subsets per member/candidate, and exact unrounded midrank ties. It
reports schedules, count, subset variability and null reasons. Percentiles are
not probabilities or confidence. Suitability labels must be explicit human
candidate-playlist judgments. The hook accepts only raw Q and a READY protocol;
there is no fitting backend. Broad/Balanced/Tight have no real default numbers.
A synthetic policy demonstrates nested sets while scores/order/seeds remain fixed.

## What waits

1. **Processing:** verified C30, Method C and fixed MuQ on common source identities;
   explicit Gemini/canonical enrollment or documented neutral genre availability.
2. **Source/split preparation:** original source provenance/permissions, actual
   curator grouping, recording/version reconciliation, sampled corpus, candidate
   catalogs, masks and independent development/lockbox assignment. Owner-authored
   lists do not automatically create independent curators.
3. **Ranker selection:** reviewed comparator/uncertainty execution settings and
   completed nested development evaluation. Only then freeze ranking_model_id.
4. **Suitability:** a defined candidate-playlist target, appropriate sampling,
   clear and uncertain labels kept separately, independent output-fit, policy and
   final-test roles. No nonmembership or genre-based pseudo-negatives.

Before opening a lockbox, freeze all inputs/hashes, source groups, recording
purges, candidate catalogs, masks, feature versions, grid/arms, comparator,
uncertainty and tie policies, selected ranker and allowed analysis. Record whether
that lockbox was previously inspected. Policy fitting needs its own data roles;
a consumed ranking test is not untouched policy confirmation.

See [ADR 0007](../decisions/0007-offline-playlist-calibration-scaffolding.md) for
explicit unresolved execution details. The authoritative scientific protocols
remain unchanged.
