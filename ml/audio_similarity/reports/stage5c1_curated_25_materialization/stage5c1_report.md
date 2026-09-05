# Stage 5C.1 — Curated 25-track materialization and representation sanity check

Verdict: **PIPELINE_AND_REPRESENTATION_SANITY_PASSED**

This deliberately curated experiment verifies the real exact-source materialization path and checks basic musical structure. It is not a representative accuracy benchmark and does not authorize production activation or representation tuning.

Manifest: `8264bc9eb65164ea6dab21ef936340eb74efa4f8c3c46c42f3b84dd5e9beed3f` (frozen before acquisition; 25 tracks; five groups of five; zero substitutions).

## A. Pipeline reliability

- Tracks attempted: **25/25**
- Exact-ID acquisitions: **25/25** success, **0** failure
- Decode and complete K=3 windows: **25/25**, **25/25**
- CLAP / MuQ / full materialization: **25 / 25 / 25**
- Cache writes: **25/25**
- Cleanup: **25/25**; temporary root absent after cleanup
- Cache rerun: **25/25** identity matches, zero acquisitions, zero encoder inference
- Silent substitutions: **0**; corrupt cache entries: **0**

The first pass took 126.24s wall clock. Exact-URL yt-dlp calls accounted for 47.20s summed request time and Stage 5A materialization took 16.12s. The cache-only rerun took 0.48s.

yt-dlp emitted 27 recorded warnings and zero provider errors. Twenty-five warnings report the missing optional YouTube JavaScript runtime; two additional extractor recovery warnings occurred on one request. Every request still produced the exact requested video ID and a valid 30-second WAV excerpt.

## B. Representation sanity

Combined mean within-group similarities:

- A, same artist / similar style: **0.7024**
- B, same artist / varied style: **0.7060**
- C, cross-artist lo-fi/chillhop: **0.6495**
- D, cross-artist rhythmic Korean pop: **0.6712**
- E, heterogeneous negative control: **0.5839**

The intended contrasts are visible: C within (0.6495) and D within (0.6712) both exceed C-vs-D (0.5441); A within exceeds A-vs-E (0.5439); and C/D within each exceeds its heterogeneous comparison. Group E has the widest combined within-group spread (0.1342), rather than forming an artificial cluster.

Group B is not uniformly identical despite its shared artist. CLAP is comparatively steady, while MuQ spans 0.2360–0.8539 with standard deviation 0.2338, larger than Group A's 0.1051. That is consistent with meaningful production variation rather than a single artist-identity score.

No zero/NaN vector, failed normalization, repeated embedding hash, repeated representation identity, repeated source-audio hash, near-1.0 collapse, tiny-variance collapse, or CLAP/MuQ duplication was detected. CLAP contributes 66.0% of weighted off-diagonal variation under the frozen 0.7173/0.2827 weights; MuQ still produces substantial pairwise disagreements and changes the combined ordering.

The nearest-neighbor queue contains an analyst structural note for every track and leaves explicit human fields blank for owner playback confirmation. No playback-based human judgment is claimed by this automated run.

## Contract and scope guards

- Discovery and Stage 5B.3 selection were not invoked or changed.
- Every media request used `https://www.youtube.com/watch?v=<frozen_id>`; searches executed: **0**.
- Stage 5A centers `[5, 15, 25]`, 5-second windows, per-segment L2/mean/final L2, encoder revisions, and weights remained frozen.
- Source media was temporary and deleted; representations remain in the ignored Stage 5A cache/dataset location.
- The 25-track membership was not changed after results and no failed source was substituted.
- No CLAP/MuQ tuning, training, MERT/MERIT, lyric analysis, clustering logic, or production activation occurred.

## Conclusion

The exact selected-source → temporary audio → frozen CLAP/MuQ → cache → cleanup pipeline passed 25/25, and the representations show the expected broad musical relationships without a collapse pathology. The proper next step is a larger frozen representative materialization run; these curated results must not be presented as corpus-level accuracy.
