# Stage 5E.3 implementation and review handoff

Governing contracts are preserved byte-for-byte in [revision 2](designs/stage5e3_revision2.md) and [execution goal](designs/stage5e3_handoff_goal.md). The design blob is `137d6cdf91e9e132b2744b8d352bf070a4549ff5`.

Work starts from `ml/stage5f1-energy-motion` at `269ee29209b7732b154cef0717ddb95384f3973e`, retaining the completed Stage 5E materialization/subset work and the existing uncommitted song-review UI and chart-acquisition changes. Those unrelated edits are not part of this implementation's commits.

The initial locked-environment non-heavy suite passed: 1,208 passed, 12 deselected, 11 warnings, 106.30 seconds. Command: `.venv/bin/python -m pytest -q` from `ml/audio_similarity`.

Implementation uses shared `load_audio()` with full-source channel mean before resampling, the installed `MuQMulanEncoder` model, existing canonical pair identity and Stage 5E.2 rating provenance, Stage 5E.1 local audio lookup, and the shared HTTP Range server. Historical encoder adapters and historical output artifacts remain unchanged.

Full-song MuQ validates the model output before the adapter's additional L2 operation. Successful chunk values are retained internally in float64 for exact interrupted-run pooling; published chunk and track vectors are float32. Cache keys cover source, model, configuration, embedding code and environment. Preparation also freezes the complete evaluation implementation and tests.

The Chromium fixture uses synthetic WAV audio and disposable review state. Real-source playback validation must never submit judgments into the real queue. The review server exposes only its allowlisted player, session and packet-submission endpoints. Submission does not reveal metadata. The CLI separates the pre-review pipeline from gated snapshot, analysis and closeout commands.

The completed engineering evidence and review handoff are recorded below. No scientific verdict has been computed. The governing design is not modified by implementation.

## Engineering amendment before any new inference or human outcomes

The first prepared run, `frozen100_v1`, configuration `6450d2266b17adb2357ae5ff009ce8e2695fbff3a83ee14f364c20439188bc9a`, stopped with zero MuQ forward passes. Passing the local snapshot directory to the installed Hugging Face mixin selected a safetensors-only local-directory path, while the pinned checkpoint is the verified `pytorch_model.bin`. Its original ledger and frozen inputs are preserved. No scientific verdict applies to this engineering interruption.

The corrected loader uses the existing `MuQMulanEncoder(revision=<pinned revision>)` repository-ID path, with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, exactly as the historical adapter expects. No weight, estimator, audio policy, rating rule, or threshold changes. The loader source is now explicitly part of the embedding implementation hash. The corrected create-once run and CLI default are `frozen100_v2`; private live review state is `.research_audio/stage5e3_frozen100_v2_review`. This version change preserves the failed preparation rather than rewriting it.

## Serialization correction after successful extraction, before human review

`frozen100_v2` completed 100/100 tracks with 1,927 MuQ forward passes in 277.90 seconds. Its first replay had 100 track-cache hits and zero forwards. Both track and chunk NPZ exports were unchanged, but Parquet column order differed because SQLite JSON metadata returned dictionary keys in sorted order while the original in-memory dictionaries used insertion order. The create-once writer correctly refused to overwrite that manifest.

The correction explicitly sorts Parquet column names in addition to rows, with a regression test comparing original and JSON-round-tripped dictionaries. It changes output serialization only. Embedding identity remains `c5f90498cb9a269d8d61e23aba5dc92a7c4c812337304ae20a0a98774e94c743`; no vectors are rekeyed or recomputed. The overall experiment configuration adds `serialization_version=canonical_columns_v2`. `frozen100_v3` is the corrected artifact run and default, reusing all compatible v2 cache entries; private state is `.research_audio/stage5e3_frozen100_v3_review`. v2 scientific outputs and its original/replay execution ledgers remain immutable. No new human outcomes or real-data quality comparisons have been inspected.

## Verified handoff

**READY_FOR_HUMAN_REVIEW** in `reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3/`. Engineering handoff complete; human review and representation recommendation pending; no production activation.

