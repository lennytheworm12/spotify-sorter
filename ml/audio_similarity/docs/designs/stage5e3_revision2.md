---
title: Stage 5E.3 — Frozen-100 Full-Song MuQ Playlist Compatibility Benchmark
aliases:
  - Stage 5E.3 — Full-Song MuQ Comparison
  - Full-Song CLAP + MuQ Playlist Compatibility Benchmark
status: design-ready-for-implementation
revision: 2
created: 2026-09-06
project: Spotify Sorter
tags:
  - spotify-project
  - audio-similarity
  - music-information-retrieval
  - full-song
  - muq
  - clap
  - human-evaluation
  - clustering-foundation
---

# Stage 5E.3 — Frozen-100 Full-Song MuQ Playlist Compatibility Benchmark

## Navigation

- Parent project: [[Spotify Sorter]]
- Frozen full-song CLAP research: [[Spotify Audio Similarity Stage 4 — Full-Song Representation Benchmark Design]]
- Future multi-view architecture: [[Spotify Future Multi-View Adaptive Similarity and Full-Track Research Design]]
- Independent explicit-attribute work: [[Spotify Audio Similarity Stage 5F.2 — Rhythm Pattern Attribute Layer Design]]

## Decision

Run a **frozen-100 representation benchmark** that asks whether broader temporal coverage in both learned encoders improves the thing the eventual clustering system actually needs: **playlist compatibility**.

The primary question is:

> **Does broader audio coverage improve playlist compatibility enough to justify using it as the foundation for clustering?**

This stage is a representation-choice experiment, not a clustering experiment.

It must:

1. preserve existing Stage 5E arms **A, C, and D** exactly as historical baselines;
2. preserve the existing centered-30 MuQ representation exactly;
3. add one new **full-song MuQ-MuLan** representation using model-native 10-second chunks at 24 kHz;
4. compare four frozen primary methods without tuning on evaluation ratings;
5. reuse retained local source audio, cached embeddings, and compatible historical judgments wherever possible;
6. create a blinded playlist-compatibility review surface for unresolved evidence plus the frozen drift-probe repeats;
7. include known-good and known-false-positive probes without allowing forced probes to masquerade as retrieval success;
8. produce one recommendation about the learned representation that should underpin later clustering research;
9. make **no production activation, MIR-feature expansion, clustering, or cluster-admission change**.

## 1. Why this experiment exists

The project has already tested two distinct questions that should not be conflated:

```text
Stage 4 / Stage 5E:
    Does broader CLAP coverage change retrieval quality?

Stage 5F:
    Do explicit mechanical attributes explain useful residual signal?

Stage 5E.3:
    If the learned backbone itself receives broader temporal coverage,
    is its neighborhood geometry more suitable for coherent playlists?
```

The current engineering representation mixes:

```text
CLAP: broader/full-song alternatives now exist
MuQ:  historical centered30_v1 sampling only
```

That creates an asymmetry. A full-song CLAP representation can summarize an entire recording while its fused MuQ channel still sees only three short windows near 5, 15, and 25 seconds.

If broader temporal evidence is genuinely useful, the cleanest next test is therefore not another handcrafted feature. It is:

```text
full-song CLAP
+
full-song MuQ
```

under the same fixed fusion weights already used by the project.

This directly tests whether the clustering foundation should represent more of the song before adding more downstream complexity.

## 2. Historical identities are immutable

Do not reinterpret the historical arm letters. Resolve their exact configuration and hashes from:

```text
ml/audio_similarity/reports/stage5e1_four_arm_retrieval/experiment_config.json
```

At the governing repository snapshot, the identities are:

### 2.1 Arm A — centered-30 Music CLAP

```text
identity:
A_CENTERED30_CURRENT_MUSIC_CLAP_V1

architecture:
HTSAT-base

checkpoint:
models/music_audioset_epoch_15_esc_90.14.pt

checkpoint SHA-256:
fae3e9c087f2909c28a09dc31c8dfcdacbc42ba44c70e972b58c1bd1caf6dedd

views:
three 5-second windows centered at 5, 15, 25 seconds

pooling:
L2 each
→ equal arithmetic mean
→ L2 result
```

### 2.2 Arm C — full-song Music CLAP

```text
identity:
C_FULL_SONG_10S_CHUNK_MEAN_MUSIC_CLAP_V1

architecture:
HTSAT-base

checkpoint:
same checkpoint and SHA as A

views:
consecutive non-overlapping 10-second chunks
covering the full retained source

final partial:
native repeatpad to 10 seconds

pooling:
L2 each chunk
→ equal arithmetic mean including final partial
→ L2 result
```

A versus C is therefore the clean historical matched-checkpoint comparison of narrower versus broader temporal coverage for Music CLAP.

### 2.3 Arm D — general-audio CLAP reference challenger

```text
identity:
D_NATIVE_GLOBAL3_EQUAL_MEAN_GENERAL_AUDIO_CLAP_V1

architecture:
HTSAT-tiny

checkpoint:
models/630k-audioset-fusion-best.pt

checkpoint SHA-256:
fb171dd9b608aebdac3d89286cd7615c5100af4cc7dc37797c7fb8d3cc15e3a5

views:
frozen global/front/middle/back native log-mel tensors

pooling:
embed views independently
→ L2 each
→ equal arithmetic mean
→ L2 result
```

D is retained for context. It is **not** a matched-checkpoint test against A or C, so differences involving D cannot be attributed purely to temporal coverage.

### 2.4 Existing fixed MuQ

Preserve the historical MuQ representation exactly:

```text
representation:
centered30_v1

sample rate:
24000 Hz

views:
three 5-second windows centered at 5, 15, 25 seconds

pooling:
L2 each segment
→ equal arithmetic mean
→ L2 result
```

Do not regenerate or silently replace these vectors when compatible cached evidence exists.

