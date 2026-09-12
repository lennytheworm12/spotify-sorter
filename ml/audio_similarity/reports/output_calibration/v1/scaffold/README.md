# Output calibration v1 — descriptive scaffold only

`synthetic_descriptive.json` exercises raw Q, top support and the equal-sized-seed
member-reference helper on invented evidence. The fixed preset is explicitly
unselected. `suitability_probability`, calibration and policy IDs remain null.
The descriptive percentile is not a probability or confidence value.

The real readiness snapshot in `readiness.json` reports NOT_CALIBRATED for output
until ranking selection/freeze, and LABELS_REQUIRED for suitability. No real
output-fit, threshold search or admission decisions were run.

Tests cover eight deterministic subsets, m=min(20,n-1), at least 20 distinct
reference recordings, no self/duplicate support, exact midrank ties, null cases,
ordered synthetic Broad/Balanced/Tight sets, unchanged ranker/scores/order/seeds,
and unsupported-domain needs_review. Synthetic policy numbers are unit-test
fixtures only; no real default thresholds exist.

See the [ranking scaffold report](../../../playlist_weight_calibration/v1/scaffold/REPORT.md)
and [runbook](../../../../../../docs/genre-force/calibration-scaffold.md) for code,
protocol details, tests, data-role gates and reproduction commands.
