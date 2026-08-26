# Stage 2B Balanced Holistic Encoder Fusion Decision

## Claim boundary

**This is a single-reviewer personal perceptual-alignment benchmark.** It does not establish general human consensus, population-level superiority, or inter-rater reliability. Bootstrap intervals describe variation across frozen queries for the designated reviewer's judgments.

## Frozen comparison

- Validation-preselected individual: `laion_clap`
- Validation-preselected fusion: `laion_clap+muq_mulan_large`
- TEST query-macro accuracy, individual: 0.7719
- TEST query-macro accuracy, fusion: 0.7594
- Fusion minus individual: -0.0125
- Paired 95% query-bootstrap CI: [-0.1260, 0.0969] (50,000 draws)

## Evidence quality

- Primary trials: 240
- Binary A/B trials: 157
- TEST binary trials / represented queries: 59 / 16
- Tie rate: 0.267
- Neither rate: 0.079
- Inter-rater agreement: not applicable under `single_reviewer_v2`

## Coefficient stability and complementarity

- Coefficient 95% intervals: `[[0.4238682452138867, 0.9609634675807454], [-0.16185477103085552, 0.6409196101932647]]`
- Coefficient sign retention: `[1.0, 0.9085]`
- Fusion rescues: 6
- Fusion-created errors: 5
- MuQ correct-minority cases: 3

Full per-model, per-query, per-source, bootstrap, redundancy, engineering, and complementarity diagnostics are frozen in `test_metrics.json`.

## Final verdict

`SINGLE_ENCODER_WINS`

Selected Stage 2B representation: `laion_clap`. This is the only Stage 2B verdict. No MIR/MERIT fusion, full-song sampling, Spotify acquisition, or application integration was started.
