# Stage 4A dual-encoder engineering amendment

Stage 2B remains scientifically closed as `SINGLE_ENCODER_WINS`; this amendment does not claim fusion won that experiment.

By explicit engineering decision, Audio Representation v1 activates the reproducibly validated CLAP and MuQ-MuLan-large representations with fixed Stage-2B-derived candidate-ranking weights:

```text
CLAP = 0.7172981519
MuQ  = 0.2827018481
```

No Stage 4 labels are used to fit these weights. Temporal pooling occurs independently inside each encoder space, after both encoders receive identical source 5-second intervals.

The prior CLAP-only Stage 4A evaluator contained three choices when this amendment was executed. Its complete bundle, ratings, and hashes are preserved under `reports/holistic_stage4a/superseded_clap_only/`; those choices are historical/diagnostic only and are forbidden from the dual-encoder primary denominator.

Focused real-model identity smoke:

```text
MuQ revision: 2e01c796b71dca71b45251384c04cd7b237c9020
track 2 existing-vs-regenerated cosine: 1.0000000230152213
maximum absolute element difference: 2.8413574965080457e-09
```

## Temporal sampling closeout amendment

Recorded on 2026-08-31, this amendment keeps three distinct results.

### 1. Frozen experimental verdict

Only 238 of the 240 expected designated-reviewer outcomes were available. The unchanged frozen Stage 4A protocol therefore returned `INSUFFICIENT_EVIDENCE_PICK_CHEAPER`. This historical statistical verdict remains authoritative and is not rewritten as `UNIFORM3_DUAL_WINS`.

On the available observations, K=3 versus K=1 had 0.6027 query-macro preference (95% CI [0.5068, 0.6986]) and +0.1027 improvement, satisfying the frozen material-improvement rule. K=5 versus K=1 had 0.5000 preference and no material improvement. K=5 versus K=3 had 0.5733 preference and no material improvement.

### 2. Post-experiment sensitivity analysis

No rating was imputed and the frozen metrics were not changed. The missing K=5 versus K=3 judgment cannot make K=5 materially superior. For the missing K=3 versus K=1 judgment, a K=3 win, Tie, or Neither outcome preserves material improvement. A K=1 win moves the lower confidence bound to the 0.5000 boundary, which fails the existing strict `> 0.50` gate. K=3 is therefore robust to every missing outcome except that single worst-case boundary condition.

### 3. Engineering/product decision

Audio Representation v1 selects `UNIFORM3_DUAL_MEAN`: K=3 with five-second segment centers `[5, 15, 25]`. Temporal aggregation, preprocessing, encoders, and fusion weights remain unchanged. The consumer contract is `audio_representation_v1.json`; future Stage 5 code must read K=3 from that contract.

This engineering selection does not change the Stage 2B scientific conclusion (`SINGLE_ENCODER_WINS` / CLAP), the active CLAP + MuQ engineering representation, or any Stage 4 experimental result. The CLAP checkpoint provenance correction and all previous stop-gate history remain unchanged. FMA Large, Stage 4B, new fusion fitting, MERT/MERIT, Stage 5 implementation, and product integration remain unstarted.
