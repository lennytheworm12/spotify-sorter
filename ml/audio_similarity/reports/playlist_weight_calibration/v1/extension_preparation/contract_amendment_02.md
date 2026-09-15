# Contract amendment 02 — playlists approved for pre-weighting (permission not supported)

**Date:** 2026-09-15 · **Authorized by:** Bi Phan, project owner
**Supersedes:** `execution_contract_v2.json` → `execution_contract_v3.json`
**Readiness:** `readiness_report_v7.json`

## The two facts, recorded separately

| Dimension | Value |
|---|---|
| `PERMISSION_SUPPORTED` | **`false`** — no permission basis, license, platform term or creator authorization is asserted |
| `PLAYLISTS_APPROVED_FOR_PRE_WEIGHTING` | **`true`** — owner approval to use the 19 playlists as search inputs |
| `SOURCE_READY` | `false` (unchanged; readiness field means "permission is supported") |
| `SOURCE_GATE_REQUIRED` | `false` (precondition removed — amendment 01) |
| `READY_FOR_WEIGHT_SEARCH` | `true` |
| `SPLIT_READY` | `true` |

**Approval and permission are different things.** This amendment records an owner authorization to use these playlists as inputs to pre-weighting. It is not a permission grant, clearance, or right — and it does not alter the protocol's reading of the published platform terms (v11 §3).

## Approved scope

| Role | Playlists | Samples | Credited source groups |
|---|---|---|---|
| development | 14 | 394 | 8 |
| confirmation | 5 | 145 | 5 |
| **total** | **19** | **539** | **13** |

Each of the 19 playlists is enumerated in `execution_contract_v3.json → owner_approval.playlists[]` with its playlist id, title, credited source group, source URL, and role, each marked `approved_as_input: true`.

## Conditions retained

1. No public redistribution of raw playlist memberships or audio.
2. No publication of member-level data.
3. Results must not be represented as permission-cleared.
4. Confirmation membership-recovery results remain uncomputed and uninspected; the one-time confirmation run is unchanged.

## Not claimed

- `permission_supported` — explicitly `false`.
- `SOURCE_READY` — remains `false`.
- No redistribution rights.

`source_use_blocker_v1.json` stays on record unchanged, documenting that no basis was asserted for these 19 sources.

## Verification

Source/config/hash and contract checks re-run; no frozen input modified. Frozen artefacts (extension feature manifest, extension role manifest, original Gemini feature manifest, original Method C artifact manifest) all **MATCH** their contract hashes. Readiness published as v7.
