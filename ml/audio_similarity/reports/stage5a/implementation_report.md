# Stage 5A — Audio Representation v1 materialization

Status: **implementation and FMA Small parity complete; FMA Large validation pending local audio**

The full FMA Large cold start has **not** run. Stage 5B has **not** begun.

## Frozen downstream contract

- Authoritative artifact: `reports/holistic_stage4a_dual/audio_representation_v1.json`
- Artifact SHA-256: `ea6fb8f71c9de262460233802ad655298c3dd61e8f0ef53c93ed87aed5a77533`
- Vector contract SHA-256: `c85855d7a737bdecc91dd4629fa4e9baa48427135ae2764c9aabe3c74b89a623`
- Representation: `audio-representation-v1`
- Canonical audio: 30-second FMA unit, mono, 24 kHz
- Sampling: `UNIFORM3_DUAL_MEAN`, centers `[5, 15, 25]`, 5-second windows
- Aggregation: L2-normalize segments, mean per encoder, L2-normalize each pooled vector
- Stored encoders: independent 512-dimensional float32 CLAP and MuQ vectors
- Retrieval weights: CLAP `0.7172981519`, MuQ `0.2827018481`

The Stage 2B scientific conclusion remains `SINGLE_ENCODER_WINS / CLAP`. This implementation consumes the later frozen CLAP + MuQ engineering/product decision and does not alter the historical conclusion.

## Reused and generalized infrastructure

The implementation directly reuses:

- `stage4a_sampling.py` for decode, mono/24 kHz canonicalization, the 29.5-second eligibility boundary, sample-exact frozen windows, and canonical PCM hashing.
- `holistic_encoders.py` for the existing LAION-CLAP and MuQ-MuLan-large adapters.
- `stage4a_dual_scoring.normalized_mean` for the exact frozen per-encoder aggregation operation.
- `manifest.py` for deterministic FMA discovery, source hashing, audio probing, and official metadata loading.
- The Stage 4 CLAP and MuQ segment caches plus the frozen K=3 aggregate artifact as the parity oracle.

New production-facing components are deliberately separate from historical Stage 4 evidence:

- `stage5a_contract.py`: strict source-of-truth loading and vector-affecting contract identity.
- `stage5a_cache.py`: arbitrary-corpus, provenance-bound SQLite work state.
- `stage5a_materialize.py`: failure-isolated segment/encoder/track orchestration.
- `stage5a_dataset.py`: deterministic, atomic, sharded Parquet materialization.
- `stage5a_manifest.py`: complete FMA Large source/metadata accounting and bounded deterministic smoke selection.
- `stage5a_parity.py`: cache-only independent CLAP/MuQ parity validation.
- `cli/stage5a.py`: manifest, parity, and bounded (maximum 500 tracks) real-model smoke commands.

Historical Stage 4 caches and reports are neither modified nor deleted.

## Work-cache schema

Schema version: `stage5a-work-cache-sqlite-v1`.

The SQLite cache uses WAL mode and commits each completed segment. Its tables are:

- `cache_metadata`: explicit schema version.
- `segments`: one `SUCCESS` or `FAILED` row per encoder analysis identity and center, including exact sample bounds, vector/hash, failure category/detail, retryability, attempts, and timing.
- `pooled`: one independently pooled encoder vector per encoder analysis identity.
- `tracks`: representation-level `SUCCESS` or `FAILED`; a track is successful only when both pooled vectors exist and validate.

The encoder analysis identity binds corpus/version, stable track ID, source audio SHA-256, canonical PCM SHA-256, representation/preprocessing/sampling/aggregation versions, exact centers, dtype/dimension, encoder identity, and encoder provenance hash. A future vector-affecting change therefore misses the old cache.

Failures never create successful zero vectors. Categories include decode, invalid/short audio, source identity, CLAP inference, MuQ inference, invalid embedding, and final materialization errors.

## Final representation schema and sharding

