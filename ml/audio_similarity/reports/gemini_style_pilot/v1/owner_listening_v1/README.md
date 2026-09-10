# Owner listening notes received; Gemini comparison pending

The submitted CSV contains all 16 independent listening descriptions and confirms
all 16 retained recordings. Every field, stable identity, timestamp and revision
matches the live saved review. No answers were lost and no re-entry is needed.
The original CSV and all 83 saved revision events are preserved here. The listening
pass has been frozen and the frontend advanced to the comparison pass without
changing any answer or revision.

**Status: LISTENING_COMPLETE_COMPARISON_PENDING.** All 16 model-description
verdicts and all 16 certainty assessments are blank. Vocal/arrangement and section
notes are also blank; those listening fields were optional. Missing assessments
are unknown, not approval or rejection. This is an interim owner-note analysis,
not the pilot's final audio-description validation or scientific closeout.

## What the owner descriptions suggest

This table juxtaposes the owner's exact words (trailing whitespace omitted only
for display) with frozen primary model labels. It does not assign correctness
labels. Secondary model styles are included to avoid treating an acceptable
alternative as absent merely because it was not primary.

| Song | Owner description | Gemini primary family; primary and secondary styles |
| --- | --- | --- |
| Wet Dreamz | the song sounds like boom bap/ golden age rap | hip-hop/rap; boom bap |
| Shoota | trap rap heavy fast/aggressive | hip-hop/rap; trap, melodic trap |
| My Gamecube Broke. | lofi electronic/gamey style | hip-hop/rap; lo-fi hip-hop, chillhop, instrumental hip-hop |
| She loves the color green and I love her | soft studying lofi sound | hip-hop/rap; lo-fi hip-hop, chillhop, instrumental hip-hop |
| Tea Time | lofi hip hop | hip-hop/rap; lo-fi hip-hop, chillhop |
| GET IT | dark alt rnb | hip-hop/rap; melodic trap, trap, electropop |
| The Hills | dark heavy rnb | electronic; hyperpop, digicore, trap |
| Shouldn't Be | soul rnb | R&B/soul; alternative R&B, contemporary R&B, pop R&B |
| Perfect Night | kpop contemporary rnb | pop; dance pop, indie pop |
| OMG | kpop hip hop contemporary rnb | pop; pop R&B, dance pop |
| Saturation in Delay, Love in Anger | lofi | pop; hyperpop, digicore, electropop |
| Sit Around | lofi soft vibes | R&B/soul; pop R&B, contemporary R&B |
| risk | dreamy whisper dream pop bedroom pop | R&B/soul; alternative R&B, contemporary R&B, ambient |
| boys dont cry | electronic hyperpop | electronic; digicore, hyperpop |
| The Peace | alt pop ballad hyperpop | R&B/soul; contemporary R&B, pop R&B, alternative R&B |
| Die Right Here | alt upbeat indie | pop; dance pop, synthpop |

There is visible agreement on several broad identities, including boom bap for
Wet Dreamz, trap for Shoota and hyperpop for boys dont cry. The descriptions also
reveal substantial differences that should not be dismissed as label spelling:
The Hills and Saturation receive hyperpop/digicore descriptions despite the owner
describing dark, heavy R&B and lo-fi respectively. GET IT, The Peace and risk also
need alternative-label checks. These are assistant interpretations of the
juxtaposition, not owner-confirmed model errors.

My Gamecube Broke.'s primary lo-fi description is closer in wording to the owner's
note than the paid repeat's ambient description. However, the owner also wrote
“electronic/gamey”; that does not establish that every ambient descriptor is
incorrect. Both outputs remain preserved. Their disagreement on vocal samples
and instrumental status is still unreviewed.

The owner confirms the intended recordings, and the earlier full-PCM checks
verified unchanged preparation. That weakens a wrong-recording explanation for
these specific description disagreements. It does not independently prove the
provider's internal audio interpretation, the claimed vocal events or timestamps.
In particular, The Hills' asserted female hook and Saturation's asserted abrasive
metallic opening still require listening-based comparison.

