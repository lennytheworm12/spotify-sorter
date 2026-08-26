# Stage 2B Protocol Amendment — Single Reviewer v2

Status: **APPROVED**

Approved: 2026-08-26

## Decision

Stage 2B is reapproved as a **single-reviewer personal perceptual-alignment benchmark**.

The original pre-collection multi-rater protocol remains frozen and auditable. This amendment does not claim that its 2/3-rater acceptance criterion was satisfied. Instead, it creates a new analysis protocol that accepts **one distinct reviewer per trial** and explicitly narrows the scientific claim.

Observed collection state at approval:

```text
240 / 240 primary trials covered
1 distinct reviewer
```

Under `single_reviewer_v2`, that satisfies the human-evidence collection gate.

## Why the amendment is allowed

The research goal is to choose a practical similarity function for this project. Additional independent reviewers are not currently worth blocking the next architectural decision.

The amendment therefore trades population-level generality for execution speed while preserving the parts of the experiment that protect against model-selection leakage:

- frozen 40-query universe;
- 16/8/16 TRAIN/VALIDATION/TEST query split;
- balanced CLAP/MERT, CLAP/MuQ, and MERT/MuQ trials;
- encoder-neutral identity duplicate filtering;
- exact shared `center5_v1` human/model evidence;
- blinded A/B orientation;
- train-only fitting/scaling;
- validation-only hyperparameter/model-subset selection;
- pushed locked selection before TEST reveal;
- one held-out TEST reveal.

## Amended rating semantics

Each trial requires exactly one reviewer choice:

```text
A
B
Tie
Neither
```

The canonical label is the latest append-only choice from that reviewer for the trial.

- `A` and `B` enter the binary pairwise fitting/evaluation denominator.
- `Tie` and `Neither` remain first-class ambiguity outcomes and are never coerced into A/B.
- Self-correction remains auditable through append-only superseding events.
- Additional raters are optional future replication evidence, not a requirement for Stage 2B v2 completion.

## Claim boundary

A successful Stage 2B v2 result may support:

> **This encoder or fusion function best aligned with the designated reviewer's overall audible-similarity judgments on the frozen Stage 2B benchmark.**

It must **not** be reported as:

- general human consensus;
- population-level perceptual superiority;
- inter-rater agreement;
- a universally calibrated definition of similarity.

Query-bootstrap confidence intervals describe variation across the frozen query set **for this reviewer's judgments**, not uncertainty across listeners.

## Analysis contract

Use:

`configs/holistic_stage2b_fusion_single_reviewer.yaml`

Do not mutate `configs/holistic_stage2b_fusion.yaml` or the frozen pre-collection bundle. The original config/evaluator/store remain historical evidence of the original approval and collection mechanics.

The active analysis should:

1. validate 240/240 coverage with one canonical review per trial;
2. construct TRAIN and VALIDATION labels without revealing TEST results to selection;
3. compare the seven predeclared representation sets;
4. fit only the predeclared L2 logistic fusion models;
5. freeze, commit, and push the selected representation/C before TEST reveal;
6. reveal TEST once and issue the predeclared verdict;
7. report the single-reviewer claim limitation prominently.

## Testing requirement

Before resuming selection, update/add focused tests for the amended analysis validator and canonical-label builder, then run the Stage 2B focused tests and the full fast suite. The original collection-bundle hash validation must continue to pass unchanged.

Do not alter the immutable collection bundle to make this amendment pass.
