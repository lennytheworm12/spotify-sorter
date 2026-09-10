# Frozen-100 free-form Gemini classifications

All 100 original amended frozen tracks are retained: 100 validated profiles,
including 16 exact prior profiles and 84 new profiles;
0 explicitly invalid outputs. No source is missing or quarantined.

Gemini `gemini-3.8-flash`, LOW thinking, described full metadata-stripped native-rate FLAC recordings.
The exact preceding free-form prompt supplies no genre vocabulary, definitions, examples or mappings.
Each request contains only its neutral audio identifier, duration, full audio, prompt and schema.
No artist/song identities, metadata, ratings, neighbors, search or conversation context were supplied.
Source identity reuses the frozen retained recording/provenance; this is not a fresh owner check of all 100 recordings.

There were 84 new generation calls, zero automatic retries and zero new repeats.
New standard-rate token cost: $0.42053400; combined prior/current cost:
$0.65923050, within the preserved $2 cap.
Each generation was preceded by exact request counting and a $0.817152 worst-case reservation.
`usage_ledger.json` preserves billed input, output, thinking, response IDs, returned versions,
finish reasons and latency. The execution directory retains every HTTP request receipt/raw response.

`classifications.csv` / `classifications.json` contain all 100 identities and raw labels/facets.
`profiles/` contains validated profiles or explicit null failures. `source_provenance/` and
`preparation/` record source/prepared hashes, durations, complete PCM equality and conversion commands.
Audio binaries and secrets are excluded from Git.

All new profiles were frozen before this aggregate export. Cache replay made zero API calls;
all 702 protected input hashes verified. The 16 reused profiles keep
their original implementation/cache identity rather than pretending to be new calls.

These are unreviewed model descriptions, not owner-confirmed style truth or playlist decisions.
Model size and asserted certainty do not establish classification accuracy. Free-form terminology
is preserved verbatim, including inconsistent spelling/case. No taxonomy normalization,
accuracy score, held-out comparison, reranking or production activation was performed.
The next step is owner inspection of these classifications before any compatibility experiment.

From `ml/audio_similarity`:

```bash
.venv/bin/python -m audio_similarity.gemini_frozen100 replay --run .research_audio/gemini_style_pilot/frozen100-free-genre-v1
.venv/bin/python -m audio_similarity.gemini_frozen100 export --run .research_audio/gemini_style_pilot/frozen100-free-genre-v1 --report reports/gemini_style_pilot/frozen100_free_genre_v1
```

The export is create-once and deterministically ordered; changed existing bytes are rejected.
`artifact_manifest.json` covers every public artifact except itself.
