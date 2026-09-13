# Real playlist corpus readiness audit

**Source readiness: SOURCE_NOT_READY. Feature readiness: WAITING_FOR_FEATURES.**

No calibration, model inference, downloads, lockbox performance inspection, or production changes occurred.

Initial scope: 28 captured lists, 2032 requests; 1927 queue completions, 69 manual tails, 36 acquisition failures. The extension remains separate.

## Provenance and eligibility

Owner confirms that each table preserves one external playlist track list. The queue wording owner-declared means owner-collected here, not independently owner-authored. No source-use status is upgraded by this audit. Original source descriptions, curator account IDs, and discovery details are incomplete.

Source-only screen: {'single_artist_excluded': 1, 'genre_focused_candidate': 11, 'mix_or_radio_source_review_required': 16}. Zero sources are cleared for calibration. Mix/radio titles are review flags, not proof of an algorithmic or heterogeneous playlist. The single-artist source is outside primary Layer A. Unknown curator stays unresolved.

## Feature verification

| Feature | Exact source/identity matches |
|---|---:|
| centered30 | 1925 |
| muq | 1925 |
| method_c | 10 |
| gemini_canonical | 1 |

Common four-feature population: 0 requests. Counts refer to inspected compatible artifacts, not title matches. Missing genre remains a no-op; this tiny coverage cannot test whether genre helps the broader corpus.

Thirsty (aespa) and Sour Grapes (LE SSERAFIM) have queue feature links to a different source hash than the retained audio. Retained bytes agree with acquisition provenance. Thirsty has exact-source historical A/C/MUQ alternatives; these are documented, not silently substituted. Sour Grapes has no matching alternate in the inspected representation caches. No source or cache was overwritten.

## Conditional split feasibility

Treating the credited curators as provisional groups gives 10 candidate playlists in 8 groups. These are not independently verified curator identities. Three outer/two inner folds can be simulated without fitting, but this does not establish a full confirmation design. If all lists are genuinely authored by the owner, one source group remains and grouped evaluation is infeasible.

Samples are drawn from complete membership before feature attrition, capped at three tracks per primary artist. Unavailable sampled tracks remain visible and are not replaced. The table reports query-feasible playlists (at least two recordings); the private audit separately reports those still meeting the main 30-recording target.

| Outer fold | Fit playlists / curators / tracks | Evaluation playlists / curators / tracks | Purged fit requests |
|---|---|---|---:|
| 1 | 7 / 5 / 201 | 3 / 3 / 82 | 0 |
| 2 | 5 / 5 / 142 | 5 / 3 / 141 | 0 |
| 3 | 8 / 6 / 223 | 2 / 2 / 60 | 0 |

All inner partitions, recording lists, purge lists, artist overlap and candidate hashes are retained in `audit.private.json`. These are conditional metadata-only plans. No lockbox was allocated or scored.

## Draft and next action

The draft retains the documented 880 nominal / 756 unique joint configurations plus 36 exact-M3 controls. It proposes eight masks, 2,000 cluster bootstrap draws, and the existing same-h/rho audio comparator with genre coefficients zero. These settings have not been fitted or scientifically selected.

Resolve source provenance first. If that passes, a small development-only pilot may be possible after feature parity and identity checks; a full grouped confirmation is not currently established. The draft feature bundle and split freeze hashes remain null.

Owner input still needed: point to any existing source-use permission/license records. Remaining execution details have explicit draft defaults or stay blocked on this factual clarification.

Capture hash: `9f68729ad6aef94d3ff89fbed138e141b0651cb019796a78449e2226eaa481ba`. Audit hash: `732b4500df8dcb8c503aee9ac57b402f1322a750f5d933ab07b2221507535b04`.

## Owner clarification

Owner confirms each Markdown table preserves one external source playlist track list and describes the files as manually recorded/self-labeled rather than API-derived. Preserve the original membership and credited curator boundaries. Do not count copying as independent owner authorship or pool lists. Owner-added labels are discovery annotations, not independently verified source-declared intent; the captured title/credit claims remain traceable to the original note.

The attributed external curators are retained. These are copies of individual external playlist memberships, not new independent owner-authored playlists or pooled lists. Source-use status remains pending.