- 100/100 tracks OK; original extraction: 1,927 chunks/forwards, 277.90 seconds, peak CUDA allocation 2,897,031,168 bytes. The original inference ledger remains in `frozen100_v2/original_execution_ledger.json`.
- v3 rebuild and replay: 100 track-cache hits each, zero new forwards; track/chunk NPZ bytes equal the original v2 exports. Parquet data are equal with canonical column order. No embedding identity migration or rekeying occurred.
- Four methods have 500 natural directional slots each; 656 unique natural pairs. Including probes, the evidence universe has 770 unique pairs.
- 385 natural pairs have compatible existing labels; 34 also receive a prescribed drift repeat, leaving 351 reused without repeat. The live queue has 419 globally unique judgments: 271 unresolved pairs plus 148 drift repeats, across 98 packets. Zero numeric conflicts.
- Final non-heavy suite: **1,245 passed, 12 deselected, 11 warnings in 160.59 seconds**. Initial focused suite: 36 passed; post-serialization focused checks: 22 passed. All 37 new tests are included in the final non-heavy suite.
- Isolated Chromium fixtures passed packet submission, revision, persistence/restart, paging, playback/seek/Range, and blinding checks. Read-only real Chromium checks passed for all 100 recordings, with no page errors, console warnings/errors, or failed requests. The real submission ledger remains zero bytes.
- Deterministic prepare/retrieval/review reruns performed zero rewrites. 197 frozen historical files and all 100 source hashes were verified. Earlier Stage 5E.3 attempts and execution ledgers were preserved.

Evidence: [handoff](../reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3/handoff.json), [verification](../reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3/engineering_verification.json), [manifest](../reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3/artifact_manifest.json), [materialization origin](../reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3/materialization_origin.json).

Hashes (SHA-256):

```text
design:         24c4d439b2366fbdd10f02eb883dd81b269f65ad6ca5440ba9ef9424c48eaec0
source manifest:1c73bf9b2a20f9dc1f623ae9e170422594d2f5af110ab194c284170bea721391
selected100:    b09447af7c28fec5dd9816dd9801da9963c3dbc4c8ae534dc5a67307db175088
embedding config:c5f90498cb9a269d8d61e23aba5dc92a7c4c812337304ae20a0a98774e94c743
MuQ weights:    d42ae3f7cb9b66759ee0089ddc70e2f28b130c2d8ba621457358272d32dd0444
track NPZ:      53ec56c415b646ad18760bd1fee41c962719330cc14a06cc7844172f3e53ff32
chunk NPZ:      d0be7ff6d4e12e83acd0a8cc1d080c994f01cc059e73fcb5a254d76ca088597f
```

From `ml/audio_similarity`, launch or resume the same frozen review:

```bash
.venv/bin/python -m audio_similarity.cli.stage5e3 review --run reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3 --state .research_audio/stage5e3_frozen100_v3_review --port 8785
```

Open `http://127.0.0.1:8785`. Submit every candidate in each packet; UNSURE is allowed and is not requeued automatically. Metadata stays hidden after submission and across reloads.

Only after the entire queue is submitted:

```bash
.venv/bin/python -m audio_similarity.cli.stage5e3 snapshot-labels --run reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3 --state .research_audio/stage5e3_frozen100_v3_review
.venv/bin/python -m audio_similarity.cli.stage5e3 analyze --run reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3
.venv/bin/python -m audio_similarity.cli.stage5e3 closeout --run reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3
```

The analysis/reveal/closeout boundary was tested only with isolated synthetic fixtures. No real-data winner selection or final scientific verdict was run at this handoff.

## Completed scientific closeout (2026-09-07)

**INCONCLUSIVE**, under the frozen revision-2 precedence. All 98 packets / 419
judgments and six notes are saved and frozen; all four methods have 100% numeric
Top-5 coverage. Analysis used cached results only, with no new inference,
judgments, weight changes, or production activation.

Read the [scientific report](../reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3/scientific_closeout_report.md).
The original run's `experiment_report.md` and earlier handoff artifacts remain
byte-for-byte unchanged as historical engineering evidence. The new scientific
report and `closeout.json` supersede their pending scientific status.

M4 versus M3: unacceptable +1.0 percentage point (95% interval -0.4 to +2.6),
coherent +0.4 points (-2.8 to +3.405), mean rating effectively 0.000 (-0.054 to
+0.050), historical-positive recovery -4.547 points (-8.466 to -0.983).
ACCEPT passes, GAIN fails, and no ordered recommendation branch passes.
This does not prove equivalence or superiority of the existing configuration.

Non-heavy suite: **1,250 passed, 12 deselected, 11 warnings, 154.19 seconds**.
Independent arithmetic checks matched all 12 ordered comparisons' quality
vectors, means, and 2,000-replicate bootstrap intervals. Analysis rerun preserved
all 54 preexisting run files. Final evidence is inventoried by
`closeout_artifact_manifest.json`, leaving the original pre-review manifest
unchanged. Full test output and the repeatable independent audit are in the
run's `verification/` directory.
