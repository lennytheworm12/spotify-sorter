# Extension preparation — weight search approved

**CONTRACT_FINALIZED=true · FEATURE_READY=true · SPLIT_GEOMETRY_READY=true ·
SPLIT_READY=true · PLAYLISTS_APPROVED_FOR_PRE_WEIGHTING=true ·
PERMISSION_SUPPORTED=false · SOURCE_READY=false · SOURCE_GATE_REQUIRED=false ·
READY_FOR_WEIGHT_SEARCH=true · WEIGHT_SEARCH_APPROVED=true**

The weight search is **approved by the project owner (2026-09-15)** to run on the frozen
14-playlist / 394-sample development split. The 5 confirmation playlists / 145 samples
stay reserved: not computed, not inspected.

**Permission is not claimed.** `permission_supported=false` and `SOURCE_READY=false` are
deliberate: no permission basis is asserted for the source playlists, and this approval
is an owner authorization to proceed, not a clearance. Results must not be represented
as permission-cleared, and no memberships, audio or member-level data may be
redistributed or published. See `contract_amendment_01.md`–`03.md`.

## Approval and change record

| Artifact | Role |
| --- | --- |
| `execution_contract_v4.json` | **current contract** — weight search approved |
| `readiness_report_v8.json` | **current readiness** — v8 |
| `contract_amendment_01.md` | source-use precondition removed (owner direction) |
| `contract_amendment_02.md` | 19 playlists approved for pre-weighting; `permission_supported=false` |
| `contract_amendment_03.md` | authorization rewritten as an explicit approval of the run |
| `execution_contract_v1.json`–`v3.json` | superseded contracts, retained |
| `source_use_blocker_v1.json` | retained record: no source-use basis was asserted |
| `source_metadata_capture_v1.json` | factual source metadata captured for the 19 playlists |

No code path enforces the source-use fields (they are reporting surfaces), so the
contract is the operative authorization for the run.

## Inventory and overlap

The extension contains **17 playlists, six credited curator labels, 1,314 original
membership slots and 1,169 requests** across twelve finished acquisition batches.
The retained set has **1,135 IDs, 1,134 unique audio hashes and 1,131 conservative
version groups**. Two IDs share audio bytes; four additional remix-family links
remain conservative purge candidates, not adjudicated equivalence. All original
playlist boundaries and positions are preserved, including unavailable memberships.

Twenty-four requests remain manual-tail and ten acquisitions failed; no retained
audio failed verification. Extension acquisition had reused 27 older local
sources and acquired 1,108 others before this task. **This task downloaded no audio.**

Exact recording-ID, source-hash and conservatively linked version overlap with
the original 28-playlist corpus and used development pilot is **zero**. Twelve
extension recordings occur in earlier frozen retrieval inputs. Two additional
recordings occur in older source-review queues, both from Dance Pop Mix; they
do not affect proposed confirmation samples. The five proposed confirmation
playlist IDs were absent from all 17 checked historical input/review manifests.
This supports the owner's statement that these lists are new; the history check
remains bounded by the captured project evidence.

Every extension list has a source URL and credited curator label. The owner
collected existing Spotify playlists and manually transcribed their track lists
into Markdown; the owner is recorded as **collector/transcriber, not grouping
author**. This study uses each original credited creator/account as its curator
key, with known duplicate/source relationships retained. Real-world identity
verification is not required. Collection by one person does not collapse sources
into one curator group. Source descriptions and source-use documentation remain
incomplete and are separate from this resolved authorship interpretation.

## Finalized roles and feasibility

Four Spotify genre lists expand development. Eight Spotify
Mix lists are **personalized/generated**, confirmed by the owner on 2026-09-14:
Dance Pop, Digicore, Drum And Bass, Drum and Bass Jungle, Electric Pop, House,
Hyperpop and Synthpop. They remain later-stress candidates outside primary Layer A
in the same **development-only curator group** and add no independent development curator.
Five credited source groups are reserved for confirmation:

| Source | Credited curator | Usable original hash samples |
| --- | --- | ---: |
| Actually Good House | Ben2424 | 30 |
| Deep House 2026 | selected. | 29 |
| Drum and Bass Top 100 | UKF | 30 |
| actual hyperpop | chemical0 | 30 |
| synthpop synthwave kpop | Niedoes | 26 |

The existing grouping and partition helpers were rerun using the accepted
credited-source policy, without ranking results. **Grouped split geometry passes:**
14 development playlists in eight credited/duplicate groups retain **394 samples**;
five reserved playlists in five groups retain **145 samples**. Curator/duplicate
and recording/version overlap across the boundary are both **zero** after the
existing eight sampled purges and 20 full-development-catalog purges. All original
memberships, source links, pilot samples and conservative version relationships
remain unchanged. The eight generated Mixes remain outside this primary cohort.

The owner accepts this smaller first experiment. The [execution
contract](execution_contract_v1.json) freezes these roles and samples, the eight
sampled and 20 full-development version purges, feature inputs, generated-Mix
exclusions and confirmation-access policy. Collector authorship, credited-source
grouping, study size, version policy and split geometry are resolved for this
experiment. No confirmation membership-recovery result was computed or inspected.

