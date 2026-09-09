# Dedicated style prior pilot

**Diagnosis: STYLE_OBSERVABLE_RERANKING_NOT_ESTABLISHED.**

Review a bounded set of high-distance accepted matches and low-distance rejected matches to identify whether the detector is wrong or the musical difference is acceptable. Do not promote a penalty from overall separation alone.

This is a single-reviewer development experiment on previously exposed frozen evidence. No production winner or independent confirmatory result is declared.

## Signal separation

AUC asks whether a rejected pair has a larger style distance than an accepted pair sharing its anchor. Chance is 0.5. Intervals are descriptive anchor bootstraps; shared candidates limit their independence.

| Rubric / slice | Anchors | AUC [95% interval] |
|---|---:|---:|
| playlist / all | 52 | 0.711 [0.627, 0.791] |
| playlist / high_D_top10 | 20 | 0.700 [0.500, 0.883] |
| playlist / cosine_caliper | 38 | 0.708 [0.586, 0.821] |
| playlist / exclude_diagnostic_artists | 38 | 0.702 [0.601, 0.799] |
| playlist / C_cosine_caliper | 31 | 0.640 [0.499, 0.775] |
| holistic / all | 80 | 0.730 [0.682, 0.776] |
| holistic / high_D_top10 | 73 | 0.718 [0.654, 0.781] |
| holistic / cosine_caliper | 76 | 0.710 [0.645, 0.772] |
| holistic / exclude_diagnostic_artists | 63 | 0.709 [0.654, 0.763] |
| holistic / C_cosine_caliper | 64 | 0.567 [0.486, 0.653] |

Frozen signal gate passed: **True**.

## Conditional penalty

### D primary

Status: DEVELOPMENT_ONLY.

| Fold | Lambda | Training accuracy | Baseline held-out | Penalty held-out | Preferences / anchors |
|---|---:|---:|---:|---:|---:|
| 0 | 0.2 | 0.544 | 0.710 | 0.613 | 75 / 23 |
| 1 | 0 | 0.613 | 0.522 | 0.522 | 98 / 27 |
| 2 | 0.05 | 0.526 | 0.526 | 0.533 | 85 / 20 |

Paired held-out anchor-macro change: -0.030 [-0.077, 0.006].

### C sensitivity

Status: DEVELOPMENT_ONLY.

| Fold | Lambda | Training accuracy | Baseline held-out | Penalty held-out | Preferences / anchors |
|---|---:|---:|---:|---:|---:|
| 0 | 0 | 0.754 | 0.512 | 0.512 | 75 / 23 |
| 1 | 0 | 0.652 | 0.749 | 0.749 | 98 / 27 |
| 2 | 0.2 | 0.694 | 0.768 | 0.737 | 85 / 20 |

Paired held-out anchor-macro change: -0.009 [-0.022, 0.001].

## Known diagnostic pairs

These influenced the research direction and are not untouched validation. A difference can coexist with a valid 4/5 match. Exact D and C differ substantially for some controls.

| Pair | Human | D cosine | C cosine | Style distance |
|---|---:|---:|---:|---:|
| risk / Sit Around | 4/5 | 0.626 | 0.798 | 0.320 |
| Uncertainty / m o v i e (Feat. Jade) | 4/5 | 0.583 | 0.706 | 0.308 |
| Heart / 2080 | 4/5 | 0.783 | 0.801 | 0.243 |
| Ever2Late! / The Peace | 4/5 | 0.778 | 0.679 | 0.213 |
| Wet Dreamz / Sit Around | 1/5 | 0.710 | 0.550 | 0.607 |
| Wet Dreamz / Cloudy Thoughts | 1/5 | 0.410 | 0.540 | 0.498 |
| Shoota (feat. Lil Uzi Vert) / Stay With Me | 1/5 | 0.717 | 0.495 | 0.306 |
| boys dont cry / Sit Around | 1/5 | 0.649 | 0.517 | 0.338 |

## Accepted matches with largest style distance

| Pair | Human | D cosine | C cosine | Style distance |
|---|---:|---:|---:|---:|
| Fresh Air / Die Right Here | 5/5 | 0.597 | 0.615 | 0.602 |
| risk / Phantom Embrace | 4/5 | 0.696 | 0.671 | 0.531 |
| boys dont cry / Shoota (feat. Lil Uzi Vert) | 4/5 | 0.611 | 0.585 | 0.515 |
| Tea Time / Sit Around | 4/5 | 0.655 | 0.693 | 0.488 |
| me2urs2ours / blue (with MINNIE) | 4/5 | 0.431 | 0.651 | 0.484 |
| risk / 2080 | 5/5 | 0.763 | 0.659 | 0.479 |
| Shiawase no Monosashi / Do We Start to Like Each Other ? | 5/5 | 0.536 | 0.492 | 0.463 |
| By My Side / Shouldn't Be | 5/5 | 0.644 | 0.713 | 0.451 |
| risk / blue (with MINNIE) | 4/5 | 0.354 | 0.670 | 0.450 |
| Soft Static Sky on Early Mornings / blue (with MINNIE) | 4/5 | 0.582 | 0.630 | 0.450 |

## Rejected matches with smallest style distance

| Pair | Human | D cosine | C cosine | Style distance |
|---|---:|---:|---:|---:|
| DOWNPOUR (feat. Gliiico) / Not Afraid | 2/5 | 0.680 | 0.555 | 0.150 |
| Hit the Wall / The Color Violet | 2/5 | 0.750 | 0.749 | 0.160 |
| Magnetic / Die Right Here | 2/5 | 0.842 | 0.739 | 0.176 |
| You Never Know / SATELLITE | 2/5 | 0.814 | 0.741 | 0.177 |
| GET IT / I'm Not Enough and I'm Sorry | 2/5 | 0.731 | 0.614 | 0.197 |
| CLOUT CHASER / Bullet Train Fantasy | 2/5 | 0.539 | 0.661 | 0.215 |
| We (OUI) (Feat. sogumm) / we used to talk every night | 2/5 | 0.572 | 0.628 | 0.217 |
| No I Don't Want, Just Anyone / The Hills | 2/5 | 0.622 | 0.729 | 0.225 |
| Magnetic / Stoked | 2/5 | 0.700 | 0.528 | 0.227 |
| The Bottom / The Peace | 2/5 | 0.702 | 0.666 | 0.228 |

## Reproduction and limitations

See `docs/style_prior_pilot.md` for exact commands and the engineering decoding amendment. Raw patch sigmoid arrays are in the content-addressed local cache; raw song means, normalized distributions, all rated-pair results, extractor identity, folds and protocol accompany this report.

There is one fixed 400-style classifier and one fixed distance. No similarity model was trained. The normalized sigmoid distribution is a comparison device, not a calibrated probability of mutually exclusive styles. Unknown pretraining overlap, one reviewer, small artist folds and purposefully selected historical neighbors limit generalization claims. A positive global AUC does not prove incremental ranking value or causal identity recognition.

Execution counts, test results and historical-integrity checks are recorded in `verification.json`. The manifest hashes every final report artifact. Existing CLAP/MuQ/fusion, human labels, historical verdicts and production behavior remain unchanged.
