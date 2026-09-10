# Original-16 genre-neighborhood review frontend

Open http://127.0.0.1:8794/neighborhood. The existing review home links here.
Launch/resume from `ml/audio_similarity`:

```sh
.venv/bin/python -m audio_similarity.cli.gemini_style_review --port 8794
```

The full-recording player accompanies raw Gemini labels, canonical concepts,
families, neighborhoods, separate scene/context labels and label-level traces.
Mapping reasonableness and audio-classification agreement are separate questions.
Optional notes autosave with explicit saved/error status, local draft recovery,
revision conflict handling and CSV export. Both questions accept uncertainty.
Answers live separately in `artifacts/genre_neighborhood_review/pilot16/`.

Validation: 27 focused tests passed. Isolated Chromium exercised all 16 durations,
native playback and seeking, HTTP Range, autosave/reload, long Unicode notes,
offline recovery/export, multi-tab conflicts, final freeze and mobile layout.
Screenshots contain synthetic disposable feedback only. Zero real answers were
written by browser tests. Windows curl reached the live server. The previous
review files and the frozen mapping package passed hash-integrity checks.
See verification.json, integrity.json and full_non_heavy_pytest.txt for evidence.

No model/API calls, full-100 mapping, reranking or production changes occurred.
The interface collects owner inspection feedback; it is not a genre-accuracy
benchmark and does not turn shared neighborhoods into automatic playlist matches.
