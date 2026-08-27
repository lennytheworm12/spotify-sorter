# Stage 4A FMA 30-second amendment

The governing Obsidian design superseded the mandatory MUSDB18 + MedleyDB corpus gate before any Stage 4 retrieval scoring or human labels.

Historical/reusable commits remain intact:

- `c42fe95` — full-track readiness tooling
- `a14e9e8` — official MedleyDB tracklist validation

The active corpus is FMA Small. This freeze contains 7,994 eligible clips (8,000 manifest rows minus three decode failures and three clips shorter than 29.5 seconds), exactly 80 pre-score queries, complete source/canonical-PCM identities, and only `CENTER5`, `UNIFORM3_MEAN`, and `UNIFORM5_MEAN`.

FMA Large bulk encoding, fusion, and Stage 4B are not authorized by this freeze.
