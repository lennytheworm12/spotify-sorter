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

The CLAP checkpoint provenance correction and all previous stop-gate history remain unchanged. FMA Large, Stage 4B, new fusion fitting, MERT/MERIT, and product integration remain unstarted.
