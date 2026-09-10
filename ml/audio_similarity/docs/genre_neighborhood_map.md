# Genre-neighborhood map v1: original-16 manual inspection

`configs/genre-neighborhood-map-v1.json` is an explicit, label-only mapper for the frozen successful free-form 16-song Gemini arm. It is independent of the earlier Discogs band-prior experiment and changes no rankings or production behavior.

From `ml/audio_similarity`:

```bash
.venv/bin/python -m audio_similarity.genre_neighborhood_review --output reports/genre_neighborhood_map/v1/pilot16
.venv/bin/python -m pytest -q tests/test_genre_neighborhood.py
```

The review command accepts no alternative corpus or full-100 option. It checks the exact A01–A10/C01–C06 membership before mapping. Existing frozen artifacts are inputs, verified by hashes. Repeating the command verifies existing output bytes instead of replacing changed artifacts. Use a new versioned output directory for intentional changes.

Read `reports/genre_neighborhood_map/v1/pilot16/manual_review.md` or its one-row-per-song CSV. `mapped_review.json` provides every raw-label trace and membership evidence. `label_audit.json` lists unresolved labels, aliases and field-granularity warnings. `pair_context.json` displays existing playlist judgments and qualitative label overlap; it is not a genre-accuracy test or a scorer.

The mapper consumes only primary/secondary family/style strings. Unicode/case/spacing/dash normalization feeds an explicit alias lookup; it never uses fuzzy matches, stems, substring guesses or automatic splitting of compound labels. Raw strings and primary/secondary positions remain intact. Family, style-neighborhood and scene/context memberships are distinct unweighted sets, with a source-label trace for every member. Duplicate occurrences are not additional confidence.

Broad family membership indicates an operational lineage, not vocal role, instrumentation, mood, measured tempo or playlist compatibility. Scene/thematic labels do not add sonic neighborhoods. Generic ambiguous labels remain review-required; unseen labels remain verbatim with no invented memberships. Specific labels can still contribute evidence alongside an unresolved umbrella. The mapping is curated and non-exhaustive, not a universal genre ontology.

`vocal_role`, `arrangement_focus`, `texture_tags` and certainty are copied for display. They cannot change mapping. Identity metadata, audio observations, owner notes and pair judgments also cannot affect it. Owner/assistant review notes are joined separately by stable identity after all 16 mappings have been computed. Track-specific review comments are not mapper exceptions.

No new Gemini calls, audio inference, labels, genre distances, learned weights, CLAP/MuQ changes, graph changes, playlist writes or full-100 mapping occur. Any future full-100 application must be separately requested; the current recommendation is limited to unchanged manual coverage inspection with unknown labels retained for review.
