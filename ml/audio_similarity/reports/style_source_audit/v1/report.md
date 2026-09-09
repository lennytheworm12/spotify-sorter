# Retained-source and classifier audit

The technical audit passed for the 24 tracks in the completed review. All retained source hashes agree with acquisition provenance, review packet identities and classifier cache identities. All 24 song means reconstruct exactly from the cached patch scores.

Fresh processes using the installed official Essentia reference predictor reproduced all 539 patch predictions across Hit the Wall, Fresh Air and Die Right Here with maximum absolute error **0.0**. These are deliberate engineering duplicates, not a cache-replay claim. No new scoring rule or model was fitted. The dominant style labels remain broadly consistent across each song's four chronological quarters, so the observed contradictions are not explained by one isolated section dominating the mean in these three cases.

## Identity questions requiring owner confirmation

| Spotify identity | Retained provider title | Question |
|---|---|---|
| Heart — chicken97 | msftz(미스피츠) 'Heart' Official MV | Is this the intended recording, an alias/reupload, or the wrong artist/song? |
| boys dont cry — sysmint | ericdoa - boys dont cry (Full Unreleased Song) | Is the sysmint entry the same recording or a different song? |
| me2urs2ours — Yayyoung, Sojou Kim | friendzone | Is this an alternate title for the intended recording? |

These are unresolved discrepancies, not confirmed wrong downloads. The other 21 titles are metadata-consistent, not independently identified by listening. Matching hashes establish that the same audio was reviewed and extracted; they do not establish that the audio belongs to the intended Spotify song.

The embedding experiment is held at this prerequisite. Do not silently drop the questioned tracks, replace historical sources, reassign ratings to new audio or alter historical verdicts. If the owner confirms the recordings are correct, preserve that confirmation and proceed with a frozen same-model 1280-D embedding control. If a source is wrong, first design a versioned source/label correction: the old judgments describe the old recording, not automatically the intended replacement.

Interpret artist-disjoint claims as conditional on correct source-to-artist identity. All prior experiment artifacts remain immutable.

## Reproduce

From `ml/audio_similarity`:

```bash
PYTHONPATH=src .venv/bin/python -m audio_similarity.style_source_audit
.venv/bin/python -m pytest -q tests/test_style_source_audit.py
```

The exact fresh-inference track list and tolerance are frozen in `reference_protocol.json`. The reference command for each listed ID is:

```bash
CUDA_VISIBLE_DEVICES=-1 TF_NUM_INTRAOP_THREADS=1 TF_NUM_INTEROP_THREADS=1 OMP_NUM_THREADS=1 TF_DETERMINISTIC_OPS=1 PYTHONPATH=src artifacts/style_prior_pilot/env/bin/python -m audio_similarity.style_source_reference --track TRACK_ID
```

Reference execution records are create-once and include timing; do not rerun into the same completed record expecting it to overwrite. No audio downloads or external audio uploads occurred.