## 3. Frozen fusion rule

The existing engineering fusion is:

```text
S(q,c) = 0.7172981519 * CLAP_cosine(q,c)
       + 0.2827018481 * MuQ_cosine(q,c)
```

Freeze these weights for this experiment.

No grid search, regression, Bayesian optimization, learning-to-rank, post-hoc coefficient adjustment, or manual weight selection may use the evaluation ratings.

If later evidence suggests the full-song channels deserve different weights, weight fitting belongs to a separate training/validation design with a separate held-out test set.

## 4. Primary methods under comparison

The new experiment has four primary methods:

| ID | Representation | Purpose |
|---|---|---|
| `M1_C_CLAP` | C CLAP cosine alone | Full-song CLAP reference |
| `M2_FULL_MUQ` | new full-song MuQ cosine alone | Measure MuQ as an independent full-song representation |
| `M3_C_PLUS_FIXED_MUQ` | C CLAP + existing centered30 MuQ at frozen weights | Current mixed-coverage fusion control |
| `M4_C_PLUS_FULL_MUQ` | C CLAP + new full-song MuQ at frozen weights | Main broader-coverage challenger |

Exact formulas:

```text
M1 = C_CLAP_cosine

M2 = FULL_MUQ_cosine

M3 = 0.7172981519 * C_CLAP_cosine
   + 0.2827018481 * FIXED_MUQ_cosine

M4 = 0.7172981519 * C_CLAP_cosine
   + 0.2827018481 * FULL_MUQ_cosine
```

The primary scientific comparison is:

```text
M4 versus M3
```

because this changes only the MuQ representation policy while holding C and fusion weights fixed. It jointly changes temporal coverage, input context from 5 to 10 seconds, and aggregation over views. It does not isolate coverage as the causal mechanism. C is an experimental control, not an already validated playlist foundation.

Secondary comparisons are:

```text
M1 versus M3   Does historical MuQ add value to full-song CLAP?
M1 versus M4   Does full-song MuQ add value to full-song CLAP?
M2 versus M1   How do the two full-song encoders behave independently?
M2 versus M4   Does CLAP complement full-song MuQ?
```

A and D remain historical reference baselines and must be reproduced in the closeout tables from frozen artifacts when compatible. They are not permitted to change identity or trigger new inference.

## 5. Full-song MuQ-MuLan representation

### 5.1 Model contract

Use the same MuQ-MuLan checkpoint family as the current project representation. Resolve and record the exact installed package version, Hugging Face revision, model-file hash, config hash, and local cache identity before inference.

The official `OpenMuQ/MuQ-MuLan-large` configuration currently declares:

```text
sample rate: 24000 Hz
clip_secs:   10
latent dim:  512
```

The official MuQ repository also states that MuQ and MuQ-MuLan strictly require 24 kHz audio input.

Primary references:

- https://huggingface.co/OpenMuQ/MuQ-MuLan-large/blob/main/config.json
- https://huggingface.co/OpenMuQ/MuQ-MuLan-large
- https://github.com/tencent-ailab/MuQ
- https://arxiv.org/abs/2501.01108

Do not use a 30-second arbitrary forward pass as the full-song policy. `full-song` means deterministic aggregation over model-appropriate fixed-length views.

### 5.2 Chunk schedule

For every retained source:

```text
sample rate:      24000 Hz
chunk duration:   10.0 seconds
chunk stride:     10.0 seconds
coverage:         consecutive, non-overlapping, full retained source
first chunk:      starts at 0.0 seconds
```

For source duration `T`:

```text
starts = 0, 10, 20, ... while start < T
```

Every source sample must belong to exactly one nominal chunk before final padding. No center crop, random crop, or stochastic start is allowed.

### 5.3 Final partial chunk

Freeze external cyclic repeat-padding of the final chunk itself. Work in integer sample indices after decoding/resampling the complete retained source to mono float32 at 24,000 Hz; do not use the existing 30-second truncation/padding path. Preserve the historical decoder/downmix/resampler convention and record its version. Do not add loudness normalization or silence trimming in this representation comparison.

Let `L = 240000` and `N` be the decoded sample count. For starts `0, L, 2L, ... < N`, take `x = waveform[start:min(start+L,N)]`. If `n = len(x) < L`, set `padded[j] = x[j % n]` for `j = 0..L-1`; otherwise use `x` unchanged. Empty input fails explicitly. This uses only the final chunk's observed samples, not samples from the beginning of the song.

Every forward pass receives exactly 240,000 samples. Do not delegate short-input padding to MuQ: the installed native helper appends a prefix and does not guarantee this length for very short recordings. A track shorter than ten seconds uses one cyclically padded chunk. Record observed sample count and added sample count. Include one-sample, empty, and boundary-length tests.

### 5.4 Chunk embedding and pooling

For each 10-second chunk:

```text
raw MuQ-MuLan music embedding
→ finite-value validation
→ L2 normalize chunk embedding
```

Then:

```text
track_mean = arithmetic mean(all scheduled normalized chunk embeddings)
FULL_MUQ   = L2(track_mean)
```

All scheduled chunks must succeed and receive equal weight, including the final partial chunk after deterministic padding.

This intentionally mirrors the conceptual pooling policy already used by C:

```text
represent each local chunk
→ normalize each
→ equal mean across the whole song
→ normalize the track vector
```

No attention pooling, duration weighting, max pooling, learned pooling, top-k chunk selection, salience selection, or section weighting is allowed in Stage 5E.3.

### 5.4.1 Failure and numeric contracts

Require each chunk vector to have shape `(512,)`, all finite values, and float64-computed L2 norm greater than `1e-12`. Apply the same norm floor to the pooled mean. Normalize using float64 arithmetic and store float32 vectors; calculate cosine matrices with float64 accumulation. Clip only floating-point overshoot to `[-1,1]`; assert symmetry and reliable self-similarity within `1e-6`.

