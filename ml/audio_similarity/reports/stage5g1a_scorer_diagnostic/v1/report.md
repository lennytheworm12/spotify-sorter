# Stage 5G.1A — scorer capacity diagnostic

Outcome: **SUPERVISION_LIMITED**. This is a developmental diagnosis, not a production winner or a fresh confirmatory TEST result.

The constrained scorer can deliberately fit the tiny TRAIN subset, and improves agreement on its larger training partitions. It does not show stable generalization beyond exact Arm D. This weakens an explanation based solely on a broken optimizer or the previous 512→16 bottleneck, but does not establish that CLAP lacks the relevant information.

## Frozen inputs and model

Reused 100 original tracks and 400 provenance-checked global/front/middle/back views from the immutable Stage 5E.1 SQLite cache. No CLAP inference, downloads, new judgments, or new representations. Reconstructed normalized equal-mean/cosine Arm D agrees with the historical baseline within 3.414e-8. Historical whole-song supervision contains 740 unique pairs; unrated pairs remain unknown. The exact governing vault design is mirrored in `design.md`.

The model is D0 plus a linear residual over four symmetric, 512-coordinate interaction summaries (global/global, aligned locals, global/local, bidirectional best local correspondence). It has **2,048 trainable parameters**, versus 8,241 previously; CLAP's 158,348,809 parameters remain frozen. It performs no dimensionality reduction or fitted preprocessing. Weights initialize to zero, exactly reproducing D0. Fixed sqrt(512) feature scaling; anchor-macro logistic preference loss with margin scale 10; ridge coefficient 1 for development, 0 for deliberate tiny memorization. CPU float64 deterministic LBFGS, seed 20260908, at most 300 iterations, no early stopping or hyperparameter selection. Full optimizer and decision settings are in `protocol.json`. Scores are ranking values, not calibrated probabilities or guaranteed self-normalized similarities.

The design/configuration, splits, tiny subset, implementation and tests were hash-frozen before running the scorer. `input_hashes.json` records those identities and historical inputs; `artifact_manifest.json` records output hashes, including each checkpoint.

## Capacity and development evidence

Tiny smoke: 16 hash-selected preferences from four original Stage 5G.1 TRAIN anchors; **100% agreement**, loss **1.9813e-9**, 27 optimizer iterations. No named-song tuning.

Five predetermined source/track groups rotate heldout and validation roles. Every fold excludes heldout and validation tracks from training on either pair axis. Cross-partition comparisons are discarded. Only three primary folds meet the frozen evidence floors; fold 3 has only 12 validation preferences, while fold 4 has only 12 heldout preferences and six informative anchors. Exclusions were retained. Artist sensitivity joins shared credited artists transitively and has five eligible folds. All of these data are development data; the previously revealed G1 TEST is not treated as untouched evidence.

| Evaluation | Fold | D1 train | D1 validation | D0 heldout | D1 heldout |
|---|---:|---:|---:|---:|---:|
| Source/track grouped | 0 | 0.697 | 0.417 | 0.595 | 0.498 |
| Source/track grouped | 1 | 0.703 | 0.636 | 0.333 | 0.361 |
| Source/track grouped | 2 | 0.707 | 0.324 | 0.588 | 0.546 |
| Source/track grouped | 3 | excluded by frozen evidence floor | — | — | — |
| Source/track grouped | 4 | excluded by frozen evidence floor | — | — | — |
| Artist grouped sensitivity | 0 | 0.697 | 0.480 | 0.504 | 0.540 |
| Artist grouped sensitivity | 1 | 0.734 | 0.458 | 0.551 | 0.471 |
| Artist grouped sensitivity | 2 | 0.671 | 0.379 | 0.486 | 0.515 |
| Artist grouped sensitivity | 3 | 0.680 | 0.400 | 0.318 | 0.616 |
| Artist grouped sensitivity | 4 | 0.692 | 0.502 | 0.543 | 0.548 |

