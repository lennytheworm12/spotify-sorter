# Phase 1 Decision Report — MERIT + FMA Small

Experiment: `merit_fma_small_v1` · Branch `ml/phase1-stage-a` · 2026-08-22
Design contract: `Spotify Audio Representation Phase 1 MERIT FMA Design.md`

## 1. Executive status

| Gate | Status |
|---|---|
| Engineering gates (§16) | **PASS** (all) |
| Full-corpus encode ≥99.5% | **PASS** — 7,997/8,000 = 99.96% |
| Repeatability | **PASS** — bit-identical reruns |
| Interruption/resume | **PASS** — zero loss/duplication |
| Retrieval invariants | **PASS** — full fast suite |
| Automatic diagnostics (§14) | Complete — see below |
| Human perceptual eval (§15) | **PENDING** — sheets generated, ratings not yet collected |
| Factor-control A/B gate | **PENDING** — 352 blinded trials prepared |

> **Provisional verdict: CONDITIONAL GO** — pending human-eval gates.
> Automatic evidence alone supports proceeding to Phase 2 planning; the
> predeclared application-utility gates require human ratings before a
> final GO can be declared.

## 2. What was run

```text
frozen manifest   data/manifests/fma_small.parquet (8,000 rows)
backbone          m-a-p/MERT-v1-330M @ 5240c2708a5acaee1007f43fb9735c7dcd0b78c9
heads             amaai-lab/merit @ a85df30eca1ba112eb594285f3ba1d96488e7883
head SHA-256      mel d40dbf84…  rhy 242c6552…  tim 9b44d58f…
preprocessing     pp-v1 (24 kHz mono, 30 s truncate/pad), one shared pass
layers            (3, 4, 5, 6, 23) mean-pooled → 5120-D → three heads
stack             Python 3.11.16, torch/torchaudio 2.6.0+cu124,
                  transformers 5.15.1, CUDA 12.4, RTX 4060 Ti 8 GB
```

## 3. Answers to the required questions

### Q1 Are MERIT neighbors useful?

Automatic proxy evidence says yes-with-caveats. Genre overlap@10 (chance =
0.125 across 8 balanced genres): **melody 0.261, rhythm 0.322, timbre
0.412** — 2.1–3.3× chance. Qualitative spot checks (`reports/qualitative_examples.md`)
show coherent neighborhoods (e.g., Blue Dot Sessions query returns same-label
acoustic/instrumental material under every factor). Final confirmation is
the human utility gate (pending).

### Q2 Which factors work best?

By genre-overlap proxy: **timbre > rhythm > melody** (0.412 / 0.322 / 0.261
@10; artist-excluded variants preserve the ordering: 0.383 / 0.296 / 0.239).
Timbre is clearly the strongest factor on this corpus.

### Q3 Are melody/rhythm/timbre neighborhoods meaningfully distinct?

**Yes — strongly.** Cross-factor Jaccard@10 = **melody↔rhythm 0.010,
melody↔timbre 0.011, rhythm↔timbre 0.017**. The decomposition produces
almost disjoint neighborhoods; factor-specific retrieval is real product
capability, not rebranded overall similarity. (RQ2/H2 supported.)

### Q4 Does MERIT add factor control beyond general MERT?

Partially evidenced automatically. Generic MERT has the highest raw genre
overlap (@10 = 0.458) and much higher same-artist rate (@10 = 0.103 vs
0.031–0.054 for MERIT factors) — i.e., generic MERT leans more on
artist/production identity, while MERIT factors retrieve more diverse
material. The decisive blinded A/B (352 trials prepared) is pending.
Current evidence suggests MERIT's value is *control*, not raw overlap.

### Q5 Dominant failure modes

Encode-level: only the 3 known-corrupt FMA clips (099134, 108925, 133297),
classified `DECODE_FAILED`, retryable=false (`artifacts/phase1_full/failures.parquet`).
Retrieval-level failure tagging (WRONG_MELODY etc.) happens during human
rating; the sheet includes an X option and the report will quantify tags.

### Q6 Measured inference cost

p50 **0.306 s/track**, p95 0.336 s/track → ~11,550 tracks/hour;
peak VRAM 2.1 GB, peak RAM 2.0 GB. Exact top-10 search p50 2.7 ms /
p95 12 ms over 7,997×(128·3+5120) vectors. Embedding store 171 MB Parquet.

### Q7 Is 30-second-excerpt performance strong enough to justify Phase 2 sampling experiments?

Provisionally yes: with timbre/rhythm/melody at 3.3/2.6/2.1× chance and
clean factor separation on 30-s excerpts, the representation merits testing
whether multi-window full-song aggregation improves it (Phase 2's exact
question). This conclusion applies **only to 30-second excerpts**, per §18.

### Q8 Recommendation

**CONDITIONAL GO.**
- If human-eval confirms median ≥2 and ≥60% rated ≥2 per factor → upgrade to GO.
- Per-factor conditional outcome is acceptable (e.g., melody FAIL alone does not block).

### Q9 Exact next experiment justified

Phase 2 as scoped in the parent design: full-song windowing comparison
(single vs first/middle/late vs evenly-spaced windows; mean vs normalized-
mean vs segment-retention aggregation) on a controlled full-length corpus,
plus scale validation 8k→25k. No Spotify acquisition work until Phase 2
confirms the sampling contract.

## 4. Decision matrix (design §26)

| Area | Melody | Rhythm | Timbre | Notes |
|---|---:|---:|---:|---|
| Human median 0–3 | TBD | TBD | TBD | pending |
| % rating >= 2 | TBD | TBD | TBD | pending |
| MERIT vs MERT preference | TBD | TBD | TBD | 352 trials ready |
| Genre overlap@10 | 0.261 | 0.322 | 0.412 | weak proxy |
| Same-artist@10 | 0.031 | 0.047 | 0.054 | general MERT 0.103 |
| Major failure mode | TBD after rating | | | |

Performance:

| Metric | Result |
|---|---:|
| Encode success rate | 99.96% |
| p50 / p95 s/track | 0.306 / 0.336 |
| tracks/hour | 11,552 |
| peak VRAM / RAM | 2.1 GB / 2.0 GB |
| exact top-10 p50/p95 latency | 2.7 ms / 12.0 ms |
| embedding artifact size | 171 MB |

Projections from measured throughput: 25k ≈ 2.2 h; 106,574 ≈ 9.2 h (extrapolated, not measured).

## 5. Deviations from design

1. Frozen queries versioned at `reports/phase1_queries.csv` instead of
   gitignored `data/eval/`. Content/protocol unchanged.
2. Heavy tests use synthetic waveforms; real-FMA smoke tests cover the
   real path deliberately (CI stays model-free).
3. Conventional features aligned to the encoded 7,997-track set rather
   than the 8,000-row manifest (3 undecodable rows cannot have features).
None affect experiment validity.

## 6. How to finish the pending gates

```bash
# rate 360 blinded cells + 352 A/B trials in reports/human_eval/*.csv
# (rubric in file headers; reveal keys stay closed until done)
uv run python -m audio_similarity.cli.summarize_human_eval \
    --sheets reports/human_eval --output reports/human_eval_summary.json
```

Then update §4 TBDs and flip Q8 to GO / CONDITIONAL GO / NO-GO accordingly.
