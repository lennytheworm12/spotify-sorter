# Stage 1A — Frozen Holistic Encoder Benchmark Report

Experiment: `holistic_encoder_stage1a` · branch `ml/holistic-encoder-benchmark-stage1a`
Governing design: *Spotify Audio Similarity Pivot — Holistic Human-Aligned Retrieval*

## Experiment contract

| Component | Value |
|---|---|
| Corpus | FMA Small — 7,972 successfully decoded clips (3 known-corrupt excluded) |
| Audio excerpt | `center5_v1`: one centered 5-second window @ 24 kHz mono, identical musical content for every encoder |
| Query set | 40 frozen queries (5 × 8 top-level FMA genres, seed 20260823), frozen before any disagreement inspection |
| Encoders | `OpenMuQ/MuQ-MuLan-large` (512-D) · `MERT-v1-330M` layers 3/4/5/6/23 concat (5120-D) · MERT last-layer meanpool (1024-D) · LAION CLAP `music_audioset_epoch_15_esc_90.14.pt` HTSAT-base (512-D) |
| Licenses | MuQ code MIT / weights CC-BY-NC-4.0; MERT research use; CLAP MIT (weights CC-BY-NC where applicable) |
| Retrieval | exact cosine (`E @ q`), self-exclusion, deterministic tie order |

**Documented preprocessing deviation:** CLAP internally resamples to 48 kHz and
quantizes input to a fixed 10-second window. The musical content is the same
frozen 5-second excerpt for every encoder; only model-side windowing differs.
Recorded per embedding in provenance.

## Mechanical results

| Encoder | Success | Failures | Dim | Repeat max-diff |
|---|---:|---:|---:|---:|
| muq_mulan_large | 7972 | 0 | 512 | 0.0 |
| mert_5120 | 7972 | 0 | 5120 | 0.0 |
| mert_generic | 7972 | 0 | 1024 | 0.0 |
| laion_clap | 7972 | 0 | 512 | 0.0 |

Identical track universe across all encoders — comparisons are apples-to-apples.

## Performance (25-track gate + full-run)

| Encoder | p50 s/clip | p95 s/clip | clips/hour | Load |
|---|---:|---:|---:|---:|
| muq_mulan_large | 0.098 | ~0.15 | 35,499 | ~28 s |
| mert_5120 | 0.089 | ~0.19 | 38,665 | ~4 s |
| mert_generic | 0.085 | ~0.11 | 35,373 | ~1 s |
| laion_clap | 0.114 | ~0.13 | 23,109 | ~14 s |

Full-corpus wall time: ~58 min for all four encoders combined.
Artifact size: 4 × Parquet ≈ 130 MB total.

## Retrieval diagnostics

⚠ **These do not select the winner.** Human holistic preference is the
selection target; the numbers below are sanity/anomaly checks only.

| Encoder | same-artist@10 | genre-overlap@10 |
|---|---:|---:|
| muq_mulan_large | 0.150 | 0.578 |
| mert_5120 | 0.130 | 0.445 |
| mert_generic | 0.105 | 0.395 |
| laion_clap | 0.192 | 0.600 |

CLAP shows the highest genre/artist clustering — consistent with its
audio-text training emphasizing nameable concepts. Whether that helps or
hurts *overall perceived similarity* is exactly what the human benchmark
will answer.

## Human benchmark readiness

| Item | Status |
|---|---|
| Frozen queries | 40 (committed manifest + seed + algorithm) |
| Candidate unions | built from all four encoders' top-10 |
| Blinded A/B trials | **310** (cross-model disagreements + competitive pairs + anchor negatives), seeded A/B randomization |
| Model identity exposure | none in human-facing artifacts (provenance in separate key file) |
| Rater support | multi-rater logs, autosave/resume, notes, export/import, volume control |
| Rating path | server mode via ngrok/LAN → Holistic A/B tab |

Target protocol: 40 queries × 8 comparisons × 3 raters ≈ 960 judgments.

## Explicit conclusion

## **READY_FOR_HUMAN_ENCODER_BENCHMARK**

All engineering gates passed; blinded sheets are live in the evaluator.
No winner is declared — encoder selection happens exclusively through
collected human preferences on held-out queries.

## Known limitations

1. Holistic trials rate through **server mode only tonight** (candidate audio
   resolution requires the server-side key file); offline/Pages support is a
   small follow-up.
2. CLAP's internal 10-s window means it hears zero-padded content beyond the
   shared 5-s excerpt — unavoidable model-contract difference, recorded.
3. Single-genre-stratified query sampling uses FMA genres as a balancing aid,
   never as similarity ground truth.
