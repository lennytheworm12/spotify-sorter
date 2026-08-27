# Stage 2B LAION-CLAP checkpoint provenance erratum

**Recorded:** 2026-08-26  
**Scope:** provenance correction only; no metric, embedding, label, evaluator, or verdict change.

The frozen Stage 2B YAML incorrectly declared the LAION-CLAP checkpoint as:

```text
models/630k-audioset-best.pt
8053c9775516af2f4902e1e8281e356cc1bf7a85e8b761908170767b77c3f037
```

Repository history and exact regeneration establish that the CLAP artifact used throughout Stage 1A/2B was actually produced by:

```text
models/music_audioset_epoch_15_esc_90.14.pt
fae3e9c087f2909c28a09dc31c8dfcdacbc42ba44c70e972b58c1bd1caf6dedd
```

Authoritative evidence:

1. Original commit `0fe0397` hard-codes `models/music_audioset_epoch_15_esc_90.14.pt` in `src/audio_similarity/cli/encode_holistic.py`.
2. Both local checkpoint files existed before `artifacts/holistic_stage1a/laion_clap.parquet` was generated, so fallback behavior did not select another checkpoint.
3. Re-encoding FMA track 2's exact `center5_v1` PCM with the music-audioset checkpoint reproduced the stored artifact vector:

```text
cosine(existing, regenerated) = 1.000000012229475
maximum absolute element difference = 7.162942100569225e-09
```

4. `630k-audioset-best.pt` cannot load into the frozen HTSAT-base adapter because its tensor shapes/architecture differ.

The original Stage 2B YAML remains unchanged as historical/auditable evidence. Stage 2B metrics and `SINGLE_ENCODER_WINS` remain valid because they were computed from the unchanged, reproducibly identified music-audioset embeddings. Stage 4A inherits the corrected actual checkpoint identity and must not use the 630k checkpoint.
