# Complete original-corpus Method C materialization

Feature precomputation only. This run does not perform ranking calibration or
select weights, representations, or admission thresholds.

The frozen input is the original 28-playlist acquisition manifest: 2,032
recording requests, 1,927 retained-source completions resolving to 1,924 distinct
stored recording IDs, and 105 unavailable requests. The separately processing
1,169-request extension is excluded. All request memberships and duplicate
request-to-recording aliases remain in the private corpus manifest.

## Exact representation

`method_c_full_song` uses the existing HTSAT-base LAION-CLAP adapter with
`music_audioset_epoch_15_esc_90.14.pt`, checkpoint SHA-256
`fae3e9c087f2909c28a09dc31c8dfcdacbc42ba44c70e972b58c1bd1caf6dedd`.
Full retained audio is decoded to mono at 48 kHz, divided into consecutive
480,000-sample chunks, and passed through the existing adapter. The actual
short tail is passed to LAION's native repeat-padding path. Every chunk receives
equal weight; normalized chunk vectors are averaged and L2-normalized using the
existing float64 pooling helper, with a float32 result. There is no centered30
or MuQ inference in this worker.

The isolated cache records source, checkpoint, implementation, package,
configuration and vector hashes. Completed chunks survive interruptions.
Per-invocation ledgers are append-only directories; replay creates a separate
receipt and does not replace original execution records. Call reservations
record attempted inference, including attempts that fail before a vector is
committed. Missing or incompatible input fails closed.

## Commands

Run from `ml/audio_similarity`. The final complete run is the GPU continuation;
the original CPU directory remains an immutable input to it. All model files
must already be local.

```bash
export METHOD_C_RUN_DIRECTORY=.research_audio/playlist_calibration_method_c_gpu_v1
export METHOD_C_DEVICE=cuda:0
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python -m audio_similarity.calibration.method_c_full_worker --replay
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python -m audio_similarity.calibration.method_c_full_verify
```

`--replay` refuses missing features and cannot instantiate an encoder for them.
The verifier checks the completed manifest without new inference. To resume an
interrupted GPU extraction, use the same environment and worker command without
`--replay`; it holds an exclusive lock and preserves completed chunks. Do not
use the updated default worker to resume the archived CPU configuration.

Matrix rows follow the explicit sorted recording-ID sidecar, with row-order and
ordered-source hashes. A second finalization must reproduce the same NPY bytes.
Common-population IDs require exact-source centered30, MuQ and Gemini profiles;
usable specific-style membership is counted separately from profile presence.
Unknown or unmapped genre evidence is not fabricated.

Final private artifacts reside in
`.research_audio/playlist_calibration_method_c_gpu_v1/`:
`corpus.json`, `reuse_manifest.json`, `configuration.json`, `features/`,
`chunks/`, `sampling/`, `invocations/`, `companion_features.json`,
`readiness.json`, `matrices/`, `verification.json`, and `artifact_manifest.json`.
The preserved CPU run is `.research_audio/playlist_calibration_method_c_full_v1/`;
handoff, parity/extraction logs and final test logs are under
`.research_audio/playlist_calibration_method_c_handoff_v1/`.

Historical experiment directories and source audio remain immutable inputs.
Source hash verification establishes linkage to retained auto-selected audio;
it does not assert owner listening verification for every recording. Source-use
and split feasibility remain separate from feature readiness. No extension
processing state is frozen or modified by this worker.

## Preserved sampling edge case

The existing shared Stage 5E.1 plan constructs native-fusion metadata as well as
Method C chunk boundaries. A synthetic recording just one sample longer than
10 seconds raises `native fusion thirds are empty` before inference. This run
preserves that explicit failure rather than silently changing the historical
sampling helper. The worker records such failures; it never writes a pooled
vector from incomplete chunks. The interruption/resume test uses a 10.1-second
fixture to exercise the valid two-chunk path separately.

## Authorized GPU continuation

The owner requested switching to GPU after acquisition really exits. Run the
read-only gate on the host where the acquisition PID and NVIDIA device are
visible:

```bash
.venv/bin/python -m audio_similarity.calibration.method_c_handoff
```

It requires all extension batches to be terminal, no matching acquisition
process, and at least 5,000 MiB free VRAM. Estimates never satisfy this gate.
The CPU implementation was archived byte-for-byte in `implementation_snapshot/`
before adding GPU orchestration. The active CPU process continues executing that
original implementation. Its completed features and ledgers remain immutable.
If a manual CPU resume is needed after that process exits, use
`method_c_continuation.resume_original_cpu(root, limit=...)`; the ordinary worker
now represents the updated runtime-aware implementation and will correctly
refuse the original CPU configuration identity.

The handoff freezes a separate continuation directory with the same corpus and
companion features. `method_c_continuation.prepare` requires the CPU worker lock
to be free, validates completed CPU views and hashes, and records an immutable
import receipt. It does not add extension recordings. GPU configuration and
feature identities explicitly differ by runtime/implementation provenance;
checkpoint, segmentation, native tail handling, normalization and pooling stay
unchanged.

For a prepared continuation in
`.research_audio/playlist_calibration_method_c_gpu_v1`:

```bash
METHOD_C_RUN_DIRECTORY=.research_audio/playlist_calibration_method_c_gpu_v1 METHOD_C_DEVICE=cuda:0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python -m audio_similarity.calibration.method_c_gpu_parity
METHOD_C_RUN_DIRECTORY=.research_audio/playlist_calibration_method_c_gpu_v1 METHOD_C_DEVICE=cuda:0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python -m audio_similarity.calibration.method_c_full_worker
```

Parity uses the first three sorted CPU-computed recordings and their unique
first/middle/final chunk indices. Before any GPU inference, the plan freezes
maximum absolute component error `1e-4` and minimum cosine `0.999999`. TF32 is
disabled. These are engineering consistency checks, not scientific evaluation.
Their calls are recorded separately from materialization, and cached parity
outputs are reused. An unresolved parity attempt requires investigation rather
than a silent retry. A failed parity gate prevents GPU extraction.

## Diagnosed CPU resume precision issue

The initial worker converted cached float64 normalized chunk vectors to float32
when resuming a partial song. Strict continuation validation caught this in one
CPU-drain track before any GPU inference. Eleven resumed chunks matched exactly
the float32 casts of their original vectors; the largest component change was
`6.658418705285385e-09`. The newly inferred final chunk was unchanged.

The original pooled artifact and all chunk files/ledgers remain intact. An
explicit, hash-bound `cpu_resume_repool_authorization.json` permits reconstruction
of that one pool from the unchanged original float64 chunks using the same
`normalized_mean` helper, with zero inference. The continuation records the
repair. Unknown discrepancies still fail closed. The current worker preserves
float64 chunk values when resuming; a nontrivial float64 fixture reproduces the
old failure and verifies the corrected resume behavior.
