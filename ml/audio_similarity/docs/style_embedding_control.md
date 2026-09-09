# Frozen Discogs latent-embedding control

The owner confirmed that the three questioned recordings are intended. The confirmation is recorded in `reports/style_source_audit/owner_resolution_v1.json`; historical source-audit files are unchanged. Byte identity checks passed for all 24 reviewed tracks, and fresh inference reproduced three outliers exactly.

This experiment tests one non-learned alternative: the **same installed Discogs-EffNet checkpoint**, using its 1280-dimensional latent output rather than its 400 sigmoid style scores. It does not download or train another model, tune a similarity function, fuse representations, generate reviews, or activate production behavior.

## Frozen rules

See `reports/style_embedding_control/v1/protocol.json` for the create-once contract. The full 100-track corpus and existing three grouped folds are reused. Full retained audio is losslessly decoded to float32 PCM, downmixed/resampled by Essentia to 16 kHz, and passed through the same 128-frame, 62-hop, repeated-final-patch pipeline. Each track must return exactly the number of patches in the prior classifier extraction.

The worker changes the predictor's output to `PartitionedCall:1`. It computes a float64 arithmetic mean of the **raw** patch embeddings, then L2-normalizes that song mean once. No per-patch normalization, fitted scaler, projection or supervision is used. Similarity is cosine.

Comparators are the frozen 400-label `1 - JS divergence`, exact Arm D cosine, and C cosine. Primary evidence is playlist-compatibility ordinal preference agreement, macro-averaged by anchor over the same grouped development holdouts. Strong preferences, separate holistic ratings, all-pair bad-versus-good discrimination and exclusion of the three alias cases are sensitivities. Unrated pairs never become negatives.

The 0.03 material-improvement threshold and descriptive 95% paired anchor bootstrap are frozen. Shared candidates, three folds, prior exposure and one reviewer limit inference. Owner confirmation establishes intended recordings, not independent artist-alias verification; the exclusion sensitivity addresses that remaining metadata uncertainty without shrinking extraction.

## Run

From `ml/audio_similarity`, using the already installed isolated environment. `prepare` initializes a new frozen run once; it is not the resume command. For the already prepared run, resume extraction directly, or use `--replay` after completion:

```bash
PYTHONPATH=src .venv/bin/python -m audio_similarity.style_embedding_control prepare
CUDA_VISIBLE_DEVICES=-1 TF_NUM_INTRAOP_THREADS=1 TF_NUM_INTEROP_THREADS=1 OMP_NUM_THREADS=1 TF_DETERMINISTIC_OPS=1 PYTHONPATH=src artifacts/style_prior_pilot/env/bin/python -m audio_similarity.style_embedding_extract
CUDA_VISIBLE_DEVICES=-1 TF_NUM_INTRAOP_THREADS=1 TF_NUM_INTEROP_THREADS=1 OMP_NUM_THREADS=1 TF_DETERMINISTIC_OPS=1 PYTHONPATH=src artifacts/style_prior_pilot/env/bin/python -m audio_similarity.style_embedding_extract --replay
PYTHONPATH=src .venv/bin/python -m audio_similarity.style_embedding_control evaluate
.venv/bin/python -m pytest -q tests/test_style_embedding_control.py
.venv/bin/python -m pytest -q
```

Cache identity includes source, model, metadata, full frozen protocol, worker implementation, serialization, Python/NumPy/Essentia and native binary identity, FFmpeg, and the required CPU environment. Replay fails on a missing cache entry rather than running inference. Numbered ledgers retain original executions; incomplete extractions publish explicit failures and no aggregate features.

## Interpretation limits

A better latent result would justify investigating the latent representation, not prove a production win. The comparison changes both the model output and the distance function; it cannot separate loss in the classification head from the choice of Jensen–Shannon versus cosine. Comparing with CLAP also changes frontend and coverage. Standalone superiority does not establish incremental value when fused with CLAP.

`COMPLEMENTARY_CANDIDATE_DEVELOPMENT_ONLY` means a candidate for a future complementarity test, not demonstrated complementarity. All C results must remain visible even if a comparison with D is favorable. The known diagnostic songs and newly reviewed pairs are developmental explanations, not fresh confirmatory evidence.
