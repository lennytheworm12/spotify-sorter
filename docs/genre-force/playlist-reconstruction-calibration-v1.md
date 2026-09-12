# Playlist Reconstruction — Joint Audio and Genre Calibration v1.2

Status: **proposed; no model or output calibration result is asserted**. This documentation update changes no runtime scorer, feature pipeline, mapper, Gemini prompt, frozen score, or playlist.

## Current protocol and retained reference

Full current vault note:

`Projects/Spotify Sorter/Spotify Playlist Reconstruction — Joint Audio and Genre Weight Calibration Design.md`

Pinned publication: vault commit `1be145263f0e6405a68b3d9a0949ce7218ddc6a4`.

[Read ranking protocol v1.2](https://github.com/lennytheworm12/obsidian-vault/blob/1be145263f0e6405a68b3d9a0949ce7218ddc6a4/Projects/Spotify%20Sorter/Spotify%20Playlist%20Reconstruction%20%E2%80%94%20Joint%20Audio%20and%20Genre%20Weight%20Calibration%20Design.md).

The previous complete v1.1 protocol is preserved byte-for-byte as:

`Projects/Spotify Sorter/Spotify Playlist Reconstruction — v1.1 Protocol Reference.md`

[Read retained source/data/split protocol](https://github.com/lennytheworm12/obsidian-vault/blob/1be145263f0e6405a68b3d9a0949ce7218ddc6a4/Projects/Spotify%20Sorter/Spotify%20Playlist%20Reconstruction%20%E2%80%94%20v1.1%20Protocol%20Reference.md).

Read both: unchanged source permissions, anti-circularity, collection, split, metric, and three-layer requirements remain applicable. v1.2 supersedes the old fixed-CLAP restriction and adds explicit representation selection and an output-calibration handoff.

Next output stage: [Output Calibration — Scores, Admission and User Strictness](output-calibration-v1.md), linking its full pinned vault design.

## Existing baseline versus proposed alternatives

The reported frozen100 mechanical gate at `c6fb6de` verifies arithmetic and UI/graph behavior only.

The documented explorer baseline is `M3_C_PLUS_FIXED_MUQ`: CLAP Method C plus centered30 MuQ. Original map coordinates are CLAP-C-based. A newer acquisition batch with `centered30_v1` CLAP/MuQ embeddings is a separate artifact even if it retains full audio. Full-song MuQ M4 must not be silently substituted.

Cache centered30 CLAP and Method C separately over the same approved, validated recordings. Reuse source hashes and exact caches. An authorized bounded extraction worker may overlap acquisition; this document starts no job. Retaining full audio permits later feature extraction without another download, but does not imply those features already exist.

Freeze corpus rules independently of model outputs. Representation manifests must identify checkpoints, sampling, pooling, source identity, and feature hashes. Common-population comparisons and coverage/attrition reporting remain required.

## Source-defined benchmark layers

Reference membership comes from the original curator/source, not our mapper. Freeze title, description, declared intent, source ID, membership, and discovery reasons before inspecting predictions. Search genre names are strata, not model-generated truth. Keep source disagreements and unusual members unless a predeclared non-model exclusion applies.

- **Layer A:** original source playlists; primary ranking calibration/confirmation.
- **Layer B:** pooled same-declared-label cohorts; derived post-selection diagnostics with original boundaries preserved.
- **Layer C:** real mixed playlists and controlled synthetic mixtures; post-freeze product stress tests.

The user's 4–5 playlists remain a separate transfer cohort. More masks or synthetic mixtures do not increase independent curator evidence. Source/access and audio-use prerequisites remain in the retained v1.1 protocol; this revision does not authorize acquisition.

Keep the twelve discovery strata, original metadata schema, approximate 12-playlist feasibility pilot and 60-source-playlist resource target in that reference. These are planning targets, not guarantees. The old approximate 48/12 split does not automatically satisfy the later output-fit/policy/final-test requirements.

## Joint representation and weight search

```text
h ∈ {centered30_v1, Method_C}
R = (1 - Jc) * Jnr
F_theta = (1-rho) * C_h + rho * M + w_c * Jc + w_n * R
0 <= rho <= 1
0 <= w_n <= w_c <= 0.10
```

Search h jointly with the audio mixture and genre weights **inside inner validation**. Keep MuQ extraction, the verified canonical/residual scorer, top-three aggregator, candidate catalog, and prompt fixed.

```text
rho: 0.0, 0.1, ..., 1.0
w_c: 0, 0.005, 0.010, 0.020, 0.035, 0.050, 0.075, 0.100
eta: 0, 0.25, 0.50, 0.75, 1.0
w_n = w_c * eta
```

There are 880 nominal configurations across the two CLAP methods before deduplicating inactive eta at w_c=0 and inactive h at rho=1. Alpha/beta are not fitted separately; their product is the effective genre coefficient.

Precompute each encoder/profile once per recording/configuration; searches combine cached features. Large-catalog ranking still needs measured runtime and bounded-memory evaluation. Preserve exact M3 as a separate baseline whether or not it equals a grid configuration.

Refit each ablation: each CLAP method alone, MuQ alone, each audio mixture, audio+canonical, audio+canonical+residual, plus fixed-M3 genre additions. Zero added genre is a valid result. No signed-force tuning, vocal/arrangement scoring, per-genre production weights, or mapper edits in the main search.

## Reconstruction and selection

Hide 20% of each eligible evaluation source playlist and use the remaining seed context. Rank hidden members among the same larger evaluation catalog for every model, never among only the hidden positives.

```text
Q(x,S) = mean(top min(3,|S|) complete pair scores F(x,s))
```

Select the top three after combining all pair features. Exclude self/duplicate recording support. Save full ranks and scores.

Use curator/duplicate-group nested splits and recording/version purges at each fitting/evaluation boundary. Primary metric remains observed-membership NDCG@20, with Recall@10/20, source/stratum macro results, uncertainty, and coverage. Nonmembership is unlabeled, not validated rejection. Prefer a simpler, smaller intervention within the retained uncertainty/recall guardrails; report boundary-limited and inconclusive outcomes.

Log per-stratum surfaces on development only. They are exploratory evidence for a future hierarchical model, not permission to select genre-specific settings using the final test. Source-adjacency discovery notes remain qualitative, not labels.

## Handoff to output calibration

Freeze `ranking_model_id`: CLAP/MuQ manifests, rho, genre coefficients, mapper, source policy, aggregator and tie breaking. Then follow the output protocol:

```text
frozen F/Q -> descriptive distributions/reference percentiles
           -> suitability-label readiness
           -> optional probability mapping
           -> policy/strictness development
           -> untouched end-to-end confirmation
```

Percentiles are not acceptance probabilities. Genre-distant candidates are not automatic negatives. Thresholds can be validated directly on raw Q, but precision claims still need a justified suitability target. User strictness changes qualification, not the ranker or the score order. Top-three local support does not guarantee whole-playlist compactness.

Do not reuse an opened ranking lockbox as an untouched final threshold test. Reserve suitable independent data roles or collect more permitted sources. If no selected ranker or labels exist, output work stays descriptive/scaffold-only.

Ranking artifacts: `ml/audio_similarity/reports/playlist_weight_calibration/v1/`.
Output artifacts: `ml/audio_similarity/reports/output_calibration/v1/`.

## Immediate implementation boundary

Continue only the source/feature/readiness work already authorized by the user. No new inference, coefficient fit, output threshold, or production activation is created by this documentation update. The full vault ranking and output notes include the next scoped Codex tasks and all prerequisite checks.
