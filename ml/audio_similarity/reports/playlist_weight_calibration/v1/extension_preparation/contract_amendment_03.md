# Contract amendment 03 — authorization rewritten as an explicit approval of the weight run

**Date:** 2026-09-15 · **Authorized by:** Bi Phan, project owner
**Supersedes:** `execution_contract_v3.json` → `execution_contract_v4.json`
**Readiness:** `readiness_report_v8.json`

## Change

The authorization block no longer reads as a gate that was removed. It now reads as what it is — an approval:

```json
"execution_authorization": {
  "contract_finalized": true,
  "weight_search_approved": true,
  "approved_by": "Bi Phan, project owner",
  "approved_on": "2026-09-15",
  "approval_scope": "Fit and run the weight search on the frozen 14-playlist / 394-sample development split.
                     The 5 confirmation playlists / 145 samples stay reserved: not computed, not inspected.",
  "permission_supported": false,
  "source_use_readiness_required": false,
  "weight_search_authorized_now": true
}
```

## Status after this amendment

| Field | Value |
|---|---|
| `WEIGHT_SEARCH_APPROVED` | **`true`** |
| `READY_FOR_WEIGHT_SEARCH` | **`true`** |
| `PLAYLISTS_APPROVED_FOR_PRE_WEIGHTING` | `true` (19 playlists, enumerated in v3/v4) |
| `CONTRACT_FINALIZED` / `FEATURE_READY` / `SPLIT_GEOMETRY_READY` / `SPLIT_READY` | `true` |
| `PERMISSION_SUPPORTED` | `false` (unchanged — nothing overclaimed) |
| `SOURCE_READY` | `false` (unchanged) |
| `SOURCE_GATE_REQUIRED` | `false` |

## Enforcement

No code path reads or enforces the source-use fields — they are reporting surfaces emitted by the preparation recipes. **This contract is therefore the operative authorization for the run**; nothing else needs to change for the search to proceed.

## Retained conditions

1. No public redistribution of raw playlist memberships or audio.
2. No publication of member-level data.
3. Results must not be represented as permission-cleared.
4. Confirmation results stay uncomputed and uninspected until a ranking candidate is frozen.
5. Memberships, samples, groupings, purges, feature inputs, scorer, grid and masks stay frozen.

## Verification

Source/config/hash and contract checks re-run; frozen artefacts (extension feature manifest, extension role manifest, original Gemini feature manifest, original Method C artifact manifest) all **MATCH**. Full change history is recorded in `execution_contract_v4.json → change_history`.
