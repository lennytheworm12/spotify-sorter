# Gemini audio-style pilot — engineering smoke results

Status: **ENGINEERING_SMOKE_FAILED — full 16-track inference remains gated off.**
Two real generation requests completed. One profile passed validation; one failed
because its evidence timestamps extended beyond the supplied recording. This is
an engineering result, not a verdict on Gemini's musical-style accuracy or a
completed playlist-compatibility study.

## Results

| Smoke | Full prepared duration | Provider result | Validation | Standard-rate token cost |
| --- | ---: | --- | --- | ---: |
| A01 — Wet Dreamz | 240.4078125 s | HTTP 200, STOP, JSON, audio input recorded | Invalid: evidence includes **340–360 s** | $0.00817125 |
| A03 — My Gamecube Broke. | 170.834395833 s | HTTP 200, STOP, JSON, audio input recorded | Passed schema and semantic checks | $0.00682875 |

Both returned `modelVersion=gemini-3.8-flash`. Generation latency was approximately
4.06 and 3.80 seconds respectively, excluding upload and token counting. Total
token-rated standard cost: **$0.01500000**, not a fetched billing statement.
There are **18 generation attempts remaining** within the original 20-attempt
limit. No new allowance is created by changing a research directory.

| Attempt | Counted input | Reported prompt | Audio input subset | Candidate | Thinking | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 10,772 | 9,090 | 6,011 | 361 | 0 | 9,451 |
| 2 | 8,546 | 7,350 | 4,271 | 351 | 0 | 7,701 |

Thinking tokens were omitted from both provider responses and reconcile as zero
under protobuf default handling. All usage and raw responses are retained. The
different counted versus reported prompt totals did not weaken the spend guard:
each request reserved the complete documented input allowance plus the bounded
8,192 output/thinking tokens before dispatch ($0.817152).

Actual Gemini operations: two uploaded recordings (four upload HTTP operations),
two CountTokens requests, two generations, and the earlier one model-metadata GET:
**nine HTTP operations total**. No generation was retried. No repeated paid
stability requests were made.

## Source identity and upload correction

All 16 candidate identities are resolved against their retained recordings.
The owner confirmed that the retained boys dont cry MP3 matches the Spotify
entry. The Spotify credit remains **sysmint**, while the uploader's **ericdoa**
attribution is preserved separately. No source file, catalog identity or old
representation was replaced. The Peace remains the exact retained official video,
with its duration difference from the Spotify album master documented.

The first upload succeeded, but the local verifier stopped before token counting
or generation because the provider encoded its SHA-256 as base64 of a 64-character
hexadecimal string. Strict decoding yields exactly the local prepared-file digest.
The initial implementation had expected base64 of the 32 digest bytes.

The fix accepts either exact representation after strict base64 decoding, and
continues to reject wrong digests, sizes, MIME types, neutral names, states and
expired resources. A regression test covers both encodings and mismatches.
The stopped original run, original code snapshot and upload response remain
immutable. A new execution manifest was frozen for the transport continuation,
and the existing verified upload was reused. This did not consume a generation
attempt or change the prompt, ontology, schema, model or sampler.

After the first generation failed timestamp validation, a separate frozen
extension completed only the second engineering smoke explicitly requested by
the owner. It used the same guarded attempt ledger, preserved the STOPPED record,
did not retry A01, and could not enable the full-run gate.

## What the evidence establishes

Full metadata-stripped audio reaches the API; the provider confirms the uploaded
byte hash and reports positive audio-input token counts. Structured responses,
response IDs, model versions, usage and latency are captured. Validated cache
replay for A03 performed **zero API calls**, with the client disabled and the
execution artifacts unchanged.

A01's literal timestamp claim is outside the known audio duration. Its original
response is preserved unchanged in `raw_profiles/`; it is not silently repaired
or admitted to `validated_profiles/`. The smoke-output freeze covers both real
responses, but it is explicitly **not an all-16 profile snapshot**.

No owner style judgments exist yet. The failure does not show whether Gemini's
family, substyle, vocal-role, arrangement or texture assignments are right or
wrong. It does not establish a taxonomy gap or explain the relationship between
style and playlist compatibility. Those scientific questions remain untested.

The remaining 14 recordings were not inferred. No repeated-request stability
analysis, full-pilot historical-rating join, six-control verification or ranking
comparison was performed. Historical rating inventories remain unread for this
run; the earlier exposure to expectations embedded in the supplied draft remains
documented. Unknown pairs were not assigned ratings.

## Verification and artifacts

The focused suite passed **42 tests**. The full non-heavy suite passed **1,351
tests, 12 deselected, 11 warnings**, in 160.85 seconds. The original retained
sources, original representation caches, map exports and all 31 original preflight
artifacts verify unchanged. No production behavior was activated.

Public evidence:
`ml/audio_similarity/reports/gemini_style_pilot/v1/engineering_smokes/`.

- Both execution manifests, source confirmation and transport-failure evidence.
- Exact raw responses, raw profiles, the single validated profile, and original
  request/reservation/settlement records.
- CSV/JSON usage ledger and 16-track status inventory.
- `owner_review_sheet.csv`, with model-output validity explicit and all owner
  judgments blank. Rows without inference require no owner assessment now.
- Partial-cache replay evidence and explicit status for every deferred deliverable.
- Test output and a deterministic artifact hash manifest.

Private originals:
`.research_audio/gemini_style_pilot/style-pilot-v1/` and
`.research_audio/gemini_style_pilot/style-pilot-v1-transport-v2/`.
The original STOPPED records and all response timestamps remain unchanged.

## Smallest proposed continuation — not executed

The supplied v1 schema gives evidence timestamps a minimum of zero but no numeric
upper bound; the prompt and local semantic validator impose the audio-duration
bound. A concrete proposed revision adds `maximum=prepared.duration_seconds` to
both `audio_evidence[].start_seconds` and `end_seconds` in the per-track response
schema. The provider documents numeric `maximum` in its
[supported JSON Schema subset](https://ai.google.dev/gemini-api/docs/structured-output#json-schema-support).
All style fields, enums, ontology, audio, prompt and sampler remain fixed.
The proposal and exact schemas for the two smoke recordings are in
`proposed_timestamp_bounds/`.

This is a general physical constraint, not a rule designed to obtain desired
styles. It adds a machine-readable duration bound; it cannot establish that an
in-range timestamp correctly locates an audible event. Owner review is still
required. The old invalid response remains invalid under the original contract.
Before any new request, the local schema validator must gain tested support for
`maximum` while retaining the existing strict span-order and duration checks.

The next proposed action is two engineering smokes under that separately reviewed
schema revision, with all prior attempts and cost carried forward. A new full
16-track pass plus the two already completed calls would use 18 attempts, so the
original four-repeat plan no longer fits the 20-attempt cap. Freeze an explicit
remaining schedule before any continuation. No new schema or further generation
has been activated because the owner requested the exact attached v1 contract.
