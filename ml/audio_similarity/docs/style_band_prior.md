# Coarse style-band prior: frozen development experiment

This study asks whether cached Discogs style probabilities complement **CLAP C**
for the existing playlist-compatibility rubric. It does not replace C, infer
new audio, train a model, create labels, or change production behavior. Historical
outputs and verdicts are immutable. All human evidence has been exposed before;
grouped evaluation here is development evidence, not a fresh confirmatory test.

## Frozen hierarchy

`configs/style_band_prior_v1.json` is the complete authored rule set.
`reports/style_band_prior/v1/mapping.json` expands it to every one of the exact
400 checkpoint styles, including fractional memberships and effective tag counts.
Rules consume only the checkpoint's class names, never song or artist identity.

| Parent neighborhood | Bands |
| --- | --- |
| Hip-hop | Rap; beat/DJ/instrumental |
| Popular song | Soul/R&B; dreamy indie; pop; rock |
| Electronic | Electronic/dance; ambient/experimental |
| Jazz/blues | Jazz/blues |
| Folk/world | Folk/world/country |
| Latin | Latin |
| Reggae | Reggae |
| Classical/screen | Classical, orchestrated and screen music |

There are 13 informative bands and an unknown/non-musical bucket. Parent
neighborhoods are deliberately broad hypotheses about related musical traditions,
not claims that every pair within a parent belongs in one playlist. In particular,
the popular-song parent allows differences between R&B, indie, pop and rock to
receive a smaller penalty without making them equivalent at band resolution.

Most styles inherit their Discogs family. Explicit generic overrides separate
instrumental/DJ/trip-hop evidence from rap, collect dreamy styles across rock/pop,
and separate ambient/experimental electronic labels from dance-oriented defaults.
Jazzy hip-hop splits equally across rap and beats because it need not be
instrumental. Indie rock and rock Lo-Fi split across rock and dreamy indie;
neither is automatically instrumental hip-hop. Contemporary R&B stays soul/R&B.
Ambiguous or heterogeneous defaults remain a limitation of this small hierarchy.
No classifier style label is asserted to be ground-truth song identity.

## Aggregation and adjustment

Let `r[s]` be the existing full-track mean sigmoid output. Each style's mapping
weights sum to one. Sum `r[s] * mapping[s,b]` to form raw band masses `m[b]`.
Keep these beside normalized values. This preserves the previous style pilot's
additive evidence convention. It does **not** calibrate multi-label scores into
genre probabilities; broad bands with more correlated labels can attract more
mass. The exact effective label counts are reported, and no post-result
normalization variant will be selected to rescue this run.

Exclude unknown mass, add `1e-8` to each informative band, and normalize to `p`.
Sum `p` into the parent distribution `h`. Let `q` be informative raw mass divided
by total raw mass, or zero for an all-zero vector. Define Jensen–Shannon divergence
in bits, bounded by `[0,1]`:

```
d(a,b) = q[a] q[b] * (0.5 JS(p[a],p[b]) + 0.5 JS(h[a],h[b]))
S(a,b) = frozen_C(a,b) - lambda * d(a,b)
```

The score is symmetric, self-scores are unchanged, and the penalty is at most
0.10 cosine units. No cutoff, hard reject, score clipping, or acceptance
threshold exists. Zero/unknown evidence contributes zero penalty, not confident
compatibility. The mixture coefficients and taxonomy are fixed without inspecting
this run's outcomes.

## Selection and evaluation

Reuse the prior's exact three artist/source-connected folds. An evaluation
preference has its anchor and both candidates inside the held-out partition;
none may enter that fold's training pairs. Revalidate identities, source/video
and credited-artist grouping, and exact human preference provenance. Unrated
pairs remain unknown. Ties in human ratings produce no preference constraints.

For each fold choose one lambda from `[0, .025, .05, .10]` using **training**
strict ordinal anchor-macro agreement only, choosing the smallest strength within
`1e-12` of the maximum. Scores within `1e-6` tie and earn half credit. No new split,
taxonomy, mixture, or penalty search follows evaluation. A raw 400-style JS
penalty uses the identical train-only grid as a secondary control, not an
alternative selectable result. Require at least 20 held-out preferences and
10 anchors per fold; failure blocks evaluation without weakening the split.

Primary: paired anchor-macro preference accuracy against C. Report training grid,
fold outcomes, strong preferences (rating gap at least two), and all correction
events. For good-versus-bad analysis, good is 4–5 and bad is 1–2. A **corrected
ordering** strictly reverses an incorrect bad-above-good ranking; a **broken
ordering** does the reverse. Report both event counts and unique affected pairs.
These counts are relative ranking outcomes, not automatic playlist admissions.
Unique affected pairs can overlap other event sets and are not a recall rate.

Top-5 reports use each held-out candidate partition for grouped evaluation.
Separately report all-99-candidate changes for held-out queries; these include
training candidates and are **not** the grouped generalization result. Distinguish
good, bad, rating-3 and unknown entrants/departures in both reports. A removed bad
pair with an unknown replacement does not establish improved playlist quality.
These sparse union-selected ratings cannot estimate full-library precision.

Descriptive 95% intervals: 5,000 paired anchor bootstrap replicates, PCG64 seed
5101; also resample artist/source-connected groups, retaining anchor-macro
weighting. Shared candidates and only three folds limit independence. Per-band
and parent-region breakdowns use dominant **predicted** aggregate mass, not human
genre annotations. Exclude historically named diagnostic artists as a fixed
sensitivity without refitting; those examples are never untouched proof.

## Decision frozen before execution

A positive development result requires all of:

- Primary macro improvement at least 0.02, with both anchor and connected-group
  interval lower bounds above zero.
- More strictly corrected than newly broken good/bad orderings.
- Positive point gains in at least three parent regions with at least three
  eligible anchors each.
- Positive point gain after excluding diagnostic artists, and after dropping
  the largest eligible parent region by anchor count (lexical tie break).

Passing yields `COMPLEMENTARY_STYLE_BAND_SIGNAL_DEVELOPMENT_ONLY` and justifies
one prospectively frozen reranker follow-up. Otherwise close this tested shortcut
as `STYLE_BAND_SHORTCUT_NOT_ESTABLISHED` and return to the learned playlist scorer /
supervision path. A negative result does not prove that every hierarchy or style
signal is useless. No production winner or activation follows either outcome.

## Reproduction

From `ml/audio_similarity`, using the existing main virtual environment:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_style_band_prior.py -q
PYTHONPATH=src .venv/bin/python -m audio_similarity.style_band_experiment prepare
PYTHONPATH=src .venv/bin/python -m audio_similarity.style_band_experiment evaluate
PYTHONPATH=src .venv/bin/python -m audio_similarity.style_band_experiment replay
PYTHONPATH=src .venv/bin/python -m audio_similarity.style_band_report report
PYTHONPATH=src .venv/bin/python -m pytest
# After recording actual test results in validation.json:
PYTHONPATH=src .venv/bin/python -m audio_similarity.style_band_report manifest
```

Preparation verifies existing cached patch receipts and exactly reconstructs
100 track means, freezes the expanded mapping and source/configuration identities,
and is safe to repeat. Evaluation reads arrays only and has no inference path.
Create-once output writes reject changed bytes. Replay recomputes lightweight
aggregation/analysis from the same cached means and checks exact artifact hashes;
it does not overwrite the initial results or historical execution ledgers.
The final artifact manifest covers outputs, test evidence, and the report.
