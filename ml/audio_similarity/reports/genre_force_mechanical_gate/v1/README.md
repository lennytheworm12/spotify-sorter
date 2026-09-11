# Genre Explorer Mechanical Verification Gate

**Mechanical result: PASS. Failing pair IDs: none.**

Regression results: **17 frontend tests** and **1,425 non-heavy Python tests
passed** (12 heavy deselections; 11 warnings). The seven focused Python mapping
tests also passed. Frontend build and lint passed. The first full-suite attempt
was interrupted by the sandbox blocking a localhost test fixture; the successful
rerun used local-server access. See `execution_attempts.json` and the saved logs.

This verifies implementation correctness on the complete frozen 100. It does not
evaluate genre usefulness, select weights, or establish playlist accuracy. The
mapper, defaults, Gemini classifications, frozen audio scores and graph artifacts
were not changed. No Gemini or other model inference ran.

| Requirement | Evidence |
|---|---|
| Jc correct, symmetric and bounded | Independent Python reference checks all 4,950 pairs against the current TypeScript scorer; exact equality of current canonical/residual components |
| Only unmatched mass contributes to Jnr | All 4,950 shared, union, residual and projected vectors independently checked; synthetic tests cover exact matches, unequal shared weights and the double-counting trap |
| Jnr and G symmetric and bounded | All pairs across 15 fixed QA scenarios; 297,000 float64 genre/force/delta/adjusted components match the independent reference exactly |
| Alpha zero exactly restores audio scores and ordering | Source NPZ audited directly; 59,400 directed rank checks across six modes, plus every Top-K prefix K=1..99 |
| Display agrees with computed components | Chromium checks 118,800 directed table rows across 12 scenarios and 1,200 pair-inspector renderings; no mismatches |
| Exclusions and insufficient evidence are neutral | Synthetic alias/weight/context/unresolved tests; all 100 profiles regenerated through the unchanged canonicalizer; 99 pairs involving the broad-only profile stay no-ops |
| Move graph off keeps exact coordinates | All 15 numerical scenarios and all 1,200 browser anchor/scenario views preserve original coordinate values |
| Move graph on uses adjusted weights deterministically | Every graph edge checked against its adjusted pair score; six layouts generated twice; browser worker matches all 600 expected song coordinates exactly and restores original positions |
| Frozen artifacts stay unchanged | Frozen-run SHA-256 and modification times unchanged; 2,036 historical files verified against their existing manifests |

Synthetic cases include exact canonical matches, weighted partial overlap,
different concepts sharing a neighborhood, no relationship, secondary weights,
duplicate aliases, context-only and unresolved profiles. The specificity gate is
the current documented rule: both tracks need a reviewed specific style. Eligible
family concepts may contribute to Jc after that gate opens; they never project
into residual neighborhoods. Broad-family-only profiles cannot open the gate.

## Precision and coverage

Arithmetic reconstructs **exactly at full precision**:
`delta = alpha * beta * G_force`; `adjusted = original_audio + delta`.
The UI intentionally formats scores/deltas/inspector components to six decimal
places and the table's G to four. Every checked string equals the correctly
rounded reference result. Rounded visible numbers are not full-precision inputs;
recalculating from those strings alone can differ in the last displayed digit.
Use `components.json` and `scores.f64` for exact reproduction.

All 4,950 unordered pairs are checked in both table orientations for every browser
scenario. The 1,200 inspector checks cover each anchor's first-ranked candidate
in each scenario; they are not a claim that every inspector was opened. All
pair-level Jc/Jnr/residual calculations are covered independently by the numerical
gate. No backend similarity service is introduced: frozen backend artifacts
provide the audio scores and mapped profiles; the existing frontend scorer is
checked against an independent Python implementation.

## Reproduce

Full commands are in [the explorer documentation](../../../../../docs/genre-force/README.md#exhaustive-mechanical-qa-gate).
Start the existing local explorer on port 5174, run `genreMechanicalGate.ts` and
`genreMechanicalGraphs.ts`, then run `genre_mechanical_audit.py`,
`browser_genre_mechanical.py` and `browser_genre_mechanical_graph.py` using a
separate QA directory. Reusing the same QA directory verifies identical numerical
outputs and refuses a changed replay.

`contract.json` freezes the tested scenarios and source hashes before execution.
The 12 primary scenarios are the three genre sources × two polarities × alpha
0/1 at unchanged beta=.05 and eta=.25. Three additional mechanical boundary
probes cover beta=0, eta=0, and fractional alpha at the existing UI coefficient
bounds. These are fixed tests, not calibration candidates or selected settings.

`scores.f64` is little-endian float64, ordered by contract scenario, then
`components.json` pair order, then `[genre, force, delta, adjusted]`. Each failure
ledger records its check, stable pair/track IDs, scenario and expected/actual
values. All failure ledgers are empty. Graph correspondence includes each checked
scenario and its exact-match result.

The original packet SHA-256 is
`3532f89e65c934c594bb2aa0e1a3f2db70573bd1b3059e8944b93162ac3afad4`.
The audio baseline remains **M3_C_PLUS_FIXED_MUQ**, source NPZ SHA-256
`efea93bb95cb1b7addb74b3816d2757ad93bdbec583215a7b43e8de004c93e97`.
`artifact_manifest.json` covers this separate QA package; earlier reports and
verdicts are preserved.
