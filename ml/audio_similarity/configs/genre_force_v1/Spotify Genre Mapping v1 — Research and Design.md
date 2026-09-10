---
title: Spotify Genre Mapping v1 — Research and Design
project: Spotify Sorter
status: development-explorer-design
mapping_version: genre-neighborhood-v1-draft
scoring_revision: canonical-first-residual-v1
revised: 2026-09-10
source_commit: 190a12596968ed84245aa1a880cdfae97214fe94
tags:
  - spotify-project
  - audio-similarity
  - music-information-retrieval
  - genre-mapping
  - research-design
  - development-experiment
---

# Spotify Genre Mapping v1 — Research and Design

## Current decision

Keep Gemini's frozen free-form genre/style classifications unchanged. Do not modify the Gemini prompt and do not make new Gemini calls for this stage.

The larger 138-concept / 29-neighborhood mapper is the current genre representation candidate. Manual review so far indicates that its **canonical concepts are the strongest part of the representation**. Therefore the current design is **canonical-first**:

- canonical concepts are the primary pairwise genre-comparison signal;
- neighborhood support is primarily an indexing/retrieval representation and a secondary bridge between different-but-related canonical concepts;
- neighborhood-only pair scoring remains available as a diagnostic, not the preferred default;
- genre remains an additive evidence channel on top of the existing audio score and does not retrain or rescale the audio model.

The **full frozen 100-song corpus is the development surface for the interactive scoring experiment**. The original 16-song subset remains useful for mapper/Gemini sanity review and as an optional UI filter, but it is not the primary scoring dataset. With 100 songs there are only 4,950 unordered pairs, so exhaustive pairwise development scoring is trivial.

The full 138-concept taxonomy rationale is preserved in [[Spotify Genre Mapping v1 — Taxonomy Research Reference]]. The machine-readable concept registry remains `genre-neighborhood-map-v1.json`.

## Source-of-truth precedence

For current development work use, in order:

1. this note for architecture and experiment sequence;
2. `genre-force-explorer-v1.json` for the current pairwise fusion / UI contract;
3. `genre-neighborhood-map-v1.json` for canonical concepts, aliases, families, neighborhoods and membership relations;
4. [[Spotify Genre Mapping v1 — Taxonomy Research Reference]] for full taxonomy research and historical rationale.

The old `scoring_boundary` inside `genre-neighborhood-map-v1.json` remains a non-authoritative placeholder. Do not treat it as the current scorer.

## 1. Representation architecture

Each song keeps **two derived representations from the same immutable Gemini output**.

### A. Canonical concept profile

This preserves the most precise normalized interpretation of Gemini's labels.

Examples:

- `R&B`, `RnB`, `rnb` → canonical R&B/soul family concept;
- `Alt-R&B` → canonical Alternative R&B style concept;
- `Contemporary R&B` → canonical Contemporary R&B style concept;
- `Dance-Pop` → canonical Dance-pop style concept;
- `K-Pop` → canonical scene/context concept.

Canonicalization resolves naming noise while preserving real musical distinctions. Alternative R&B and neo-soul remain different concepts. Hyperpop and electropop remain different concepts. Afrobeat and Afrobeats remain different concepts.

For sonic pairwise scoring, use only eligible musical concepts. Scene/context-only, unresolved, ambiguous, review-required-without-specific-evidence and non-sonic facet concepts contribute zero by default.

### B. Neighborhood profile

Canonical style concepts may also map into one or more broader overlapping style neighborhoods such as R&B/soul, boom bap/jazz-hop, lo-fi/chillhop, trap/cloud-rap, downtempo/trip-hop, synth/dance-pop, house/nu-disco, techno and ambient/drone.

This representation intentionally compresses exact style identity in order to encode relationships between different canonical concepts.

```text
Gemini labels
    ↓
canonical concepts ───────────────→ precise pairwise comparison
    │
    └─ concept→neighborhood map ──→ indexing/retrieval + cross-concept relation
```

Neighborhoods do not replace canonical concepts.

## 2. Why use both

Canonical concepts answer:

> How much do the songs' explicit normalized classifications agree?

Neighborhoods answer:

> Where exact labels differ, do those different concepts still occupy related stylistic territory?

`Alternative R&B ↔ Alternative R&B` should receive strong exact canonical agreement. `Alternative R&B ↔ Neo-soul` has different exact style identities but can still receive limited residual relationship support through the shared R&B/soul neighborhood.

The neighborhood layer is most valuable for **bridging different exact concepts** and for **retrieving candidate songs** that exact concept lookup or audio geometry might otherwise miss.

## 3. Canonical pairwise similarity

Represent each song as a sparse vector over eligible canonical musical concepts.

Use the mapper's existing field strengths as the first development defaults:

- primary style: 1.0;
- secondary style: 0.5;
- primary family: 0.5;
- secondary family: 0.25.

Repeated aliases and duplicate routes must not add duplicate mass. Scene/context labels and non-sonic facets are retained for display and future experiments but contribute zero to this sonic genre score.

Require at least one usable specific style-like concept on both tracks before canonical genre scoring is considered informative. Broad-family-only profiles are a no-op for the first experiment rather than a perfect match.

The primary exact-concept comparison is weighted Jaccard:

```text
J_canonical(a,b)
  = Σ_k min(c_a[k], c_b[k])
    / Σ_k max(c_a[k], c_b[k])
```

with range `[0,1]`. This score is not a probability of playlist compatibility.

## 4. Residual neighborhood bridge

The preferred fusion does **not** simply average full canonical Jaccard and full neighborhood Jaccard because that would double-count exact matches that already share a neighborhood.

Instead:

1. compute exact matched canonical mass;
2. remove matched mass from both profiles;
3. project only the remaining unmatched eligible style concepts through the concept→neighborhood mapping;
4. compare those residual neighborhood profiles with weighted Jaccard.

```text
matched[k] = min(c_a[k], c_b[k])
residual_a[k] = c_a[k] - matched[k]
residual_b[k] = c_b[k] - matched[k]
```

Only eligible unmatched style-like concepts are projected to neighborhoods. Broad family concepts do not create residual neighborhood support by themselves.

```text
J_residual_neighborhood(a,b)
  = weighted Jaccard(neighborhood(residual_a), neighborhood(residual_b))
```

If either side has no usable residual neighborhood evidence, this term is zero.

## 5. Canonical-first genre score

The current preferred development score is:

```text
G_genre(a,b)
  = J_canonical
    + eta * (1 - J_canonical) * J_residual_neighborhood
```

where `eta ∈ [0,1]` controls how much broader cross-concept relationships are allowed to fill the remaining headroom after exact concept agreement.

Initial development default: `eta = 0.25`.

This is an engineering starting point, not a calibrated musical truth. `eta` may be explored interactively on the frozen 100 development set, but once the 100 has been inspected or used to choose parameters it is development data and must not be described as fresh confirmation.

## 6. Diagnostic pairwise modes

The frontend should allow three comparison sources for `G`:

- `canonical_only`: `G = J_canonical`;
- `canonical_plus_residual`: `G = J_canonical + eta * (1 - J_canonical) * J_residual_neighborhood` — preferred current candidate;
- `neighborhood_only_diagnostic`: weighted Jaccard over the full neighborhood profiles — retained only to compare against the earlier neighborhood-first proposal.

## 7. Neighborhood role in retrieval and indexing

Neighborhoods remain highly useful even if canonical concepts win pairwise scoring.

For each song, store its full neighborhood vector and maintain an index that can retrieve stylistically related candidates.

```text
Candidates(a)
  = TopK_audio(a)
    ∪ TopK_neighborhood(a)
```

The union is deduplicated before final scoring. Neighborhood retrieval only decides which candidates are considered; it does **not** automatically make those candidates good matches.

For the current frozen 100 explorer, exhaustive all-pairs scoring is small enough that retrieval is not required for correctness. Retrieval behavior can still be shown as a diagnostic because it matters for the eventual larger library.

## 8. Overall score combination

Genre remains independent additive evidence on top of the current frozen audio score:

```text
S_adjusted(a,b)
  = S_audio(a,b)
    + alpha * beta * G_mode(a,b)
```

where `S_audio` is the existing frozen C + M score, `alpha ∈ [0,1]` is the user-facing genre-strength slider, and `beta` is the maximum genre contribution in score units. Initial `beta = 0.05`.

`alpha = 0` must reproduce the exact current audio baseline. Do not multiply or renormalize the audio score by genre.

## 9. Pull-only versus signed development ablation

**Pull-only is the default:** `G_pull = G_mode`. No shared genre evidence means no bonus, not a penalty.

Retain an explicitly experimental signed switch for development inspection only:

```text
G_signed = 2 * G_mode - 1
```

only when both tracks have usable specific genre evidence; otherwise signed genre contribution is zero. This signed transformation is a low-overlap penalty ablation, not a learned notion of genre incompatibility.

## 10. Frontend explorer requirements

Use the **entire frozen 100-song development set** as the main interactive explorer corpus. The original 16 may remain as an optional filter for quick semantic review, but score/rank behavior should be computed against all 99 other candidates for each anchor.

Expose:

- all 100 songs as anchors;
- pairwise source mode: `canonical_only`, `canonical_plus_residual`, `neighborhood_only_diagnostic`;
- polarity mode: `pull_only`, `signed_experimental`;
- `alpha` slider 0–1;
- visible `beta` and `eta` values;
- original audio score and adjusted score simultaneously;
- original and adjusted rank among the full 99-candidate anchor list;
- exact shared canonical concepts;
- canonical union / unmatched concepts;
- `J_canonical`;
- residual contributing neighborhoods;
- `J_residual_neighborhood`;
- final `G_mode`;
- applied genre delta;
- raw Gemini labels, canonical concepts and warnings;
- read-only `vocal_role` and `arrangement_focus` for context, with zero effect on this genre-only experiment.

Useful 100-song diagnostics should include top-K entry/exit, largest rank movers, distribution of genre deltas, and cases where a candidate is retrieved by neighborhood support but not by the original audio neighborhood.

The graph should have two behaviors:

- `Move graph = off` by default: coordinates remain frozen; only scores, ranks and diagnostics change.
- `Move graph = on`: derive a temporary layout from adjusted edge weights. Never overwrite frozen graph artifacts.

Physical graph distance remains approximate. Pair scores and ranks are the authoritative comparison.

## 11. Development sequence

1. Keep the larger 138-concept mapper unchanged.
2. Use the already-reviewed original 16 and additional spot checks only for mapper/Gemini semantic sanity; do not make the 16 the scoring surface.
3. Implement canonical weighted-Jaccard scoring across the **full frozen 100**.
4. Implement residual-neighborhood fusion and retain neighborhood-only as a diagnostic across the same 100.
5. Build the interactive 100-song explorer with full 99-candidate rankings per anchor, alpha/beta/eta controls, score deltas, rank changes and traces.
6. Explore pull-only first; keep signed mode as a separate ablation.
7. Treat all parameter/mode choices informed by this page as development choices on the frozen 100.
8. Freeze the chosen mapper/scoring rule before any fresh confirmatory evaluation on new held-out songs/pairs.

## 12. Invariants

- No new Gemini calls.
- No Gemini prompt changes.
- Raw Gemini outputs remain immutable.
- No song- or artist-specific mapper exceptions.
- Canonical concepts are preserved even when neighborhoods are derived.
- Neighborhoods do not overwrite canonical style identity.
- Scene/context labels do not silently become sonic similarity.
- Broad-family-only evidence is not a perfect pairwise match.
- Unresolved / ambiguous / review-required evidence is a no-op unless explicitly resolved.
- Vocal/arrangement fields remain read-only and orthogonal during this genre-only stage.
- The frozen 100 may be used for development/tuning, but after inspection it is not a fresh confirmatory set.
- No production playlist activation.

## Navigation

- [[Spotify Genre Mapping v1 — Artifact Index]]
- [[Spotify Genre Mapping v1 — Taxonomy Research Reference]]
- [[Spotify Sorter]]
