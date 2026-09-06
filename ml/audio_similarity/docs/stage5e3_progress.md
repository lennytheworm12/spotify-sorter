# Stage 5E.3 implementation and review handoff

Governing contracts are preserved byte-for-byte in [revision 2](designs/stage5e3_revision2.md) and [execution goal](designs/stage5e3_handoff_goal.md). The design blob is `137d6cdf91e9e132b2744b8d352bf070a4549ff5`.

Work starts from `ml/stage5f1-energy-motion` at `269ee29209b7732b154cef0717ddb95384f3973e`, retaining the completed Stage 5E materialization/subset work and the existing uncommitted song-review UI and chart-acquisition changes. Those unrelated edits are not part of this implementation's commits.

The initial locked-environment non-heavy suite passed: 1,208 passed, 12 deselected, 11 warnings, 106.30 seconds. Command: `.venv/bin/python -m pytest -q` from `ml/audio_similarity`.

Implementation uses shared `load_audio()` with full-source channel mean before resampling, the installed `MuQMulanEncoder` model, existing canonical pair identity and Stage 5E.2 rating provenance, Stage 5E.1 local audio lookup, and the shared HTTP Range server. Historical encoder adapters and historical output artifacts remain unchanged.

Full-song MuQ validates the model output before the adapter's additional L2 operation. Successful chunk values are retained internally in float64 for exact interrupted-run pooling; published chunk and track vectors are float32. Cache keys cover source, model, configuration, embedding code and environment. Preparation also freezes the complete evaluation implementation and tests.

The Chromium fixture uses synthetic WAV audio and disposable review state. Real-source playback validation must never submit judgments into the real queue. The review server exposes only its allowlisted player, session and packet-submission endpoints. Submission does not reveal metadata. The CLI separates the pre-review pipeline from gated snapshot, analysis and closeout commands.

Engineering verification and real materialization are pending. No scientific verdict has been computed. The governing design is not modified by implementation.

## Engineering amendment before any new inference or human outcomes

The first prepared run, `frozen100_v1`, configuration `6450d2266b17adb2357ae5ff009ce8e2695fbff3a83ee14f364c20439188bc9a`, stopped with zero MuQ forward passes. Passing the local snapshot directory to the installed Hugging Face mixin selected a safetensors-only local-directory path, while the pinned checkpoint is the verified `pytorch_model.bin`. Its original ledger and frozen inputs are preserved. No scientific verdict applies to this engineering interruption.

The corrected loader uses the existing `MuQMulanEncoder(revision=<pinned revision>)` repository-ID path, with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, exactly as the historical adapter expects. No weight, estimator, audio policy, rating rule, or threshold changes. The loader source is now explicitly part of the embedding implementation hash. The corrected create-once run and CLI default are `frozen100_v2`; private live review state is `.research_audio/stage5e3_frozen100_v2_review`. This version change preserves the failed preparation rather than rewriting it.