Schema version: `audio-representation-dataset-v1`.

Each success row contains corpus/version, stable track identity, source and canonical hashes, representation/artifact/vector-contract identities, preprocessing and sampling versions, exact centers, aggregation version, frozen similarity weights, independent encoder analysis identities and provenance JSON, independent fixed-size float32 embeddings with their SHA-256 hashes and dimensions, status, representation identity, and materialization timestamp.

Rows sort by `(corpus, corpus_version, stable_track_id, representation_identity)`. The default bounded shard size is 10,000 rows. Files are named `part-00000.parquet`, use Zstandard compression, and are accompanied by `dataset_manifest.json` with counts, shard bounds, and SHA-256 hashes. Output replacement is atomic. No pairwise similarities or fused opaque vectors are stored.

## FMA Small parity hard gate

Artifact: `reports/stage5a/fma_small_parity.json`

- Tracks: 7,994
- Frozen method: `UNIFORM3_DUAL_MEAN`
- Centers: `[5, 15, 25]`
- CLAP maximum absolute error: `0.0`
- CLAP minimum cosine: `0.9999998807907104`
- MuQ maximum absolute error: `0.0`
- MuQ minimum cosine: `0.9999998807907104`
- Tolerance: `2e-6`
- Result: **PASS** independently for CLAP and MuQ

This validation pooled the frozen Stage 4 center vectors through the Stage 5A aggregation path and compared all available tracks with the frozen Stage 4 K=3 aggregate artifact. It performed no model inference and did not rerun or redesign Stage 4.

## Resume, idempotency, failure, and tests

The focused fixture validation interrupts after two persisted CLAP segments. On restart, those two segments are reused; only the remaining CLAP segment and three MuQ segments execute. A third completed run performs zero encoder calls, emits no duplicate rows, preserves the representation identity, and produces byte-identical dataset artifacts.

A deterministic MuQ per-track failure does not stop another track. The failure remains explicit and retryable; retry reuses the completed CLAP work and computes only the unfinished MuQ work. Invalid, zero, non-finite, or wrong-dimensional vectors are rejected.

Executed results so far:

- Focused Stage 5A: 14 passed.
- Relevant audio/sampling/encoder/cache/manifest regressions: 92 passed.
- Full non-heavy suite after pushing the implementation checkpoints: 461 passed, 12 deselected, 0 failed. The 12 deselected tests are explicitly marked heavy tests excluded by the repository's default pytest configuration.

## FMA Large manifest and smoke

The official FMA metadata is present locally, but no FMA Large audio directory or archive is currently available under the local data tree or searched host storage roots. Accordingly:

- FMA Large eligible count: **pending acquired corpus**
- FMA Large manifest identity/hash: **pending acquired corpus**
- Smoke requested count: approximately 100, bounded to at most 500 by the CLI
- Smoke success/failure categories: **pending acquired corpus**
- CLAP, MuQ, and total throughput: **pending acquired corpus**
- Smoke cache/resume/idempotency and shard hashes: **pending acquired corpus**

The manifest builder will account for every official metadata identity plus every discovered source identity. It derives eligibility from the acquired files and explicitly reports missing audio, duplicate source IDs, decode failures, too-short audio, and missing metadata. It does not hard-code 100,000 or 106,574 as the acquired-corpus denominator.

No FMA Large smoke was substituted with FMA Small, and the full FMA Large cold start was not run.

## Commands

From `ml/audio_similarity`:

```bash
uv run python -m audio_similarity.cli.stage5a parity

uv run python -m audio_similarity.cli.stage5a manifest \
  --audio-root /path/to/fma_large \
  --corpus-version fma_large_2017

uv run python -m audio_similarity.cli.stage5a smoke \
  --audio-root /path/to/fma_large \
  --count 100
```

The smoke command verifies the local CLAP checkpoint and MuQ weight/config hashes against Audio Representation v1 before loading either frozen model.
