# Output Calibration — Scores, Admission and User Strictness v1

Status: **proposed, not fitted or production activated**. The frozen100 mechanical gate does not establish calibrated weights, probabilities, or admission thresholds.

## Authoritative full design

Vault note:

`Projects/Spotify Sorter/Spotify Output Calibration — Scores, Admission and User Strictness.md`

Pinned publication: vault commit `1be145263f0e6405a68b3d9a0949ce7218ddc6a4`.

[Full output-calibration protocol](https://github.com/lennytheworm12/obsidian-vault/blob/1be145263f0e6405a68b3d9a0949ce7218ddc6a4/Projects/Spotify%20Sorter/Spotify%20Output%20Calibration%20%E2%80%94%20Scores%2C%20Admission%20and%20User%20Strictness.md).

Predecessor: [ranking calibration v1.2](playlist-reconstruction-calibration-v1.md). The full design governs reference construction, labels, data roles, fitting, policy, output fields, and validation. This is a repository entry point, not a second conflicting specification.

## Reviewed decisions

Keep these outputs distinct:

```text
F(a,b)     raw song-pair score
Q(x,P)     raw song-to-playlist score (top-three combined pair scores)
u(x,P)     descriptive member-reference percentile
p(x,P)     optional validated suitability estimate
policy     user strictness -> admission threshold
```

Percentile is not probability. A distant-genre source does not establish an unsuitable candidate. Nonmembers are unlabeled. The average lowest Top-K score is not an acceptance calibration target. Top-three support measures fit to a local playlist region, not global all-pairs compactness.

The current ranker must be selected and frozen before output fitting. Pin CLAP representation, MuQ extraction, coefficients, mapper, source hashes, top-three aggregation, and candidate policy. Never apply a playlist-Q calibrator to pairwise F.

## Stage sequence

1. **O1 descriptive audit:** reuse eligible cached scores and observed membership. Save full ledgers, member/unlabeled score distributions, support IDs, seed sizes, and candidate-source provenance. No new labels are required to characterize outputs.
2. **O2 suitability-label readiness:** define candidate–playlist suitability under a fixed intent; record suitable/unsuitable/uncertain/cannot-assess separately. Historical membership and genre-distant examples are weak evidence, not automatic binary truth.
3. **O3 optional probability mapping:** fit a monotone sigmoid on independent frozen-ranker scores; isotonic is a later predeclared comparison with enough data. Evaluate reliability, log loss/Brier, counts and source-cluster uncertainty. Raw-score threshold validation is also possible without probability conversion.
4. **O4 policy and user strictness:** choose ordered Broad/Balanced/Tight operating points on policy-development data, based on an approved unwanted-addition versus missed-fit tradeoff. Test the entire frozen pipeline on untouched final data.

Without suitable labels, stop at descriptive/ranking output. Do not fabricate negatives or claim calibrated acceptance precision.

## Member-reference construction

Ordinary leave-one-out scores compare existing members against n-1 possible seeds, while new candidates see n; top-three selection benefits from extra available neighbors. The full protocol specifies an equal-sized seed helper: for at least 20 unique reference recordings, m=min(20,n-1), eight deterministic subsets per query, self/duplicate exclusion, and a tie-aware empirical percentile of the resulting averaged scores.

This helper is descriptive only, separate from full-context Q. Return null for inadequate references and expose reference size/protocol. Repeated subsets are not independent members. No confidence, conformal-coverage, or false-addition guarantee follows from this percentile.

## Data roles

Separate ranking development, output-fit, policy development, and final end-to-end test. Preserve curator/duplicate-source boundaries, recording/version purges, and inherited partitions for mixtures. An inspected ranking lockbox is not a fresh threshold test. The old 48/12 source-cohort proposal must be revised or supplemented before claiming these roles are all independent.

Calibration samples should represent the intended candidate-generation policy. Oversampled challenge cases require separate reporting or justified sampling weights. Precision is population-dependent. Do not pool metadata-visible personal preferences and blinded audible-fit labels into one undefined target.

## Strictness behavior

Strictness does not alter CLAP/MuQ/genre weights or ordering. For a fixed playlist snapshot, higher strictness yields a subset of the lower-strictness recommendations. Threshold units must be explicit: raw Q or validated suitability probability.

No numeric default thresholds or precision guarantees have been selected. Before policy validation, expose only an explicitly uncalibrated research cutoff preview. Unavailable calibration, missing evidence, or unsupported domains return not-calibrated/needs-review states, not rejection.

Freeze playlist seeds for a batch preview. Predicted additions must not recursively become seeds for later candidates. Existing playlist members are not removed by a stricter setting. Recommendation and user-authorized playlist writing remain separate.

## Immediate Codex goal

Build readiness and descriptive scaffolding only: verify a selected ranking model exists; define the output ledger and data-role audits; implement deterministic reference-helper and null/monotonicity/self-exclusion tests on synthetic fixtures. Keep probabilities and validated admission decisions unavailable until evidence exists. No weight tuning, threshold selection, mapper change, model calls, audio acquisition, or playlist writes. If no frozen selected ranker exists, mark the report blocked on ranker selection rather than treating the mechanical gate as scientific calibration.

Report namespace: `ml/audio_similarity/reports/output_calibration/v1/`. The full vault protocol contains the proposed typed output contract, scoped outcomes, source references, and all operational details.
