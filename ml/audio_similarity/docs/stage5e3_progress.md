# Stage 5E.3 implementation and review handoff

Governing contracts are preserved byte-for-byte in [revision 2](designs/stage5e3_revision2.md) and [execution goal](designs/stage5e3_handoff_goal.md). The design blob is `137d6cdf91e9e132b2744b8d352bf070a4549ff5`.

Work starts from `ml/stage5f1-energy-motion` at `269ee29209b7732b154cef0717ddb95384f3973e`, retaining the completed Stage 5E materialization/subset work and the existing uncommitted song-review UI and chart-acquisition changes. Those unrelated edits are not part of this implementation's commits.

The initial locked-environment non-heavy suite passed: 1,208 passed, 12 deselected, 11 warnings, 106.30 seconds. Command: `.venv/bin/python -m pytest -q` from `ml/audio_similarity`.

Implementation uses shared `load_audio()` with full-source channel mean before resampling, the installed `MuQMulanEncoder` model, existing canonical pair identity and Stage 5E.2 rating provenance, Stage 5E.1 local audio lookup, and the shared HTTP Range server. Historical encoder adapters and historical output artifacts remain unchanged.

Full-song MuQ validates the model output before the adapter's additional L2 operation. Successful chunk values are retained internally in float64 for exact interrupted-run pooling; published chunk and track vectors are float32. Cache keys cover source, model, configuration, embedding code and environment. Preparation also freezes the complete evaluation implementation and tests.

The Chromium fixture uses synthetic WAV audio and disposable review state. Real-source playback validation must never submit judgments into the real queue. The review server exposes only its allowlisted player, session and packet-submission endpoints. Submission does not reveal metadata. The CLI separates the pre-review pipeline from gated snapshot, analysis and closeout commands.

Engineering verification and real materialization are pending. No scientific verdict has been computed. The governing design is not modified by implementation.
