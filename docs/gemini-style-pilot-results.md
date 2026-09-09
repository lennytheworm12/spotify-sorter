# Gemini audio-style pilot: inference complete, owner review pending

All 16 full retained recordings have validated profiles under the approved
duration-bounded schema. The pilot used **20 generation attempts in total** and
**$0.146808 at the verified standard token rates**. This is token-accounted cost,
not a fetched billing statement. No generation allowance remains.

**The current evidence does not justify a genre/style reranker.** Output stability
and audio-description fidelity need owner review first. This selected pilot does
not measure held-out playlist improvement, and no production behavior changed.

## Execution and preservation

The original two smokes are preserved: Wet Dreamz failed because it cited
340–360 seconds in a 240.4078125-second recording; My Gamecube Broke. passed.
After owner approval, a separate run added only a per-recording numeric maximum
to both evidence timestamp fields. The original prompt, ontology, model, sampling
defaults, audio and earlier responses remain unchanged. Nothing was repaired in
an existing classification.

The continuation ran 16 new primaries and two explicit repeats, A01 and A03.
Both revised engineering smokes passed before the remaining requests began.
The old calls consumed the allowance for the originally planned A08 and C05
repeats. There were no silent retries or profile replacements.

All 18 continuation requests passed schema, semantic, audio-input, transport and
usage checks. All returned `modelVersion=gemini-3.8-flash` and `STOP`.
`thinkingLevel=LOW`, temperature 1, topP 0.95, topK 64, candidateCount 1 and the
8,192 combined output/thinking-token cap stayed fixed. Each request counted its
exact input and reserved $0.817152 before generation. Previous settled spending
was deducted from the continuation's cap.

There were **73 recorded Gemini HTTP operations overall**: 32 upload operations
for 16 recordings, 20 CountTokens calls, 20 generations and one earlier model
metadata lookup. The continuation reused the two verified smoke uploads.

No recordings were missing or substituted. The retained-source identities,
provider attribution, source/prepared hashes, durations, conversion commands and
source-correction status are exported. The owner-confirmed boys dont cry
recording retains Spotify credit **sysmint** and the separate uploader attribution.
The Peace is the retained official underscores video. Some retained video versions
differ in duration from their Spotify album entries; the report concerns the full
retained recordings, not an asserted identical Spotify master.

All 16 source/prepared pairs also passed a fresh full-waveform comparison after
inference: decoded signed-16-bit PCM and byte counts match, and the FLACs have no
identity tags. This rules out a preparation swap or crop. It cannot independently
prove musical identity or the truth of an API description.

## Repeat consistency

| Track | Primary versus repeat | Implication |
| --- | --- | --- |
| Wet Dreamz | `hip_hop_rap / boom_bap` remains stable; `rap_led` changes to `mixed_rap_and_singing`; section variation and secondary tags change | Main style is stable in this one repeat, while role and section labels are not |
| My Gamecube Broke. | `hip_hop_rap / lofi_hip_hop` changes to `electronic / ambient`; `vocal_samples_only` changes to `instrumental` | Material family/style instability on exactly the same audio and request configuration |

Neither repeat is independent correctness evidence. Primary results were retained
as primary even when a repeat differed. The initial schema's responses remain
separate and are not pooled into the revised primary profiles.

## Existing playlist judgments

The canonical frozen snapshot contains 419 `PLAYLIST_COMPATIBILITY_V1` pairs.
Exactly **15** have both endpoints in this pilot: seven rated 1–2, one rated 3,
and seven rated 4–5. All six draft controls verify against stable Spotify pair
identities. Derived style-experiment evidence copies agree with the canonical
snapshot and do not create additional labels.

Every one of these 15 pairs shares at least one predicted family when secondary
families are included. A broad-family-overlap check therefore does not separate
the good and bad pairs here.

Five of seven bad pairs share no predicted style label. However, four of seven
good pairs also share no predicted style label. These counts describe token
overlap in selected model outputs; they are not measured corrections or changes
to CLAP rankings. Descriptions still need owner validation.

