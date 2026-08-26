# Stage 1A Human Encoder Pilot — Preliminary Results

Input export: `reports/holistic_stage1a/holistic_human_ratings.csv`<br>
Input SHA-256: `038081b7aecb7d6c63a4670c1ba0b509837eec8575e0487b93d9371f21ea1672`<br>
Trial-key SHA-256: `6ecb31573463dbaef8ceda4d870e6ac2a2fec6c91174281b867a896bc1b67c92`<br>
Analysis date: 2026-08-25

## Verdict

**Best observed encoder: LAION-CLAP, provisionally.**

This pilot does **not** establish a statistically decisive winner between
LAION-CLAP and MERT-5120, and it does not provide a fair test of MuQ-MuLan.
The defensible engineering decision is therefore:

1. use **LAION-CLAP as the provisional primary baseline** for exploratory
   Stage 2 work;
2. keep **MERT-5120 as the active challenger**;
3. do not reject MuQ-MuLan from these results because the current duplicate
   filter disproportionately removed MuQ comparisons.

Do not describe this result as a final held-out encoder-selection result.

## Input validation

- 136/136 exported trial rows have a choice.
- 137 stored judgments: 134 by `lenny`, 3 by `cody`; one trial has both and
  both selected B.
- Choice totals by primary trial judgment: A 52, B 53, Tie 17, Neither 14.
- A/B choice balance is effectively exact across the full sheet.
- All 136 trial IDs resolve to the matching blinded key entry.
- The reduced sheet covers 34 of the 40 frozen queries.

Because almost all trials have one listener, this pilot cannot estimate
inter-rater reliability or distinguish personal preference from population
preference.

## Primary analysis: top-1 encoder disagreements

Only `disagree:<encoder>_vs_<encoder>` trials are primary model-comparison
evidence. Ties count as 0.5 for each encoder; Neither is excluded from the
preference-share denominator. Confidence intervals are 50,000 query-cluster
bootstrap replicates (seed 20260825).

| Pair | n | Raw outcomes (first-second / Tie / Neither) | First encoder tie-adjusted share | Query-bootstrap 95% CI |
|---|---:|---:|---:|---:|
| LAION-CLAP vs MERT-5120 | 19 | 6-5 / 7 / 1 | 0.528 | [0.344, 0.711] |
| LAION-CLAP vs MERT-generic | 17 | 10-3 / 3 / 1 | 0.719 | [0.500, 0.906] |
| LAION-CLAP vs MuQ-MuLan | 5 | 4-0 / 1 / 0 | 0.900 | [0.700, 1.000] |
| MERT-5120 vs MERT-generic | 21 | 15-4 / 1 / 1 | 0.775 | [0.595, 0.944] |
| MERT-5120 vs MuQ-MuLan | 5 | 2-1 / 2 / 0 | 0.600 | [0.300, 0.900] |
| MERT-generic vs MuQ-MuLan | 5 | 1-2 / 0 / 2 | 0.333 | uninformative ([0, 1]) |

The direct top-1 result between CLAP and MERT-5120 is essentially a tie: six
CLAP wins, five MERT wins, and seven ties. MERT-5120 clearly outperforms the
generic last-layer MERT representation in this sample.

## Secondary diagnostic: include reconstructed rank-2 trials

The original `competitive_rank2` keys omitted their encoder-pair names. The
pairs were deterministically reconstructed from the frozen retrieval unions;
all 44 mapped uniquely. The mapping is stored in
`competitive_trial_model_pairs.json`.

These results are diagnostic rather than primary because they combine top-1
and rank-2 candidate-generation mechanisms.

| Pair | n | Raw outcomes (first-second / Tie / Neither) | First encoder share | Query-bootstrap 95% CI |
|---|---:|---:|---:|---:|
| LAION-CLAP vs MERT-5120 | 39 | 20-10 / 7 / 2 | 0.635 | [0.472, 0.784] |
| LAION-CLAP vs MERT-generic | 17 | 10-3 / 3 / 1 | 0.719 | [0.500, 0.906] |
| LAION-CLAP vs MuQ-MuLan | 5 | 4-0 / 1 / 0 | 0.900 | [0.700, 1.000] |
| MERT-5120 vs MERT-generic | 43 | 23-10 / 4 / 6 | 0.676 | [0.571, 0.786] |
| MERT-5120 vs MuQ-MuLan | 5 | 2-1 / 2 / 0 | 0.600 | [0.300, 0.900] |
| MERT-generic vs MuQ-MuLan | 7 | 1-4 / 0 / 2 | 0.200 | [0.000, 0.600] |

CLAP's observed advantage over MERT-5120 comes mostly from rank-2 comparisons
(14-5, one Neither), not the top-1 comparisons.

## Anchor diagnostic

The encoder candidate beat the random anchor in 14/20 anchor trials; the random
anchor won 3, and 3 were Neither. This confirms that retrieval is non-random,
but it is not a fair encoder comparison because anchor trials were sourced from
the first sorted encoder path.

## Critical limitations

1. **Single-rater pilot:** nearly all choices come from one listener.
2. **MuQ-dependent filtering bias:** the near-duplicate filter uses MuQ cosine
   geometry. Compared with the pre-filter sheet, direct comparisons involving
   MuQ fell from 36-38 per pair to only 5 per pair, while other pairs retained
   17-21. The current data cannot fairly rank MuQ.
3. **Reduced query coverage:** only 34/40 frozen queries have any surviving
   trial; primary model comparisons cover 26 queries.
4. **CLAP vs MERT uncertainty:** both the primary and combined query-bootstrap
   intervals include 0.5.
5. **Post-filter protocol deviation:** 136 trials replace the originally
   planned 320 trials and three independent ratings per trial.
6. **No held-out confirmation:** this is a model-selection pilot, not a final
   test set.

## Provisional next action

Proceed with Stage 2 only as an **exploratory dual-baseline ablation**:

- primary provisional baseline: LAION-CLAP;
- retained challenger: MERT-5120;
- drop MERT-generic from the active baseline set;
- retain MuQ as unresolved rather than treating it as a loser.

Before making a final production/model-selection claim, run a small balanced
corrective comparison where duplicate detection is encoder-neutral and CLAP,
MERT-5120, and MuQ receive equal query coverage.
