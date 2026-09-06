---
title: Goal — Stage 5E.3 Implementation and Frozen-100 Review Handoff
status: ready
created: 2026-09-06
project: Spotify Sorter
design_revision: 2
goal_scope: implementation-materialization-review-handoff
tags:
  - spotify-project
  - implementation-goal
  - audio-similarity
  - human-evaluation
---

# Goal — Stage 5E.3 Implementation and Frozen-100 Review Handoff

Parent: [[Spotify Sorter]]
Governing design: [[Spotify Audio Similarity Stage 5E.3 — Frozen-100 Full-Song MuQ Playlist Compatibility Benchmark Design]]

## Objective and stopping boundary

Implement the revision-2 Stage 5E.3 benchmark, materialize only missing full-song MuQ representations for the original amended frozen 100, and deliver a reproducible, globally blinded playlist-compatibility review queue using the existing local player infrastructure.

Implement and fixture-test the eventual analysis and deterministic verdict pipeline now, before new human outcomes are available. Stop this autonomous Goal at **READY_FOR_HUMAN_REVIEW** after engineering verification. Do not invent ratings, complete the human review, expose real method-quality results, or declare a representation winner.

This Goal completes the implementation/materialization/review-handoff slice, not the entire Stage 5E.3 scientific experiment. The experiment remains **AWAITING_HUMAN_REVIEW**. A later explicit analysis/closeout action consumes the completed frozen human snapshot. Do not write a final INCONCLUSIVE merely because the intended human-review boundary has been reached.

## Governing sources and repository starting point

Use the design in `lennytheworm12/obsidian-vault`:

`Projects/Spotify Sorter/Spotify Audio Similarity Stage 5E.3 — Frozen-100 Full-Song MuQ Playlist Compatibility Benchmark Design.md`

Reviewed revision: **2**, at vault commit `0b8970bb0aeba2d2a3f8bd49e80ad1693c69eb48`, file blob `137d6cdf91e9e132b2744b8d352bf070a4549ff5`. Revision 2 supersedes the original chat description, especially padding, full-track failure handling, reveal timing, label semantics, and verdict rules. Snapshot and hash the governing bytes locally. Check for a later explicit revision before preparing the run; never silently combine revisions.

The latest relevant pushed implementation branch observed during goal preparation was `ml/stage5f1-energy-motion` at `269ee29209b7732b154cef0717ddb95384f3973e`; `main` was still `53f29d35ad74ba301139b892cce3036bab385d47`. Inspect the actual local checkout, uncommitted changes, branch ancestry, and any newer implementation first. Reuse completed work rather than overwrite it. Work on a feature branch containing the required Stage 5E infrastructure; do not reset the checkout, merge to main, or discard unrelated changes.

Read and reuse the frozen Stage 5E.1 configuration, corpus, matrices and materialization provenance; the amended Stage 5C.2 original-100 membership and selected sources; Stage 5E.2 subset/label/review helpers; the existing `MuQMulanEncoder`; and the locked Python environment. Read project agent instructions before editing.

## 1. Freeze inputs before experiment inference

Create the Stage 5E.3 run under:

`ml/audio_similarity/reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v1/`

Verify exactly 100 original amended Spotify identities, selected video identities, and retained-source hashes. Restrict both query and candidate axes to those 100. Preserve all A/C/D and fixed centered30 MuQ definitions, vectors, weights, ranks in their historical artifacts, and historical labels. Existing ranks may be recomputed for the restricted universe only in new Stage 5E.3 outputs.

Record code, embedding-affecting environment, model revision/weight/config hashes, corpus and historical-artifact hashes. Resolve baseline sampling offsets from actual provenance; do not reinterpret centered30 offsets as necessarily the first 30 seconds of the recording. No model substitution or upgrade.

Freeze the algorithm, source-by-source label-compatibility decisions, shuffle seed, retrieval exclusions, pooling, evaluation rules, and output serialization before experiment inference/review. Develop numeric and verdict logic against separate synthetic fixtures, not by inspecting real method performance.

Make prepare create-once. Identical reruns verify without rewriting; changed inputs require a separately versioned run. Missing or changed sources are explicit blockers, not authorization to download or reduce the corpus.

## 2. Implement full-song MuQ exactly as revision 2