Track statuses are `OK`, `SOURCE_MISSING`, `SOURCE_CHANGED`, `DECODE_FAILED`, `EMPTY_AUDIO`, `NONFINITE_AUDIO`, `INFERENCE_FAILED`, `INVALID_EMBEDDING`, or `ZERO_NORM`. Store the failing chunk index and diagnostic message where applicable. Any failed scheduled chunk invalidates the pooled track vector: retain successful chunk evidence for recovery but never pool a subset. Invalid vectors and associated similarities are null, never zeros or confident mismatches.

All 100 tracks must be `OK` before freezing retrieval or opening review. A failed materialization produces a status report and pauses dependent phases; it does not shrink the corpus or manufacture Top-5 entries. If closed without repair, the verdict is `INCONCLUSIVE`. Engineering fixes must preserve prior ledgers and create a new representation identity if embedding behavior changes.

### 5.5 Preserve chunk-level evidence

Do not save only the pooled vector. Preserve:

```text
spotify_track_id
source_sha256
chunk_index
start_seconds
nominal_end_seconds
observed_audio_seconds
padding_seconds
padding_policy
embedding_sha256
embedding_norm_before_normalization
status
warnings
```

Store chunk vectors separately from pooled track vectors so later structural research can reuse them without rerunning MuQ.

## 6. Frozen corpus

### 6.1 Primary universe

Use exactly the amended frozen 100 Spotify tracks from:

```text
ml/audio_similarity/reports/
stage5c2_representative_100_amended_v2/
```

The Stage 5C.2 amendment is the authoritative review surface:

```text
100 review tracks
98 historical representations reused
2 versioned supplemental exact-ID materializations
```

Restrict **both query and candidate axes** to these exact 100 identities.

### 6.2 Source identity

Resolve membership and retained source paths through the frozen selected-source and full-source manifests already used by Stage 5E/5F.

Require:

- exactly 100 expected Spotify IDs;
- one retained source per expected ID;
- source SHA-256 equality with the frozen manifest;
- selected YouTube video identity equality where applicable;
- no silent source replacement;
- no silent corpus shrinkage.

A missing or changed local source is an explicit preparation failure for that identity.

### 6.3 Pair exclusions

Exclude:

- self-pairs;
- pairs sharing retained source SHA-256;
- pairs sharing canonical YouTube video identity;
- other exact duplicate identities already excluded by Stage 5E.

The same exclusion function must be applied to all four primary methods.

## 7. Reuse before inference

The experiment must be cache-first.

Reuse, hash, and verify:

1. A, C, and D embeddings/similarity matrices from Stage 5E.1;
2. existing centered30 MuQ vectors or similarity matrices;
3. the amended original-100 membership from Stage 5C.2;
4. compatible original-100 ratings from Stage 5C.2, Stage 5E.1, Stage 5E.2, Stage 5F.1, and any later immutable compatible rating artifact discovered during preparation;
5. retained full source audio already present locally.

The only new encoder inference authorized is the missing **full-song MuQ** materialization.

No acquisition, YouTube search, Spotify API call, or source redownload is part of this stage.

## 8. Rating semantics

The evaluation target is not merely “sounds similar.” It is playlist compatibility.

Freeze this exact primary reviewer question:

> **How well do the anchor track and candidate track belong in the same coherent playlist group?**

Use:

```text
5 — Definitely belong in the same coherent playlist group.
4 — Probably belong; the pairing feels cohesive.
3 — Borderline; the pairing could work, but is not strongly cohesive.
2 — Probably should not belong in the same coherent playlist group.
1 — Definitely should not belong in the same coherent playlist group.
UNSURE — I cannot judge this pair with enough confidence.
```

`UNSURE` is nonnumeric. It must never be converted to 3 or any other score.

The reviewer may use holistic musical judgment, including timbre, arrangement, energy, rhythm, vocals, production, mood, and overall transition/cohesion. The task intentionally does not ask the reviewer to reverse-engineer why a pairing works.

## 9. Historical-rating compatibility

### 9.1 Immutable source labels

Never rewrite a historical rating artifact.

Every reused judgment must preserve:

```text
canonical unordered pair identity
anchor/candidate directional appearances when known
numeric rating or UNSURE
original prompt/scale identifier
source artifact path
source artifact SHA-256
timestamp when available
review note when available
compatibility decision
```

### 9.2 Compatible labels

Before inference, freeze a source-by-source mapping containing artifact hash, exact original prompt and scale, identity scheme, acceptance decision, and reason. Accept numeric 1–5 judgments only when the recorded prompt covers holistic musical similarity or coherent playlist compatibility and score direction matches Section 8. Missing/ambiguous prompt provenance is `SEMANTICS_UNRESOLVED`, excluded from automatic reuse and eligible for new review. Do not infer compatibility from filenames or stage numbers. Reuse a derived Stage 5F export only through its original rating provenance, deduplicated against that source.

Historical holistic-similarity judgments remain explicitly tagged `HOLISTIC_SIMILARITY`; new coherent-group judgments use `PLAYLIST_COMPATIBILITY_V1`. Report source/semantic composition and descriptive results separately by semantic tag. This mixed-label benchmark is retrospective and owner-specific, not an independent held-out validation of playlist sorting.

Follow the Stage 5E.2 precedent:

- old FMA-scale judgments are incompatible;
- song-identity `SAFE` labels are incompatible;
- duplicate exports do not create new evidence;
- reciprocal appearances of the same frozen unordered pair do not create independent ratings;
- conflicting numeric labels are not silently averaged.

Preparation must generate a `rating_compatibility_audit.json` explaining every accepted and rejected rating source.

### 9.3 Conflicts and revisions

If two compatible historical artifacts contain conflicting numeric ratings for the same canonical pair:

```text
status = CONFLICT_REVIEW_REQUIRED
```

