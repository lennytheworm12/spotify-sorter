# Stage 5G.1B — interpretable zero-shot mismatch probes

Outcome: **ZERO_SHOT_NOT_ESTABLISHED**. No similarity model was trained, and no production behavior was activated.

## Question and evidence

Can a compact set of general musical identity signals distinguish existing rated false positives from compatible matches? We reused 100 frozen tracks, 1,927 frozen full-song CLAP segment embeddings and the exact 400 Arm-D views. Primary evidence is the 419 frozen playlist-compatibility judgments: 55 bad (1–2), 251 good (4–5), 113 ambiguous (3). The 740 older holistic-similarity judgments are a separate sensitivity population, not pooled labels. Unknown pairs are never negatives. Ratings reflect one reviewer and this selected candidate population, not universal perception or the whole library.

Six existing notes span only three motivating anchors. They support a broad family/style mismatch hypothesis but do not independently annotate the causes of errors across unrelated songs. There are **zero causal taxonomy labels**. No synthetic explanations, inferred listening judgments, or new human ratings are substituted for those missing labels. Model-derived mismatch classes below are hypotheses, not verified explanations.

## Small provisional taxonomy

1. **Musical family:** eight broad prompt families spanning rap/hip-hop, pop, rock, electronic dance, acoustic folk, jazz/soul, ambient and orchestral music.
2. **Vocal delivery:** rhythmic speech/rap, melodic singing, instrumental, wordless/chopped voice, shouting/screaming.
3. **Rhythmic behavior:** driving beat, laid-back groove, busy syncopation, free-flowing/no steady pulse.
4. **Production texture:** rough/distorted, clean electronic, warm/hazy sampled, natural acoustic.

These axes were fixed before probe results. No song-, artist-, or genre-specific exception rule exists. Broad family labels are a vocabulary, not a playlist admission policy. Arrangement/structure and melodic/harmonic identity were deferred: this small text-prompt experiment has no validated measurement of them. Rhythm descriptions likewise are semantic probes, not measured tempo or beat structure. Categories are non-exhaustive, overlapping and imperfect: for example, jazz and soul share one coarse prompt category. Failure of this vocabulary does not rule out a better one.

## Frozen method

Use the exact HTSAT-tiny `630k-audioset-fusion-best.pt` checkpoint's frozen text encoder, already locally available, to encode 42 prompts (two independently worded phrasings for 21 concepts). No downloads or new audio inference. Audio evidence uses the mean cosine to all normalized G1 full-song segments; exact Arm-D four-view mean cosine is a separate sensitivity. Softmax temperature 0.07 produces relative prompt weights, **not calibrated class probabilities**. Pairwise profile divergence is normalized Jensen–Shannon divergence in [0,1].

A categorical mismatch requires both prompt phrasings to choose the same concept for each track and each top-versus-runner-up cosine margin to be at least 0.02; the two tracks must then choose different concepts. Ambiguous cases explicitly abstain. Abstentions are included in overall coverage denominators, never silently converted into confident compatible classifications. No thresholds or prompts were tuned to outcomes. No per-song metadata is a predictive input; artist names serve only exclusion/group sensitivity.

For each axis, evaluate within-anchor bad-versus-good divergence ordering (macro AUC, ties half-credit). Require the frozen performance, coverage, paraphrase, exact-D, high-neighbor and artist-exclusion gates in `protocol.json` before recommending a compatibility layer. Four-axis intervals use 98.75% paired-anchor bootstrap percentiles (2,000 draws). They are descriptive, not fully independent confidence intervals: anchors share candidate tracks, artist exclusions overlap, and all historical outcomes have previously been exposed. No untouched TEST claim. High-neighbor slices use exact Arm-D Top-10 on the frozen 100; missing ratings outside the reviewed union remain unknown.

## Results

