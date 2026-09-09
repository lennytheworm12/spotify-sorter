# Dedicated style prior pilot

This isolated development experiment tests whether a frozen dedicated style classifier separates existing bad and good playlist matches. It uses the original 100 tracks and human ratings; it never changes production ranking or trains a neural scorer.

## Frozen contract

The authoritative statistical and extraction settings are `configs/style_prior_v2.json`, copied create-once to `reports/style_prior_pilot/v2/protocol.json`. Historical inputs are hashed before inference. Playlist compatibility is primary (419 pairs); historical holistic similarity is a separate sensitivity (740 pairs). These are exposed development data from one reviewer, not a new confirmatory test.

One model is used: [Discogs-EffNet bs64-1](https://essentia.upf.edu/models/music-style-classification/discogs-effnet/discogs-effnet-bs64-1.json). Its 400 outputs are multilabel sigmoid scores, not calibrated categorical probabilities. Preserve the raw patch predictions and their mean; normalize the mean plus epsilon solely to compute Jensen–Shannon distance. Scores are pooled across the entire retained source.

The reference [Essentia predictor](https://essentia.upf.edu/reference/std_TensorflowPredictEffnetDiscogs.html) operates at 16 kHz, with 128-frame patches and 62-frame hops. Final partial patches repeat; the last batch uses the provider's `same` behavior and only returned real patch predictions are pooled. There is no source loudness normalization or added audio feature. The pretrained frontend is kept intact.

Version 1 failed before producing any predictions because this Essentia build cannot decode the retained WebM codec. Version 2 changes only the decoding bridge: system FFmpeg decodes the full source into temporary original-rate/channel float32 PCM WAV; Essentia then performs its mono downmix and resampling. Original audio is immutable. The aborted protocol and original implementation are retained under `reports/style_prior_pilot/v1`. Its original input hash map records the then-current source code, which has since been explicitly superseded by this amendment.

## Run

From `ml/audio_similarity`, with local model files already present:

```bash
uv venv artifacts/style_prior_pilot/env --python .venv/bin/python
uv pip install --python artifacts/style_prior_pilot/env/bin/python essentia-tensorflow==2.1b6.dev1389 numpy==1.26.4 pyyaml==6.0.2 six==1.17.0
PYTHONPATH=src .venv/bin/python -m audio_similarity.style_prior
CUDA_VISIBLE_DEVICES=-1 TF_NUM_INTRAOP_THREADS=1 TF_NUM_INTEROP_THREADS=1 OMP_NUM_THREADS=1 TF_DETERMINISTIC_OPS=1 PYTHONPATH=src artifacts/style_prior_pilot/env/bin/python -m audio_similarity.style_prior_extract
CUDA_VISIBLE_DEVICES=-1 TF_NUM_INTRAOP_THREADS=1 TF_NUM_INTEROP_THREADS=1 OMP_NUM_THREADS=1 TF_DETERMINISTIC_OPS=1 PYTHONPATH=src artifacts/style_prior_pilot/env/bin/python -m audio_similarity.style_prior_extract --replay
PYTHONPATH=src .venv/bin/python -m audio_similarity.style_prior_analysis
.venv/bin/python -m pytest -q tests/test_style_prior.py
.venv/bin/python -m pytest -q
```

The main project environment is unchanged. Model/runtime downloads are prerequisites; inference is local and does not upload audio. HTTP tests need localhost access. There is no review or production activation command in this pilot.

## Artifacts and recovery

`artifacts/style_prior_pilot/cache` contains content-addressed raw patch predictions with checksummed receipts. Identity includes source, model, metadata, preprocessing, implementation, serialization, Python/NumPy/Essentia identity, native Essentia binary and FFmpeg binary. A replay fails rather than running inference for a missing entry. Numbered execution ledgers preserve previous runs; aggregate NPZ and JSON files are create-once and deterministic.

An interruption before aggregate publication can resume from existing track receipts. A completed run with explicit failed tracks is an incomplete experiment and must not be analyzed; use a new reviewed version to remedy an extraction-contract failure rather than replacing published partial aggregates. Cache corruption fails validation.

## Analysis

The primary signal gate requires overall anchor-macro bad-versus-good AUC with a descriptive 95% interval above 0.5, positive discrimination among exact-D Top-10 neighbors and positive discrimination among pairs within 0.05 D cosine. At least 20 anchors must contribute overall. Ratings of 3 do not become bad examples.

Only after that gate passes, choose one scalar penalty from the frozen grid on two artist/source-disjoint folds and evaluate it on the remaining fold, rotating three times. All three tracks in each preference must be in its partition. Missing cross-partition comparisons are excluded, never relabeled. The fixed scorer is D cosine minus lambda times style distance; exact C is a separately reported sensitivity. Artist grouping and splits do not depend on predictions or rating values. There is no learned feature transform or categorical genre veto.

Report accepted cross-label pairs and regressions alongside improvements. Named songs and prior taxonomy examples are developmental diagnostics. No model choice, prompt, distance metric, or lambda grid is adjusted to repair those examples.

Anchor bootstrap intervals describe the available sample; shared candidates mean they are not independent-track confidence guarantees. Three folds are insufficient for precise fold-level uncertainty. Unknown overlap with Discogs training audio prevents a claim about foundation-model generalization to unseen music.

## Human handoff

The pilot found observable style separation but did not establish an effective penalty. The next step is a **12-pair explanatory audit**, with no repeat of the previous 16 taxonomy pairs. Six accepted matches with relatively large style distance and six rejected matches with relatively small distance are selected with track disjointness and reduced artist reuse. This purposefully selected development sample cannot estimate prevalence or establish reranker efficacy.

The reviewer should explain which audible differences matter for sharing a playlist, and what connects a pair that works despite differences. Genre vocabulary is optional. These annotations supplement the existing 12 compatibility ratings; they do not replace them. Model scores, predicted style labels, strata and old ratings stay out of the browser payload. Interpret the annotations against the private selection only after the answer snapshot is frozen.

```bash
# Launch or resume; then open http://localhost:8792
PYTHONPATH=src .venv/bin/python -m audio_similarity.style_prior_review review --port 8792

# Only after all 12 answers are complete:
PYTHONPATH=src .venv/bin/python -m audio_similarity.style_prior_review freeze

# Recheck extraction, cache and historical integrity:
PYTHONPATH=src .venv/bin/python -m audio_similarity.style_prior_verify

# Real-model synthetic checks in the isolated environment:
CUDA_VISIBLE_DEVICES=-1 TF_NUM_INTRAOP_THREADS=1 TF_NUM_INTEROP_THREADS=1 OMP_NUM_THREADS=1 TF_DETERMINISTIC_OPS=1 PYTHONPATH=src artifacts/style_prior_pilot/env/bin/python tests/style_prior_engineering_golden.py
CUDA_VISIBLE_DEVICES=-1 TF_NUM_INTRAOP_THREADS=1 TF_NUM_INTEROP_THREADS=1 OMP_NUM_THREADS=1 TF_DETERMINISTIC_OPS=1 PYTHONPATH=src artifacts/style_prior_pilot/env/bin/python tests/style_prior_input_response.py
```

The public packet is `reports/style_prior_pilot/review_v1/packet.json`. Human answers autosave under `artifacts/style_prior_pilot/review_v1/answers.sqlite` and `taxonomy-answers.csv`; the browser export is named `style-audit-answers.csv`. Notes support 50,000 characters. `freeze` creates `labels_snapshot.json` and blocks further edits. It does not automatically tune a model or make a scientific claim.

The final non-heavy suite currently has two pre-existing publication-lock failures because local HEAD is not an ancestor of the remote feature branch. Do not weaken those historical checks or change remote refs to make the suite appear green. No push or production activation is part of this handoff.
