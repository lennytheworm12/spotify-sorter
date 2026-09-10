# Frozen-100 canonical-first genre explorer

Status: **DEVELOPMENT_EXPLORER_READY**. The complete local explorer is available at
`http://127.0.0.1:5174/#/genre`. Reproduction and launch commands are in
[`docs/genre-force/README.md`](../../../../../docs/genre-force/README.md).

All 100 original songs have their original Gemini fields and source hashes, all
4,950 unordered pairs are scored, and each song has 99 ranked candidates. The
independent audit checks 9,900 directed baseline ranks against the original matrix.
This is an inspection tool, not an evaluation of playlist accuracy.

## Baseline and contract interpretation

The current vault contract is `genre-force-explorer-v1.2`, revision
`canonical-first-residual-v1`. Its pinned registry has 138 concepts and 29
neighborhoods. No old 41-concept mapping enters the scorer.

“Existing frozen C + M” is implemented as **M3_C_PLUS_FIXED_MUQ**, C plus the
existing centered30 MuQ representation. The source NPZ SHA-256 is
`efea93bb95cb1b7addb74b3816d2757ad93bdbec583215a7b43e8de004c93e97`.
M4 (full-song MuQ) also exists; choosing M3 is an explicit implementation
interpretation of “existing,” not an owner-confirmed or outcome-selected winner.
The exporter requires the matrix key and copies scores exactly, without fusion
recalculation. Its M4 path remains available for a separately named run.

The existing visual map is CLAP C. The new run freezes coordinates recreated by
its unchanged seeded layout engine. These coordinates do not claim to be a frozen
C+MuQ geometry. Move graph off preserves them; Move graph on uses temporary
adjusted edges, and resetting alpha or turning movement off restores them.

The old registry's scoring placeholder is superseded by the current contract.
Reviewed families can contribute canonical mass once both tracks have a specific
style. They cannot create residual neighborhood support. Reviewed `kind=style`
opens this gate; the registry's broad Rap/Electronica umbrellas cannot open it
alone. Duplicate labels use maximum field strength. No taxonomy changes were made.

## What is available

- Exact canonical weighted Jaccard; subtract matched canonical mass, then project
  residual styles through existing core/related neighborhood weights using max.
- Preferred `G = Jc + eta*(1-Jc)*Jnr`; canonical-only and neighborhood-only modes.
- `adjusted = M3 + alpha*beta*G_force`. Defaults: alpha 0, beta .05, eta .25,
  pull-only. Signed mode is explicitly an experimental low-overlap penalty.
- All candidate scores/ranks, pair explanations, exact/unmatched/recovered/context
  tag colors, original fields/traces/warnings, vocals and arrangement as context.
- Top-K entries/exits, largest movers, all-pair delta distribution and neighborhood
  retrieval diagnostics. Retrieval does not restrict the 99 candidates.
- Manual alpha, beta and eta controls; no automatic selection or persistence of
  test slider settings as new defaults.
- Original graph and old/new mapping comparison links; keyboard Left/Right for
  songs and Space for anchor playback, with input controls protected.

`Love Always Leaves Me` has only broad eligible family concepts. Its 99 pairs have
zero genre contribution in every mode. Classification/mapping disagreements
remain visible; neither missing style information nor a broad family is a hard
playlist rejection.

## Verification

| Contract | Direct evidence |
|---|---|
| 100 songs, 4,950 pairs, 99 candidates each | `explorer.json`, `independent_audit.json`, real browser audit |
| Exact unchanged M3 baseline and alpha-zero ranks | `baseline_rankings.json`; independent comparison of all 9,900 ranks to source NPZ |
| Canonical/residual formulas, gates and symmetry | 8 focused TypeScript tests; independent Python oracle over all 4,950 pairs; `engineering_checks.json` |
| Default and alternate modes bounded | `engineering_checks.json`; real and synthetic browser audits |
| Raw labels and source identity preserved | 100-profile equality/source checks in `independent_audit.json`; hashes in packet provenance |
| No repeated inference or rewritten run files | `replay.json`: network forbidden, zero inference, identical hashes and modification times, no new files |
| Deterministic finalization | Repeated `freezeGenreForce.ts` verified identical output bytes |
| Existing history unchanged | `historical_integrity.json`: 2,036 files verified against pre-existing manifests |
| Sliders, rankings, inspector and graph restoration | Real Chromium visits all 100 anchors, toggles all modes and checks coordinate signatures |
| Playback, seeking, Range, keyboard, mobile | `browser_real/verification.json` and screenshots; no console errors or review writes |
| Frontend regression/build/lint | 14 tests passed; `tests_frontend.txt`, `build_frontend.txt`, `lint_frontend.txt` |
| Full non-heavy Python suite | 1,422 passed, 12 deselected, 11 warnings; `tests_non_heavy.txt` |
| No production activation or outcome fitting | Opt-in read-only local data bridge; no rating input or model invocation in exporter/scorer |

The first full-suite attempt reported 1 failure and 1,421 passes: the original
mapper replay fixture unintentionally included newly added contract files in its
provenance. Its test now reproduces the original frozen input membership; original
mapper outputs remain untouched. The complete rerun passed. Browser screenshots
show manual test settings alpha 1, beta .10 and eta .50; these are not selected
parameters or evidence of musical improvement.

## Files and limits

`explorer.json` is the full reviewable packet: song IDs/titles, exact raw profiles,
canonical vectors, neighborhood vectors, exclusions/traces, source hashes, frozen
coordinates and every audio pair. `pair_genre_evidence.json` records Jc/Jnr/Jn;
the browser applies the selected mode and coefficients interactively.

`artifact_manifest.json` covers this published package. The private run remains at
`.research_audio/genre_force/v1_m3/`; its manifest hash is recorded in the
independent audit. Private audio paths and recordings are not published. Replay
requires the retained local audio, not an API call or download.

No human labels were read, manufactured or changed. No Gemini requests, new audio
inference, embedding changes, production ranking changes, playlist writes or
automatic parameter optimization occurred. The 100 songs are development data.
Any mode/parameter choice informed by this page needs new held-out evidence before
claiming improved playlist compatibility.