One prerequisite gate remains open. The current v1.2 protocol says source/access
permission and audio-processing approval are prerequisites and manual collection
does not settle permitted use. Retained v1.1 Gate A requires a permission/access
ledger, source title/description/intent and discovery records, ending in `READY`
or `SOURCE_NOT_READY`. All **19 selected playlists**—14 development and five
confirmation—still have pending permission fields. They also lack observation
dates, discovery/nomination and selection records, explicit validation status,
and an observed description or evidence that no description was present.

The [source-use blocker](source_use_blocker_v1.json) lists every affected source,
the exact pinned requirements and the evidence needed: a cited, scoped use/access
basis mapped to each playlist, plus the missing source metadata and a ledger
disposition. Prior audio-processing and upload approvals are documented separately
and do not establish use of playlist membership as ranking evidence. Real-world
curator identity verification is not required, and collector identity is not an
authorship blocker.

The contract is final but cannot execute while Gate A is `SOURCE_NOT_READY`.
After supported evidence is recorded, only source/config/hash checks need rerun;
if they pass without changing frozen inputs, `SOURCE_READY`, `SPLIT_READY` and
`READY_FOR_WEIGHT_SEARCH` can become true. The search will not start automatically.
No tuning ran.

## Features and API accounting

Counts below cover this preparation as a whole.

| Feature | Reused pre-existing caches | Newly completed | Missing |
| --- | ---: | ---: | ---: |
| Full-song CLAP Method C | 12 | 1,123 | 0 |
| Centered30 MuQ | 1,135 | 0 | 0 |
| Centered30 CLAP retained comparison | 1,135 | 0 | 0 |
| Gemini profiles and canonical/neighborhood support | 0 | 1,135 | 0 |

Method C used 22,501 new chunk inferences with zero failures under the unchanged
checkpoint, sampling and pooling contract. Gemini used the unchanged metadata-stripped
full-recording audio and pinned prompt/schema contract. The final assembly reused 597 mappings
from the earlier verified partial snapshot and added 538. Of the valid profiles,
**996 have specific-style evidence and 139 are valid but uninformative** under the
unchanged scorer. No replacement labels or extension deferrals were introduced;
the two original approved deferrals remain unchanged.

Extension generation accounting: **1,137 attempts, 1,135 settled valid responses,
$5.84514975 settled and $1.63430400 reserved across two timed-out requests**.
Total conservative exposure is **$7.47945375**, within the approved **$10 cap**.
The initial storage-quota failure preceded generation and created no reservation.
After the owner authorized cleanup and completion, reviewed continuations retained
all stopped evidence and both unresolved reservations. All **1,137 successful
temporary provider uploads were deleted**, with automatic deletion after verified
responses; local audio and evidence are retained.

The original run remains separately accounted: **$9.04152825 settled plus
$2.45145600 unresolved across three reservations**, under its original $15 cap.
No reservation was released or charged against another corpus's allowance.

## Artifacts and verification

Inventory and draft root:
`.research_audio/playlist_calibration_extension_preparation_v1/`.
Current roles: `.research_audio/playlist_calibration_extension_source_followup_02/role_split_manifest_v5.private.json`.
This owner-evidence update preserves prior drafts, every membership and all
feature artifacts. The recomputed partition retains the same assignments and
purges; its identifier records the revised provenance. Full feature snapshot:
`.research_audio/playlist_calibration_extension_recovery_03/feature_snapshot_v2/`.
[Current readiness](readiness_report_v5.json), the [execution
contract](execution_contract_v1.json), and the [source-use
blocker](source_use_blocker_v1.json) identify the frozen roles, exact open gate,
source proofs, matrices, execution ledgers and replay evidence. The complete prior
feature report remains in `readiness_report_v4.json`.

Separate role artifacts contain 485 proposed-confirmation and 737 development
candidate recording IDs, with 87 shared IDs in these **raw feature catalogs**.
Selection purges remain separate. Both artifacts are explicitly marked
`selection_input=false` and `membership_results_allowed=false`; neither is a
ranking-result input.

Ordering, hashes, exact symmetry, bounds, the residual identity and role-submatrix
checks passed. The 356,409 previously valid genre cells and all three audio-matrix
files remained identical. All profiles now have valid processing evidence; the
explicit validity mask is retained, and valid uninformative evidence keeps the
existing behavior of contributing zero genre evidence. Earlier missing-profile
artifacts remain immutable.

The existing scorer reproduced all 4,950 mechanical-gate pairs exactly. Full
feature replay, including genre arithmetic recomputation, reproduced identical
bytes with network access disabled and zero new inference/API calls. Completed
runner replay also forbade credential access and transport initialization.
Original sources, development artifacts, historical reports and stopped execution
evidence passed integrity checks. Focused tests: **74 passed**; applicable
regressions: **1,502 passed, 12 deselected**. Cleanup scope/idempotency checks passed.
Contract hash/scope/privacy checks and the six focused split tests also passed
without inference, preprocessing, API use or confirmation-result access.

Restricted memberships, raw audio, credentials, responses and provider resource
identifiers remain outside Git. No mapper, prompt, scoring-rule, production or
playlist changes were made. Preparation stops here; the source gate remains open
and weight search is not authorized or started.
