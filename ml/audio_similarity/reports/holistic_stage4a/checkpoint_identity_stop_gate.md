# Stage 4A checkpoint identity stop gate

## Status

`STOP — frozen provenance contradicts the validated Stage 2B embedding artifact`

No Stage 4A retrieval scoring or human labels have been generated.

## OBSERVED evidence

The Stage 2B YAML and amended Stage 4A freeze declare:

```text
models/630k-audioset-best.pt
SHA-256 8053c9775516af2f4902e1e8281e356cc1bf7a85e8b761908170767b77c3f037
```

However, the immutable Stage 1A encoding CLI that produced the reused Stage 2B CLAP artifact has always loaded:

```text
models/music_audioset_epoch_15_esc_90.14.pt
SHA-256 fae3e9c087f2909c28a09dc31c8dfcdacbc42ba44c70e972b58c1bd1caf6dedd
```

Evidence:

- `git blame 57bc409 -- src/audio_similarity/cli/encode_holistic.py` attributes lines 33–35 to original commit `0fe0397`; those lines select `music_audioset_epoch_15_esc_90.14.pt`.
- Both checkpoint files predate `artifacts/holistic_stage1a/laion_clap.parquet`, so the CLI fallback cannot explain the difference.
- Loading `630k-audioset-best.pt` through the frozen `LaionClapEncoder` (`HTSAT-base`) fails with architecture/shape mismatches before inference.
- A controlled track-2 re-encode using `music_audioset_epoch_15_esc_90.14.pt` reproduced the stored Stage 1A vector:

```text
cosine(existing, regenerated) = 1.000000012229475
maximum absolute element difference = 7.162942100569225e-09
```

This proves the validated Stage 2B representation is the music-audioset checkpoint, while the Stage 2B provenance declaration names the other checkpoint.

## Required decision

The governing objective says to use exactly the validated Stage 2B representation. That implies correcting Stage 4A to the actually validated music-audioset checkpoint/hash. Doing so changes a currently frozen provenance invariant, so execution cannot make that correction silently.

Choose one explicit reframe:

1. **Correct provenance and continue (recommended):** amend Stage 4A checkpoint identity to `music_audioset_epoch_15_esc_90.14.pt` / `fae3e9...`, preserve Stage 2B metrics as the observed result of that actual representation, and refreeze Stage 4A before scoring.
2. **Enforce the declared 630k checkpoint:** define its compatible CLAP architecture, regenerate the baseline corpus, and acknowledge that this is not the representation that produced the Stage 2B verdict.

Rollback remains pushed commit `11a7fca`. The local segment-cache encoder work is preserved but no new inference was accepted.
