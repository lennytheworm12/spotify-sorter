# Contract amendment 01 — source-use precondition removed (owner direction)

**Date:** 2026-09-15 · **Authorized by:** Bi Phan, project owner (recorded by agent, not self-authorized)
**Applies to:** `execution_contract_v1.json` → superseded by `execution_contract_v2.json`
**Gate affected:** Gate A source-use precondition only

## What changed

The retained protocol (v11 §3 and Gate A) made a cited, scoped **source-use basis** a hard precondition before any fitting or evaluation:
`execution_authorization.source_gate_must_be_ready_before_search: true` (v1) → **`false`** (v2).

The owner directed that no basis statement be recorded and that the precondition be removed from the retained protocol, so the weight search may proceed.

## What is *not* claimed

This amendment asserts **no permission basis**. It records a decision to proceed anyway:

| Field | Value |
|---|---|
| `source_use_basis_asserted` | `false` |
| `SOURCE_READY` | **remains `false`** — the field means "permission is supported", and it is not |
| `SOURCE_USE_STATUS` | `PERMISSION_UNRESOLVED_OWNER_RISK_ACCEPTED` |
| `SOURCE_GATE_REQUIRED` | `false` (precondition removed) |
| `READY_FOR_WEIGHT_SEARCH` | `true` (by this amendment) |
| `owner_acknowledged_risk` | `true` |

`source_use_blocker_v1.json` is **retained unchanged** as the historical record that no basis was asserted for the 19 affected sources (14 development / 5 confirmation).

## Why this is recorded rather than silently flipped

Protocol v11 §3 states an operational reading of published platform terms:

> *"Spotify's published Developer Policy III.13–14 restricts analysis and ML/AI use of Platform/Content. Public visibility, a manual transcription, an export, curator consent, or an existing cache does not automatically establish permission for every intended use. Resolve permission for the particular data and workflow before calibration."*

Removing the precondition does not change that reading — it records that the owner accepts the risk and proceeds. The distinction matters for anyone reading this later: a `READY` flag would have claimed cleared permission; this amendment claims only a deliberate owner decision on an uncleared corpus.

## Consequences carried forward

1. Any downstream artifact, write-up, publication or demo derived from this corpus **must not be represented as permission-cleared**.
2. **No public redistribution** of raw playlist memberships or audio; **no publication of member-level data**.
3. Confirmation membership-recovery results stay **uncomputed and uninspected**; the one-time confirmation run is unchanged.
4. Everything else stays frozen: memberships, samples, curator/duplicate groupings, version purges, feature inputs, scorer, grid, masks.
5. Per `contract_change_policy`, this change is versioned with new hashes (v2) rather than edited in place; v1 remains on record.

## Verification performed

Re-ran **only** the source/config/hash + contract checks; no frozen input was modified:

| Frozen artifact | Result |
|---|---|
| `extension_feature_manifest` | MATCH |
| `extension_role_manifest` | MATCH |
| `original_gemini_feature_manifest` | MATCH |
| `original_method_c_artifact_manifest` | MATCH |

Publishing readiness `v6`: `CONTRACT_FINALIZED=true`, `FEATURE_READY=true`, `SPLIT_GEOMETRY_READY=true`, `SPLIT_READY=true`, `SOURCE_READY=false`, `SOURCE_GATE_REQUIRED=false`, `SOURCE_USE_STATUS=PERMISSION_UNRESOLVED_OWNER_RISK_ACCEPTED`, `READY_FOR_WEIGHT_SEARCH=true`.
