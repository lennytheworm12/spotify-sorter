# Gemini free-genre retry: labels changed, reliability still unresolved

The same 16 full retained recordings were sent to **gemini-3.8-flash** with no
genre definitions, allowed genre names, genre examples or family/style mapping.
The final arm produced **16/16 validated profiles**. The Hills changed from
`electronic / hyperpop` to **R&B / Contemporary R&B**, with **Trap** and
**Alternative R&B** as secondary styles.

That result is more consistent with the owner's description of The Hills. It
does not establish that removing the ontology improves overall accuracy: My
Gamecube Broke. became **Drum and Bass / Neurofunk / Dubstep**, and Saturation
became **minimal techno / dub techno / microhouse**. These substantial shifts
need audio-based validation. No new profile has an owner-approved accuracy verdict.

**Status: INFERENCE_COMPLETE_OWNER_VALIDATION_PENDING.** The authorized retry is
executed and preserved. There is no production winner or measured improvement in
playlist ranking. The earlier pilot's outstanding owner comparisons remain open.

## What changed in the request

- Broad family and specific style fields accept free text; no genre enums remain.
- No ontology text is sent. Genre-specific listening hints are also removed.
- The closed-vocabulary `unmapped_styles` field is removed because labels are open.
- The model still reports vocal role, arrangement, texture, density, sections and
  ordinal certainty using the original facet fields. These enums do not supply
  genre names or definitions.
- No song/artist identity, prior prediction, owner note, human rating, genre
  expectation, web source, conversation history or playlist information is sent.

The source audio, neutral IDs, uploaded file resources, full durations, model and
sampling configuration remain the same. No audio was downloaded, reconverted,
cropped or substituted. The new requests reused all 16 existing unexpired,
hash-verified Files API uploads. No new upload calls were necessary.