Preserve both. Do not choose the newest or highest score automatically.

If the reviewer intentionally revises a prior judgment during this experiment:

- the original frozen label remains untouched;
- append the revision to a new ledger;
- record old value, new value, reason, timestamp, and review-session identity;
- the primary analysis uses the predeclared rule for revisions frozen before outcomes are examined;
- report a sensitivity analysis using original versus revised labels when revisions affect evaluated pairs.

Frozen revision rule:

```text
primary closeout:
latest valid judgment submitted before the analysis freeze,
with full provenance and original value preserved

historical-preservation sensitivity:
original frozen judgment only
```

## 10. Retrieval construction

For each of the 100 anchors:

1. rank all eligible other frozen-100 candidates under M1;
2. take M1 Top-5;
3. repeat independently for M2, M3, and M4;
4. tie-break by Spotify track ID ascending;
5. preserve raw scores and ranks outside the blind payload;
6. form the union of all four Top-5 sets.

Maximum raw retrieval slots:

```text
100 anchors × 4 methods × 5 = 2,000 directional slots
```

Because methods will overlap, actual unique anchor-candidate judgments should be substantially smaller.

### 10.1 Shared candidates

If the same candidate appears in multiple methods’ Top-5 for one anchor:

- review it once;
- store one judgment;
- credit the judgment to every method that naturally retrieved it;
- preserve each method’s rank and score in the hidden mapping;
- never duplicate it in the reviewer packet to create artificial sample size.

If the same unordered pair appears under reciprocal anchors, preserve both directional retrieval appearances but treat the underlying human pair judgment as one piece of evidence unless the frozen prompt explicitly treats direction as meaningful.

Primary playlist-compatibility ratings are symmetric.

## 11. Known-good and false-positive probes

Top-5-only review can miss an important failure mode: a method may avoid terrible results but also fail to recover pairs already known to work.

Construct a frozen probe bank from the **pre-run compatible label snapshot**.

### 11.1 Known-good

```text
KNOWN_GOOD := compatible frozen rating >= 4
```

### 11.2 Known false positive / unacceptable pair

```text
KNOWN_BAD := compatible frozen rating <= 2
```

Rating 3 is neither known-good nor known-bad.

### 11.3 Probe inclusion

For each anchor, after natural Top-5 union construction:

- include up to one known-good pair not already present;
- include up to one known-bad pair not already present;
- select deterministically using a frozen seed and stable pair-ID order;
- do not include a probe when the anchor has no eligible pair in that category;
- mark probe provenance only in the hidden manifest.

This gives the reviewer occasional anchors against established positive/negative evidence and provides a drift/revision check.

### 11.4 Critical accounting rule

A forced probe does **not** count as retrieval recovery.

Known-good recovery is credited only when a method naturally places a pre-run known-good pair in its own Top-5.

Likewise, known-bad recurrence is counted only when a method naturally retrieves the pair.

## 12. Blinded reviewer surface

### 12.1 What the reviewer sees

For one anchor at a time:

- anchor title + artist;
- anchor audio player;
- candidate title + artist;
- candidate audio player;
- 1–5 rating controls;
- `UNSURE`;
- optional note;
- progress within the current anchor packet.

Candidate order is deterministically shuffled per anchor. Players serve the full retained local recording with seeking, start paused at time zero, and never substitute model excerpts or remote previews. Record playback/seek durations as diagnostics, without imposing a listening-duration gate. Keep player gain behavior identical for anchor and candidate; permit ordinary user volume adjustment. No automatic excerpt selection or representation-specific playback is allowed.

### 12.2 What the reviewer must not see before submission

Hide:

- method identity;
- CLAP/MuQ identity;
- similarity score;
- rank;
- whether the candidate was shared by multiple methods;
- known-good/known-bad status;
- probe status;
- historical rating;
- which representation is currently “winning” aggregate metrics.

Do not encode method identity in IDs, filenames, CSS labels, query strings, sort order, or visible debug metadata.

### 12.3 Reveal timing

The reviewer submits the **entire anchor packet** atomically; submission does not unlock representation metadata during the review phase.

Do not reveal any method, rank, score, probe metadata, or aggregate results until the entire review phase and post-review label snapshot are frozen. This applies across reciprocal appearances and later packets as well as within an anchor.

## 13. Review queue and stopping rules

The queue is built once from frozen representations and the pre-run label snapshot.

Existing compatible numeric judgments are reused automatically. Unresolved or explicitly conflicted pairs enter the live review queue. The sole automatic-reuse exception is the frozen drift-probe bank: the up-to-one known-good and up-to-one known-bad probes selected per anchor in Section 11.3 receive blinded repeat judgments. Deduplicate reciprocal probes globally by unordered pair ID and assign them to the first anchor in frozen shuffled order. Record these as repeat judgments, preserving the original label. Do not display the historical score. These are the only automatically scheduled repeats; deliberate reviewer revisions remain append-only.

Use all selected probes, including those assigned to an anchor with no unresolved natural candidates. Report original-to-repeat score differences, category changes, and UNSURE count. Freeze the known-good retrieval bank from original pre-run ratings regardless of subsequent probe revisions.

Review order:

```text
seed = 20260906
shuffle anchors deterministically
within each anchor, shuffle candidates deterministically
```

Do not stop because one method appears ahead or behind.

The representation-choice closeout requires all of:

1. at least 80% numeric rating coverage of Top-5 slots for every primary method;
2. at least 90% numeric coverage for the primary M3 and M4 Top-5 slots;
3. at least 40 anchors with complete numeric Top-5 coverage for both M3 and M4;
4. at least 30 anchors with at least one pre-run known-good candidate in the eligible candidate universe;
5. at least 30 anchors with enough paired M3/M4 evidence for anchor-level comparison;
6. `UNSURE` reported separately rather than counted as numeric coverage.

