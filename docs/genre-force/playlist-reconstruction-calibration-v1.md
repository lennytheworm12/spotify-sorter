# Playlist Reconstruction — Joint Audio and Genre Calibration v1

Status: **proposed; source permission/access and feasibility must pass before data collection or calibration**. No scorer change, new inference, coefficient selection, or production activation is included in this documentation update.

## Authoritative full protocol

Vault note:

`Projects/Spotify Sorter/Spotify Playlist Reconstruction — Joint Audio and Genre Weight Calibration Design.md`

Pinned publication: vault commit `1a4ecb502a807ba49c7831c8d648545d422ecd4c`.

[Read the full protocol](https://github.com/lennytheworm12/obsidian-vault/blob/1a4ecb502a807ba49c7831c8d648545d422ecd4c/Projects/Spotify%20Sorter/Spotify%20Playlist%20Reconstruction%20%E2%80%94%20Joint%20Audio%20and%20Genre%20Weight%20Calibration%20Design.md).

This file is a repository entry point, not a replacement for the full protocol. Follow its source checks, sampling rules, nested splits, metrics, selection policy, and permitted-use requirements. Preserve historical explorer contracts and results.

## Starting point

The frozen100 mechanical gate is PASS in `ml/audio_similarity/reports/genre_force_mechanical_gate/v1/REPORT.md`, reported commit `c6fb6de`. It verifies mechanics, not music usefulness.

The exact current audio baseline is `M3_C_PLUS_FIXED_MUQ`: CLAP C plus the existing centered30 MuQ arm. The original map is CLAP-C-based, not a C+MuQ distance display. Do not silently substitute full-song MuQ M4. Read `docs/genre-force/README.md` and pin the executed `configs/genre_force_v1/` hashes, not merely a historical similarly named design file.

## Hypothesis and collection paths

Use historical playlist membership as weak reference organization. Hide members, rank them from the remaining seed tracks, and ask whether audio/genre features improve observed-member recovery. This is not a claim that absent tracks are wrong, genres are objective truth, or the map defines admission.

Support both manual playlist/reference-set nomination and reproducible genre-query discovery. Ungrouped manually chosen songs are insufficient for reconstruction: explicit owner-created groups are new human labels and belong in a separate manual cohort. The user's 4–5 personal playlists are reserved for separately reported transfer, not the global training target.

The full protocol specifies twelve discovery strata spanning R&B substyles, boom bap, melodic/cloud rap, lo-fi/chillhop, downtempo/trip-hop, softer and synthetic pop, hyperpop, house, and drum-and-bass. Proposed feasibility pilot: 12 playlists × 20 tracks. Proposed main target: 60 playlists × 30 tracks, at least 30 curator/source groups, approximately 48 development playlists and 12 untouched lockbox playlists. These are resource targets, not power guarantees.

## Source restrictions are a real prerequisite

Spotify's [Developer Policy](https://developer.spotify.com/policy), especially III.13–14, restricts analysis and ML/AI use of Platform/Content. Its [Development Mode migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide) also restricts access to others' playlist contents. Do not assume public visibility, manual export, an existing cache, or curator permission resolves every platform/audio right.

Distinguish discovery references from eligible membership/audio sources. Do not evade access restrictions by scraping or copying playlists into an owned account. Independently supplied authorized groupings or an appropriately licensed research source may be eligible after the applicable checks. The historical Million Playlist Dataset is not assumed currently downloadable or usable through an unofficial mirror.

## Joint model and controlled comparisons

Freeze the per-track feature pipeline and mapper. Fit only:

```text
R = (1 - Jc) * Jnr
F = (1 - rho) * C + rho * M + w_c * Jc + w_n * R
0 <= rho <= 1
0 <= w_n <= w_c <= 0.10
```

This anchors the audio scale and leaves three effective parameters. Joint fitting is the main candidate once data readiness passes; refitted ablations accompany it. Compare exact frozen M3, CLAP, MuQ, tuned audio fusion, fixed-M3 genre additions, and joint audio/genre alternatives. No genre contribution is a valid outcome.

Use the full protocol's finite grid (396 unique joint settings, at most 432 with the original off-grid audio ratio), not unconstrained optimization. Keep pull-only, aggregation, encoder sampling, mapper relations, and prompt fixed. Vocal/arrangement/texture remain display-only; no signed-mode tuning or admission thresholds in this study.

For a candidate x and seed S, take the mean of the top three **combined pair scores**. Rank the entire fixed evaluation-partition catalog, identical across methods. Do not compute separate per-feature top-three means or select each model's own easier candidate pool.

Separate curator/duplicate-playlist groups, purge evaluation recordings from fitting seeds/positives/challengers, and use nested grouped validation inside development. Repeated 80/20 masks are queries, not independent outer folds. Preserve an untouched public lockbox and separately report artist-disjoint sensitivity and personal transfer.

Optimize observed-membership NDCG@20, report Recall@10/20, aggregate by playlist/curator/stratum, and prefer a simpler, smaller genre intervention within the stated uncertainty band. Nonmembership is unlabeled; these metrics are not true acceptance precision. Large repeated-artist or source overlap must not masquerade as generalization.

## Immediate Codex goal — Gate A only

Read the full protocol and verified artifacts. Implement a permission-aware playlist/reference-set intake manifest, the twelve-stratum query/nomination register, curator/duplicate grouping preflight, and a feature-overlap/cost report. Accept manual sources and permitted query-discovered references. Separate `discovery_only`, `permission_pending`, and eligible data. Do not collect new audio, make model calls, fit weights, alter the mapper, or activate production. Return source blockers and a bounded materialization proposal. Build synthetic fixtures if real sources are not cleared; report `SOURCE_NOT_READY` rather than a scientific verdict.

Subsequent gates are corpus freeze, feature parity, nested joint calibration, and one-time confirmation. The full protocol governs their details.
