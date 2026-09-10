# Frozen 100 manual genre-neighborhood review

Live URL: http://127.0.0.1:8798/neighborhood

Launch/resume from `ml/audio_similarity`:

```sh
.venv/bin/python -m audio_similarity.genre_neighborhood_frozen100 --serve --port 8798
```

All 100 existing frozen free-form Gemini profiles were mapped with the exact
original v1 configuration. No API calls, audio inference, taxonomy expansion,
ranking or production changes occurred. There are 112 flagged label occurrences
across 59 tracks. These are mapper coverage/ambiguity warnings, not measured
Gemini errors. Original text and context fields remain available on every card.

Review answers autosave to `artifacts/genre_neighborhood_review/frozen100/`.
The earlier 16-song review remains on port 8794 with its own state. No prior
answers were imported or fabricated; this expanded review has an independent
packet hash and export. No test answers were written into real owner state.

29 focused tests passed, including network-forbidden byte-identical artifact
replay, exact raw-label/identity preservation and all prepared-audio hashes.
Isolated Chromium checked all 100 rendered rows, full-recording durations and
HTTP Range responses, plus native playback/seeking, save/reload/CSV export and
mobile layout. Screenshots show disposable synthetic feedback only.
Frozen-input manifests were reverified; see integrity.json. Full regression
results are recorded in full_non_heavy_pytest.txt.

This is a manual mapping/classification inspection, not a numerical accuracy or
playlist-ranking benchmark. Unrecognized labels remain review-required.
