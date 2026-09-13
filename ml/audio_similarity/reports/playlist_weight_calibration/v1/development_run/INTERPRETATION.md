# What this development run supports

Steps 1–4 completed: both stale source links were repaired in an isolated cache,
the fixed samples were materialized, and the grouped nested comparison ran and
replayed deterministically. See [the metric table](REPORT.md), [full compact
results](results.json), and [execution checks](execution_validation.json).

The strongest practical finding is that full-song Method C is a better candidate
than the legacy centered30 CLAP representation on these source-playlist samples.
Method C alone reached macro NDCG@20 **0.7863**, compared with **0.6254** for
centered30 CLAP alone. The fixed M3 recipe reached **0.7638**. The paired
curator-cluster interval for Method C minus M3 was **[+0.0026, +0.0350]**.
These intervals describe this small grouped development evaluation; they do not
include new-corpus uncertainty or rerunning the entire selection procedure inside
each bootstrap draw.

All three inner searches for the joint canonical/residual procedures selected
Method C with `rho=0`, `w_c=0`, and `w_n=0` under the predeclared one-standard-error
simplicity rule. This is a development candidate, not an activated production
configuration. The genre-capable procedures therefore reproduce the Method-C-only
outer results; those repeated rows are not independent confirmations.

Genre information was not universally harmful or proven useless. The maximum
inner NDCG configurations did use small genre coefficients: `.020`, `.005`, and
`.010` in the three outer folds. Their inner improvements over the selected
simpler model were about **.0013, .0008, and .0108**, against bootstrap standard
errors of **.0090, .0633, and .0508**. That evidence did not justify the additional
terms under the frozen rule. We did not adjust that rule after seeing results.

Method C exceeded M3 in five of six represented source strata; E1 was slightly
lower (NDCG difference about −.0064). Several strata have very few independent
curators, and the P1 result remained weak in absolute terms. This is not evidence
that all playlist types are solved or that MuQ is generally unhelpful.

## Coverage and limits

The experiment used **284 available recordings**, from the original fixed
30-member samples of ten playlists and eight credited curator groups. Fourteen
sampled requests lacked usable retained audio and were listed without replacement.
The separate Sour Grapes repair brings the audio materialization count to 285.

All 284 sample tracks have validated Gemini profiles; **266** have an eligible
specific style in the unchanged mapper. The remaining 18 stay in every model's
candidate population with a zero genre adjustment. Missing mapped specificity
is not treated as a confident genre mismatch or a negative human judgment.

Curator/duplicate groups and recording versions were kept apart across fitting
and evaluation boundaries. There are only eight independent source groups;
80 repeated outer queries do not make 80 independent playlists or curators.
There was no untouched lockbox. Source-use documentation remains pending under
the owner's explicit personal-development authorization.

The target here is recovery of observed source-playlist membership. A nonmember
is unlabeled, not necessarily unsuitable. Consequently this result does not
establish personal listening-fit precision, admission thresholds, or the absence
of concerning false positives.

## Engineering closeout

- **Thirsty — aespa:** reused exact-source A/C/MuQ evidence; original stale cache
  links and source artifacts remain preserved.
- **Sour Grapes — LE SSERAFIM:** created fresh CLAP and MuQ evidence for the retained
  source. The old embeddings referred to a different file hash; this was a cache
  provenance problem, not a dead URL or proof that the retained song was wrong.
- **283 Gemini generations**, one reused profile, **$1.68255450**, no generation
  retries, no unsettled usage, and zero-call replay.
- **6,873 CLAP segment calls and three MuQ calls** contributed to completed audio
  records. Two failed MuQ initializations each followed three uncommitted CLAP
  segment calls: **six additional partial-attempt CLAP calls**, retained separately
  in the failure receipts. Total CLAP calls including those attempts: **6,879**.
- The proxy initialization failure was fixed with an explicitly offline Hub
  transport that cannot open a socket. No new model, package, or audio downloads
  were needed. No completed song cache was recomputed during recovery.
- Final audio replay reused all 285 entries with zero new inference and preserved
  all original per-track execution ledgers. Search replay verified all 494 output
  artifacts byte-for-byte. Historical source and published-artifact checks passed.
- Final non-heavy suite: **1,467 passed, 12 heavy tests excluded**. Focused
  calibration suite: **37 passed**. Genre arithmetic exactly matched all 4,950
  pairs in the frozen frontend mechanical gate.

The smallest justified next experiment is an independently grouped confirmation
of the frozen Method-C-only development candidate against M3, with a separate
owner-playlist transfer check. Keep the genre-capable result as a negative or
inconclusive incremental finding for this setup. Do not expand tuning, infer
suitability labels from nonmembership, or activate the selected settings on the
strength of these ten playlists alone.
