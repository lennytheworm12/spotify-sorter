# Active chart-based download batches

This queue replaces the old Spotify genre-search batches for active work.
Historical Stage 5D.0A artifacts and completed downloads are not deleted.

Frozen input: the 534 matched Spotify recordings in the chart matching snapshot
referenced by `source_reference.json`. Pending/ambiguous matches are excluded.
The full popular-song catalog is not complete; this is its first matched cohort.

| Batch | Frozen tracks | Automatic continuation |
|---|---:|---|
| 0001 | 500 | None |
| 0002 | 34 | None |

`artifact_manifest.json` pins the input reference, cohort, and batch hashes.
Preparing again is idempotent; changed input or batch size cannot replace the
freeze. Matching more songs does not silently change these batches.

## Run overnight

From the existing research checkout:

```bash
cd ~/PersonalProjects/spotifyProject/ml/audio_similarity
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -m audio_similarity.cli.stage5d0a resume --batch 1
```

`resume` works for both first start and restart. It runs Batch 0001 only, then
stops. Existing completed cache entries are validated and reused. Keep the
terminal open, or run inside your own terminal multiplexer session for overnight
use. This setup did not start the worker. The direct module
`audio_similarity.chart_download_batches` accepts the same commands.

In another terminal:

```bash
.venv/bin/python -m audio_similarity.cli.stage5d0a status --batch 1
.venv/bin/python -m audio_similarity.cli.stage5d0a stop --batch 1
```

Stop is graceful and may wait for the bounded current operation/local inference.
The stop flag is shared across chart batches: it stops the active chart worker.
Only `resume` clears a requested stop; it never clears an open circuit.
Start Batch 0002 only with a separate explicit `resume --batch 2` command.

## Behavior

- Serial network jobs; randomized 30–60 seconds between ordinary job starts.
- Existing bounded retries and Retry-After handling; longer cooldowns take priority.
- First YouTube 429: substantial cooldown. Second: open circuit and stop.
- Verification/challenge and broad provider failures preserve existing circuit rules.
- Shared provider state across chart batches; changing batch number cannot reset it.
- Frozen selector-aware discovery and Stage 5B.3 selector; no manual substitutions.
- Full compressed source retained locally with provenance; only scratch is deleted.
- Frozen centered30_v1 CLAP/MuQ inference when missing; valid cache entries reused.
- No automatic next batch and no batch-wide retry of terminal manual-tail failures.

At 45 seconds per uncached job start, 500 jobs imply roughly 6.25 hours of pacing;
local inference, transfer time, and backoff can increase runtime. Cache hits can
reduce network work. This is not a guarantee of overnight completion.

Runtime: `.research_audio/chart_download_batches_v1/batch_0001/` (or `batch_0002`).
Shared provider log/circuit: `.research_audio/chart_download_batches_v1/provider/`.
Retained media and representation caches are the existing shared caches, not new
copies of the corpus. Runtime state and media remain Git-ignored.

## Offline readiness

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -m audio_similarity.cli.stage5d0a preflight --batch 1
```

This checks frozen manifests, media Git-ignore coverage, ffmpeg/ffprobe, and the
CLAP/MuQ checkpoint hashes. It does not search, download, or run encoder inference.
Preflight passed on the owner's environment during setup. Both queues were
`NOT_STARTED` afterward.

## Review

The five-axis review preserves runtime behavior through shared worker reuse,
validates snapshot and batch identities before execution, keeps provider safety
state across batches, and isolates the chart queue from historical artifacts.
Deterministic mock tests exercise batching, cache resume, one-batch stopping,
ambiguity exclusion, tamper rejection, and the old-circuit guard. Existing worker,
processor, network pacing, and retry tests exercise the reused implementation.
