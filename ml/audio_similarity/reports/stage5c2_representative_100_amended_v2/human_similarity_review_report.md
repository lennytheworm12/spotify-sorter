# Stage 5C.2 amended 100 — completed human similarity review

**Status:** `HUMAN_REVIEW_COMPLETE`

The owner reviewed all 359 unique unordered pairs covering 500 directional Top-5 relationships across 100 queries. No labels were inferred and no embeddings or rankings changed.

## Results

- Mean Top-1 rating: **3.970 / 5**.
- Mean Top-5 rating: **3.596 / 5**.
- Top-1 rated at least moderately similar (3–5): **92.0%**.
- Top-5 rated at least moderately similar (3–5): **86.4%**.
- Top-5 rated at least somewhat related (2–5): **97.6%**.
- Directional labels: `{'1': 12, '2': 56, '3': 149, '4': 188, '5': 95}`.

Mean rating by rank: #1 3.970, #2 3.640, #3 3.540, #4 3.470, #5 3.360.

## Alignment diagnostics

Pearson correlation with owner ratings: CLAP **0.259**, MuQ **0.158**, combined **0.276**. These are descriptive single-owner results on the frozen reviewed relationships, not a new weight-tuning set.

## Boundary

This completes human review of the amended representative corpus. It does not establish population-level agreement, authorize model tuning, or activate the pipeline in production.
