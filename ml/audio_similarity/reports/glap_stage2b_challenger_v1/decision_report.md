# GLAP Stage 2B Historical Challenger Closeout

## Decision

`GLAP_REJECTED_AS_GLOBAL_CHALLENGER`

On the frozen held-out TEST queries, GLAP reached 0.5479 query-macro agreement versus 0.7719 for LAION-CLAP. The paired difference was -0.2240 with a 95% query-bootstrap interval of [-0.3760, -0.0646]. The interval is entirely below zero, 12 of 16 TEST queries favored LAION-CLAP, and GLAP created 19 TEST errors while rescuing 3 LAION-CLAP errors.

This result does not modify the historical Stage 2B verdict. Stage 2B remains `SINGLE_ENCODER_WINS / CLAP`.

This result does not modify Audio Representation v1. It remains LAION-CLAP + MuQ-MuLan-large with K=3 at [5, 15, 25] seconds and the frozen engineering weights.

## Research question and claim boundary

Primary question:

> Does GLAP agree with the existing Stage 2B human similarity choices at least as well as the validated LAION-CLAP representation?

For this frozen evidence, no.

The evidence is the existing single-reviewer personal perceptual-alignment benchmark. It is not a population-level human-consensus result, a general music benchmark, or a purpose-built multilingual benchmark.

## Frozen contract and model provenance

- Experiment: `glap_stage2b_challenger_v1`
- Pre-outcome contract SHA-256: `1895ac7bc91d7ef718f58fc0000112cc096ec07aabe6ad145c6232e545b3b708`
- Official repository: `https://github.com/xiaomi-research/dasheng-glap`
- Repository revision: `8b323fa057cd1afe8771da8d828dfe244d33fa98`
- Model: `mispeech/GLAP`
- Model revision: `79b13014511e2d5628cb57c4712a90edd19cebbd`
- Model SHA-256: `ee8fd92bba30d03b4c31c624739b1599a222506f0e045cde7cb51c34e3223864`
- Executable configuration module SHA-256: `9fb623f5be62e70967ecb8f8c8a49981313b28156b0a0fb4cdf51f4f07d88cb9`
- Model size: 3,422,036,400 bytes
- License recorded by the official repository/model card: Apache-2.0
- Input: 16 kHz mono, converted with `torchaudio.functional.resample` 2.6.0
- Output: 1024-D float32, L2-normalized
- Inference: eval mode, no gradients, float32, no autocast, deterministic cuBLAS workspace

The contract was committed and pushed before successful GLAP inference. Contract checkpoints were `9eb051e` and `2fa6b48`; deterministic CUDA execution was pinned at `4103f31` before the successful real-model smoke.

## Historical evidence audit

The challenger used the exact Stage 2B evidence:

- 240 frozen trials
- 157 eligible A/B judgments
- 64 `Tie` exclusions
- 19 `Neither` exclusions
- 67 / 31 / 59 eligible TRAIN / VALIDATION / TEST comparisons
- 40 frozen queries; 16 TEST queries
- 246 unique query/candidate audio tracks
- 246/246 source files present
- 246/246 source SHA-256 identities matched
- no frozen PCM identity contradictions

Audio was not replaced with Stage 4/5 sampling. For both encoders the musical evidence was the exact `pp-v1` 24 kHz mono `center5_v1` excerpt from 12.5 to 17.5 seconds (samples 300,000–420,000). GLAP alone received the model-required deterministic resampling to 16 kHz after the frozen excerpt was extracted and hash-verified.

## Mandatory LAION-CLAP reproduction

The baseline was reconstructed directly from the hash-validated LAION-CLAP embedding parquet, frozen trial identities, and canonical A/B labels.

| Split | Binary trials | Pairwise | Query-macro |
|---|---:|---:|---:|
| TRAIN | 67 | 0.7164 | 0.7056 |
| VALIDATION | 31 | 0.7097 | 0.7167 |
| TEST | 59 | 0.7627 | 0.7719 |

The reproduced TEST query-macro value was exactly 0.771875, matching the frozen artifact.

## GLAP results

| Split | Binary trials | GLAP pairwise | GLAP query-macro | LAION-CLAP query-macro |
|---|---:|---:|---:|---:|
| ALL | 157 | 0.6497 | 0.6768 | 0.7355 |
| TRAIN | 67 | 0.7313 | 0.7511 | 0.7056 |
| VALIDATION | 31 | 0.7742 | 0.8119 | 0.7167 |
| TEST | 59 | 0.4915 | 0.5479 | 0.7719 |

No exact GLAP margin ties occurred. The primary held-out comparison was:

```text
GLAP TEST query-macro:        0.5479167
LAION-CLAP TEST query-macro:  0.7718750
GLAP - LAION-CLAP:           -0.2239583
paired 95% query CI:         [-0.3760417, -0.0645833]
bootstrap draws / seed:       50,000 / 20260901
```

