# Gate 5 — weight search design (v1)

**Status:** DESIGN FOR APPROVAL · Owner: Bi Phan · 2026-09-15
**Entry state:** execution_contract_v8.json · readiness_report_v12.json · split_manifest_v2.private.json

## Why a design doc is warranted

The pre-gate-5 sanitation check found **87 lockbox recordings leaked into the
learn-and-train set** (recording-level membership overlap across playlists; v1
assigned roles per playlist). Running the search on that split would have
contaminated the one-time confirmation set. Split v2 fixes it and the design
below pins the discipline before any fitting starts.

## 1. Inputs (frozen, hashed)

| Item | Value |
|---|---|
| Feature snapshot | 3,059 recordings / 7 matrices (Jc, Jnr, R, M, C_center30, C_method_c, genre_pair_valid) |
| Learn-and-train | 1,484 recordings (20 playlists) |
| Outer validation | 297 recordings (3 playlists) |
| Lockbox (SHUT) | 485 recordings (5 playlists) |
| Span available | all 7 matrices; 6,117 NaN cells = the 1 recording with no profile |
| Cost | $0 — no API calls, no audio inference |

## 2. Question the search answers

One weight vector w over the evidence channels, so that a playlist's hidden
members rank above non-members — fitted only on learn-and-train, selected only
on outer validation.

## 3. Protocol (must be locked before the run)

1. **Fit** on learn-and-train only. Grouped by curator/duplicate family; no
   family may straddle a boundary.
2. **Select** on outer validation only. Record the selection criterion and the
   full candidate table, not just the winner.
3. **Freeze** the winning w + procedure, hash it, and only then open the lockbox
   ONCE. Lockbox results are reported as-is, never used to re-select.
4. **Leakage guards:** assert learn ∩ lockbox = ∅ and learn ∩ validation = ∅
   immediately before and after the fit (split v2 invariants are TRUE).
5. **Per-pair validity:** pairs with mask=False / NaN are excluded from the
   score, never treated as zero.
6. **Determinism:** fixed seed, sorted ids, and a re-run must reproduce the
   weights bit-for-bit.

## 4. Deliverables

- w (weights) + the full candidate/search table
- the selection receipt: criterion, validation numbers, tie-breaks
- a frozen procedure hash, then the single lockbox evaluation
- a report with costs ($0 expected) and hashes for every artifact

## 5. Stop conditions

- Any invariant false → abort, do not fit
- Lockbox touched before the freeze → the run is void
- Reproducibility failure → abort and report

## 6. Known limits (to state in the result)

- The 2.18M cross-corpus pairs are new evidence; this is a new measurement, not
  a superset of the earlier extension-only calibration.
- 1 recording has no profile (Neon Kitchen II) — NaN + mask, excluded not zeroed.
- 1 repaired profile (radio-edit substitution) carries substituted-audio provenance.
- Permission for the corpus is NOT claimed: `permission_supported: false`.