If the queue is exhausted but these evidence gates are not met, the verdict must be `INCONCLUSIVE`.

Complete one pass over the entire frozen queue, with every assigned pair receiving a numeric judgment or UNSURE. Minimum coverage gates are adequacy checks, not an early-stop trigger. An interrupted review remains pending until resumed or explicitly closed INCONCLUSIVE; do not repeatedly requeue UNSURE until numeric gates pass.

## 14. Primary metrics

All retrieval-quality metrics are calculated on **naturally retrieved Top-5 slots only**. Forced probes are excluded unless a metric explicitly says otherwise.

### 14.1 Rating coverage

For each method:

```text
numeric_slot_coverage
unsure_slot_fraction
unrated_slot_fraction
complete_anchor_count
unique_pair_numeric_coverage
```

Report both raw slots and unique judgments so shared tracks do not create misleading review counts.

### 14.2 Unacceptable matches

Define:

```text
unacceptable := rating <= 2
```

For each anchor:

```text
unacceptable_rate@5
= numeric unacceptable Top-5 slots / numeric Top-5 slots
```

Primary quality summaries use complete anchors only, as defined below. Partial-anchor observed-only rates are descriptive and must be labeled as such.

Also report:

- raw unacceptable count;
- number of anchors with at least one unacceptable Top-5 result;
- worst-position distribution;
- known-bad recurrence@5.

### 14.3 Coherent matches

Define:

```text
coherent := rating >= 4
```

Report anchor-macro:

```text
coherent_rate@5
mean_rating@5
median_rating@5
```

### 14.4 Recovery of known-good matches

Freeze the known-good bank before generating final metrics.

For anchor `q` and method `m`:

```text
known_good_recall@5(q,m)
= naturally retrieved known-good candidates
  / eligible pre-run known-good candidates for q
```

Calculate this only for anchors with at least one eligible known-good pair.

Report:

- anchor-macro recall@5;
- number of known-good pairs recovered;
- number uniquely recovered by each method;
- rank of recovered known-good pairs;
- known-good candidates lost by M4 relative to M3;
- known-good candidates newly recovered by M4 relative to M3.

Because the historical known-good bank is selected rather than exhaustive, describe this metric as **recovery of known historical positives**, not true recall over all good songs.

## 15. Shared-track and overlap accounting

Methods are expected to retrieve many of the same candidates. A fair comparison must not pretend these are independent observations.

For every method pair, report:

```text
mean Top-5 Jaccard overlap
shared Top-5 slots
unique Top-5 slots contributed by each method
shared unique unordered pairs
unique pairs requiring new review
```

For inferential comparisons:

- compare methods on the same anchor whenever possible;
- use paired anchor-level deltas;
- bootstrap anchors, not raw retrieval rows;
- report leave-one-anchor-out influence;
- add a track-node sensitivity so one frequently retrieved song cannot dominate the conclusion.

A single human rating may support multiple methods when they retrieved the same pair. It is still one judgment in the evidence store.

## 16. Primary comparison

The primary effect is M4 versus M3:

```text
C + full-song MuQ
versus
C + existing centered30 MuQ
```

For each eligible anchor calculate:

```text
Δ unacceptable@5
Δ coherent@5
Δ mean rating@5
Δ known-good recall@5 when defined
```

For each comparison `(challenger, control)`, primary quality deltas use exactly the intersection of anchors with five numeric natural Top-5 ratings for both methods. Require at least 40 such anchors for any verdict comparison. Each method's denominator is five; shared unordered ratings may populate multiple slots but remain one judgment. Define every delta as challenger minus control. Compute known-good recovery deltas separately on all anchors with at least one eligible pre-run historical positive, independent of numeric Top-5 coverage; require at least 30 such anchors.

For incomplete quality data, report full-100 macro bounds: assign every nonnumeric slot first to an unacceptable/noncoherent rating of 1, then to a coherent rating of 5. For comparison bounds allow missing slots in challenger and control to take opposing extremes. These are descriptive missing-data bounds, not imputed primary scores.

Use 2,000 paired anchor-bootstrap replicates, NumPy `Generator(PCG64(20260906))`, sampling the eligible anchor IDs with replacement at the original eligible-set size, in ascending Spotify-ID order. Calculate percentile intervals at 2.5 and 97.5 using linear interpolation. Bootstrap each metric on its specified fixed eligible set; never bootstrap raw slots. Report eligible IDs, point means and intervals; undefined metrics are null with a reason. The interval describes anchor variation conditional on this selected corpus and mixed historical labels; it does not account fully for shared candidate dependence.

Report point estimates and 95% bootstrap intervals. Do not collapse the experiment into one p-value.

The most important product asymmetry is:

> Avoiding obviously incompatible playlist neighbors is more important than gaining a tiny average-rating improvement.

Therefore unacceptable-rate noninferiority is a prerequisite for recommending M4.

## 17. Secondary representation comparisons

Report the same descriptive metrics for:

```text
M1 C CLAP
M2 full-song MuQ
M3 C + fixed MuQ
M4 C + full-song MuQ
```

Also report frozen A and D historical reference metrics where compatible evidence exists.

Interpretation examples:

```text
M2 strong, M4 strong:
full-song MuQ contains useful independent geometry and complements C.

M2 strong, M4 weak:
MuQ may be useful, but the frozen fusion is not justified.

M1 ~= M4 and M3:
MuQ adds little playlist benefit on this frozen set.

M4 improves known-good recovery but adds bad neighbors:
coverage creates a recall/precision tradeoff; do not activate without a later rule.

M4 lowers bad neighbors and recovers more known-good pairs:
strongest case for using full-song fusion as clustering foundation.
```

## 18. Frozen advancement thresholds

The thresholds below are decision rules for choosing a **research foundation**, not production quality gates.

### 18.1 Common comparison predicates

