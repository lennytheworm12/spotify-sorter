# Stage 5E.3 scientific closeout: INCONCLUSIVE

Full-song MuQ at the frozen fusion weights does **not demonstrate the required
playlist-compatibility improvement** over existing MuQ on frozen100_v3.
The revision-2 decision rules select exactly **INCONCLUSIVE**. This is a completed
comparison with adequate review coverage, not a placeholder for pending review.
Retaining the current research configuration is operationally reasonable, but
this experiment does not establish its superiority. No production activation.

## Frozen scope and evidence

Both query and candidate axes contain the original amended 100 tracks. C CLAP,
existing centered30 MuQ, and full-song MuQ representations are unchanged. Fusion
weights remain CLAP 0.7172981519 and MuQ 0.2827018481. Analysis consumed existing
cached matrices only: no inference, downloads, new ratings, or weight tuning.
The original full-song extraction used 1,927 chunks; the already-verified cache
replay recorded 100 hits and zero new forwards.

All 98 review packets / 419 unique judgments are submitted, with six notes and
no UNSURE. The original CSV matches the frozen snapshot exactly. Compatible
historical labels are reused under the frozen semantic policy. Every method has
500/500 numeric natural Top-5 slots, 100 complete anchors, and 100% unique-pair
numeric coverage. All support gates pass. Forced drift probes are not counted
as natural retrievals. The 2,000 directional slots are not 2,000 independent
judgments: the natural union contains 656 unique unordered pairs.

## Four-method comparison

Unacceptable means rating <=2; coherent means rating >=4. Quality values are
complete-anchor macro averages. Recovery is recovery of selected pre-run
historical positives, not recall over every compatible song.

| Method | Unacceptable | Coherent | Mean rating | Historical-positive recovery |
|---|---:|---:|---:|---:|
| M1_C_CLAP | 7.4% | 65.4% | 3.774 | 34.93% |
| M2_FULL_MUQ | 11.0% | 57.6% | 3.598 | 29.58% |
| M3_C_PLUS_FIXED_MUQ | 6.8% | 63.0% | 3.744 | 39.45% |
| M4_C_PLUS_FULL_MUQ | 7.8% | 63.4% | 3.744 | 34.90% |

## Primary comparison: M4 minus M3

All quality deltas use the same 100 complete paired anchors. Historical-positive
recovery uses its separate fixed set of 98 eligible anchors. Intervals use 2,000
paired anchor bootstrap replicates, PCG64 seed 20260906, ascending Spotify IDs,
and linearly interpolated 2.5/97.5 percentiles. Rate changes below are percentage
points; the mean-rating change is in rating points.

| Metric | Delta | 95% interval |
|---|---:|---:|
| unacceptable | +1.000 | [-0.400, +2.600] |
| coherent | +0.400 | [-2.800, +3.405] |
| mean_rating | +0.000 | [-0.054, +0.050] |
| recovery | -4.547 | [-8.466, -0.983] |

M4 has 39 unacceptable slots versus M3's 34. M3 and M4 share 369 of 500
directional slots, each contributes 131 different slots, and their mean
anchor Top-5 Jaccard overlap is 0.6111. The recovery decrease is supported by
the conditional bootstrap interval, but no result here is population-wide.

## Exact advancement decision

M4 versus M3 passes ACCEPT: +1.0 percentage point unacceptable change is within
+3 points, its upper confidence bound +2.6 points is below +5, coherence is
within the -3-point margin, and mean rating is within -0.15.

It fails every GAIN alternative: recovery decreases rather than increasing by
8 points, unacceptable matches increase rather than decreasing by 5 points,
and coherence rises only 0.4 rather than 5 points. Thus WIN and ROBUST_WIN fail.

All 100 leave-one-anchor-out checks fail the combined ACCEPT-and-GAIN condition;
all 100 track-node deletions remain computable and pass the strong-reversal
check. Restoring pre-run originals gives delta unacceptable +0.8 points,
coherent +0.6 points, mean rating 0.000, recovery -4.547 points. This sensitivity
also fails GAIN. STABLE is therefore false; that does not mean the primary
result depends on one outlier, since STABLE explicitly requires a gain.

The other ordered recommendation branches also fail: C alone has no ROBUST_WIN
against either fusion, full-song MuQ alone has no ROBUST_WIN against either
fusion, and existing fusion has no ROBUST_WIN against full-song fusion. C alone
has the best descriptive coherence/mean rating, but its improvement over the
fusions is too small under the predeclared rules. A highest-average selection
would violate the contract. The final ordered fallback is INCONCLUSIVE.

## Notes, uncertainty, and limitations

The owner's six notes identify incompatible listening character among lo-fi
candidates for Shoota, Wet Dreamz, and boys dont cry. These notes are preserved
in the completed-review CSV and frozen snapshot; they did not alter formulas,
thresholds, or labels after the freeze. They motivate future separately designed
error analysis, not post-hoc tuning of this experiment.

This is one owner's selected 100-song corpus, with mixed historical similarity
and new playlist-compatibility labels. The historical positive bank is selected,
not exhaustive. Anchor bootstrap intervals do not fully account for shared
candidate dependence; full track-node deletion and original-label sensitivity
are provided. Full-song MuQ changes coverage, input context, and pooling jointly,
so the comparison cannot isolate sampling coverage as the cause. A/D historical
reference metrics are available only as descriptive compatible-evidence context.
No claim of equivalence, global winner, or validated playlist admission follows.

## Reproduction and artifact map

From ml/audio_similarity, using the locked environment and retained inputs:

```bash
.venv/bin/python -m audio_similarity.cli.stage5e3 verify
.venv/bin/python -m audio_similarity.cli.stage5e3 analyze
.venv/bin/python reports/stage5e3_full_song_muq_playlist_compatibility/frozen100_v3/verification/validate_closeout.py
.venv/bin/python -m audio_similarity.cli.stage5e3 closeout
```

Analysis and closeout are create-once and verify identical reruns. Historical
sources must be available locally for input verification; Git does not include
audio or model weights. Numerical outputs, eligible IDs, all 12 ordered
comparisons, bootstrap intervals, per-node deletion results, original-label
sensitivity, semantic strata, recovery lists, overlap, and missing-rating bounds
are in their named JSON artifacts beside this report. Coverage is complete, so
missing-rating bounds collapse to observed effects.

`verification/closeout_validation.json` records validation results, and
`verification/non_heavy_tests.txt` preserves the complete suite output.
`closeout_artifact_manifest.json` inventories the final run, excluding itself.
The original pre-review `artifact_manifest.json` remains unchanged.
Live review/revision ledgers remain private; their frozen evidence is captured
by `post_review_rating_snapshot.json` and the revision-sensitivity output.
