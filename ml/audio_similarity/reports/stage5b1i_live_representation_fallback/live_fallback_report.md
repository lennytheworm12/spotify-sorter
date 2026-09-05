# Stage 5B.1I — Representation-Equivalent Live Fallback

Status: `STAGE5B1I_LIVE_REPRESENTATION_FALLBACK_EVALUATED`

## Outcome

The frozen Stage 5B.1H control reproduced exactly at **42/50 AUTO_MATCH and 8/50 MATCH_UNCERTAIN** with every prior candidate ID unchanged. The new ordinary-live fallback recovered **0** tracks, so measured coverage remains **42/50 (84%)**.

This zero-gain result is informative: the one unresolved ordinary-live target has no conflict-free canonical studio candidate in its frozen Q0 top five. The experiment does not loosen identity rules or relabel an uncorroborated user upload as representation-equivalent.

## Decision contract

Stage 5B.1I records two distinct outcomes:

- `EXACT_RECORDING`: the frozen Stage 5B.1H resolver selected the requested recording.
- `REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK`: exact-live resolution failed, then a canonical studio recording was selected for downstream CLAP/MuQ representation.

Exact recording always wins. The fallback runs only for an ordinary live target whose only material version family is `live`. Live targets that also specify acoustic, orchestral, remix, instrumental, remaster, slowed/sped/reverb, or another arrangement-changing identity remain unresolved.

A fallback candidate requires strong structural title and performer identity, no cover/performer/version/modification conflict, no evidence of another live performance, no production-changing candidate version, and strong artist, Topic, label/distributor, or structured-release provenance. Unknown provenance remains neutral in the general resolver but is insufficient by itself for this approximation.

Live-target versus studio-candidate duration is retained for inspection but is not an eligibility or preference signal. Live and studio performances legitimately differ in crowd interaction, tempo, and performance structure.

## Frozen live-target replay

| Track | Target | Classification | Risk | Exact candidates | 1H outcome | Studio fallback candidates | 1I mode |
|---|---|---|---|---:|---|---:|---|
| `s5b1c_026` | Free Fallin' - Live at the Nokia Theatre, Los Angeles, CA - December 2007 | `ORDINARY_LIVE` | `ELEVATED` | 2 | `AUTO_MATCH` | 0 | `EXACT_RECORDING` |
| `s5b1c_027` | Slow Dancing in a Burning Room - Live at the Nokia Theatre, Los Angeles, CA - December 2007 | `ORDINARY_LIVE` | `ELEVATED` | 1 | `AUTO_MATCH` | 0 | `EXACT_RECORDING` |
| `s5b1c_028` | Hotel California - Live on MTV, 1994 | `ORDINARY_LIVE` | `ELEVATED` | 1 | `AUTO_MATCH` | 0 | `EXACT_RECORDING` |
| `s5b1c_029` | The Night We Met - Live at the Ryman | `ORDINARY_LIVE` | `ELEVATED` | 0 | `MATCH_UNCERTAIN` | 0 | `NONE` |

## Unresolved ordinary-live candidate evidence

### `s5b1c_029` — The Night We Met - Live at the Ryman

| Rank | Candidate | Canonicality | Live evidence | Eligible | Failed gates |
|---:|---|---|---:|---:|---|
| 1 | `N2K1LUWlF-4` The Night We Met by Lord Huron @ Ryman Auditorium | `CANONICAL_UNKNOWN` | true | false | strong_core_title_identity, candidate_is_not_another_live_performance, canonical_studio_provenance |
| 2 | `7QADmsRUGgg` Lord Huron “The  Night We Met” | `CANONICAL_UNKNOWN` | true | false | candidate_is_not_another_live_performance, canonical_studio_provenance |
| 3 | `lx0T48q_eg8` Lord Huron - The Night We Met | `CANONICAL_UNKNOWN` | false | false | canonical_studio_provenance |
| 4 | `z4JfPakDYiU` Lord Huron - The Night We Met, Bonner MT, 5/25/2025 live | `CANONICAL_UNKNOWN` | true | false | strong_core_title_identity, candidate_has_no_production_changing_version, candidate_is_not_another_live_performance, canonical_studio_provenance |
| 5 | `5q2KTSVV7PY` Lord Huron - The Night We Met - (Toronto, June 26, 2023) | `CANONICAL_UNKNOWN` | false | false | canonical_studio_provenance |

The frozen pool consists of uncorroborated live/user-upload evidence. It does not contain a candidate with artist, Topic, distributor, or release-backed studio provenance, so representation equivalence cannot be established safely.

## Measurement

- live targets identified: **4**
- ordinary live targets: **4**
- arrangement-changing live targets: **0**
- exact live AUTO_MATCHes: **3**
- ordinary-live exact failures: **1**
- studio fallback opportunities in frozen Q0: **0**
- new representation-equivalent AUTO_MATCHes: **0**
- remaining MATCH_UNCERTAIN: **8**
- absolute coverage change: **0 percentage points**
- human-review queue: **0 candidates** (`NO_REVIEW_REQUIRED`)

## Safety and scope

No existing exact selection changed. No non-live version semantics changed. Remix, acoustic, instrumental, karaoke, remaster, extended/radio mix, rerecording, slowed/sped/reverb, nightcore, bass-boosted, mashup, and arrangement-changing live targets remain exact-only. Explicit performer, cover, and version conflicts remain hard negatives.

Searches 0; audio/video downloads 0; Sol runs 0; human labels changed 0; Stage 5A, CLAP, and MuQ calls 0. This policy is evaluated offline and is not production-activated.

## Representation risk and future validation

Ordinary unqualified live targets are marked `LOW`; venue/year-specific ordinary live targets are marked `ELEVATED` because the requested performance may differ more materially even though fallback is allowed. Arrangement-changing live targets are `UNSUITABLE` and never receive studio fallback.

A later audio experiment should compare exact live audio against its studio fallback using CLAP cosine, MuQ cosine, the frozen combined similarity, and nearest-neighbor overlap. That experiment was not run here.

## Recommendation

Keep the explicit match-mode abstraction: it faithfully represents the product tradeoff and is covered by deterministic safety tests. On this frozen challenge, however, no actual fallback can be justified because discovery did not surface a canonical studio candidate for the unresolved live target. Rebuild the later human-oracle audit around exact versus representation-equivalent semantics, while leaving the measured baseline at 42/50.

## Verification

- focused Stage 5B.1I tests: `26 passed`
- complete Stage 5B resolver regression suite: `401 passed`
- full non-heavy suite: `862 passed, 12 deselected, 11 warnings`

Reproduce the frozen artifacts from `ml/audio_similarity` with:

```bash
uv run python -m audio_similarity.cli.stage5b1i_live_fallback
```
