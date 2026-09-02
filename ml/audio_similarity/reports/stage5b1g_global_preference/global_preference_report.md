# Stage 5B.1G — Global Candidate Preference + Graduated Duration Evidence

Status: `STAGE5B1G_AWAITING_HUMAN_REVIEW`

## Outcome

The frozen pre-1G resolver replayed exactly at **42/50 AUTO_MATCH and 8/50 MATCH_UNCERTAIN**. Global preference produced **42/50 AUTO_MATCH (84%)**, a **0-percentage-point** mechanical coverage change.

It changed 10 existing selections and newly resolved 0 tracks. Every changed or new selection is queued for human review; production activation remains false.

Among all 42 selected candidates, frozen human evidence currently marks 34 SAFE, 0 WRONG, and 1 UNCERTAIN; the rest are unreviewed. These are evidence-availability counts, not a population precision estimate.

## Architecture

The historical Balanced V1 → 1C-A → 1C-B → 1C-C cascade is replayed unchanged. Stage 5B.1G then considers every conflict-free candidate admitted by any frozen tier plus candidates independently admitted by the graduated-duration gate. The admitting tier is evidence provenance only and never affects preference.

Global lexicographic preference is: structural recording identity; target-relative version compatibility; performer identity; internally consistent provenance; graduated duration; source quality; album/year corroboration; finally views and search rank as weak tiebreakers.

## Graduated duration evidence

| Bucket | Interval | Considered | Eligible | Selected | Human SAFE | Human WRONG | Human UNCERTAIN |
|---|---:|---:|---:|---:|---:|---:|---:|
| DURATION_VERY_CLOSE | 0–2 s | 82 | 64 | 28 | 25 | 0 | 1 |
| DURATION_CLOSE | >2–7 s | 50 | 38 | 12 | 8 | 0 | 0 |
| DURATION_EXTENDED_1 | >7–12 s | 11 | 1 | 0 | 0 | 0 | 0 |
| DURATION_EXTENDED_2 | >12–16 s | 14 | 3 | 1 | 1 | 0 | 0 |
| DURATION_EXTENDED_3 | >16–20 s | 6 | 1 | 1 | 0 | 0 | 0 |
| DURATION_TOO_FAR | >20 s | 72 | 0 | 0 | 0 | 0 | 0 |
| DURATION_UNKNOWN | unknown | 0 | 0 | 0 | 0 | 0 | 0 |

Candidates beyond seven seconds require progressively stronger corroboration. A delta above 20 seconds is a hard rejection. Explicit performer, cover, version, or unrequested-modification conflicts remain hard rejections at every band.

## Changed and newly resolved selections

- `s5b1c_004`: `sk6rMb8OsQY` → `SQnc1QibapQ` (SELECTION_CHANGED; existing human=IDEAL; frozen Sol=IDEAL).
- `s5b1c_013`: `aHnHwrJjR3U` → `ioNng23DkIM` (SELECTION_CHANGED; existing human=unreviewed; frozen Sol=IDEAL).
- `s5b1c_017`: `62TrmUvQGjo` → `6uvUTu716rU` (SELECTION_CHANGED; existing human=unreviewed; frozen Sol=IDEAL).
- `s5b1c_024`: `MYBN-XP2CUs` → `VI9gIPBH_dM` (SELECTION_CHANGED; existing human=IDEAL; frozen Sol=IDEAL).
- `s5b1c_025`: `9gnyYxEWgi4` → `5MenFU9qCzs` (SELECTION_CHANGED; existing human=unreviewed; frozen Sol=IDEAL).
- `s5b1c_035`: `q5YJ9JREVRk` → `igIfiqqVHtA` (SELECTION_CHANGED; existing human=IDEAL; frozen Sol=IDEAL).
- `s5b1c_043`: `CUbJQGqFoi0` → `zDOILKOOUCo` (SELECTION_CHANGED; existing human=IDEAL; frozen Sol=IDEAL).
- `s5b1c_048`: `yJDJ9eWx3ac` → `ca48oMV59LU` (SELECTION_CHANGED; existing human=unreviewed; frozen Sol=ACCEPTABLE).
- `s5b1c_049`: `sABVNz31WA0` → `dawrQnvwMTY` (SELECTION_CHANGED; existing human=IDEAL; frozen Sol=IDEAL).
- `s5b1c_050`: `Rbg6BBkmGfU` → `5NjJLFI_oYs` (SELECTION_CHANGED; existing human=unreviewed; frozen Sol=ACCEPTABLE).

Frozen human-label transitions among changed selections:

- `ACCEPTABLE -> IDEAL`: 3
- `ACCEPTABLE -> None`: 5
- `IDEAL -> IDEAL`: 1
- `UNCERTAIN -> IDEAL`: 1

Source-type transitions:

- `LYRIC_VIDEO -> LYRIC_VIDEO`: 1
- `LYRIC_VIDEO -> OFFICIAL_AUDIO`: 1
- `LYRIC_VIDEO -> OFFICIAL_MUSIC_VIDEO`: 1
- `LYRIC_VIDEO -> OTHER`: 3
- `OTHER -> LYRIC_VIDEO`: 2
- `OTHER -> OFFICIAL_MUSIC_VIDEO`: 1
- `OTHER -> OTHER`: 1

### Stage 5B.1F preference-case replay

| Track | Prior cause | Global selection equals best known human-SAFE candidate |
|---|---|---:|
| `s5b1c_004` | `DURATION_PRECEDES_PROVENANCE_AND_SOURCE_IN_ORDERING` | yes |
| `s5b1c_024` | `FALLBACK_ONLY_CASCADE_PREVENTS_CROSS_TIER_RERANK` | yes |
| `s5b1c_035` | `DURATION_PRECEDES_PROVENANCE_AND_SOURCE_IN_ORDERING` | yes |
| `s5b1c_044` | `FALLBACK_ONLY_CASCADE_PREVENTS_CROSS_TIER_RERANK` | no |
| `s5b1c_049` | `OFFICIAL_MUSIC_VIDEO_DURATION_RESTRICTION` | yes |

## Remaining tail

The experiment leaves **8/8** previously unresolved tracks unresolved.

- `s5b1c_021` — `NO_DEFENSIBLE_CANDIDATE_IN_TOP5`; decision `MATCH_UNCERTAIN`; prior blocker: Q0 returned zero candidates.
- `s5b1c_029` — `NO_DEFENSIBLE_CANDIDATE_IN_TOP5`; decision `MATCH_UNCERTAIN`; prior blocker: requested Ryman recording is not established.
- `s5b1c_030` — `SAFE_CANDIDATE_PRESENT_BUT_METADATA_INSUFFICIENT`; decision `MATCH_UNCERTAIN`; prior blocker: acoustic recording identity is unproven.
- `s5b1c_032` — `NO_DEFENSIBLE_CANDIDATE_IN_TOP5`; decision `MATCH_UNCERTAIN`; prior blocker: Q0 returned zero candidates.
- `s5b1c_033` — `SAFE_CANDIDATE_PRESENT_BUT_METADATA_INSUFFICIENT`; decision `MATCH_UNCERTAIN`; prior blocker: 2022 remaster evidence is absent.
- `s5b1c_034` — `NO_DEFENSIBLE_CANDIDATE_IN_TOP5`; decision `MATCH_UNCERTAIN`; prior blocker: Q0 returned zero candidates.
- `s5b1c_040` — `TRUE_CONFLICTING_CANDIDATES`; decision `MATCH_UNCERTAIN`; prior blocker: no result establishes the released Slowed Down recording.
- `s5b1c_041` — `SAFE_CANDIDATE_PRESENT_BUT_METADATA_INSUFFICIENT`; decision `MATCH_UNCERTAIN`; prior blocker: modification rate/recording identity is unproven.

## Conclusions

1. Global competition materially changes source preference: it selects the best known human-SAFE candidate in four of the five Stage 5B.1F preference cases. Track 044 remains unchanged because its release-description evidence still ranks ahead of the neutral reviewed alternative, although that evidence does not meet the stricter internally-consistent Art Track definition. Five additional changed candidates lack frozen human labels and require the generated audit.
2. Graduated duration removes the 7-second mathematical cliff without creating new coverage. The selected >16-second Official Music Video is frozen-Sol ACCEPTABLE but human-unreviewed, so safety of that band remains pending. Extended bands cannot override conflicts, and 12–20-second candidates require strong or strongest corroborated provenance.
3. Existing selections changed: 10; new tracks resolved: 0. Four changed selections are upgrades in frozen human evidence, one is IDEAL-to-IDEAL, and five are unreviewed. No changed selection is frozen-human WRONG or frozen-Sol WRONG.
4. Mechanical coverage does not reach the 90% milestone: 42/50 (84%). The eight-track tail remains four pools with no defensible candidate, three metadata-insufficient pools, and one pool dominated by conflicting candidates.
5. The selection-bottleneck hypothesis is supported for source quality, not for remaining coverage. Global comparison corrects known duration/provenance and tier-lock inversions, but no defensible deterministic path to at least 45/50 is demonstrated by the frozen top-five metadata. Better discovery or additional evidence remains necessary for the unresolved tail.
6. Counterfactual negatives remain protected: no selected candidate carries an explicit performer/cover, version, or unrequested modified-audio conflict, and every >7-second eligible candidate records the corroboration that admitted it.

## Review and scope

- review queue: `reports/stage5b1g_global_preference/human_review.csv`
- queued tracks/candidates: 10/10
- Q0 changed: no; searches run: 0; media downloaded: 0; Sol rerun: no
- historical resolver policies changed: no
- production activation: no

## Tests

- focused Stage 5B.1G tests: `36 passed`
- resolver regression suite: `59 passed`
- full non-heavy suite: `799 passed, 12 deselected, 11 warnings`
