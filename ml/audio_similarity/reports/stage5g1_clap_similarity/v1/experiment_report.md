# Stage 5G.1 scientific closeout: REPRESENTATION_LIMITED

Neither full-segment mean/cosine nor the small learned scorer demonstrates a
credible held-out improvement under the frozen 5-percentage-point plus positive
lower-95%-bound rule. This outcome is **limited to this experiment**. It does not
prove that CLAP lacks human-relevant information, or that a different learner
could not recover it. No production behavior is activated.

## Supervision and split

740 unique compatible numeric whole-song similarity pairs involve 100 tracks
and 107 credited artists. There are 7,680 strict anchor-based preferences and
3,827 tied candidate comparisons; ties do not enter training. No numeric
conflicts or uncertain pairs were found in the accepted similarity evidence.
The 419 Stage 5E.3 playlist judgments use a different rubric and are inventoried
separately. Stage 2B excerpt/FMA labels and source-identity reviews are excluded.
Unrated pairs remain unknown. Copies of evidence are not independent labels.

The one frozen source-grouped split contains 60 train, 20 validation and 20 test
tracks. Only within-partition human pairs generate constraints. The 410 crossing
pairs are excluded. Track IDs, preference lists, per-track degrees and artist
reuse are published in split.json, human_evidence.json and the inventory/audit.

| Partition | Rated pairs | Informative anchors | Strict preferences | Strong (gap >=2) |
|---|---:|---:|---:|---:|
| train | 258 | 60 | 1525 | 493 |
| validation | 42 | 17 | 116 | 21 |
| test | 30 | 16 | 58 | 25 |

The primary exploratory gate passes. Artist grouping is transitive across every
credited artist and source/video alias. Its test split has only 10 informative
anchors / 27 preferences, below the frozen 15/50 floor; no artist-disjoint model
claim is made. Artist names are used only for split auditing, never prediction.
The gate is an exploratory adequacy floor, not a power guarantee for small gains.

## Representations and model

B0 is exact historical Arm-D d_clap. B1 and M1 share the same 1,927 normalized
512-D segments over all 100 retained sources. Every window is 480,000 samples at
48 kHz; the tail cyclically repeats its own samples. Arm D's HTSAT-tiny
630k-audioset-fusion-best.pt checkpoint, quantization, mel extraction, and
independent-view forward path are reused. Checkpoint SHA-256:
`fb171dd9b608aebdac3d89286cd7615c5100af4cc7dc37797c7fb8d3cc15e3a5`.
No trimming, loudness normalization, new audio, or CLAP training.

B1 uses L2(equal mean of normalized segments) cosine. M1 uses a shared 512-to-16
tanh projection, mean all-section absolute differences/products, a 32-to-1 head
and sigmoid. It is symmetric and permutation-invariant; no Transformer or
metadata/other-model inputs. Arm D already has a full-song resized global view,
so B0-to-B1 tests construction/local coverage, not simply access to more seconds.
B1-to-M1 isolates this learned scorer on identical frozen segment inputs.

The 8,241-parameter model uses torch default seeded Linear initialization,
AdamW (lr 0.001, weight decay 0.001), full-batch anchor-macro logistic preference
loss, seed 20260908, deterministic single-thread CPU training, at most 200 epochs,
and patience 20 on validation loss. Validation chooses the earliest improvement
exceeding 1e-6. CLAP's 158,348,809 parameters remain frozen. No scaler is fitted.

## Held-out and split results

Preference score ties within 1e-6 receive half credit. Primary agreement is
anchor-macro, not a raw-row average. Test contains 16 informative anchors and
58 preferences, supported by 30 human pair labels.

| Method | Train macro | Validation macro | Test macro | Test micro |
|---|---:|---:|---:|---:|
| B0 | 52.25% | 38.94% | 62.58% | 65.52% |
| B1 | 56.74% | 43.39% | 54.39% | 55.17% |
| M1 | 55.80% | 47.16% | 56.10% | 60.34% |

| Comparison | Test macro delta (percentage points) | Paired 95% interval |
|---|---:|---:|
| B1_vs_B0 | -8.19 | [-26.62, +8.68] |
| M1_vs_B0 | -6.48 | [-37.47, +22.75] |
| M1_vs_B1 | +1.71 | [-25.00, +26.06] |

Intervals resample paired test anchors, 2,000 PCG64 replicates at seed 20260908,
with sorted IDs and linear percentiles. They are conditional on this selected
corpus and do not fully model shared-candidate dependence. Strong-preference
results, per-method absolute intervals and per-anchor values are in
supplemental_audit.json. Wide intervals preclude equivalence or absence claims.

## Learning curves and overfitting

| Training fraction | Preferences | Train macro | Validation macro | Selected epoch |
|---|---:|---:|---:|---:|
| 25% | 381 | 60.67% | 46.97% | 1 |
| 50% | 762 | 59.05% | 47.16% | 1 |
| 100% | 1525 | 55.80% | 47.16% | 1 |

All three runs stop after 21 epochs and select epoch 1. Later fitting does not
improve validation loss, an overfitting/weak-generalization warning. Training
loss and validation loss for every epoch are preserved in the execution ledgers.
The final model is the predeclared 100% fraction, not a test-selected curve point.
Its training runtime was 4.461 seconds; scoring 5,050 unordered
pairs including self pairs took 0.750 seconds on CPU.
CLAP extraction took 182.189 seconds after identity checks, with
1,927 forwards. Replay made zero forwards and reproduced exact NPZ/JSON artifacts.
All three real training runs replayed identical epoch histories and checkpoint
hashes. Final checkpoint SHA-256: `27205f6abd7f2e8cb7d26c26213e318f594711f4e87dcbd9553cccd5370e0e76`.

## Interpretation and next research boundary

The modest +1.71-point learned-versus-B1 difference is below the fixed +5-point
margin and has a wide interval spanning negative and positive effects. B1 also
does not improve B0. Thus the required outcome is REPRESENTATION_LIMITED under
this frozen operational rule, with no broad information-theoretic conclusion.
Validation selected almost-untrained models; model inadequacy and sparse
supervision remain plausible explanations alongside representation limitations.

Known Wet Dreamz, Shoota and boys dont cry cases are listed only where a real
compatible similarity label exists, marked as research-influencing diagnostics.
Their newer playlist ratings are not substituted, and an unrated suggested
comparison is not assigned a label. This stage does not tune those cases away.
A later reviewed experiment may test complementary MuQ information or stronger
evidence; this stage creates no new review queue and activates nothing.

## Reproduction and verification

Use the commands in docs/stage5g1.md with the locked environment and retained
local audio/checkpoint. Replay never invokes the CLAP forward path on a cache
miss; it fails explicitly. Original ledgers are create-once; later executions
append numbered ledgers. The final artifact_manifest.json inventories all run
files except itself. Input hashes protect historical artifacts, raw sources,
label provenance, protocol and fitting/extraction implementation.

Focused suite: 11 passed. Full non-heavy suite: 1,261 passed, 12 deselected,
11 warnings, 121.30 seconds. verification/audit_outputs.py checks isolation,
human-only preferences, timestamps, normalization, cache replay, finite symmetric
scores, all reported split metrics, and historical hashes. Supporting evidence
and exact test output are in verification/. No network downloads, MuQ/MIR inputs,
CLAP tuning, new judgments, Spotify writes, or production changes occurred.