Model configuration: LOW thinking; temperature 1; topP 0.95; topK 64;
candidateCount 1; maxOutputTokens 8192 including thinking; JSON output; seed
omitted; standard service tier. These are the same settings as the original arm.
Official [model capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)
and [standard rates](https://ai.google.dev/gemini-api/docs/pricing) were checked
before this retry. Exact request bodies are preserved for every attempt.

## The engineering stop and continuation

The first free-genre smoke passed. The second returned an evidence interval from
**31 seconds to 30 seconds**. It passed JSON/usage/audio-input checks but failed
the interval semantic contract. The runner stopped immediately. Both raw
responses, paid settlements, the STOP marker and the exact implementation remain
preserved under `stopped_interval_arm/` and source commit `b322790`.

Before any genre comparison, a separate continuation replaced each start/end
interval with **one bounded `at_seconds` timestamp**. Its genre instructions and
all other descriptive instructions stayed unchanged. No response was repaired.
The continuation reran all 16 primaries in the same smoke-first order, freezing
every result before the assistant inspected the new genres.

The two spent smokes consumed the planned repeat slots: **18 new generations in
total: two stopped-arm smokes plus 16 final primaries**. There are no same-request
repeats for the final arm, so its output stability is **not tested**. The initial
successful smoke is not substituted for a later primary or treated as an identical
request repeat, because the evidence schema changed.

The combined inventory is **38 generations**, including the original pilot's 20.
New token-accounted cost is **$0.09188850**; combined cost is **$0.23869650**.
This is calculated from provider token usage at published rates, not a fetched
billing statement. Each request first reserved the full 1,048,576-input-token
bound plus 8,192 output/thinking tokens ($0.817152), within the remaining combined
**$2 cap**. All previous costs were deducted; the budget was never reset.

There were 36 new provider HTTP operations: 18 CountTokens and 18 generateContent.
No automatic retries, preferred-answer selection or additional generations occurred.

## Complete primary label comparison

Spellings below preserve the free labels. Their formatting and specificity vary
because no normalization or semantic remapping was fitted.

| Recording | Original primary style | New primary family | New primary and secondary styles |
| --- | --- | --- | --- |
| Wet Dreamz | boom_bap | Hip Hop | Boom Bap; Conscious Hip Hop; East Coast Hip Hop |
| Shoota | trap | hip hop | trap; plugg |
| My Gamecube Broke. | lofi_hip_hop | Electronic | Drum and Bass; Neurofunk; Dubstep |
| She loves the color green and I love her | lofi_hip_hop | Hip Hop | Lo-Fi Hip Hop; Downtempo; Chillout |
| Tea Time | lofi_hip_hop | hip_hop | lo_fi_hip_hop; chillhop; downtempo |
| GET IT | melodic_trap | Hip Hop | Trap; Pop Rap; Melodic Rap |
| The Hills | hyperpop | R&B | Contemporary R&B; Trap; Alternative R&B |
| Shouldn't Be | alternative_rnb | R&B | Contemporary R&B; Alt-Pop; Ambient Pop |
| Perfect Night | dance_pop | Pop | Dance-Pop; Contemporary R&B; Nu-Disco |
| OMG | pop_rnb | Pop | K-Pop; Contemporary R&B; Synth-Pop |
| Saturation in Delay, Love in Anger | hyperpop | electronic | minimal techno; dub techno; microhouse |
| Sit Around | pop_rnb | Pop | Indie Pop; Electropop; Alternative R&B |
| risk | alternative_rnb | Electronic | Trip Hop; Downtempo; Dream Pop |
| boys dont cry | digicore | Hip Hop | Trap; Emo Rap; Melodic Rap |
| The Peace | contemporary_rnb | R&B and Soul | Contemporary R&B; Trap; Alternative R&B |
| Die Right Here | dance_pop | Pop | Dance-Pop; Nu-Disco; Synth-Pop |

All 16 final profiles claim clear family and style certainty. That is asserted
confidence, not measured accuracy. None abstained. The model's confident and
materially different descriptions of Gamecube and Saturation make calibration
and descriptive fidelity unresolved concerns.

The Hills' new evidence describes low male vocals in the verse and high-register,
processed chorus vocals. The earlier explicit female-hook claim is absent.
Gamecube's new evidence describes orchestral strings, aggressive reese bass,
rolling breakbeats and a half-time wobble breakdown. Saturation's new evidence
describes repeated vocal samples, a sparse percussion groove and dub delay.
The Peace still receives an R&B description and an asserted female lead.
These are model claims requiring comparison with the recording, not facts the
assistant independently verified by listening.

## Interpretation and next step

Removing the instruction/ontology bundle is associated with a changed The Hills
label. We cannot isolate causality from this selected, stochastic two-arm study:
several instructions changed, the evidence format changed after an engineering
failure, and the final arm has no identical-request repeats. The contrast does
show why the original result should not be attributed only to model capability.

The owner's clarification that Saturation's hyperpop label seemed more plausible
remains preserved separately from the first-pass “lofi” note. Its new techno
label is not treated as owner accepted merely because the previous label was
reconsidered. The Hills' new R&B label is closer to the earlier owner wording;
that does not approve every vocal/section assertion in its profile.

All **15** existing `PLAYLIST_COMPATIBILITY_V1` pairs within this pilot are joined
by Spotify IDs with original C scores, original profile evidence, both new
profiles and frozen owner notes in `joined_pair_diagnostics.json`. The **three**
qualitative diagnostic pairs retain null playlist ratings. Original model-only
implications remain inside the explicitly named `frozen_pair_evidence`; they
are not presented as implications of these new labels. No unknown pair is scored.

Good cross-style controls Sit Around/risk and Tea Time/Sit Around remain rated 4.
The bad Die Right Here/OMG pair remains rated 2 despite both new profiles being
broadly Pop. GET IT/Gamecube and Wet Dreamz/Saturation still require accurate
endpoint descriptions before any label-based separation can be credited. Changed
labels alone neither correct nor damage a ranking: no scores were modified.

The smallest next step is a focused owner check of the actual audible claims in
Gamecube, Saturation, The Hills and The Peace using these already generated
profiles. There is no new queue or pair-rating request. Inspect the complete
comparison and continue the existing review before designing another prompt or
reranker. Genre-band weights, model training, CLAP/MuQ changes, graph coordinates
and production behavior remain untouched.

## Reproducibility and tests

The final private run is `.research_audio/gemini_style_pilot/free-genre-point-v1`.
Its manifest SHA-256 is
`ecdbfcb4ad91688f840ad395e425fe68bf4eca5a26a8163820e979054e960a06`.
The stopped interval arm is `.research_audio/gemini_style_pilot/free-genre-v1`.
All source/prepared hashes and lineage are in the manifests and source provenance.

`verification.json` records test outcomes, integrity counts and replay evidence.
The final full non-heavy suite passed **1,379 tests**, with 12 deselected and
11 warnings, in 172.64 seconds. The focused suite passed 43 tests; its expanded
complete-continuation fixture also passed separately before real inference.
The first full post-continuation suite had 1,377 passes and two failures because
HEAD was not yet an ancestor of the pushed research branch. The implementation
was pushed without changing those tests, and the final full rerun is recorded
separately. The original free-genre milestone had passed 1,378 tests before the
single-timestamp test was added. All test provider responses are isolated fixtures.

From `ml/audio_similarity`, these commands make zero model calls:

```bash
.venv/bin/python -m audio_similarity.gemini_free_genre_runner replay --run .research_audio/gemini_style_pilot/free-genre-point-v1
.venv/bin/python reports/gemini_style_pilot/v1/free_genre_v1/rebuild.py
```

The completed runner's `next` also returns zero new generation calls. Historical
input hashes and all profile/response hashes are verified before replay. Exports
are deterministically ordered and create-once; the artifact manifest covers the
package except itself. The original review UI still displays the original frozen
profiles, preserving that review packet; the new labels are in
`profile_comparison.csv` and `profiles/` here.
