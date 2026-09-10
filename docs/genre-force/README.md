# Canonical-first genre force explorer

This development-only explorer scores all 4,950 unordered pairs of the original
frozen 100. Each anchor sees all 99 candidates. It reuses the existing Song Space
renderer/layout worker, private audio bridge and frozen Gemini source plumbing.
The old mapper comparison and saved review answers remain separate.

## Governing contract and unresolved baseline

The local Obsidian checkout was behind the remote vault. The current note,
138-concept registry and force contract were read from vault commit
`e19e8eadb84b143bd5ae81171d278647c707ccba` and pinned in
`ml/audio_similarity/configs/genre_force_v1/`. The registry bytes equal the already
implemented 138-concept mapper. The force contract is revision 1.2,
`canonical-first-residual-v1`; it supersedes the registry's old scoring placeholder.

The docs say “existing frozen C + M,” but Stage 5E.3 contains two such matrices:
M3 with existing centered30 MuQ, and M4 with full-song MuQ. The exporter requires
an explicit matrix key; it never chooses one silently or recomputes fusion.
Owner clarification was requested before freezing the actual exploratory run.
The independent real-data preparation has completed in
`.research_audio/genre_force/prepared_v1/`: 100 profiles, 99 with specific style
evidence, all 100 source identities/hashes aligned with the frozen audio sources.
`prepared_genres.json` deliberately contains no audio pair scores and cannot be
loaded as a completed explorer packet until the baseline is chosen.

## Scoring and scope

Canonical vectors include reviewed `family`, `style`, and `style_umbrella` concepts
at the prescribed field weights. Duplicates use maximum, not addition. Both tracks
must contain a reviewed `kind=style` concept to open the specificity gate. The
registry's broad Rap/Electronica umbrellas cannot open that gate alone. Family
concepts may contribute to Jc once it opens; they cannot create residual support.
This is a change from the old mapping-only step, which did not score families.

Jc is canonical weighted Jaccard. Exact shared mass is subtracted before projecting
unmatched styles into neighborhoods using the existing core/related weights and
coordinatewise maximum. Empty residual evidence gives Jnr=0.

`G = Jc + eta * (1 - Jc) * Jnr`, default eta=.25. Canonical-only and full-neighborhood
Jaccard remain explicit alternatives. Pull-only uses G; signed_experimental uses
2G-1. Insufficient specific evidence is a no-op in every mode, including signed.

`adjusted = frozen_audio + alpha * beta * G_force`. Alpha starts at 0 and ranges
0..1. Beta starts at .05 (manual UI range 0..0.20), eta at .25 (0..1). No automatic
parameter selection, rating ingestion, new model calls or production writes occur.
Scores are not normalized, clipped, calibrated probabilities, or inferred labels.

The table shows every candidate's original/adjusted scores and ranks, delta and G.
The inspector shows union/shared/unique/residual canonical mass, recovered
neighborhood relationships, exclusions, raw labels, mapping traces, coefficients,
Jc/Jnr/Jn, vocal and arrangement context. The latter have zero score effect.
Top-K movement, delta distributions and neighborhood-only retrieval candidates
are diagnostics, never verified corrections of human-bad pairs.

## Coordinates

The existing frozen100 graph export contains CLAP C, not C+MuQ. Its original
layout is reproduced with the unchanged seeded Song Space engine and saved in the
new run. Move graph off retains those coordinates exactly while scores/ranks and
Top-12 display edges update. The origin is labeled in the UI. Move graph on derives
a temporary adjusted layout; returning off or setting alpha=0 restores the saved
positions. No old graph file is overwritten. Pairwise ranks, not screen distance,
are authoritative. Layout uses Top-12 edges; scoring always uses 99 candidates.

## Prepare and launch (after baseline confirmation)

From `ml/audio_similarity`, use an explicitly confirmed key:

```sh
.venv/bin/python -m audio_similarity.genre_force_export \
  --audio-key M3_C_PLUS_FIXED_MUQ --output .research_audio/genre_force/v1
```

If the intended baseline is M4, use `M4_C_PLUS_FULL_MUQ` and a separate run folder.
From `frontend`:

```sh
node --import tsx dev/freezeGenreForce.ts ../ml/audio_similarity/.research_audio/genre_force/v1
SONG_SPACE_DATA_DIR="$PWD/../ml/audio_similarity/.research_audio/song_space/v3" \
GENRE_FORCE_DATA_DIR="$PWD/../ml/audio_similarity/.research_audio/genre_force/v1" \
pnpm dev --port 5174
```

Open `http://127.0.0.1:5174/#/genre`. The private GET-only bridge is opt-in and not
bundled into production. A clean replay verifies identical bytes and makes zero
inference/API calls. Existing source hashes, exact matrix identity and conversion
provenance are retained; a corrected Gemini source mismatch is displayed rather
than silently treated as the frozen audio source.

The 100 songs are development data. A chosen rule/parameter set must be frozen
before new track/source-disjoint confirmation; nothing here establishes a winner.
