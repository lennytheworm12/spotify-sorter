# Gemini audio-style pilot — preflight, not run

Status: **PREPARED_NOT_RUN_MISSING_DESIGN_INPUTS**. This is an intermediate
readiness report, not a scientific closeout or a completed implementation.

The supplied `/mnt/c/Users/bphan/Downloads/prompt.txt` contains the audio-style
instructions only. The referenced `style-pilot-v1` draft, exact 16-candidate
list (including A01/A03/A08/C05), ontology and JSON Schema were not found in
the checkout, Downloads or the Spotify Sorter vault notes. Their locations
have been requested. They will not be reconstructed from earlier examples.

## Completed checks

- Inspected the feature checkout `ml/stage5f1-energy-motion` at `9b3adf4`,
  263 commits ahead of local main, and the clean vault at `45a0daa`.
  Existing unrelated checkout edits were preserved.
- A locally configured Google key successfully accessed the exact
  `models/gemini-3.8-flash` metadata endpoint. No key is recorded in artifacts.
- **Generation attempts: 0. Audio uploads: 0. Model metadata calls: 1.
  Generation spend: $0.** No profiles, smoke results or human outcomes exist.
- Prepared full-recording FLACs for the 11 stable identities explicitly named
  in the user's instruction, independently of the missing draft. These are
  not claimed to be the frozen 16-candidate set.
- Neutral filenames; no identity metadata, chapters or artwork; native sample
  rate and channels; signed 16-bit PCM, no gain normalization, no truncation.
  Source hashes and complete decoded PCM hashes match the prepared files at
  the documented 16-bit conversion precision. Commands, sample counts,
  durations and prepared hashes are recorded.
- Preparation replay checked all 11 source/prepared hashes with conversion
  calls disabled. Protected source, original cache and map hashes match.
  Source-correction and quarantine indexes were verified and consulted.

A content hash proves that the actual bytes match retained provenance, not
that an uploader's attribution is true. No artist-field edit is being used
as a substitute for verification. Owner-confirmed audible identity remains
separate from the byte/provenance checks.

## Identity findings

**boys dont cry:** Spotify identity `1ON9XudZFxwu43tQXBszIX` is catalogued as
**sysmint** (ISRC QZNMU2348693). Its actual retained source is
[an upload credited to ericdoa](https://www.youtube.com/watch?v=3jTMJRKqR_I),
by ericdoaVault, described as an unreleased recording. The attribution
conflict is explicit and blocks treating the source as verified for that
catalogue identity. No recording or historical metadata was replaced.

**The Peace:** Spotify identity `6wm3t4VpTxSFfOUgTMlHZM`, album U, maps to
[underscores' official video](https://www.youtube.com/watch?v=Gf-fCJ6TkRU).
The retained container is 173.321 seconds; its decoded audio is approximately
173.302 seconds. Spotify's album duration is 169.500 seconds. This pins the
actual video recording; it does not establish that the missing draft intended
that version, the exact album master or the separately catalogued Frost
Children remix. No variant has been silently substituted.

`risk` resolves to **lace**, Spotify `2js0td9w2MzNUVPlMKYOEs`, rather than
Gracie Abrams' distinct `Risk`.

## Verified API contract and budget machinery

Use the existing httpx client with Gemini Developer API REST v1beta. The
[model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)
and successful model lookup confirm the requested model and low thinking.
The lookup returns sampler defaults temperature 1, topP 0.95 and topK 64.
Keep them fixed, candidateCount 1, seed omitted, no tools, no search, no
identity context. The pending execution configuration uses
`generationConfig.thinkingConfig.thinkingLevel: LOW`, `responseMimeType` and
`responseJsonSchema` as documented in the
[REST reference](https://ai.google.dev/api/generate-content).

The [standard pricing page](https://ai.google.dev/gemini-api/docs/pricing)
currently lists $0.75 per million input tokens and $3.75 per million output
tokens including thinking through December 31, 2026. The
[thinking guide](https://ai.google.dev/gemini-api/docs/generate-content/thinking)
explicitly documents that maxOutputTokens is a hard bound on combined output
and thinking. The proposed limit is 8,192 tokens.

The tested ledger uses a deliberately conservative reservation: validate the
counted request is within the documented input limit, then reserve **the whole
1,048,576-token model input allowance plus 8,192 output/thinking tokens**.
This is $0.817152 per request at those rates. It is an upper reservation, not
an expected charge. Unused funds are released only after exact provider
prompt/output/thinking/total accounting reconciles. Pending or unaccounted
attempts stop continuation, all reservations are create-once, the cap cannot
exceed $2, and no more than 20 attempts can be reserved. This avoids assuming
CountTokens and billed prompt counts always match exactly.

Actual multimodal CountTokens, generation transport, schema validation,
smoke handling, response IDs/usage, profile caching, repeats, owner style
review and pair diagnostics remain **untested/not run**. No rating or expected
style evidence was read to construct profiles. The six controls and all
eligible PLAYLIST_COMPATIBILITY_V1 pairs still require a post-profile join.

## Local artifacts and next action

Research run:
`ml/audio_similarity/.research_audio/gemini_style_pilot/style-pilot-v1/`.

- `preflight/prompt.txt`: exact supplied prompt copy.
- `preflight/model_access.json`, `api_contract.json`: verified API metadata and
  documented configuration/cost basis.
- `preflight/input_readiness.json`: explicit blockers and call counts.
- `preflight/source_inventory.json`: stable identities, source attribution,
  overlay handling, prepared hashes and conversion receipts for 11 named songs.
- `preflight/protected_hashes.json`: original-input integrity baseline.
- `prepared/N*.flac` and `prepared/N*.json`: full audio and local-only receipts.

An execution manifest has **not** been falsely marked ready. Supply the
remaining draft/candidate list/ontology/schema paths; then finish source
resolution, freeze the complete request contract and run the two prescribed
engineering smokes before any wider generation. No production changes,
source replacements, graph coordinate changes, model training or new ratings
were made by this preflight.

Validation: **3 focused tests passed** for full-recording preparation, metadata
removal, conversion-free replay, strict token accounting and attempt/spend
bounds. The full non-heavy suite passed: **1,312 passed, 12 deselected,
11 warnings** in 122.20 seconds. These are engineering utility tests, not
Gemini profile validation.