All rate margins are absolute fractions. For challenger X versus control Y, define `ACCEPT(X,Y)` as all of:

- complete paired quality anchors >= 40 and positive-bank anchors >= 30;
- delta unacceptable <= +0.03 and its paired-bootstrap upper 95% bound < +0.05;
- delta coherent >= -0.03;
- delta mean rating >= -0.15.

Define `GAIN(X,Y)` as at least one point estimate: delta historical-positive recovery >= +0.08, delta unacceptable <= -0.05, or delta coherent >= +0.05. Define `WIN(X,Y) = ACCEPT(X,Y) and GAIN(X,Y)`.

Define `STABLE(X,Y)` by the following frozen checks:

1. Delete each primary eligible anchor once and recompute point estimates on the remaining anchors. The point-estimate conditions of ACCEPT and at least one GAIN condition must hold in every deletion. Do not recompute bootstrap intervals or minimum-count gates for these influence checks.
2. Track-node deletion: for each of the 100 track IDs, remove its anchor row and all candidate slots involving it without backfilling ranks. On the original complete paired quality anchor set, retain other anchors with at least one remaining slot for each method, calculate each method's rate using its remaining slots, and macro-average paired deltas. For positive recovery remove that node from both retrieved-positive numerators and eligible-positive denominators, omitting zero-denominator anchors. Require all deletions to remain computable. A strong reversal is delta unacceptable > +0.05, delta coherent < -0.05, or delta mean rating < -0.15; any strong reversal fails STABLE. Report every deletion and worst values.
3. Original-label sensitivity: replace intentional revisions with the unambiguous pre-run original label. Pre-run conflicts have no single original and are excluded from this sensitivity. Rebuild complete paired anchors without changing rankings. Require at least 30 paired anchors and 30 positive-bank anchors. Point-estimate ACCEPT and at least one GAIN condition must still hold. No applicable revisions/conflicts means this check is identical to the primary calculation. Insufficient sensitivity support fails STABLE.

Define `ROBUST_WIN = WIN and STABLE`. Report all predicates, including failed and undefined ones. Missing required data never evaluates as success.

### 18.2 Deterministic verdict precedence

First require all Section 13 support gates, successful full-100 materialization, historical integrity, and frozen review completion. Otherwise write `INCONCLUSIVE`.

Then evaluate these rows in order and choose the first matching verdict:

1. `RECOMMEND_C_CLAP_FOUNDATION`: ROBUST_WIN(M1,M3) and ROBUST_WIN(M1,M4).
2. `RECOMMEND_C_PLUS_FULL_MUQ_FOUNDATION`: ROBUST_WIN(M4,M3), ACCEPT(M4,M1), and not ROBUST_WIN(M2,M4).
3. `FULL_MUQ_PROMISING_FUSION_UNRESOLVED`: ROBUST_WIN(M2,M3) and ROBUST_WIN(M2,M4).
4. `KEEP_C_PLUS_EXISTING_MUQ_FOUNDATION`: ROBUST_WIN(M3,M4) and ACCEPT(M3,M1).
5. `INCONCLUSIVE`: all other cases, including small differences, overlapping uncertainty, conflicting comparisons, or failed sensitivities.

An inconclusive outcome may retain the existing research configuration operationally, but cannot claim that it is better. M2's promising verdict authorizes only a later separately designed fusion investigation. All foundation recommendations are provisional for subsequent clustering research on this owner-specific corpus, not global winners over A, D, or every possible representation.

Exactly one verdict is written. Freeze unit-test fixtures for each branch, overlapping predicates, insufficient support, equality at margins, and null inputs before analysis.

## 19. No production activation

Regardless of outcome, Stage 5E.3 must not:

- change the production representation pointer;
- change Spotify playlist output;
- create user playlists;
- implement clustering;
- choose a clustering algorithm;
- set cluster-admission thresholds;
- add rhythm, tonal, timbral, structural, or lyric features;
- tune fusion weights;
- train a classifier or ranker on the review labels;
- alter A, C, D, or centered30 MuQ artifacts.

The strongest permitted conclusion is:

> **Use representation X as the frozen learned backbone for the next clustering experiment.**

## 20. Preparation and immutability contract

Before full-song MuQ inference:

1. record Spotify repository HEAD;
2. hash this design note or its mirrored implementation spec;
3. hash Stage 5E.1 configuration and similarity matrices;
4. hash the Stage 5C.2 amended selected-source manifest;
5. hash Stage 5E.2 label evidence and every accepted rating artifact;
6. snapshot the exact 100 identities;
7. resolve the installed MuQ package/version and checkpoint revision;
8. freeze full-song MuQ chunk/padding/pooling configuration;
9. freeze retrieval tie-breaking;
10. freeze rating compatibility rules;
11. freeze review shuffle seed;
12. freeze decision thresholds.

`prepare` is create-once: an identical rerun verifies frozen files and returns without rewriting them; changed inputs/configuration require a new run directory and explicit amendment. Preserve an immutable original inference execution ledger; cache reruns write separate numbered ledgers and never replace original timings or forward-pass counts. Cache identities must hash embedding-affecting code/dependencies specifically, not report-only changes. Never relabel old embeddings with a new implementation identity to obtain cache hits.

`closeout` is likewise create-once for a particular frozen analysis snapshot. Byte-identical verification is permitted; changed labels or analysis code require a separately versioned closeout preserving the old one. After preparation, no formula may be changed because preliminary human outcomes look unfavorable.

Any necessary scientific amendment must:

- be written explicitly;
- create a new config hash;
- preserve the old run;
- happen before the amended run’s outcome is reviewed.

## 21. Cache identity

Full-song MuQ cache key must include at least:

```text
source_sha256
model_identity
model_revision
model_file_sha256
model_config_sha256
muq_package_version
sample_rate_hz
chunk_seconds
stride_seconds
final_partial_policy
segment_normalization
track_pooling
pooled_normalization
implementation_sha
embedding_environment_hash
```

