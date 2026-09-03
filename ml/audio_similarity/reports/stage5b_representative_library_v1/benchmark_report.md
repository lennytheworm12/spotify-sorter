# Stage 5B — Representative Owner-Library Benchmark v1

Status: `STAGE5B_REPRESENTATIVE_LIBRARY_AWAITING_HUMAN_REVIEW`

## Frozen evaluation contract

- resolver stack: `STAGE5B_RESOLVER_CANDIDATE_V1`
- benchmark manifest SHA-256: `cec77ef960fa5da7725e8a0df244a5829fb90fdc5463dc1ce6a2ef72667f4285`
- deterministic 100-track sample from liked songs plus owner-owned playlists
- all historical DEV/calibration/challenge identities excluded before sampling
- Q0 discovery: `"{primary_artist}" "{normalized_title}" official` via metadata-only `ytsearch5`
- no benchmark-driven query, parser, threshold, or resolver mutation permitted

## Discovery

- benchmark tracks: **100**
- searches: **100**
- fallback searches: **0**
- provider failures: **0**
- warnings: **0**
- yt-dlp: `2026.08.19`

## Automated resolution

- AUTO_MATCH: **81/100 (81.0%)**
- EXACT_RECORDING: **81**
- REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK: **0**
- REPRESENTATION_EQUIVALENT_MASTER_FALLBACK: **0**
- MATCH_UNCERTAIN: **19**
- ≥90% product coverage gate: **MISS**
- source composition: `{"ART_TRACK_TOPIC": 20, "AUDIO_PRESENTATION": 2, "LYRIC_VIDEO": 13, "OFFICIAL_AUDIO": 8, "OFFICIAL_LYRIC_VIDEO": 4, "OFFICIAL_MUSIC_VIDEO": 3, "OTHER": 31}`
- unresolved reasons: `{"EXPLICIT_CONFLICT": 3, "METADATA_INSUFFICIENT": 16}`

## Human precision gate

- selected candidates requiring review: **81**
- completed: **0**
- labels: `{}`
- SAFE precision: **pending**
- product safety target: **≥95% SAFE**

Human precision remains pending until every automatically selected candidate is reviewed. The benchmark is frozen evaluation evidence and must not be used to tune this stack.

## Adversarial comparison

The separately reported adversarial challenge is **43/50 (86%)** after the human-safe representation fallback. Its metric is not merged with this representative sample.

## Limitations

- human SAFE precision is not available until the 81 selected sources are reviewed
- this deterministic random sample happened to contain no title parsed as a version family; the adversarial challenge remains the relevant stress evidence for live/remaster fallbacks
- metadata-only resolution cannot directly verify audio cleanliness or equivalence
- the 81% coverage miss is benchmark evidence; this frozen benchmark must not become tuning data

## Verification

- focused representative benchmark tests: **6 passed**
- complete Stage 5B resolver regressions: **437 passed**
- full non-heavy `ml/audio_similarity` suite: **898 passed, 12 deselected**
- known warnings: **11 existing librosa warnings**

## Scope guards

Audio downloads 0; video downloads 0; Stage 5A calls 0; CLAP calls 0; MuQ calls 0. The frozen resolver remains a candidate stack, not production activated.
