# Genre Registry v1 — Current Operational Contract

This folder contains the larger **138-concept / 29-neighborhood** genre mapper and its historical research bundle.

For current development work, use the following precedence:

1. `CURRENT.md` — current architecture and implementation sequence.
2. `genre-force-explorer-v1.json` — current pairwise/retrieval/scoring contract.
3. `genre-neighborhood-map-v1.json` — authoritative canonical concepts, aliases, families, neighborhoods and membership relations.
4. `research-and-design.md` — full taxonomy/research reference and historical design rationale.

The `scoring_boundary` embedded in `genre-neighborhood-map-v1.json` is a historical placeholder only. Do **not** implement the old neighborhood-first `S_CLAP_C + lambda * r_style` idea as the current scorer.

## Current architecture

Keep the frozen Gemini classifications unchanged.

```text
Gemini frozen labels
        ↓
canonical concepts ───────────────→ primary pairwise genre comparison
        │
        └─ neighborhood profile ──→ indexing/retrieval + residual relation
```

Canonical concepts are the primary pairwise signal because manual review indicates that the normalized concepts are highly descriptive. Neighborhoods remain useful as a lower-dimensional relationship/indexing representation.

## Pairwise genre scoring

Primary exact comparison:

```text
Jc(a,b) = weighted Jaccard over eligible canonical concepts
```

Use mapper field weights as the initial development defaults:

- primary style: 1.0
- secondary style: 0.5
- primary family: 0.5
- secondary family: 0.25

Scene/context-only, non-sonic facet, unresolved and unsupported review-required concepts do not contribute to sonic pairwise scoring. Broad-family-only profiles are a no-op rather than a perfect genre match.

### Residual neighborhood bridge

After exact canonical overlap is accounted for, project only the unmatched eligible style concepts into neighborhoods and compare those residual neighborhood profiles:

```text
matched[k] = min(c_a[k], c_b[k])
residual_a[k] = c_a[k] - matched[k]
residual_b[k] = c_b[k] - matched[k]

Jnr = weighted Jaccard(
  neighborhood(residual_a),
  neighborhood(residual_b)
)
```

Preferred development fusion:

```text
G = Jc + eta * (1 - Jc) * Jnr
```

with initial `eta = 0.25`.

This gives exact canonical identity priority while allowing related-but-not-identical styles limited partial credit. It avoids double-counting exact matches through their shared neighborhoods.

## Diagnostic modes

The frontend should compare:

- `canonical_only` → `G = Jc`
- `canonical_plus_residual` → preferred current candidate
- `neighborhood_only_diagnostic` → full neighborhood weighted Jaccard, retained only to compare with the earlier neighborhood-first idea

## Neighborhood role in retrieval

Neighborhoods are also intended for candidate indexing/retrieval:

```text
Candidates(anchor)
  = TopK_audio(anchor)
    union TopK_neighborhood(anchor)
```

Deduplicate the union before final scoring. Neighborhood retrieval affects candidate availability only; it does not automatically make a candidate a strong final match.

## Overall development score

Keep genre additive and independent of the frozen audio score:

```text
S_adjusted = S_audio + alpha * beta * G_force
```

where:

- `S_audio` is the existing frozen C + M score;
- `alpha` is the 0–1 frontend genre-strength slider;
- `beta` defaults to 0.05 for the first explorer;
- pull-only is the default: `G_force = G`;
- signed mode is an experimental low-overlap penalty only: `G_force = 2G - 1` when both tracks have usable specific genre evidence.

A negative signed result is not evidence of true genre incompatibility.

## Development sequence

1. Implement the 138-concept mapper unchanged.
2. Manually review the original 16 frozen Gemini profiles.
3. Implement canonical weighted-Jaccard scoring.
4. Implement residual-neighborhood fusion.
5. Compare the three pairwise source modes on the same 16.
6. Use pull-only as the default; keep signed mode as a development ablation.
7. Show original score, adjusted score, rank changes and the exact contributing concepts/neighborhoods in the frontend.
8. Only then apply the unchanged definitions to the frozen 100 development set.
9. Freeze a chosen rule before any fresh confirmatory evaluation.

No new Gemini calls, Gemini prompt changes, song-specific mapper hacks, or production playlist activation are allowed in this stage.