Decode/resample the full retained source to mono float32 at 24,000 Hz using the recorded existing decoder/downmix/resampler convention. Do not call the historical 30-second truncation path, trim silence, or add loudness normalization.

Use integer sample indices, chunk length and stride **240,000 samples**. Cover the whole recording with consecutive nonoverlapping chunks. Externally cyclically repeat-pad only the final partial chunk's own samples: `padded[j] = chunk[j % len(chunk)]`. Every forward receives exactly 240,000 samples. Do not delegate padding to MuQ or pull padding samples from the start of the song. Empty/nonfinite audio fails explicitly.

Require each output to be finite, shape `(512,)`, with float64-computed norm above `1e-12`. Normalize each chunk, equally average every scheduled normalized chunk including the padded tail, and normalize the mean with the same norm floor. Use float64 normalization/accumulation and float32 stored vectors. Verify cosine symmetry/self-similarity within `1e-6` and clip only floating-point overshoot.

All scheduled chunks must succeed. One failed chunk invalidates the pooled track vector; retain successful chunks for recovery but never pool a surviving subset. Implement the design's exact status enum, failing-chunk diagnostics, and null invalid outputs. Require **100/100 OK** before retrieval/review preparation.

Reuse the installed cached model and valid existing embeddings. The only newly authorized encoder computation is missing full-song MuQ for these 100, including a tiny local smoke check whose compatible results are reused. Never rerun CLAP, historical MuQ, other encoders, or the 741-track materialization.

Persist chunk vectors, track vectors, interval/padding metadata, source/model provenance and failure evidence atomically. Keep the original execution ledger immutable; cache reruns get separate numbered ledgers. Prove an identical replay yields 100 track-cache hits, zero new MuQ forwards, and unchanged scientific outputs. Report inference counts, runtime, memory and storage as diagnostics without inventing new scientific gates.

## 3. Build the four frozen methods

Use cosine similarities and weights `wC = 0.7172981519`, `wM = 0.2827018481`:

```text
M1_C_CLAP             = C
M2_FULL_MUQ           = full-song MuQ
M3_C_PLUS_FIXED_MUQ   = wC * C + wM * historical MuQ
M4_C_PLUS_FULL_MUQ    = wC * C + wM * full-song MuQ
```

M4 versus M3 is primary. Preserve A and D as reference baselines without expanding the new review to their extra retrievals. C remains an experimental control, not a validated winner. This compares MuQ representation policies: coverage, 5s-to-10s input context, and aggregation all change. Do not claim isolated coverage causality.

Rank eligible candidates with identical self/source-SHA/video-identity exclusions and Spotify-ID ascending tie-breaking. Freeze natural Top-5 lists, union membership, per-method ranks/scores, and matrices before review. Shared ratings support every method that naturally retrieved the pair, but are not independent duplicate judgments.

## 4. Reuse labels and schedule the blinded review

Audit exact historical prompts, scales and identity provenance. Tag accepted old labels `HOLISTIC_SIMILARITY` and new labels `PLAYLIST_COMPATIBILITY_V1`. Ambiguous semantics become `SEMANTICS_UNRESOLVED`; incompatible FMA/identity-SAFE labels are excluded. Deduplicate derived exports against original evidence. Conflicting numeric labels require review, not automatic averaging or newest/highest selection.

Freeze the pre-run positive bank at rating >=4 and negative bank at <=2. Per anchor add up to one of each outside the natural four-method Top-5 union, selected deterministically. These are blinded repeat/drift probes even when a historical numeric label exists, including for anchors with no unresolved natural candidates. Forced inclusion never counts as natural retrieval recovery or recurrence. Keep the original positive bank fixed despite revisions.

Use seed `20260906`. Deduplicate reciprocal unordered pairs globally, with one assigned presentation in frozen anchor order; retain all directional retrieval memberships. Preserve old labels and append repeats/revisions with provenance. Primary label selection and original-label sensitivity must follow revision 2.

Present the exact question and 1–5/UNSURE rubric in design Section 8. UNSURE remains nonnumeric. Serve full retained recordings, paused at time zero, with seeking and identical gain behavior. Log playback diagnostics without imposing a minimum listening duration.