Changing review thresholds or report formatting must not invalidate audio embeddings.

Persist chunk embeddings and track vectors atomically.

A second identical run must produce:

```text
100 expected track-level cache hits
0 unexpected MuQ forward passes
0 changed track vectors
```

subject to the exact frozen corpus and environment contract.

## 22. Engineering tests

### 22.1 Historical-lock tests

Assert:

- A identity exactly equals `A_CENTERED30_CURRENT_MUSIC_CLAP_V1`;
- C identity exactly equals `C_FULL_SONG_10S_CHUNK_MEAN_MUSIC_CLAP_V1`;
- D identity exactly equals `D_NATIVE_GLOBAL3_EQUAL_MEAN_GENERAL_AUDIO_CLAP_V1`;
- A/C checkpoint SHA matches the frozen Music CLAP hash;
- D checkpoint SHA matches the frozen general-audio hash;
- historical fixed MuQ remains centered `[5,15,25]` with three 5-second views;
- fusion weights equal `0.7172981519 / 0.2827018481`;
- no historical file is mutated.

### 22.2 Full-song MuQ tests

Test:

1. required 24 kHz input;
2. 10-second chunk size;
3. non-overlapping starts at exact 10-second increments;
4. complete source coverage;
5. one and only one final partial chunk when duration is not divisible by 10 seconds;
6. deterministic short-track handling;
7. deterministic final padding;
8. finite embeddings;
9. chunk L2 normalization;
10. equal arithmetic track mean;
11. final L2 normalization;
12. self-similarity approximately 1;
13. symmetric cosine matrix;
14. deterministic embedding/cache replay.

Use synthetic durations around boundaries:

```text
0.1
9.999
10.0
10.001
19.999
20.0
20.001 seconds
```

### 22.3 Retrieval tests

Assert:

- exactly 100 query identities;
- candidate universe restricted to the same 100;
- self/duplicate exclusions identical across methods;
- five eligible results per method when possible;
- stable Spotify-ID tie-breaker;
- shared unordered pair reviewed once globally in the live queue, including reciprocal appearances;
- forced probes do not alter natural ranks;
- forced known-good probes never count toward recall@5;
- forced known-bad probes never count toward false-positive recurrence.

### 22.4 Blinding tests

The blind payload must contain none of:

```text
method_id
score
rank
probe_type
known_rating
retrieved_by_methods
embedding identifier
```

Add tests that fail if these values appear in visible labels, element IDs, filenames, URLs, or serialized reviewer data.

### 22.5 Rating tests

Assert:

- accepted ratings are 1–5 or UNSURE;
- UNSURE remains nonnumeric;
- old labels are immutable;
- revisions append rather than overwrite;
- conflicting historical labels are explicit;
- incompatible scales cannot leak into metrics;
- duplicate source rows do not increase evidence count.

## 23. Suggested implementation layout

Prefer extending the existing Stage 5E code rather than creating parallel identity/rating logic.

Suggested files:

```text
ml/audio_similarity/src/audio_similarity/full_song_muq.py
ml/audio_similarity/src/audio_similarity/stage5e3_playlist_compatibility.py
ml/audio_similarity/src/audio_similarity/playlist_compatibility_eval.py
ml/audio_similarity/src/audio_similarity/cli/stage5e3.py

ml/audio_similarity/tests/test_full_song_muq.py
ml/audio_similarity/tests/test_stage5e3_playlist_compatibility.py
ml/audio_similarity/tests/test_stage5e3_review_blinding.py
ml/audio_similarity/tests/test_stage5e3_heavy.py
```

Reuse Stage 5E.1/5E.2 helpers for:

- corpus restriction;
- source identity;
- duplicate filtering;
- deterministic Top-K;
- rating compatibility;
- label provenance;
- browser/local-player review behavior;
- canonical hashing.

## 24. CLI contract

Suggested idempotent commands:

```text
prepare
embed-full-muq
build-similarities
build-review
review
snapshot-labels
analyze
closeout
run-all
```

### `prepare`

Freeze all historical inputs, configuration, model identity, corpus identity, and label compatibility.

### `embed-full-muq`

Run only missing full-song MuQ inference and populate the chunk/track cache.

### `build-similarities`

Create M1–M4 matrices using frozen inputs and exact fixed weights.

### `build-review`

Create natural Top-5 unions, deterministic probes, hidden mappings, and blinded review payloads.

### `review`

Serve unresolved/conflicted judgments and assigned frozen drift-probe repeats. Do not expose method metadata or aggregate outcomes until the post-review snapshot is frozen.

### `snapshot-labels`

Freeze the completed review snapshot used by analysis.

### `analyze`

Compute all predeclared coverage, quality, recovery, overlap, uncertainty, and sensitivity metrics.

### `closeout`

Write one representation recommendation with no production activation.

## 25. Required artifacts

Default report directory:

```text
ml/audio_similarity/reports/
stage5e3_full_song_muq_playlist_compatibility/frozen100_v1/
```

Required outputs:

```text
algorithm_spec.json
experiment_config.json
input_reference.json
baseline_reference.json
source_manifest.json
environment.json
full_song_muq_config.json
full_song_muq_chunk_manifest.parquet
full_song_muq_chunk_embeddings.npz
full_song_muq_track_embeddings.npz
full_song_muq_cache_rerun.json
similarity_matrices.npz
retrieval_top5.parquet
candidate_union.parquet
probe_manifest.parquet
rating_compatibility_audit.json
pre_review_rating_snapshot.json
review_manifest.json
review_blind_payload.json
review_submissions.jsonl
rating_revision_ledger.jsonl
post_review_rating_snapshot.json
review_reveal.json
rating_coverage.json
playlist_compatibility_metrics.json
known_good_recovery.json
known_false_positive_recurrence.json
method_overlap.json
paired_method_comparison.json
track_node_sensitivity.json
revision_sensitivity.json
closeout.json
experiment_report.md
artifact_manifest.json
```

