# Coarse hierarchical style-band prior on frozen CLAP C

Outcome: **STYLE_BAND_SHORTCUT_NOT_ESTABLISHED**. Development-only; no production activation.

This tests one predefined taxonomy and one bounded soft-penalty family. It does not test all possible style priors, and previously inspected ratings do not constitute fresh confirmation.

## Inputs and protocol

100 frozen tracks; 419 existing playlist-compatibility pairs (55 bad, 113 middle, 251 good). The exact grouped evaluation contains 258 strict preferences over 70 anchors. Holistic ratings and taxonomy-review answers were not used as extra training labels.

Configuration SHA-256: `1413390b926d97ab4c803ca0f0a48f3da58e7dd911d8fd3315db4f528dd9b0fc`. `input_hashes.json` locks every implementation/configuration and protected input; `mapping.json` lists all 400 exact style assignments. `band_features.npz` retains raw masses, band/parent profiles, known-signal fractions, distance, identities and unchanged C scores.

Thirteen informative bands plus unknown; eight parent neighborhoods. Sum raw full-track sigmoid means through the fixed mapping, smooth informative band masses by 1e-8, normalize, and sum into parents. Distance = known fractions × (half band JS + half parent JS), in bits. `adjusted C = C - lambda * distance`; no hard rejection. Multi-label mass is not calibrated genre probability; correlated tag counts can bias the aggregation.

## Grouped ranking agreement

| Method | Anchor-macro agreement, descriptive 95% interval |
| --- | --- |
| C | 0.6765 [0.5904, 0.7613] |
| band | 0.6765 [0.5904, 0.7613] |
| raw_style_control | 0.6718 [0.5863, 0.7567] |

Band-minus-C paired delta: **0.0000 [0.0000, 0.0000]**. Artist/source-cluster sensitivity: 0.0000 [0.0000, 0.0000], 53 connected groups.

Strong-preference delta: 0.0000 [0.0000, 0.0000]. Diagnostic-artist exclusion delta: 0.0000 [0.0000, 0.0000]. Neither sensitivity refits the selected lambdas.

| Fold | Selected band lambda | Raw-style control lambda | C held-out | Band held-out |
| --- | --- | --- | --- | --- |
| 0 | 0 | 0 | 0.5116 | 0.5116 |
| 1 | 0 | 0 | 0.7493 | 0.7493 |
| 2 | 0.1 | 0.1 | 0.7679 | 0.7679 |

Selection uses only training preferences on tracks disjoint from that fold’s evaluation tracks, including credited artist and source/video groups. Grid: 0, .025, .05, .10; smallest maximizing strength wins. All training grid scores and per-anchor evaluation scores are in `results.json`. No taxonomy or strength was changed after inspecting results.

## Corrections and damage

Among 39 good-versus-bad preferences, C had 11 strict errors and 28 strict correct orderings. The prior strictly corrected **0** orderings involving **0 unique bad pairs**, and broke **0** orderings involving **0 unique good pairs**. There were 0 tie transitions. Net good/bad ranking credit: +0.

These are observed relative-order changes, not playlist admission decisions. A unique pair can be affected in multiple anchor comparisons. `changed_orderings.csv` identifies every changed ordering with song titles, artists, ratings and before/after scores; `preference_changes.json` also includes unchanged orderings.

| Top-5 scope | Removed bad | Removed good | Added good | Added bad | Added unknown |
| --- | --- | --- | --- | --- | --- |
| top5_grouped | 2 | 0 | 1 | 0 | 7 |
| top5_all_candidates_diagnostic | 0 | 2 | 0 | 0 | 1 |

Top-5 counts above are directed query/candidate slots; `top5_summary.json` also provides global pair deduplication and all good/middle/bad/unknown kept/added/removed categories. Grouped candidate pools contain only held-out tracks. The all-candidate diagnostic includes training candidates and is not held-out generalization evidence. Removing a bad match does not establish benefit when its replacement is unknown.

## Breadth and complementary signal

| Dominant predicted parent | Anchors | Paired delta, 95% interval | Corrected / broken good-bad orderings |
| --- | --- | --- | --- |
| electronic | 11 | 0.0000 [0.0000, 0.0000] | 0 / 0 |
| hip_hop | 11 | 0.0000 [0.0000, 0.0000] | 0 / 0 |
| popular_song | 48 | 0.0000 [0.0000, 0.0000] | 0 / 0 |

The same breakdown at fine band resolution is in `results.json`, with correction counts in `region_corrections.json`. These regions are classifier-derived, not verified genres. Empty or tiny regions cannot demonstrate broad generalization.

| Distance signal | All-pair good/bad macro AUC | Within C cosine .05 caliper | Either-direction C Top-5 |
| --- | --- | --- | --- |
| C_distance | 0.8002 [0.7238, 0.8728] | 0.6022 [0.4607, 0.7409] | 0.8045 [0.6000, 0.9636] |
| band_distance | 0.7042 [0.6215, 0.7860] | 0.6683 [0.5280, 0.7989] | 0.7121 [0.5379, 0.8864] |
| raw_style_distance | 0.7114 [0.6273, 0.7908] | 0.6398 [0.4995, 0.7747] | 0.8333 [0.6970, 0.9545] |

Caliper and Top-5 diagnostics test whether distance distinguishes good/bad pairs in similar C-score neighborhoods. They are descriptive, may involve few anchors, and cannot override the grouped ranking verdict.

## Frozen decision and next step

- anchor_interval_positive: FAIL
- cluster_interval_positive: FAIL
- diagnostic_exclusion_positive: FAIL
- largest_region_exclusion_positive: FAIL
- material_primary_gain: FAIL
- more_corrections_than_damage: FAIL
- multiple_regions: FAIL

Largest eligible parent: `popular_song`; excluding it gives 0.0000 [0.0000, 0.0000].

Close this coarse genre-band shortcut as not established. Return to the learned playlist-compatibility scorer / supervision path: first audit grouped-data sufficiency for frozen CLAP C and the actual playlist rubric, then design one small regularized scorer if evidence permits. Do not expand taxonomy rules or retune this result.

## Verification and limitations

100 existing cached track outputs (18,823 classifier patches) were validated and reused; **zero new audio inference**. `replay.json` records exact-byte replay of seven numerical/analysis artifacts. Historical source and artifact hashes are checked before execution and on replay. No historical verdict, representation, rating or ledger is overwritten.

`validation.json` records actual focused/full-suite results and any publication-dependent check timing. `artifact_manifest.json` covers all final artifacts except itself; verify it with the canonical `verify_hashes` helper. Commands and complete frozen interpretation rules are in `docs/style_band_prior.md`.

Limits: one reviewer, sparse candidate-union-selected ratings, reused development folds, small correlated evaluation groups, approximate musically authored hierarchy, uncalibrated style outputs, and classifier-derived regions. Neither success nor failure establishes universal human perception or fresh test-set performance.
