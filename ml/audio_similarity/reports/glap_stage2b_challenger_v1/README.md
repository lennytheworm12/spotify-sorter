# GLAP Stage 2B Challenger v1

This directory contains a new, outcome-isolated challenger experiment. It does not modify the historical Stage 2B evidence or Audio Representation v1.

The pre-outcome contract is `experiment_contract.json`. `phase0_audit.json` records the exact historical LAION-CLAP reproduction gate and local source-identity audit completed before GLAP scoring.

Frozen comparison:

```text
same Stage 2B query/candidate tracks
same pp-v1 center5_v1 audio evidence (12.5s–17.5s)
same single-reviewer A/B labels and exclusions
same split and query-macro metric
LAION-CLAP  ->  GLAP is the only changed component
```

No GLAP outcome was calculated before this contract was frozen.

The experiment is now closed. The final verdict is `GLAP_REJECTED_AS_GLOBAL_CHALLENGER`; see `decision_report.md` and `comparison_summary.json`. Audio Representation v1 was not changed.

Machine-readable outputs:

- `experiment_contract.json`: frozen pre-outcome protocol and provenance
- `phase0_audit.json`: historical evidence and baseline reproduction gate
- `embedding_cache_manifest.json`: resumable cache/embedding identities
- `predictions.csv`: all 240 frozen trials with GLAP, LAION-CLAP, and MuQ diagnostics
- `per_query_metrics.csv`: paired query-level metrics
- `bootstrap.json`: 50,000-draw paired TEST query bootstrap
- `diagnostics.json`: paired errors, correlations, and margin distributions
- `language_audit.json`: multilingual-analysis support limitation
- `performance_full.json`: independent empty-cache engineering measurement
- `real_model_validation.json`: real-model shape/norm/repeat determinism
