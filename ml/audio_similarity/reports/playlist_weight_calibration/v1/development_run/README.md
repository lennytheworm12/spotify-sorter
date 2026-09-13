# Personal development calibration run

This is an isolated execution of the existing ranking-calibration harness on
fixed source-playlist samples. It does not change production rankings, playlist
contents, strictness policies, historical reports, or frozen model artifacts.

The owner authorized steps 1–4 (cache repairs, fixed sampling, missing features,
grouped development comparison) after the audit. The owner separately authorized
283 metadata-stripped full-recording uploads to Google's Gemini API, capped at
$5. Source-use documentation remains **PENDING**; this personal development run
does not assert permission clearance or formal confirmatory readiness.

## Fixed inputs

- Original audit: `../corpus_audit/`.
- Run directory, relative to `ml/audio_similarity`:
  `.research_audio/playlist_calibration_development_v1/`.
- Ten original source playlists, eight credited curator/duplicate groups.
- Preserve the audited 30-member deterministic samples; no replacement of
  unavailable recordings. The 298 distinct sampled requests yield 284 available
  recordings after 14 documented acquisition/manual-tail exclusions.
- The two stale source links are Thirsty (aespa) and Sour Grapes (LE SSERAFIM).
  Sour Grapes is outside the sample and is repaired separately: 285 audio-cache
  records in total. Original provenance and caches are never overwritten.
- At least 20 surviving sampled members per playlist are required for this
  development run. This explicitly differs from a complete 30-member sample.

The CLAP methods retain the existing `centered30_v1` and Method C contracts.
The legacy centered30 name describes the existing three-window representation;
the actual window spans and source hashes, rather than the name alone, define
its identity. Method C uses consecutive 10-second chunks of the full retained
recording and the existing native final-window handling. MuQ remains the existing
centered30 representation. CPU extraction uses two Torch threads while the
separate acquisition worker continues independently.

Gemini uses the unchanged frozen100 free-genre prompt and schema,
`gemini-3.8-flash`, LOW thinking, the original sampler settings and an
8,192-token output bound. One compatible prior profile is reused. There are no
automatic generation retries. Operational/schema/accounting failures stop the
run for inspection; they are not silently repaired or replaced. No identities,
playlist names, source strata, expected styles or human ratings are sent.

## Frozen comparison

`search_protocol.json` freezes the grouped splits and implementation hashes before
real tuning. Three outer folds each contain two inner folds. Each playlist uses
eight deterministic 80/20 masks; these are repeated queries, not independent
sources. Candidate catalogs contain all evaluation recordings in each fold,
excluding seed/duplicate versions, and are identical across configurations.

The documented grid has 880 nominal combinations, 792 after inactive eta
deduplication, and 756 after inactive CLAP-representation deduplication. The exact
M3 recipe and its genre additions bring the shared registry to 792 unique
configurations across 14 ablation arms. On new recordings, the fixed
`.7172981519 * Method C + .2827018481 * centered30 MuQ` recipe is materialized
as a new research matrix; it does not pretend to be a historical frozen100 score.

Selection retains the existing one-standard-error simplicity rule and the
Recall@20 guardrail against the same representation/rho audio comparator with
genre terms zero (tolerance .02). Bootstrap uses 2,000 curator/duplicate-cluster
draws, seed 1701. Complete pair scores are combined before Top-3 support selection.
Nonmembers remain **unlabeled**, not negative suitability judgments.

Inner ledgers include all model configurations, per-query/fold/stratum metrics,
uncertainty and selection/rejection reasons. NPY score and rank files preserve
every candidate ranking in a shared model/query index. Outer folds estimate each
predeclared selection procedure; they do not select a winning model family.
There is no lockbox, suitability fit, admission cutoff or production winner.

## Commands

From `ml/audio_similarity`:

```bash
.venv/bin/python -m audio_similarity.cli.playlist_calibration_development status
.venv/bin/python -m audio_similarity.cli.playlist_calibration_development audio
.venv/bin/python -m audio_similarity.cli.playlist_calibration_development profiles-run
.venv/bin/python -m audio_similarity.cli.playlist_calibration_development build
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m audio_similarity.cli.playlist_calibration_development tune
```

Run only one audio worker and one profile worker for this directory. Completed
audio entries and original execution ledgers are reused. The profile runner
verifies previous responses before proceeding, and its completed-run replay
makes zero API calls. A `STOPPED.json` means inspect the preserved failure before
continuing; do not delete the file to force a retry.

`build` requires a complete, validated common population. `tune` requires the
frozen feature bundle and verifies input and implementation hashes. It performs
no audio inference or API requests. Replays must reproduce artifact bytes.

No musical or ranking results are asserted by this README. Read the execution
closeout for actual completion counts and test/results evidence.
