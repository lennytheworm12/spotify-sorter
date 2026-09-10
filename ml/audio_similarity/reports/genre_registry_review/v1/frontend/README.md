# Vault registry comparison handoff

Open http://127.0.0.1:8798/compare, linked from the existing 100-song review.
Old, New vault and Side by side views compare the same selected recording.
Raw Gemini labels and audio are shared. New typed concepts, background families,
separate contexts/facets, weighted memberships and label-level contributions
are displayed. The section is read-only and preserves existing review answers.

The exact vault JSON and supplied reference mapper/tests are pinned separately in
`configs/genre_registry_v1/`. The JSON SHA-256 is
`4fab997c03a79c7df7102fe0b145237f3ade62403bc3d3963a8ade98236742e3`.
The old mapper and reports remain unchanged. The derived comparison packet and
full coverage audit are in `../frozen100/`.

The new registry contains 138 concepts and 29 neighborhoods. It produces specific
style support on 99/100 songs; one song has a review-required/unmapped label,
compared with 59 under the old compact mapper. These are vocabulary coverage
counts, not audio-description accuracy, ranking gains or owner-approved truth.
No model calls, score adjustments, graph movement or production changes occurred.

Validation: 40 supplied engineering tests and 9 focused integration/regression
tests passed. The latter include network-forbidden byte-identical export replay,
raw-label/identity preservation, protected-output checks and existing review-store
contracts. Chromium exercised all 100 rows, all three view modes, search, audio
playback, mobile layout and zero console errors, with no answer writes.
Screenshots were visually inspected. Saved owner-state bytes were identical
before/after the live server restart. Full non-heavy results are recorded in
`full_non_heavy_pytest.txt`.

Launch/resume from `ml/audio_similarity`:

```sh
.venv/bin/python -m audio_similarity.genre_neighborhood_frozen100 --serve --port 8798
```
