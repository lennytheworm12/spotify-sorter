# Compact Stage 5E.3 reviewer

This presentation update restores the previous song-review layout: compact candidate rows, direct 1–5/Unsure buttons, optional notes, a shared candidate player, song dropdown, and unsubmitted-song filtering. Only one audio player plays at a time. Draft choices persist in the current browser tab across navigation and reloads; complete packets are still submitted atomically to the existing review ledger. Submitted-packet changes require a revision reason.

Run from `ml/audio_similarity`:

```bash
.venv/bin/python -m audio_similarity.cli.stage5e3_compact_review --port 8785
```

Open `http://127.0.0.1:8785`. This uses the same `frozen100_v3` artifacts and `.research_audio/stage5e3_frozen100_v3_review` state as the original launcher. Stop an existing server on that port before launching another.

The original frozen HTML, backend, analysis code, input manifests, extraction outputs and ratings remain unchanged. The separate launcher allows the presentation update without rewriting the frozen implementation reference. All method/rank/score/probe metadata remains inaccessible through the reviewer. Post-review snapshot/analysis commands remain unchanged.

Validation: `python -m pytest -q tests/test_stage5e3_compact_ui.py` in the locked environment: 1 passed, 9.75 seconds. The isolated Chromium fixture checks playback/seeking, draft persistence across reload/navigation, complete-packet submission, saved-state reload, continued navigation after saving, global blinding and a 390px mobile viewport. No fixture judgments enter the real state. Frozen input integrity and unchanged real ledger verified after the local-server restart.