| Control | Human playlist rating | Frozen C | Model evidence | Review implication |
| --- | ---: | ---: | --- | --- |
| Wet Dreamz / Saturation in Delay, Love in Anger | 1 | 0.601257 | No shared style; rap-led versus sung-led | Possible separation, conditional on description accuracy |
| GET IT / My Gamecube Broke. | 2 | 0.478741 | Melodic-trap versus lo-fi style set; mixed vocals versus samples | Possible separation, but Gamecube's repeat is unstable |
| GET IT / Saturation in Delay, Love in Anger | 2 | 0.702716 | Shared `electropop` and all three assigned families | Conflict for a simple overlap rule |
| Die Right Here / OMG | 2 | 0.783445 | Both primary `pop`, shared `dance_pop`, sung-led | Preserve as a same-family counterexample |
| Sit Around / risk — lace! | 4 | 0.797607 | Both primary R&B; shared `contemporary_rnb`, sung-led and lead-vocal focus | Compatible evidence; not automatic admission |
| Tea Time / Sit Around | 4 | 0.693170 | No shared style; both sung-led, different arrangement focus | Protect this good match from a label-mismatch penalty |

The complete 15-pair table is exported, including the additional good
Tea Time / Saturation pair rated 5. All 120 unordered pilot pairs appear in an
inventory. Pairs with only older holistic labels retain **null playlist ratings**;
those labels are not pooled. boys dont cry / The Peace remains a qualitative
production-style diagnostic, not fresh numerical playlist truth.

## Description and taxonomy review

All 16 primary profiles claim a clear family. Thirteen claim a clear style and
three a tentative style. No primary output abstains or reports non-music. This is
model-asserted coverage and certainty, not an accuracy result.

OMG proposes the vocabulary addition `uk_garage_pop`. Its existing allowed labels
are `pop_rnb` and `dance_pop`. This is a reported vocabulary gap; it does not
authorize changing the ontology during the run.

Prioritize these owner checks:

- **My Gamecube Broke.**: verify which description matches the audio, given the
  lo-fi-to-ambient change on repeat.
- **The Hills**: the model assigns hyperpop/digicore and describes a high-pitched
  female hook. Check the retained recording and those specific audible claims.
- **Saturation in Delay, Love in Anger**: check the asserted abrasive metallic
  opening, hyperpop/digicore production and heavy vocal processing.
- **The Peace**: check the contemporary-R&B description and `mostly_consistent`
  section label against the exact recording and the owner's previously discussed
  processed/contrasting production.

These are review flags, not established errors. Source attribution, audio
description, vocabulary coverage and playlist usefulness are separate questions.
No expected genre label is substituted for an owner listening judgment.

The smallest next action is the supplied 16-track owner audio-review sheet,
starting with those four flags. Record independent descriptions before consulting
the model summary. Then assess acceptable alternatives, vocal/arrangement claims,
sections, timestamps and certainty. Do not collect more pair ratings for this
pilot. No reranker experiment is justified until those checks establish a useful,
repeatable signal.

## Artifacts and verification

Public package:
`ml/audio_similarity/reports/gemini_style_pilot/v1/duration_v3/`.

It includes exact raw responses and per-attempt ledgers across all 20 calls,
validated primaries and repeats, both schema identities, source provenance,
owner review sheet, complete pair diagnostics, six-control verification,
repeat differences, full-PCM checks, deterministic hash manifests and test output.
Historical stopped-run artifacts remain in the earlier engineering-smoke package.

Private run:
`ml/audio_similarity/.research_audio/gemini_style_pilot/style-pilot-v1-duration-v3/`.

Continuation manifest SHA-256:
`9998eb650b4514bf39c7020847a1ec16d6f9fab186350f345670b3ecee4e2e70`.

**45 focused tests passed. The full non-heavy suite passed 1,354 tests, with
12 deselected and 11 warnings, in 186.55 seconds.** Its first sandboxed attempt
was interrupted at a loopback-only test server; the complete rerun with loopback
access passed. All 60 protected original files and 106 frozen manifest inputs
verify unchanged. Complete cache replay validated 18 attempts and 16 primary
profiles with **zero API calls** and unchanged execution bytes.

Offline replay and report export, from `ml/audio_similarity`:

```bash
.venv/bin/python -m audio_similarity.gemini_style_pilot replay --run .research_audio/gemini_style_pilot/style-pilot-v1-duration-v3
.venv/bin/python reports/gemini_style_pilot/v1/duration_v3/rebuild.py
```

Status: **INFERENCE_COMPLETE_AWAITING_OWNER_AUDIO_REVIEW**. No held-out efficacy,
universal perception claim, ranking change, production activation or completed
owner-grounded style-accuracy result is asserted.
