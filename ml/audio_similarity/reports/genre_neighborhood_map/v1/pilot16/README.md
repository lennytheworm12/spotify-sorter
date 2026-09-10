# Genre-neighborhood map v1 — original 16-song review

The mapper is coherent enough for an **unchanged full-100 manual coverage inspection**, with unknown/ambiguous labels retained for review. That extension has **not been run**. This is not evidence for genre accuracy, playlist compatibility, a penalty, or production use. Inspect this 16-song result before deciding to extend it.

Start with [the 16 song cards](manual_review.md) or [the one-row-per-song CSV](manual_review.csv). They show raw labels, canonical concepts, broad families, overlapping neighborhoods, separate scene/context, raw vocal/arrangement/texture fields and warnings/owner notes. Mapping and classification decisions have separate blank review fields; no owner answers were invented. [The reference](mapping_reference.md) explains every family and neighborhood.

## Inputs and scope

- Exact successful **free-form, point-timestamp** original pilot: A01–A10 and C01–C06. The original ontology-constrained arm remains historical context, not a mapping input.
- All **16 tracks / 88 label occurrences** preserved. No new Gemini/API calls or audio inference. No full-100 mapping, scoring, reranking, embedding, coordinate, playlist or production changes.
- Raw label strings and primary/secondary slots are preserved verbatim. Each derived membership has a raw-label trace. Unweighted sets do not turn repeated labels or model certainty into stronger evidence.
- The 41-concept registry includes explicit alias/control entries, four broad families and 27 overlapping neighborhood definitions. It is a curated, non-exhaustive operational map, constructed on exposed pilot vocabulary, not an independently validated universal ontology.
- **Pray — City Girl, tiffi (`2yQY2IzeQtUKanVo78Fg23`) is not in these 16.** It belongs to the frozen 100 and is deferred. No Pray classification or mapping was analyzed here.

## Unresolved / mapping-review-required labels

| Raw label | Song | Current treatment |
| --- | --- | --- |
| Bass Music | My Gamecube Broke. | Recognized ambiguous umbrella; no family or neighborhood guessed from it. Specific D&B/Neurofunk/Dubstep labels still map literally. |
| Chillout | She loves the color green and I love her | Preserve an explicitly ambiguous context/style umbrella separately; no automatic downtempo or lo-fi membership. |
| Dance | OMG | Preserve the ambiguous function/style/family label; no automatic EDM or dance-pop membership. |

There are **zero unrecognized label occurrences** in this pilot, but the three ambiguous labels remain unresolved in sonic interpretation. This is handling coverage, not classification accuracy. Bare Trap is mapped only to a broad trap-related neighborhood, with subtype-unspecified warnings; it does not infer a hip-hop/electronic family by itself. Generic Lo-fi and unseen labels are retained as review-required rather than guessed. Full-100 label coverage is unknown because it was not tested.

## Alias / normalization findings

| Canonical concept | Observed raw spellings |
| --- | --- |
| downtempo | `Downtempo`; `downtempo` |
| electronic | `Electronic`; `electronic` |
| hip_hop | `Hip Hop`; `Hip-Hop`; `hip hop`; `hip_hop` |
| lofi_hip_hop | `Lo-Fi Hip Hop`; `lo_fi_hip_hop` |
| trap | `Trap`; `trap` |

Unicode NFKC, case, whitespace, hyphens and underscores normalize consistently. Explicit aliases cover lexical abbreviations; no fuzzy matching, substring rules, stem guessing or automatic composite-label splitting is used. There are no cross-concept alias collisions.

`R&B` and `R&B and Soul` remain **different canonical concepts** within a shared broad umbrella. The combined label is not split into two independently predicted styles. Ambient (Saturation) and Downtempo (risk) occur in family slots but are resolved as style-level concepts with warnings. risk repeats Downtempo in family and style slots: both traces remain, with no extra membership weight.

K-Pop stays a scene/context label rather than a unique sonic style. East Coast Hip Hop and Conscious Hip Hop preserve regional/thematic context; neither adds boom-bap. Perfect Night does not gain K-Pop merely because of its artist or the owner's wording. Vocal role, arrangement, texture, density, audio observations and owner notes do not change any mapping.

## What the requested examples show

