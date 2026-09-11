# Playlist Reconstruction — Joint Audio and Genre Calibration v1.1

Status: **proposed; source permission/access and feasibility must pass before data collection or calibration**. No scorer change, new inference, coefficient selection, or production activation is included in this documentation update.

## Authoritative full protocol

Vault note:

`Projects/Spotify Sorter/Spotify Playlist Reconstruction — Joint Audio and Genre Weight Calibration Design.md`

Pinned publication: vault commit `76533ea6d3988f3a436a35ce27525c6702d10001`.

[Read the full protocol](https://github.com/lennytheworm12/obsidian-vault/blob/76533ea6d3988f3a436a35ce27525c6702d10001/Projects/Spotify%20Sorter/Spotify%20Playlist%20Reconstruction%20%E2%80%94%20Joint%20Audio%20and%20Genre%20Weight%20Calibration%20Design.md).

This file is a repository entry point, not a replacement for the full protocol. Preserve historical explorer contracts and results.

## Starting point

The frozen100 mechanical gate is PASS in `ml/audio_similarity/reports/genre_force_mechanical_gate/v1/REPORT.md`, reported commit `c6fb6de`. It verifies mechanics, not music usefulness.

The exact current audio baseline is `M3_C_PLUS_FIXED_MUQ`: CLAP C plus the existing centered30 MuQ arm. The original map is CLAP-C-based, not a C+MuQ distance display. Do not silently substitute full-song MuQ M4.

## Anti-circularity rule

Reference membership and source intent must exist independently of our model.

Use playlist title, description, curator/source statement, and observed membership as external supervision. Search terms such as `neo soul`, `alternative R&B`, or `hyperpop` are **discovery strata**, not the ground-truth ontology. Do not use Gemini, the canonical mapper, neighborhoods, CLAP/MuQ scores, or the Song Space map to remove “wrong-genre” songs before the benchmark is frozen.

A source playlist saying `Neo Soul` while our mapper later calls some tracks `Alternative R&B` is useful disagreement, not dataset contamination.

## Three benchmark layers

### Layer A — original source playlists

Primary v1 calibration and confirmation.

Preserve every human playlist boundary independently, even when several sources use the same genre/style name. Fit the global C/M/genre weights only on these original source playlists using grouped nested validation.

### Layer B — pooled same-label cohorts

Secondary post-fit diagnostic.

If three independent sources all describe lists as `Alternative R&B`, derive a union such as:

```text
alt_rnb_pool = union(source_A, source_B, source_C)
```

but never replace A/B/C with the pool. Preserve source provenance and report source-consensus counts. The pool measures a broader shared style region; it does not assert that every A song should strongly match every C song. Do not tune v1 weights on Layer B.

### Layer C — mixed playlists

Post-freeze product/generalization stress test.

Most real playlists are heterogeneous, so evaluate the frozen v1 model later on real mixed human playlists and controlled synthetic mixtures such as 50% pop + 50% R&B. Mixed playlists are intentionally not the first calibration target because they make signal attribution harder.

Synthetic mixtures test whether the playlist aggregator can recover multiple modes; they are not human ground truth. If mixed-playlist results expose a major failure, preregister a v2 mixed/product objective and obtain a fresh holdout rather than silently retuning v1 on the stress test.

The user's existing 4–5 playlists remain a separate personal-transfer cohort.

## Collection scope

The twelve discovery strata remain:

- alternative R&B
- neo soul
- contemporary/pop R&B
- boom bap/jazz rap
- melodic trap/cloud rap
- lo-fi/chillhop/instrumental hip hop
- downtempo/trip-hop
- indie/bedroom/dream pop
- synth-pop/electropop/dance-pop
- hyperpop/digicore
- house/deep house/nu-disco
- drum & bass/liquid dnb/jungle

These are search strata only. Human/source wording like `late night r&b`, `modern soul`, `dreamy indie`, or `internet pop` can be kept exactly as the source-defined intent.

Collecting a source means recording title, description, creator/curator, platform/reference, source-declared intent, date observed, membership/reference, discovery query/reason, and permission/status **before joining model outputs**.

Proposed feasibility pilot remains ~12 source playlists × 20 tracks. Proposed main Layer A target remains ~60 original source playlists × up to 30 sampled tracks, at least 30 curator/source groups, with an approximately 48/12 development/lockbox split when feasible. Derived pools and synthetic mixtures do not increase the independent human-source count.

## Source restrictions are a real prerequisite

Spotify's [Developer Policy](https://developer.spotify.com/policy), especially III.13–14, restricts analysis and ML/AI use of Platform/Content. Its [Development Mode migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide) also restricts access to others' playlist contents. Public visibility or manual transcription does not automatically establish permitted model-calibration use.

Separate discovery references from eligible membership/audio sources. Do not evade access restrictions by scraping or copying playlists into an owned account. Independently supplied authorized groupings, manually authored reference sets, or appropriately licensed research sources may be eligible after the applicable checks.

## Joint model and controls

Freeze per-track feature pipelines and the mapper. Fit only:

```text
R = (1 - Jc) * Jnr
F = (1 - rho) * C + rho * M + w_c * Jc + w_n * R
0 <= rho <= 1
0 <= w_n <= w_c <= 0.10
```

This leaves three effective parameters. Joint fitting is the main Layer A candidate once data readiness passes; refitted ablations accompany it. Compare exact frozen M3, CLAP, MuQ, tuned audio fusion, fixed-M3 genre additions, and joint audio/genre alternatives. Zero genre/neighborhood contribution is a valid result.

For candidate x and seed S:

```text
Q_theta(x,S) = mean(top-3 combined pair scores F_theta(x,s), s in S)
```

The top-three operation happens after the complete pair score is computed. Keep aggregation fixed during v1. This same aggregator is later stress-tested on Layer C multimodal playlists.

Use fixed candidate catalogs across methods, grouped/nested validation, record purging, and an untouched Layer A lockbox. Primary selection metric is observed-membership NDCG@20; report Recall@10/20 and per-source/per-stratum results. Nonmembership is unlabeled, not proven incompatibility.

Layer B, personal playlists, and Layer C do not choose v1 coefficients. They diagnose broader generalization after the Layer A model is frozen.

## Immediate Codex goal — Gate A only

Read the full v1.1 protocol and verified artifacts. Implement a permission-aware playlist/reference-set intake manifest and validator, the twelve-stratum source-discovery/nomination register, and source metadata capture that freezes title, description, creator, declared intent, original playlist identity, and membership before model outputs are joined.

Preserve separate source playlists even when several share one declared label. Support derived same-label pools only as later Layer B artifacts. Accept mixed playlists as `layer_c_candidate`, excluded from v1 calibration. Add curator/duplicate grouping preflight and a feature-overlap/cost report.

Do not scrape restricted sources, collect new audio, make model calls, fit weights, alter the mapper, use mapper predictions to clean membership, or activate production. If real sources are not cleared, build synthetic fixtures and return `SOURCE_NOT_READY` rather than a musical verdict.