The TRAIN and VALIDATION values are reported transparently but do not override the predeclared TEST result.

## Paired errors and complementarity

TEST paired outcomes:

| Outcome | Count |
|---|---:|
| Both correct | 26 |
| LAION-CLAP only correct | 19 |
| GLAP only correct | 3 |
| Both wrong | 11 |

At query level, GLAP was better on 2 TEST queries, tied on 2, and worse on 12. Its largest positive query deltas were query 106277 (+0.50) and 113284 (+0.3333); the full per-query table is retained in `per_query_metrics.csv`.

GLAP and LAION-CLAP were not redundant, but the independent signal was not beneficial enough here:

- TEST margin Pearson correlation: 0.3071
- TEST margin Spearman correlation: 0.2722
- all-trial raw similarity Pearson/Spearman: 0.4385 / 0.4083
- TEST GLAP-vs-MuQ margin Pearson/Spearman: -0.2509 / -0.1476

The low correlations are diagnostic only. No CLAP+GLAP, GLAP+MuQ, or three-encoder fusion was fitted.

## Exploratory language audit

The acquired FMA/Stage 2B manifests contain no reliable vocal-language metadata. Genre names, artist names, titles, and filenames were not treated as language labels. No outcome-informed manual annotation was created.

Therefore:

> Historical Stage 2B does not support a reliable multilingual subgroup analysis.

GLAP's multilingual behavior remains untested by this experiment. The result does not justify promoting GLAP to a multilingual challenger, but it also is not evidence about a future purpose-built multilingual benchmark.

## Engineering measurements

Real-model validation on frozen track 714 produced two byte-identical embeddings:

- shape: 1024
- finite: yes
- norms: 1.000000018 / 1.000000018
- maximum repeated-inference difference: 0.0
- first/warm inference in the final integrity-gated validation: 1,827.2 ms
- repeated inference: 20.3 ms

An independent empty-cache 246-track performance run recorded:

| Measurement | GLAP |
|---|---:|
| Successful / failed | 246 / 0 |
| Model load | 5.96 s |
| p50 / p95 inference | 19.69 / 21.25 ms |
| Inference-only throughput | 155,965 clips/hour |
| End-to-end wall time | 30.93 s |
| End-to-end throughput | approximately 28,632 tracks/hour |
| Peak allocated VRAM | 3,464,466,944 bytes |
| Embedding storage | 4,096 bytes/track |
| Checkpoint storage | 3,422,036,400 bytes |

Historical LAION-CLAP recorded 31,027 clips/hour, 2,048 embedding bytes/track, and a 1,863,587,645-byte checkpoint. The throughput procedures are not perfectly controlled: the historical LAION-CLAP timing included its original batch pipeline, while GLAP's report separates inference-only and end-to-end timing. GLAP is 2x the embedding size and about 1.84x the checkpoint size. Those costs provide no reason to override its materially worse held-out agreement.

## Resume, idempotency, and failures

- Three-track real smoke: 3/3 success.
- Three-track rerun: 3 reused, zero inference, no model load.
- Twelve-track smoke: 12/12 success; first 3 reused.
- Full historical run: 246/246 success; first 12 reused.
- Full rerun: 246 reused, zero inference, no model load.
- Initial deterministic-runtime failures were stored as explicit failures with null embeddings, diagnosed, and retried successfully after `CUBLAS_WORKSPACE_CONFIG=:4096:8` was frozen. No failed row was converted to a zero-vector success.

The retained SQLite cache is gitignored. `embedding_cache_manifest.json` binds its 246 source, PCM, analysis, and embedding identities; its stable embedding-set SHA-256 is `013a8f1920cef905caa70c94e2dfe103114af43aced8a191f061a41b7d5248ad`.

## Reproduction commands

From `ml/audio_similarity`:

```bash
uv sync --extra glap-challenger
uv run hf download mispeech/GLAP --revision 79b13014511e2d5628cb57c4712a90edd19cebbd --local-dir models/glap_stage2b_challenger_v1/hf
PYTHONPATH=src uv run python -m audio_similarity.cli.glap_stage2b_challenger model-smoke --root . --device cuda --track-id 714
PYTHONPATH=src uv run python -m audio_similarity.cli.glap_stage2b_challenger encode --root . --device cuda --batch-size 1
PYTHONPATH=src uv run python -m audio_similarity.cli.glap_stage2b_challenger analyze --root .
PYTHONPATH=src uv run python -m audio_similarity.cli.glap_stage2b_challenger cache-manifest --root .
```

The frozen checkpoint SHA-256 must be verified before inference. Model weights, audio, and SQLite caches remain outside Git.

## Final boundary

`GLAP_REJECTED_AS_GLOBAL_CHALLENGER`

No production representation, preprocessing rule, K value, temporal center, encoder checkpoint, MuQ revision, or CLAP/MuQ weight changed. No new ratings were collected. No fusion was fitted. No Stage 5B acquisition behavior changed.
