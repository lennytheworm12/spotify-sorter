# Development comparison closeout

Completed 284 songs across 10 playlists / 8 curator groups.
Gemini: 283 new calls, $1.68255450; one prior compatible profile reused.

These are grouped development estimates. They do not select a production winner or admission cutoff.

| Predeclared procedure | NDCG@20 | Recall@20 | Recall@10 | NDCG delta vs M3 | Paired 95% interval |
|---|---:|---:|---:|---:|---|
| centered30_v1/audio_mixture | 0.6254 | 0.7326 | 0.5747 | -0.1385 | [-0.2056, -0.0799] |
| centered30_v1/clap_only | 0.6254 | 0.7326 | 0.5747 | -0.1385 | [-0.2056, -0.0799] |
| centered30_v1/joint_canonical | 0.6173 | 0.7240 | 0.5729 | -0.1465 | [-0.2116, -0.0897] |
| centered30_v1/joint_residual | 0.6173 | 0.7240 | 0.5729 | -0.1465 | [-0.2116, -0.0897] |
| frozen_m3 | 0.7638 | 0.8299 | 0.6719 | +0.0000 | [+0.0000, +0.0000] |
| joint_canonical | 0.7863 | 0.8542 | 0.7014 | +0.0224 | [+0.0026, +0.0350] |
| joint_residual | 0.7863 | 0.8542 | 0.7014 | +0.0224 | [+0.0026, +0.0350] |
| m3_canonical | 0.7638 | 0.8299 | 0.6719 | +0.0000 | [+0.0000, +0.0000] |
| m3_residual | 0.7638 | 0.8299 | 0.6719 | +0.0000 | [+0.0000, +0.0000] |
| method_c_full_song/audio_mixture | 0.7863 | 0.8542 | 0.7014 | +0.0224 | [+0.0026, +0.0350] |
| method_c_full_song/clap_only | 0.7863 | 0.8542 | 0.7014 | +0.0224 | [+0.0026, +0.0350] |
| method_c_full_song/joint_canonical | 0.7863 | 0.8542 | 0.7014 | +0.0224 | [+0.0026, +0.0350] |
| method_c_full_song/joint_residual | 0.7863 | 0.8542 | 0.7014 | +0.0224 | [+0.0026, +0.0350] |
| muq_only | 0.4896 | 0.5816 | 0.4392 | -0.2742 | [-0.3684, -0.1984] |

Inspect `results.json` for each fold’s selected settings and per-stratum results. `inner_search_ledgers.json.gz` retains every configuration’s metrics and selection reasons.

Limitations: small source-selected development sample; missing recordings are listed without replacements; source-use documentation remains pending; catalog nonmembers are unlabeled. No untouched lockbox, suitability calibration, or playlist writes were used. Repeated masks are not independent curators.
