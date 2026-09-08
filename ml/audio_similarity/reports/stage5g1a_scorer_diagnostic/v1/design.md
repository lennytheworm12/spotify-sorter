---
title: Stage 5G.1A — CLAP Scorer Capacity and Aggregation Diagnostic
aliases:
  - Stage 5G.1A — D-View Learned Scorer Diagnostic
status: design-ready-for-implementation
created: 2026-09-08
project: Spotify Sorter
parent: Spotify Audio Similarity Pivot — Holistic Human-Aligned Retrieval Design
previous: Stage 5G.1 — CLAP-only learned similarity pilot
tags:
  - spotify-project
  - audio-similarity
  - supervised-learning
  - metric-learning
  - clap
  - diagnostic
---

# Stage 5G.1A — CLAP Scorer Capacity and Aggregation Diagnostic

> [!summary] Decision
> Do **not** jump directly from Stage 5G.1's operational `REPRESENTATION_LIMITED` verdict to MuQ. First determine whether the Stage 5G.1 learner itself imposed a new bottleneck. The primary test is a learned scorer over the **exact Arm-D four-view CLAP evidence**, plus a training-capacity smoke test. No new human judgments and no production activation.

## 1. Why this stage exists

Stage 5G.1 closed at Spotify repository commit:

```text
c407d0005fceda0d93e806786ff49aa19dd6c3ca
```

Held-out query-macro preference agreement:

```text
B0 — historical Arm D             62.6%
B1 — full-segment mean/cosine     54.4%
M1 — learned full-segment scorer  56.1%
```

M1 improved over B1 by only about +1.7 percentage points, with a very wide paired 95% interval spanning large negative and positive effects. Under the frozen rules the stage therefore recorded `REPRESENTATION_LIMITED`.

That verdict is operationally correct for the frozen experiment, but it is **not strong evidence that CLAP intrinsically lacks the desired information**.

Three observations motivate one more CLAP-only diagnostic:

1. B1 degraded substantially relative to B0, so replacing D's global/front/middle/back construction with an equal mean over every 10-second segment was itself harmful.
2. M1 compressed each 512-D segment to 16 dimensions, then averaged absolute differences and elementwise products over **all cross-song segment pairs** before scoring. This is permutation-invariant and discards local section correspondence before the final head.
3. The 100%-training run selected epoch 1. Training loss continued to improve while validation loss worsened immediately, so sparse supervision / model regularization / aggregation remain plausible limitations.

The next question is therefore narrower:

> **With the exact same Arm-D CLAP evidence that produced the strongest historical baseline, can a small learned scorer fit and generalize better than D's fixed mean/cosine rule?**

## 2. Scientific scope

This is a **development diagnostic**, not a new confirmatory winner study.

Stage 5G.1's TEST results have already been revealed and influenced the next design. They must not be represented as an untouched final test for a newly selected architecture.

Use existing labels only. The purpose is to decide what kind of fresh evidence the next confirmatory stage should collect.

No production activation is permitted.

## 3. Frozen inputs

Reuse and hash:

- Stage 5G.1 human-evidence snapshot and pair identities;
- Stage 5G.1 split and training artifacts;
- Stage 5G.1 10-second CLAP segment cache for diagnostics only;
- Stage 5E.1 exact Arm-D checkpoint/configuration;
- original frozen-100 retained source identities;
- historical Arm-D B0 scores.

Historical artifacts are immutable.

### Exact D-view evidence

Primary learned input must use the same four independent Arm-D CLAP views:

```text
1. native global resized full-song mel view
2. front local 10-second view
3. middle local 10-second view
4. back local 10-second view
```

Use cached per-view vectors if provenance-valid vectors already exist. If they were not retained, rematerialize only the required original-100 D views using the exact frozen checkpoint, Stage 5E.1 view plans, preprocessing, and hashes.

Do not substitute Stage 5G.1 consecutive segments for the primary D-view experiment.

## 4. Capacity smoke test

Before any generalization interpretation, prove that the model family can actually learn a deliberately tiny training problem.

Freeze a small subset of Stage 5G.1 TRAIN anchors before running the smoke test.

Train the candidate scorer without early stopping on only this tiny subset and report whether it can strongly fit the known preferences.

The purpose is diagnostic:

```text
cannot fit tiny subset
    → model / optimization / aggregation bottleneck

can fit tiny subset
    → model has enough capacity; generalization becomes the relevant question
```

Do not tune the model on historical TEST performance.

A failure of the capacity smoke blocks any claim that CLAP is representation-limited.

## 5. Learned D-view scorer

Keep CLAP frozen.

Use a small symmetric scorer over the four D-view embeddings.

Requirements:

