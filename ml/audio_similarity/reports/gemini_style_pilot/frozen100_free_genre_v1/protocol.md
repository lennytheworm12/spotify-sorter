# Frozen-100 free-form genre extension, version 1

Frozen before any new inference on 2026-09-10. User explicitly authorized Gemini calls on the original frozen 100.

## Population and identity

Use exactly the 100 Spotify identities in Stage 5E.3 frozen100_v3/source_manifest.json (SHA-256 1c73bf9b2a20f9dc1f623ae9e170422594d2f5af110ab194c284170bea721391). Both local source bytes and per-track provenance must match. Check current source-correction and quarantine overlays and map linkage; no silent substitutions. All 100 currently match and none is quarantined. This reuses retained recording provenance, not fresh independent owner identity confirmation of every recording.

Prepare the complete source as native-rate, native-channel, signed-16-bit FLAC with identity metadata removed. Preserve ffmpeg command, source/prepared hashes, sample counts and full decoded PCM equality. Never truncate, resample, normalize volume or download replacements. Neutral IDs are N001-N100; preserve the previous 16 neutral IDs to retain exact request/cache compatibility. The other 84 neutral IDs follow stable Spotify-ID ordering. F001-F100 are internal corpus row IDs and never sent to the model.

## Request contract

Reuse the exact successful free-genre-point-v1 prompt, per-duration point-timestamp schema, gemini-3.8-flash model and LOW generation configuration. No genre vocabulary, examples, definitions or family mappings. The retained facet enums cover vocal role, arrangement, texture, density and sections. One full audio file per request. No artist/song identity, metadata, expected labels, ratings, neighbors, playlist names, prior conversation or search. Files API supports audio/flac. The schema bounds evidence points to the recording duration. No free-form output repair.

Model settings: candidateCount 1; maxOutputTokens 8192 including thinking; temperature 1; topP 0.95; topK 64; responseMimeType application/json; thinkingConfig {includeThoughts: false, thinkingLevel: LOW}. Seed and service tier omitted; documented standard billing tier required in returned accounting. Other sampler defaults unchanged. Model input limit 1,048,576. Verify response ID, returned model version, one STOP candidate, positive AUDIO token usage and complete token accounting. Preserve actual returned model version even if provider changes it.

Official REST fields/model/prices were verified on 2026-09-10 at https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash , https://ai.google.dev/gemini-api/docs/pricing , https://ai.google.dev/api/generate-content and https://ai.google.dev/api/tokens . Standard input $0.75/M; output including thinking $3.75/M; verified rate window through 2026-12-31.

## Exact reuse and bounds

Reuse all 16 successful free-form profiles only after matching source/prepared hash, neutral identifier, duration, exact model/config, prompt, per-track schema, environment and original producer implementation/cache identity. Preserve their raw responses and producer references. Wrapper changes do not retroactively invalidate an identical semantic request.

Exactly 84 new primary requests; zero automatic retries, repeats or winner selection. Keep all responses. The two first new tracks are engineering smokes and count toward 84. Check transport/schema/audio handling only, without inspecting whether genre labels agree with expectations. Continue after both pass. A fully accounted schema/semantic InvalidProfile after those two is an explicit null track result and does not block other independent songs. Any smoke failure, audio/provider-envelope/transport/auth failure, or missing billing accounting stops the run. No retries or repairs without a separately frozen revision.

There were 38 previous generations costing $0.23869650 across the original and free-form pilot arms. Preserve the combined $2 cap: this run has $1.76130350 available and at most 84 new generations (122 combined). Before each new generation, count the exact request and reserve the full documented input limit plus 8192 output/thinking tokens: $0.817152 worst case. Stop if settled cost plus that bound exceeds the remaining cap. Release reservation only after all billed tokens reconcile. Never log or expose the local configured key.

## Freeze, replay and interpretation

Freeze manifest, code/config/input hashes before inference. Preserve original audio, caches, map exports, representations, ratings and reports. Check all protected bytes at startup and completion; validate manifest/code/critical inputs before each request and full audio hash at upload. Freeze all profiles before aggregate classifications or any rating joins. Cache replay must contact no provider, repeat no inference, preserve original execution ledger bytes and reproduce the export exactly.

Deliver all 100 rows in stable identity order, including explicit failed/null/uncertain status. Preserve raw label strings and certainty without musical-family remapping. This is a descriptive collection expansion with no accuracy, held-out generalization, compatibility, taxonomy-learning, reranking or production claim. Do not infer correctness from model size or high self-reported certainty. Owner inspection of the classifications is the next step. No new human review queue is generated by this batch; existing review data remains untouched.
