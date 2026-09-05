# Stage 5B.4A — Natural Multi-Artist Query Contract Repair

**Verdict: FAIL.** Both searches executed, but at least one repaired case still lacked a SAFE candidate in the top three.

## Decision

Do not freeze the repaired contract. No additional query heuristic is introduced in this phase.
Representative V3 remains unchanged and is not reinterpreted; this work is recorded only as `QUERY_CONTRACT_REPAIR_SUPPLEMENT`.

## Contract

The builder starts from the raw Spotify display title, performs only mechanical Unicode/quote/control/whitespace sanitation, then appends up to the first three distinct Spotify-credited artists in credited order. It adds no `official` token, exact-match quotes, Boolean syntax, semantic title stripping, inferred artists, or song-specific behavior.

## Offline V3 replay

All 100 frozen V3 tracks produced non-empty queries; failures: 0; maximum artists included: 3; harmless-punctuation rejections: 0. No YouTube request was made during replay.

## Bounded repair discovery and human review

### Girl, Interrupted — 2xxx / Miso

Exact query: `Girl, Interrupted 2xxx Miso`

Provider error: `null`; warnings: `[]`; yt-dlp returned zero candidates, so no human candidate label was possible; first SAFE rank: **none**. The provider supplied no error or warning that would explain the empty result.

| Rank | Video ID | Title | Uploader/channel | Duration | Views |
|---:|---|---|---|---:|---:|

### All The Stars (with SZA) - From "Black Panther: The Album" — Kendrick Lamar / SZA

Exact query: `All The Stars (with SZA) - From Black Panther: The Album Kendrick Lamar SZA`

Provider error: `null`; warnings: `[]`; first SAFE rank: **1**.

| Rank | Video ID | Title | Uploader/channel | Duration | Views |
|---:|---|---|---|---:|---:|
| 1 | `ju4KQT0wL0I` | All The Stars | Kendrick Lamar / Kendrick Lamar | 233.0 | 104911221 |
| 2 | `GfCqMv--ncA` | Kendrick Lamar, SZA - All The Stars | Kendrick Lamar / Kendrick Lamar | 237.0 | 80850470 |
| 3 | `JQbjS0_ZfJ0` | Kendrick Lamar, SZA - All The Stars | Kendrick Lamar / Kendrick Lamar | 235.0 | 738967296 |

## Scope and history guards

- Live YouTube searches: 2, sequential, metadata-only `ytsearch3`.
- Full V3 discovery reruns: 0.
- Stage 5B.3 selector changes or invocations: 0.
- Audio/video downloads, proof-heavy resolver, Sol, CLAP, and MuQ runs: 0.
- Historical V3 artifacts overwritten: 0; their identities are pinned in `repaired_query_contract.json` and `artifact_manifest.json`.

## Reproduction

```bash
uv run python -m audio_similarity.cli.stage5b4a_query_contract_repair offline
uv run python -m audio_similarity.cli.stage5b4a_query_contract_repair discover
uv run python -m audio_similarity.cli.stage5b4a_query_contract_repair build-review
# Apply sequential human labels to human_review.csv, then:
uv run python -m audio_similarity.cli.stage5b4a_query_contract_repair finalize
```