Primary equal-fold mean: D0 **0.5056**, D1 **0.4684**; difference **−0.0372**, descriptive paired-fold 95% bootstrap interval **[−0.0976, +0.0278]**. Only one of three eligible folds improves. Training D1 agreement is approximately 0.70, compared with D0 0.50–0.54. Development optimization reaches maximum absolute gradients below 1.7e-7. The train-to-heldout gap is a generalization problem for this constrained model, not evidence of failure to minimize its frozen objective.

Artist-grouped sensitivity: difference **+0.0574**, interval **[−0.0366, +0.1855]**, four of five folds positive. The estimate is unstable and partly driven by one +0.298 fold. It is not promoted to the primary result. Fold bootstrap intervals are descriptive: few folds, overlapping training partitions, reused tracks across development rotations and sparse labels limit population inference. Paired within-fold anchor intervals, strong-preference metrics and all per-anchor values are included in the result JSON files.

Exactly one predeclared extra diagnostic used the existing full-song G1 segment vectors: mean bidirectional best-match cosine. On the previously revealed G1 TEST's 58 preferences/16 anchors, it scores **0.5924** versus historical G1 M1 **0.5610**: **+0.0314**, interval **[−0.2022, +0.2738]**. This is neither fresh confirmation nor proof of a local-correspondence gain.

## Interpretation and next experiment

The learner demonstrably fits TRAIN, but grouped generalization remains unstable. Missing primary-fold evidence and broad sensitivity intervals prevent a representation-limit claim. A single fixed regularization strength also cannot rule out every better CLAP scorer. The stage therefore closes as SUPERVISION_LIMITED under its frozen rules.

The smallest justified next experiment is a separately designed, modest human-supervision seed concentrated on coherent, track-disjoint groups, sized in advance to populate all development partitions with enough differently rated candidates. Freeze the rubric and group allocation before labeling, then repeat this fixed scorer/control comparison. No review queue is created here. Alternative pretrained music representations remain a subsequent hypothesis, not an inference compelled by these results; a broad architecture search is not justified.

## Reproduction and integrity

From `ml/audio_similarity`:

```bash
.venv/bin/python -m audio_similarity.stage5g1a_experiment prepare
.venv/bin/python -m audio_similarity.stage5g1a_experiment run
.venv/bin/python -m audio_similarity.stage5g1a_experiment verify
.venv/bin/python -m pytest tests/test_stage5g1a.py -q
.venv/bin/python -m pytest -q
```

A second prepare reused all 400 views with zero new CLAP inference; all nine fits replayed with identical weights, optimization histories and scientific results. New numbered execution ledgers preserve originals. `verification.json` records runtime/environment and score cost; the original nine fits took about 0.486 seconds of optimizer time (excluding Python startup, feature construction and historical hash verification). Future reruns append ledgers, which must be listed in a new manifest rather than silently altering this sealed snapshot.

Historical inputs are SHA-256 verified unchanged. No production rankings, fusion weights, historical verdicts, or ratings were modified. Automated validation results are recorded separately in `test_results.txt`. The focused suite covers symmetry, full feature dimensionality, exact baseline initialization, deterministic tiny fitting, unknown-pair rejection, source/artist grouping, track-disjoint constraints, immutable artifact replay, ties and diagnosis branches. Actual cache reuse and deterministic replay were also exercised on all 100 tracks.

Validation: focused suite **6 passed**; full non-heavy suite **1,267 passed, 12 deselected, 11 warnings**, 141.08 seconds. Warnings come from existing short-signal MIR fixtures.

Implementation review covered optimizer inputs, symmetric interaction construction, frozen-baseline reconstruction, grouped fold isolation, unknown-pair exclusion, deterministic artifact writes, and historical SQLite read-only access. No new dependencies or application behavior changes. This is a fixed research CLI; configuration and implementation are jointly hash-pinned, and changing either requires a new reviewed protocol version.