- `f(a,b) = f(b,a)` by construction;
- do not collapse the four views to D's equal mean before the learned scorer;
- preserve the global view separately from local views through at least the first comparison layer;
- use a modest latent projection rather than an extreme 512→16 bottleneck unless justified by the capacity test;
- expose exact trainable parameter count;
- deterministic initialization/training under a frozen seed;
- human pairwise preferences remain the only target.

A reasonable small family is:

```text
four 512-D D views per song
        ↓
shared small projection
        ↓
symmetric view-to-view comparison matrix
        ↓
small fixed-size summary / pooling
        ↓
small MLP similarity head
```

The implementation may use fixed predeclared statistics such as diagonal/global-local similarities, best-match summaries, means, and lower quantiles. Do not launch architecture search across many neural families.

## 6. Development evaluation

Because Stage 5G.1 TEST has already been consumed, use grouped cross-validation / repeated grouped development evaluation over the existing frozen-100 human evidence rather than claiming a new untouched TEST result.

Prevent track leakage within each development fold. Preserve artist-group sensitivity where feasible.

Report anchor-macro preference agreement and uncertainty across folds.

Compare:

```text
D0 = historical Arm-D fixed score
D1 = same exact D-view evidence + learned scorer
G1 = Stage 5G.1 full-segment learned scorer (historical diagnostic only)
```

The primary comparison is **D1 versus D0** because it isolates learned scoring while holding the underlying Arm-D evidence fixed.

## 7. Optional aggregation diagnostic

Only after the D-view capacity/scoring result is established, use the already-cached Stage 5G.1 full-song segments to answer one secondary question:

> Did averaging over all cross-song segment pairs wash out useful local matches?

Compare the historical M1 all-pairs-mean rule against one predeclared symmetric local-correspondence rule, such as forward/backward best-match pooling with robust quantiles.

Do not build a Transformer, sequence model, or architecture sweep in this stage.

This secondary result is developmental and must not consume new human labels.

## 8. Interpretation branches

### `SCORER_OR_AGGREGATION_BOTTLENECK`

Use when:

- the capacity smoke passes; and
- D1 consistently improves over D0 in grouped development evaluation, or the local-correspondence diagnostic materially outperforms Stage 5G.1's all-pairs mean.

Interpretation:

> Stage 5G.1's learned architecture/aggregation was too lossy to test CLAP fairly.

Next: freeze the best simple CLAP scorer and obtain a **small fresh held-out review set** before making a generalization claim.

### `SUPERVISION_LIMITED`

Use when:

- the capacity smoke can fit the training subset;
- development folds are highly unstable / validation does not generalize;
- no clear representation-specific failure is established.

Interpretation:

> Existing supervision is too sparse/noisy to distinguish scorer quality confidently.

Next: use active learning to collect a small informative fresh batch rather than adding MuQ immediately.

### `COMPLEMENTARY_REPRESENTATION_JUSTIFIED`

Use when:

- the capacity smoke passes;
- the D-controlled scorer and the less-lossy segment diagnostic both fail to show useful development signal;
- the failure is not attributable to implementation, optimization, or leakage.

Interpretation:

> The project has now exhausted the most obvious CLAP-only scoring explanations enough to justify testing MuQ or another complementary representation.

### `MODEL_CAPACITY_OR_IMPLEMENTATION_FAILURE`

Use when the scorer cannot intentionally fit the tiny frozen training subset or fails deterministic/model-contract checks.

Interpretation:

> Do not draw a representation conclusion. Repair the learner first.

## 9. Hard exclusions

Do not add:

- MuQ inputs;
- new foundation models;
- energy/motion or Stage 5F.2 rhythm features;
- stems;
- lyrics;
- metadata predictive features;
- CLAP fine-tuning;
- pseudo-labeling/self-training;
- new human judgments;
- production ranking changes;
- Spotify playlist writes.

## 10. Definition of done

Stage 5G.1A is complete when:

1. exact Arm-D per-view CLAP evidence is provenance-verified or reproducibly rematerialized;
2. the tiny-subset capacity smoke is executed and reported;
3. a small symmetric D-view learned scorer is implemented deterministically;
4. grouped development evaluation prevents track leakage;
5. D1 is compared directly with D0 using identical underlying D evidence;
6. at most one predeclared full-segment local-correspondence diagnostic is run;
7. no new human labels are collected;
8. historical artifacts remain unchanged;
9. focused and full non-heavy tests pass;
10. exactly one interpretation branch is recorded;
11. no production behavior is activated.

## Navigation

- [[Spotify Sorter]]
- [[Spotify Audio Similarity Pivot — Holistic Human-Aligned Retrieval Design]]
- [[Spotify Audio Similarity Research Roadmap]]
- [[Spotify Audio Similarity Stage 5F.2 — Rhythm Pattern Attribute Layer Design]]