| Rubric | Axis | Informative anchors | Macro AUC | Descriptive interval | Bad pairs flagged | Good pairs flagged |
|---|---|---:|---:|---|---:|---:|
| playlist | musical_family | 52 | 0.607 | [0.483, 0.733] | 1.8% | 5.2% |
| playlist | production_texture | 52 | 0.553 | [0.438, 0.662] | 0.0% | 0.8% |
| playlist | rhythmic_behavior | 52 | 0.522 | [0.405, 0.645] | 0.0% | 0.4% |
| playlist | vocal_delivery | 52 | 0.577 | [0.464, 0.691] | 0.0% | 0.0% |
| holistic | musical_family | 80 | 0.582 | [0.511, 0.649] | 0.8% | 3.3% |
| holistic | production_texture | 80 | 0.540 | [0.460, 0.614] | 0.0% | 0.6% |
| holistic | rhythmic_behavior | 80 | 0.530 | [0.453, 0.605] | 0.0% | 0.3% |
| holistic | vocal_delivery | 80 | 0.593 | [0.512, 0.670] | 0.0% | 0.0% |

`results.json` contains both paraphrase estimates, exact-D sensitivity, high-D-neighbor slices, diagnostic-artist exclusions, leave-one-artist-out results, abstention rates and per-anchor estimates. The union of any confident axis is descriptive only. `baseline_controls.json` compares each probe with negative D cosine and also reports ordering within a predeclared 0.05 cosine caliper. These controls assess redundancy; they are not a trained or simulated reranker. `counterexamples.json` includes rated bad/high-divergence examples, good/high-divergence counterexamples, and bad/low-divergence misses, with stable IDs and titles. Those lists are model-score-selected illustrations, not confirmatory data.

## What can and cannot be concluded

The existing notes do not establish that most errors concentrate in a few causal mismatch classes. That part of the goal remains unverified. The experiment does establish how consistently this fixed, existing zero-shot capability distinguishes reviewed good/bad pairs and how often it can emit an unambiguous proposed mismatch. A positive association alone would not validate the proposed human-readable reason.

No axis passed every predeclared advancement condition in the primary playlist population. The present probe layer is therefore not ready to justify a fixed compatibility reranker. This does **not** demonstrate that the failures are inherently heterogeneous, that all pretrained music signals fail, or that training a new similarity model is proven superior. Only one existing checkpoint and one compact vocabulary were tested. Stage 5G.1A's supervision limitation also remains relevant to returning to learned similarity.

The smallest justified next experiment is a bounded, blinded taxonomy audit of roughly 12–20 diverse rated bad/good pairs, selected across unrelated artists and including probe successes, false alarms and misses. Ask the reviewer for the dominant difference (including “none of these/unclear”), without showing probe outputs. Freeze selection and annotation rules first. This would separate a poor taxonomy from a poor detector before adding another model or a reranker. This stage creates no new review queue. If those annotations validate a recurring dimension, test one pretrained detector for that dimension; if they reveal heterogeneous reasons, return to learned perceptual similarity with a stronger supervision design.

## Reproduce and verify

From `ml/audio_similarity`:

```bash
.venv/bin/python -m audio_similarity.stage5g1b_analysis prepare
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m audio_similarity.stage5g1b_analysis extract
.venv/bin/python -m audio_similarity.stage5g1b_analysis replay
.venv/bin/python -m audio_similarity.stage5g1b_analysis analyze
.venv/bin/python -m audio_similarity.stage5g1b_analysis verify
.venv/bin/python -m pytest tests/test_stage5g1b.py -q
.venv/bin/python -m pytest -q
```

`text_identity.json` records exact checkpoint/package/tokenizer/source identities; `input_hashes.json` freezes historical inputs, source, tests, configuration and rubric-separated evidence before extraction. Text caching is keyed by the complete identity and exact prompts, with checksum validation and explicit refusal to infer on replay. `verification.json` records actual replay and test results. Original numbered execution ledgers are preserved. `artifact_manifest.json` lists all sealed report artifacts; later replay ledgers require a separate updated manifest. Historical verdicts, sources, ratings, representations, fusion and production paths are unchanged.
