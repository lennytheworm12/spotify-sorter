# Gemini style pilot runner — offline validation milestone

The isolated pilot runner is implemented and tested with synthetic provider
responses. **The real pilot is still PREPARED_NOT_RUN_SOURCE_IDENTITY_BLOCKED.**
No real execution manifest, audio upload, generation, profile, smoke result or
post-profile rating join exists. This does not close the scientific pilot.

The source issue remains `C04`, boys dont cry: Spotify credits sysmint, while the
retained upload credits ericdoa. The owner has been asked to confirm the actual
recording. The [source-readiness report](gemini-style-pilot-contract-readiness.md)
records the complete 16-track inventory, exact hashes, recording variants and
pre-inference exposure to the hypotheses embedded in the supplied design.

## Execution contract

`freeze-manifest` verifies all 16 original Spotify identities, source and prepared
audio hashes, protected historical hashes, source readiness, exact supplied
model inputs, the verified model's token limits, sampler settings, implementation
files and Python/httpx environment. Missing or blocked identities prevent manifest
creation. Changing only an `eligible` flag does not override a blocked source
status. No request is permitted without this frozen manifest.

The runner uses `gemini-3.8-flash`, LOW thinking, temperature 1, topP 0.95, topK 64,
one candidate, JSON-schema output, and an 8,192-token combined output/thinking
bound. It omits seed and service tier, using the documented provider defaults.
The [REST reference](https://ai.google.dev/api/generate-content#ServiceTier)
specifies standard service when the tier is omitted. An unexpected reported tier
halts accounting rather than silently using the wrong rate.

The [verified standard rates](https://ai.google.dev/gemini-api/docs/pricing)
are $0.75/M input tokens and $3.75/M output tokens including thinking through
December 31, 2026. The runner refuses to initiate requests after that pricing
validity date. Each generation requires exact-request token counting and reserves
the full documented input allowance plus bounded output: **$0.817152**. It
releases unused reservation only after complete token accounting reconciles.
This is a conservative upper reservation, not an estimated charge. Total cap:
**$2**, at most **20 generation attempts**.
Settlements price actual reported token usage at those standard rates; they are
not a fetched billing statement. Free-tier or input-cache discounts can reduce
the provider's charge without weakening the conservative cap.

## Transport, sequence and failure handling

The [Files API](https://ai.google.dev/api/files) receives full metadata-stripped
FLAC bytes and a neutral display name. Returned byte size, MIME type, active state,
expiry, and SHA-256 must match the prepared audio. Provider-supplied upload URLs
must use the documented Google host. Keys and signed upload URLs are not printed
or recorded; request authentication stays in headers. Full raw response bodies
are retained with response hashes and timing.

The deterministic schedule is:

1. A01 and A03 engineering smokes: Wet Dreamz and My Gamecube Broke.
2. The other 14 original candidates in design order.
3. Four explicit repeats: A01, A03, A08 and C05.

Each `run-next` invocation makes at most one generation attempt. After two
successful smoke responses, the gate freezes their evidence hashes. The checks
require verified uploaded audio, positive provider AUDIO input tokens, a response
ID and returned model version, a complete STOP finish, reconciled usage, and valid
schema/semantics. They do not require agreement with expected styles. Legitimate
uncertainty, missing ontology vocabulary and non-music are not parse failures.

Operational failures stop the run. Original requests, raw responses, reservations,
settlements and the stop record are preserved. An interrupted or unaccounted
generation cannot be dispatched again on restart. There are no automatic retries
or classification repairs. Any operational recovery requires inspection and a
documented continuation design; do not delete ledger entries or select a more
convenient output. The current schedule intentionally stops on failure rather
than spending repeat slots on automatic retries.

Profile cache identity includes prepared-audio hash, model/configuration,
prompt/schema/ontology hashes, neutral input context and implementation hash.
Repeats have separate attempt results and cannot overwrite primary profiles.
Replay validates cached profiles against the original raw provider response and
hashes without constructing a client or reading the configured key. A final
profile freeze includes every primary and repeat before owner style review or
historical-rating analysis. Console success output contains operational status
and costs, not predicted styles.

## Commands after source resolution

Run from `ml/audio_similarity/`. The original `inventory.v1.json` remains blocked
and immutable. A subsequent inventory must document verified recording identity;
the `inventory.v2.json` path below does **not** exist yet. Do not create it by
simply relabeling the source or flipping eligibility.

```bash
.venv/bin/python -m audio_similarity.gemini_style_pilot freeze-manifest \
  --inventory .research_audio/gemini_style_pilot/style-pilot-v1/source_checks/inventory.v2.json

# First smoke, then second smoke. The runner enforces the gate before attempt 3.
.venv/bin/python -m audio_similarity.gemini_style_pilot run-next
.venv/bin/python -m audio_similarity.gemini_style_pilot run-next

# Continue one attempt at a time after the engineering gate passes.
.venv/bin/python -m audio_similarity.gemini_style_pilot run-next

# After all 16 primary responses and four explicit repeats:
.venv/bin/python -m audio_similarity.gemini_style_pilot replay
.venv/bin/python -m audio_similarity.gemini_style_pilot freeze-profiles
```

Private execution artifacts live under
`.research_audio/gemini_style_pilot/style-pilot-v1/execution/`: `transport/` records
every HTTP operation; `attempts/` holds immutable request/reservation/settlement/
result records; `profiles/` holds validated primary caches; `smoke_gate.json`
records the engineering gate. `execution_manifest.json` and `profiles_frozen.json`
sit in the run root. None of these real execution artifacts exists yet.

## Validation and remaining work

The synthetic tests exercise all 20 requests, complete uncertainty responses,
the two-smoke gate, preservation of primary profiles during repeats, deterministic
replay with zero new calls, absent source approval, substituted identities,
changed audio, cache tampering, interrupted attempts, bad upload hashes, token
count failures, HTTP failures, lost connections, incomplete accounting, wrong
service tier, missing audio-input evidence, malformed JSON and truncated output.
All fake recordings and responses are isolated in pytest temporary directories.
They are never written into the real pilot or historical ratings.

Final results: **41 focused tests passed** in 7.76 seconds; **1,350 full non-heavy
tests passed, 12 deselected, 11 warnings** in 133.23 seconds. The full suite was
rerun after the final source-status regression guard was added. These are
engineering validations, not real Gemini classification results.

The real source-gate check also rejects the actual unresolved inventory before
provider access. Original source/cache/map hashes and all 31 original preflight
artifact hashes still match. Exact test results and code hashes are in
`ml/audio_similarity/reports/gemini_style_pilot/v1/runner_validation/`.

Remaining real work: resolve C04; freeze the execution manifest; execute and
inspect engineering smokes; complete the bounded run; freeze all profiles;
produce repeat diagnostics and the owner style-review sheet; join every eligible
PLAYLIST_COMPATIBILITY_V1 pair by stable identity; verify all six cited controls;
produce the evidence-supported closeout. No style penalties, graph movement,
scorer training, inferred ratings or production behavior are introduced here.
