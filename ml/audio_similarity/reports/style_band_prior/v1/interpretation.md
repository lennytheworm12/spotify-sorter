# Interpretation of the frozen result

The coarse style distance is not devoid of signal: among 31 anchors with 84
human good/bad comparisons within a C-score caliper of 0.05, its descriptive
macro discrimination AUC is 0.6683 [0.5280, 0.7989]. That is insufficient to
establish an effective additive reranker. It is a marginal discrimination
measurement, not a paired estimate of incremental ranking improvement over C.

Training preferred zero penalty in two folds. In the third, lambda 0.10 improved
training macro agreement from 0.66354 to 0.67110, but left every eligible held-out
preference ordering unchanged. Across all folds, agreement remained 0.67653
(to four decimals, 0.6765), with 258 preferences and 70 anchors. The all-zero
paired bootstrap interval describes these unchanged observed orderings; it is
not proof that the methods are universally equivalent or that uncertainty about
future songs is zero.

## What actually moved

In held-out-only candidate pools, two rated bad Top-5 pairs were removed, both
for the same previously inspected development anchor:

| Query | Removed candidate | Existing rating |
| --- | --- | --- |
| Wet Dreamz | DOWNPOUR (feat. Gliiico) | 2 |
| Wet Dreamz | Cloudy Thoughts | 1 |

They were replaced by Shoota (feat. Lil Uzi Vert) and Bullet Train Fantasy.
Both replacements have **unknown playlist ratings** in this frozen evidence.
Consequently these removals are not verified bad-to-good corrections, and their
concentration in the motivating rap neighborhood does not establish breadth.
There were no strictly corrected bad-versus-good held-out orderings.

A separate query, DOWNPOUR, gained the rated-4 candidate Fall in love with you
in every 4AM., replacing the unrated MOON. That is a known-good entrant, but the
unknown departing pair prevents calling it a proven improvement. Seven of the
eight directed entrants in the grouped Top-5 comparison were unrated.

In the all-99-candidate diagnostic, there were no removed rated-bad pairs and
two known-good losses, both replaced by rated-3 candidates:

| Query | Removed candidate | Rating | Entering candidate | Rating |
| --- | --- | --- | --- | --- |
| id T41104 (feat. 267) | Tell Me | 4 | SATELLITE | 3 |
| MOON | Flash Forward | 4 | Sunday (feat. HEIZE, Jay Park) | 3 |

Fresh Air also swapped the unrated Stoked for the unrated Stay With Me. This
snapshot does not license treating either pair as bad, regardless of prior
qualitative discussions. The all-candidate diagnostic includes training
candidates and must not be confused with the grouped primary evaluation.

## Decision

**STYLE_BAND_SHORTCUT_NOT_ESTABLISHED.** The predefined soft prior neither
improved held-out ranking agreement nor produced corrections across multiple
musical regions. The tiny visible bad-neighbor removals are concentrated in a
known development example, while the full-candidate diagnostic exposes good-match
damage. Do not rescue this run by expanding taxonomy rules or trying larger
penalties after seeing these outcomes.

The smallest justified next step is the previously proposed data-sufficiency
and protocol design for a small regularized learned scorer over frozen **CLAP C**
using the actual **playlist-compatibility** rubric. This experiment does not
prove CLAP contains everything needed, nor does it rule out every other style
aggregation. No new training, review queue, or production change is authorized
by this closeout itself.
