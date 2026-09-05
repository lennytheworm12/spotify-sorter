# Stage 5E.2 Arm D evaluation

Verdict: `ARM_D_HUMAN_EVIDENCE_INSUFFICIENT`. D remains an experimental challenger; no winner or activation is justified yet.

Scope correction: only the original amended frozen 100 tracks are queries AND candidates.
The 741-track Stage5E1 experiment and retired Stage5E2 queue remain preserved, but are not the active review target.
Frozen A/D similarities are restricted on both axes before recomputing native Top-5 ranks, with zero inference.
D CLAP + COMBINED contain 527 unique pairs. Prior numeric ratings cover 146 (27.70%).
The blinded queue contains only the remaining 381 pairs.

| Retrieval | Rated / total | Observed mean rating@5 | Fully rated queries |
| --- | ---: | ---: | ---: |
| D_CLAP | 133 / 500 | 3.819548872180451 | 0 |
| D_COMBINED | 185 / 500 | 3.7621621621621624 | 0 |
| A_CLAP | 345 / 500 | 3.6028985507246376 | 16 |
| A_COMBINED | 345 / 500 | 3.652173913043478 | 11 |

Observed ratings are selected historical coverage, not an unbiased estimate of all 100 queries. UNSURE is nonnumeric. Paired results require complete Top-5 ratings for both arms. No winner is inferred from partial evidence.

CLAP: 0 complete paired queries; wins/losses/ties 0/0/0; mean D-A None.

COMBINED: 0 complete paired queries; wins/losses/ties 0/0/0; mean D-A None.

Conflicting numeric labels are held out for review. Duplicate exports and reciprocal pairs do not add independent evidence. Existing labels retain source-file hashes, notes, and timestamps in label_evidence.json. Scale-v1, FMA comparisons, and song-identity SAFE labels are incompatible.

Strongest observed low-rated D results are recorded in evaluation_metrics.json; these are examples, not a population failure rate. A/C and B/D use different checkpoints in Stage5E1, so D-versus-A is a system comparison, not an isolated pooling comparison.

Launch the reused local player with `python -m audio_similarity.cli.stage5e2 review --no-browser` (port 8784). Mutable judgments remain in the ignored research directory. Run `python -m audio_similarity.cli.stage5e2 metrics` after review to refresh metrics without changing the queue.
