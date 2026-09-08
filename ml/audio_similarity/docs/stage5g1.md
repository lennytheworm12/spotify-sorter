# Stage 5G.1: frozen CLAP segments and learned similarity

This experiment tests full-song coverage separately from learned scoring on the
same latent segments. The frozen protocol is `configs/stage5g1_v1.json`; results
are under `reports/stage5g1_clap_similarity/v1/`. Historical reports and audio are
immutable inputs. No production activation is implemented.

The primary target is the historical 1–5 whole-song sonic-similarity rubric.
The Stage 5E.3 playlist-compatibility rubric is a different target and is
inventoried separately, not merged with similarity ratings. Stage 2B provides
useful splitting/ranking patterns, but its FMA centered-five-second listening
judgments are not compatible supervision. Unrated pairs never become negatives.
Same-rating comparisons are ties and produce no preference constraint.
Conflicting numeric evidence and uncertain pairs are excluded. Duplicate exports
do not increase the number of judgments.

The single deterministic 60/20/20 partition uses source/video-connected track
groups. Pairs crossing partitions are dropped, not reassigned. Artist sensitivity
additionally joins all normalized credited artists transitively. No metadata is
passed to the model. The evidence gate requires 30 informative training anchors
and 200 preferences, and 15 informative anchors / 50 preferences in each held-out
partition. These are conservative exploratory adequacy floors, not a formal
power calculation. Correlated preferences do not replace independent anchors;
uncertainty is reported at anchor level and the small test set remains a limit.
The partition is not searched or optimized using model performance.

Audio is decoded exactly through Stage 5E.1's mono/resample function at 48 kHz.
480,000-sample non-overlapping chunks cover every source sample. Only the last
partial chunk is cyclically repeated to 480,000 samples. There is no trimming or
loudness normalization. Arm D's quantization, mel extraction, and independent
view sample path are reused under the exact HTSAT-tiny fusion checkpoint. Each
window supplies four identical mel views with `longer=False`, matching Arm D's
independent-view convention. Float64 L2 normalization yields 512-D float32
vectors. Stored timestamps end at the last real source sample, excluding padding.

B0 is historical `d_clap`. B1 averages and renormalizes all segment vectors,
then takes cosine. M1 uses a shared 512→16 tanh projection, then averages absolute
differences and products over all segment pairs before a 32→1 linear head.
Its output is sigmoid similarity. Section order is retained in the artifact but
this minimal model is permutation-invariant; it does not learn musical form.
Training uses only strict human preferences and anchor-macro logistic loss.
The protocol records AdamW, regularization, seed, epochs and validation stopping.
There are 8,241 trainable parameters; CLAP is frozen and never optimized.

Increasing 25/50/100% fractions select only training constraints by a fixed hash
order. Validation chooses epochs. The 100% model is the predeclared final model;
neither fraction nor architecture is chosen using test performance. A fixed
5-percentage-point gain and a paired-bootstrap lower 95% bound above zero define
credible improvement. Broad representation inadequacy cannot be proved by one
small learner: `REPRESENTATION_LIMITED` would mean this particular frozen
representation/aggregation/model experiment did not demonstrate a credible gain.

Commands from `ml/audio_similarity`:

```bash
.venv/bin/python -m audio_similarity.cli.stage5g1 prepare
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUBLAS_WORKSPACE_CONFIG=:4096:8 .venv/bin/python -m audio_similarity.cli.stage5g1 extract
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUBLAS_WORKSPACE_CONFIG=:4096:8 .venv/bin/python -m audio_similarity.cli.stage5g1 replay
.venv/bin/python -m audio_similarity.cli.stage5g1 train
.venv/bin/python -m audio_similarity.cli.stage5g1 verify
```

Extraction uses the existing local GPU and checkpoint; no model/audio download
is authorized. Replay refuses to invoke CLAP on any missing cache entry. Prior
execution ledgers are never overwritten. JSON and NPZ outputs use the existing
canonical create-once writers. A changed input or implementation requires a new
reviewed run identity rather than overwriting the old experiment.

After extraction, replay, training, and the verification script, seal the run:

```bash
.venv/bin/python reports/stage5g1_clap_similarity/v1/verification/audit_outputs.py
.venv/bin/python -m audio_similarity.clap_similarity_closeout
```

Read `experiment_report.md` for the completed result. The final outcome is
`REPRESENTATION_LIMITED` under the frozen operational rule, with an explicit
limitation: the small held-out set and epoch-1 selection do not establish that
CLAP intrinsically lacks the required information.
