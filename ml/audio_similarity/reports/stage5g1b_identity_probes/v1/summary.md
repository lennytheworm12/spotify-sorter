# Stage 5G.1B closeout

**ZERO_SHOT_NOT_ESTABLISHED.** The tested CLAP text probes do not justify an interpretable compatibility filter or reranker.

- Four general axes, 42 fixed prompts, 100 frozen tracks; no model training or new audio inference.
- Best playlist axis: musical family, AUC 0.607 (descriptive interval 0.483-0.733). On rated Arm-D Top-10 neighbors it falls to 0.392.
- Any confident mismatch catches **1/55 bad pairs** but flags **15/251 good pairs**. Those good-pair flags are counterexamples to using the layer as a filter.
- Vocal delivery changes from AUC **0.495 to 0.674** between phrasings. Reliable track profiles: family 56/100, production 17/100, rhythm 8/100, vocals 7/100.
- Family prompts assign 72 or 78 tracks to their rap/hip-hop option depending on phrasing. Rhythm phrasings shift from 71 tracks selecting a driving beat to 76 selecting no regular pulse. These are model outputs, not verified descriptions of the songs. They expose prompt dependence and vocabulary bias.
- Continuous probes sometimes improve over D cosine on the full reviewed pool (family +0.100 AUC), but that does not survive the relevant neighbor/observability checks. The additional cosine-caliper controls are descriptive and do not establish reranking gains.

The six historical notes concern only three motivating anchors. We therefore cannot establish that most false positives share a small causal taxonomy, nor conclude that the errors are irreducibly heterogeneous. Weak zero-shot observability is the demonstrated limitation. Lowering confidence thresholds after seeing these results would not validate the descriptions.

Smallest next experiment: a separately frozen **12-20 pair blinded taxonomy audit**, balanced across bad/good judgments, unrelated artists, and probe hits/false alarms/misses. Validate whether the proposed musical differences actually explain judgments before choosing a targeted pretrained detector or returning to learned similarity. No new queue is created in this stage.

See report.md for methods and all axis results, counterexamples.json for named illustrations, and verification.json for tests, hashes and replay evidence. No production behavior or historical artifact was changed.