The artifact manifest hashes every final artifact except itself and intentionally append-only live-review state, whose frozen post-review snapshot receives its own hash. Sort manifest entries by relative path. Serialize JSON with sorted keys, UTF-8, finite numbers only and a final newline; freeze Parquet writer settings and row sort keys in algorithm_spec.json; write NPZ members in stable name order with fixed archive timestamps. Keep wall-clock timings and run timestamps in immutable execution ledgers, not regenerated scientific outputs. Hash-verify all listed files after writing and verify every frozen historical input remains unchanged.

Also require `original_execution_ledger.json`, separate cache-rerun ledgers, `track_status.json`, `review_playback_policy.json`, `missing_rating_bounds.json`, and `verdict_predicates.json`.

## 26. Execution sequence

### Phase A — Freeze historical contracts

- resolve A/C/D config and hashes;
- resolve fixed MuQ identity;
- resolve amended original100 membership;
- snapshot compatible ratings;
- freeze exact evaluation semantics and thresholds.

### Phase B — Validate MuQ implementation before human outcomes

- implement native 10-second chunk schedule;
- implement deterministic final partial handling;
- test pooling;
- run synthetic boundary tests;
- run a tiny retained-audio smoke test;
- freeze `algorithm_spec.json`.

### Phase C — Materialize full-song MuQ

- cache-first inference over the frozen 100;
- preserve chunk vectors;
- pool track vectors;
- validate finite outputs and norms;
- rerun to prove cache reuse.

### Phase D — Freeze retrieval and review queue

- construct M1–M4 similarities;
- generate Top-5 per anchor;
- build natural union;
- add deterministic known-good/known-bad probes;
- reuse compatible ratings;
- blind and shuffle unresolved candidates and assigned drift probes;
- hash review manifest before live review.

### Phase E — Human review

- review one anchor packet at a time;
- submit complete packets; reveal metadata only after the entire review snapshot is frozen;
- preserve UNSURE;
- append revisions rather than changing old files;
- do not inspect running aggregate method results.

### Phase F — Analysis

- freeze post-review label snapshot;
- calculate coverage;
- calculate unacceptable/coherent metrics;
- calculate known-good recovery;
- calculate known-bad recurrence;
- calculate method overlap;
- perform paired anchor bootstrap;
- run track-node, conflict, and revision sensitivities.

### Phase G — Closeout

Write exactly one:

```text
RECOMMEND_C_PLUS_FULL_MUQ_FOUNDATION
KEEP_C_PLUS_EXISTING_MUQ_FOUNDATION
RECOMMEND_C_CLAP_FOUNDATION
FULL_MUQ_PROMISING_FUSION_UNRESOLVED
INCONCLUSIVE
```

Then hash artifacts and verify that no production pointer or historical representation was modified.

## 27. Definition of done

Stage 5E.3 is complete only when:

1. A, C, D, and fixed MuQ identities are verified against frozen artifacts;
2. exact original100 membership is verified on both axes;
3. full-song MuQ uses the frozen 24 kHz / 10-second contract;
4. full-song MuQ chunking/padding/pooling passes deterministic engineering tests;
5. only missing full-song MuQ inference is executed;
6. cache replay causes zero unexpected inference;
7. M1–M4 matrices are frozen before review;
8. natural Top-5 candidate unions and probe sets are frozen before review;
9. scores, ranks, methods, and probe identities are hidden during review;
10. compatible historical ratings are reused with complete provenance;
11. revisions are append-only;
12. shared tracks/pairs are reviewed once but credited correctly to every retrieving method;
13. rating coverage gates are satisfied or the result is explicitly `INCONCLUSIVE`;
14. unacceptable matches and known-good recovery are reported for every primary method;
15. M4 versus M3 is evaluated with paired anchor-level uncertainty;
16. A and D remain visible as historical references without reinterpretation;
17. no fusion weight is tuned on evaluation ratings;
18. no clustering or cluster-admission logic is implemented;
19. no production representation is activated;
20. exactly one representation recommendation is written and artifact-hash verified.

## 28. What a positive result means

If M4 wins under the frozen gates, the conclusion should be narrow:

> **With C CLAP and fusion weights held fixed, replacing historical five-second MuQ views with equally pooled full-recording ten-second views improves this frozen-100 benchmark enough to recommend that representation policy provisionally for the next clustering experiment. The experiment does not isolate coverage from context length or pooling effects.**

It does not mean:

- every playlist should use the same global distance threshold;
- full-song mean pooling is permanently optimal;
- handcrafted MIR attributes are unnecessary;
- cluster admission has been solved;
- production is ready.

## 29. What a negative or neutral result means

If M4 fails to beat M3, that is useful evidence.

Possible interpretations include:

- the historical three five-second views may capture enough MuQ signal for this use case;
- equal full-song pooling dilutes salient local moments;
- CLAP benefits from broad coverage more than MuQ does;
- MuQ contributes little after full-song C;
- playlist compatibility is driven by local or conditional factors not captured by global mean embeddings.

Do not respond by tuning weights on the same ratings. Preserve the result and design the next experiment from the observed failure mode.

## 30. Relationship to clustering

The next clustering stage should begin only after this benchmark chooses a representation foundation or explicitly concludes that the evidence is insufficient.

The intended ordering is:

```text
choose learned song representation
        ↓
freeze representation for clustering research
        ↓
measure neighborhood / cluster structure
        ↓
choose clustering algorithm and stability protocol
        ↓
validate cluster coherence
        ↓
only then design cluster-admission / playlist-write policy
```

This prevents cluster algorithm choices from obscuring a more basic representation problem.