Submit anchor packets atomically. Keep methods, scores, ranks, historical ratings, probe identities and shared-method membership server-side and inaccessible through reviewer payloads, assets, URLs, debug data or endpoints. **No reveal after an individual submission: reveal only after the entire review and post-review label snapshot are frozen.** Test this across reloads, later packets and reciprocal pairs.

The frozen queue requires one complete pass. Adequacy gates are not early-stop triggers; do not repeatedly requeue UNSURE to force numeric coverage.

## 5. Implement analysis and closeout, but exercise them on fixtures now

Implement design Sections 13–18 exactly: coverage; complete-anchor unacceptable/coherent/mean/median metrics; historical-positive recovery; known-bad recurrence; overlap; missing-rating bounds; paired deltas; and every stability check.

Keep the required 80% numeric coverage for all four methods, 90% for M3/M4, >=40 complete paired anchors for verdict comparisons, >=30 positive-bank anchors, and all other Section 13 support gates. Unknown data never passes a predicate.

Use the specified 2,000 paired anchor bootstrap replicates, PCG64 seed, eligible-ID ordering, percentile interpolation, leave-one-anchor-out, no-backfill track-node deletion, and original-label sensitivity. Acknowledge selected mixed-label/owner-specific evidence and residual shared-candidate dependence.

Implement Section 18's exact `ACCEPT`, `GAIN`, `STABLE`, `ROBUST_WIN` predicates and ordered five-verdict precedence; do not replace them with a highest-average heuristic. Test every verdict branch, overlapping predicates, equality boundaries, nulls, missing data, and insufficient sensitivity support before outcomes are examined.

Gate real analysis/reveal/closeout behind completed review and frozen labels. `run-all` must stop at the human boundary instead of treating missing ratings as completion. Make scientific closeout create-once and version changes. Do not create placeholder final-metric/closeout files that could be mistaken for evidence.

## 6. Verification and artifacts

Run the existing non-heavy suite in the locked environment and all new targeted tests. Keep heavyweight tests explicit and limited to this authorized MuQ scope; never run unrelated model-download tests. Add real Chromium validation of playback, seek/HTTP Range, pagination, packet submission, persistence, restart/resume, and global blinding. Use an isolated fixture run for browser test ratings; never inject them into the real queue.

Cover empty/one-sample input; sample counts immediately around chunk boundaries; norm/NaN/shape failures; mid-song inference failure; historical integrity; both-axis restriction; duplicate accounting; probe exclusion from retrieval metrics; append-only revisions; immutable prepare/ledgers; deterministic NPZ/JSON/Parquet output; and all decision branches.

Produce all artifacts applicable before human review from design Section 25, plus preparation/engineering verification and a clear review handoff. Document post-review artifacts as pending rather than fabricate them. Use deterministic serialization, a manifest excluding itself, and post-write hash verification. Keep audio, model weights, private mutable review state and hidden reviewer keys outside public Git/reviewer assets. Preserve research inputs byte-for-byte.

Commit and push coherent tested implementation milestones on the working feature branch. Update a separate progress/handoff note with source links and evidence; do not rewrite the governing design or historical reports to make implementation pass.

## Acceptance and final handoff

Report **READY_FOR_HUMAN_REVIEW** only when the verified full-100 representation, cache replay, four-method rankings, deterministic unresolved/probe queue, analysis fixtures, real-browser checks and input-integrity checks all pass.

If a prerequisite fails, report the exact blocker and completed evidence; do not simulate full-100 success or open a reduced review. Use the installed workflow's supported status mechanism rather than inventing a new tool enum.

Return the actual branch/commit, governing design hash, test commands/results, 100-track status, chunk/forward/cache counts, original and replay ledgers, four-method slot counts, global unique pairs, compatible reused labels, unresolved/conflicted pairs, drift repeats, artifact locations, and exact working commands to launch/resume review and later snapshot/analyze/close out.

Explicitly state: **engineering handoff complete; human review and representation recommendation pending; no production activation**.

## Out of scope

No new source acquisition or searches, Spotify calls/writes, model downloads/substitutions, fusion tuning, new MIR/lyric features, cluster algorithm selection, cluster-admission implementation, 741-track review expansion, main-branch merge, or production pointer change. Do not resume Stage 5F attribute work inside this Goal. Do not declare Stage 5E.3 scientifically complete before its genuine human-review and closeout requirements are met.