## Relationship to existing playlist judgments

All 15 existing `PLAYLIST_COMPATIBILITY_V1` pairs within the pilot are joined by
stable Spotify identities in `all_playlist_pairs_with_owner_notes.json`. The
original ratings, C scores and model-only diagnostic implications are preserved
inside `frozen_model_and_playlist_evidence`. Owner validation of those model
signals is explicitly pending. No new numeric rating or reranking implication
is inferred from these free-text descriptions.

Several selected examples help locate the next checks:

| Pair | Existing rating | Frozen C | Implication of owner notes, pending model comparison |
| --- | ---: | ---: | --- |
| Wet Dreamz / Saturation | 1 | 0.601257 | Owner distinguishes boom bap from lo-fi, but Gemini's apparent separation uses an unvalidated hyperpop description of Saturation. Correct pair separation alone would not validate its explanation. |
| GET IT / My Gamecube Broke. | 2 | 0.478741 | Dark alternative R&B versus gamey lo-fi is an owner-described distinction. The model's labels and unstable Gamecube repeat still require validation. |
| GET IT / Saturation | 2 | 0.702716 | Owner describes dark alternative R&B versus lo-fi; the model instead overlaps on electropop. |
| Tea Time / Saturation | 5 | 0.790522 | Both owner descriptions say lo-fi, while the model's style labels diverge. This good pair tests the cost of a mistaken description. |
| Tea Time / Sit Around | 4 | 0.693170 | Both owner notes describe lo-fi; the model uses different style labels. Preserve the good historical judgment. |
| Sit Around / risk | 4 | 0.797607 | Lo-fi/soft and dreamy/bedroom-pop language coexist in a good match. Different labels remain compatible; this is not evidence for a hard genre gate. |
| Die Right Here / OMG | 2 | 0.783445 | Owner distinguishes upbeat indie from K-pop/contemporary R&B; both model profiles are broadly pop. Keep this same-broad-family counterexample. |

These selected examples were already inspected. They are development diagnostics,
not held-out evidence of improved ranking. Three qualitative diagnostic pairs
retain null playlist ratings, including boys dont cry / The Peace. Older holistic
labels are not pooled. There is no measured count of corrected or damaged rankings
because no rankings were changed.

## Finish the existing review

Refresh **http://127.0.0.1:8794**. The saved listening notes are now read-only and
Gemini's frozen primary descriptions are available beside them. For each track,
choose whether its description fits and whether its certainty is appropriate.
Use “not sure” where needed. Notes and alternative labels are optional. Repeats
remain separately visible. Start with The Hills, Saturation, My Gamecube Broke.
and The Peace, then complete the remaining comparisons and click **Finish review**.
Autosave is active; exporting again is optional.

The comparison is needed to separate acceptable vocabulary differences from
incorrect descriptions of audible events. It should not become a request to
produce formal genre annotations or additional song-pair ratings. The earlier
report/conversation already exposed some model results, so the first listening
pass is not claimed to be untouched or naive evidence.

The smallest justified next action is this already-prepared comparison pass.
There is not yet evidence to deploy or tune a genre prior, change model prompts,
train a scorer or commission more API calls. The 20-call allowance is exhausted;
this import, preservation and analysis made **zero new Gemini calls**. Recorded
pilot token cost remains **$0.14680800**.

## Preservation and replay

Run from `ml/audio_similarity`:

```bash
.venv/bin/python reports/gemini_style_pilot/v1/owner_listening_v1/rebuild.py
```

The exporter validates the exact CSV against the captured SQLite answers and
independent snapshot, verifies the original inference manifest and protected
historical inputs, and produces deterministic, create-once track/pair exports.
It does not read later live review answers, make network calls or overwrite
historical reports. `artifact_manifest.json` hashes every file except itself.
`verification.json` records the actual import/integrity checks. Application code
is unchanged; this is an evidence-only handoff, not a new claim of a full test run.

Submitted CSV SHA-256:
`baf8889e107854aaabf3f95017271082d61ef31485bf1f4e46ee092e1bae8cdb`.