- **Wet Dreamz / explicit lo-fi tracks:** Boom Bap, Lo-Fi Hip Hop and Chillhop share `hip_hop_beat_lineage`, while boom-bap and lo-fi/chill-beats retain separate narrower memberships. This does not equate rap vocals with instrumental beats or make all hip-hop compatible.
- **The Hills / Shouldn't Be:** shared modern-R&B membership, with different secondary branches. The Hills retains alternative-R&B / trap-related memberships; Shouldn't Be retains alternative-pop / atmospheric-pop memberships. Generic R&B by itself never implies those substyles.
- **GET IT:** Gemini's explicit Hip Hop + Pop + R&B families all survive. Trap / Pop Rap / Melodic Rap provide overlapping style memberships. The owner's dark-alt-R&B description is a review question, not permission to add an absent Alternative R&B label.
- **Sit Around / risk:** their existing playlist rating is 4/5. Indie Pop and Dream Pop share a general `indie_pop_related` neighborhood without asserting that all indie pop is dreamy. The relationship uses only concepts, not song/artist rules. It is not independent confirmation of genre truth.
- **Tea Time / Sit Around:** also an existing 4/5 pairing, but no shared style neighborhood under the current labels. Only a broad electronic family overlaps. No mapper rule is added to manufacture a match; missing genre overlap cannot become automatic rejection.
- **boys dont cry / The Peace:** both raw profiles include Trap, so `trap_related` overlaps; broad hip-hop/pop/R&B memberships also overlap. Both profiles differ from the owner's hyperpop-oriented words. This remains an owner-specific exploratory pairing with no numeric genre label or fresh confirmatory truth.
- **OMG / Die Right Here:** the existing 2/5 pairing still shares broad pop/electronic/R&B families and electronic-pop/synth-pop neighborhoods. Correct normalization does not eliminate same-family compatibility counterexamples.
- **My Gamecube Broke. / Tea Time (4/5)** and **Saturation / Tea Time (5/5):** the current free-form classifications produce no shared style neighborhood. These are useful classification/compatibility review cases, not evidence to collapse bass music, minimal techno and lo-fi into one neighborhood.

[Pair context](pair_context.json) preserves all 15 existing pilot PLAYLIST_COMPATIBILITY_V1 rows plus four explicitly unrated illustrative pairs. Unknown ratings stay null. No rating is treated as a genre-accuracy label and no numerical genre score, performance summary or ranking change is computed.

## Classification concerns are not mapper bugs

The main priorities are **My Gamecube Broke.** (DnB/Neurofunk/Dubstep versus owner lo-fi electronic/gamey wording), **Saturation** (minimal/dub techno and microhouse versus earlier owner/model interpretations), **boys dont cry** (trap/emo/melodic rap versus owner electronic hyperpop), and **The Peace** (contemporary/alternative R&B and trap versus owner alt-pop ballad/hyperpop).

The owner later found Saturation's *older hyperpop* interpretation more plausible; that does not endorse its newer minimal-techno profile or prove that either interpretation is wrong. The older objection to The Hills' hyperpop assignment is not applied as a rejection of its current R&B profile.

GET IT, Sit Around, Perfect Night and Die Right Here also have terminology, emphasis or context differences worth inspecting. These are explicitly suggested review cases, **not eight measured model errors**. No new independent listening verdict was collected. The mapper preserves the current predictions; it does not repair classifications to fit owner notes. See [classification review cases](classification_review_cases.json) for exact current labels and source-qualified notes.

## Recommendation and verification

Proceed unchanged only if the next request is a **manual full-100 mapping/coverage review**. Keep this map version frozen, retain new unknown labels, and review mapping ambiguity separately from questionable model descriptions. No evidence here establishes that band distances or genre penalties improve playlists. The good cross-style pairs and bad same-neighborhood pair are reasons to avoid using shared/missing membership as an automatic decision.

Focused tests cover raw-label preservation, alias/collision rules, scene separation, broad versus narrow overlap, ambiguity/abstention, duplicate traces, metadata/facet/owner-note independence, exact-16 membership and immutable deterministic review replay. Verification artifacts record the full suite, actual frozen-input checks and replay. No browser code was changed.

From `ml/audio_similarity`:

```bash
.venv/bin/python -m audio_similarity.genre_neighborhood_review --output reports/genre_neighborhood_map/v1/pilot16
.venv/bin/python -m pytest -q tests/test_genre_neighborhood.py
```

[Config](genre-neighborhood-map-v1.json), [mapped records](mapped_review.json), [label audit](label_audit.json), [source hashes](input_hashes.json), and the final artifact manifest make the result reproducible. Rebuild uses no API and refuses to replace changed frozen artifacts.
