# Stage 5B.1J — Representation-Equivalent Rediscovery

Status: `STAGE5B1J_PART_A_AWAITING_HUMAN_REVIEW`

## Frozen control

The pre-1J Stage 5B.1H/1I stack reproduced exactly at **42/50 AUTO_MATCH and 8/50 MATCH_UNCERTAIN**, with every historical selection unchanged.

## Rediscovery contract

Fallback discovery is restricted to unresolved ordinary-live and true-remaster targets. It uses metadata-only `ytsearch5` with the frozen Q0 form `"{primary_artist}" "{base_title}" official`. The original Q0 pools are referenced but never replaced. Each new pool is first judged against the exact Spotify target; only an exact failure permits evaluation against the base representation target.

- ordinary live → `REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK`
- true remaster → `REPRESENTATION_EQUIVALENT_MASTER_FALLBACK`
- exact recording always wins
- remix, alternate mix, rerecording, acoustic, instrumental, karaoke, slowed/sped/reverb, nightcore, bass-boosted, radio/extended edits, and arrangement-changing live targets remain exact-only

## Discovery

- searches run: **4**
- tracks with candidates: **4**
- failures: **0**
- warnings: **0**
- unique candidates: **20**
- yt-dlp versions: `2026.08.19`
- operational preflight: the first sandboxed attempt was preserved after the workspace proxy returned HTTP 403; the same frozen queries then ran successfully with direct network authorization

## Decisions

- new exact selections from fallback pools: **0**
- new studio fallbacks: **1**
- new master fallbacks: **0**
- coverage: **42/50 (84%) → 43/50 (86%)**
- absolute gain: **2 percentage points**

The live search produced canonical official studio audio and is the sole pending representation fallback. The remaster searches produced no eligible canonical base master: Landslide returned other remasters/live uploads; Sweet Child O' Mine returned an overlong music video, third-party uploads, an alternate version, and a live take; the otherwise canonical Whitney release result explicitly identified itself as Dolby Atmos, an alternate mix that the master-fallback guardrail rejects.

| Track | Family | Query | Decision | Match mode | Candidate |
|---|---|---|---|---|---|
| `s5b1c_029` | `LIVE_TO_STUDIO` | `"Lord Huron" "The Night We Met" official` | `AUTO_MATCH` | `REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK` | `KtlgYxa6BMU` |
| `s5b1c_032` | `REMASTER_TO_MASTER` | `"Fleetwood Mac" "Landslide" official` | `MATCH_UNCERTAIN` | `NONE` | `NONE` |
| `s5b1c_033` | `REMASTER_TO_MASTER` | `"Guns N' Roses" "Sweet Child O' Mine" official` | `MATCH_UNCERTAIN` | `NONE` | `NONE` |
| `s5b1c_034` | `REMASTER_TO_MASTER` | `"Whitney Houston" "I Wanna Dance with Somebody Who Loves Me" official` | `MATCH_UNCERTAIN` | `NONE` | `NONE` |

## Human validation gate

- selections requiring review: **1**
- completed: **0**
- labels: `{}`
- Part B authorized: **false**

Part B may run only after every new selection is human `IDEAL` or `ACCEPTABLE`. Any `WRONG` or `UNCERTAIN` result stops the phase. Zero selections do not authorize automatic continuation.

## Scope guards

Audio downloads 0; video downloads 0; Stage 5A calls 0; CLAP calls 0; MuQ calls 0; Sol runs 0. The experiment is not production activated.

## Verification

- focused Stage 5B.1J tests: `23 passed`
- complete Stage 5B resolver regressions: `424 passed`
- full non-heavy suite: `885 passed, 12 deselected, 11 warnings`
