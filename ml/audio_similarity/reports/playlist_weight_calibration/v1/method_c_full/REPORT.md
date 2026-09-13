# Full-corpus Method C materialization

**Method C: COMPLETE. Calibration readiness: WAITING_FOR_FEATURES.**

The original 28-playlist manifest contains 2,032 requests.
1,924 distinct retained recording IDs were
materialized without changing source membership. The 105
requests without validated retained audio remain explicit; the extension corpus
was not added.

| Evidence | Count |
|---|---:|
| Method C complete | 1924 |
| Existing Method C reused | 293 |
| Newly computed Method C | 1631 |
| New on CPU / GPU | 373 / 1258 |
| Missing Method C / source-blocked retained recordings | 0 / 0 |
| Exact-source MuQ / centered30 | 1924 / 1924 |
| Existing Gemini profiles / usable specific-style mappings | 284 / 266 |
| Common audio + existing profile population | 284 |

The full corpus still lacks 1640
Gemini profiles. Completing Method C does not silently substitute the smaller
profile-covered population for the full corpus. Profile presence and usable
specific-style mapping are reported separately. No new Gemini calls occurred.

The GPU handoff required terminal acquisition states, actual process exit and
released VRAM. Its predeclared CPU/GPU parity check passed on
9 chunk comparisons; maximum component difference was
2.78806919e-07, and minimum cosine was
0.999999999998. Completed CPU outputs and
original ledgers were preserved. Engineering parity attempts are counted
separately from extraction; any interrupted CPU chunk attempts remain in the
original append-only ledgers.

Continuation validation caught a float32 cast in the original CPU resume path.
1 affected pool was reconstructed from unchanged
original float64 chunk vectors, with no inference. The original artifact remains
intact, and the corrected continuation records explicit source hashes and repair
provenance. A regression test reproduces the original failure and verifies that
future resumes preserve the original chunk values exactly.

The ordered full Method C matrix and common-population submatrix passed
symmetry, diagonal and byte-replay checks. The replay reused
1924 features with **zero inference calls**.
Historical input/source and published-artifact integrity checks passed.

The focused suite passed **28 tests**.
The final non-heavy suite passed **1479 tests**;
12 heavy tests were excluded and 11 warnings
were reported. Focused fixtures cover native chunk boundaries, explicit legacy
boundary failure, incomplete-track resume, source/config mismatch rejection,
zero-encoder replay, matrix ordering/symmetry/byte replay, separate readiness,
and acquisition-release/continuation guards.

## Artifacts

Private run: `.research_audio/playlist_calibration_method_c_gpu_v1`.
Full matrix SHA-256: `1549ab23230f0e51484da7ec700a1e229ea7e14b73d4f17d11f90e9be01d9d62`.
Configuration SHA-256: `b9ecd3e0b90bbe9d0ab51fa4986912e2aa0b123bba929fd15c52e49aef136e01`.
Corpus SHA-256: `bebb90d013cbbf5092d64eda16776f57aed9635cbb5f13d6cbf88926c00b1312`.
Private artifact-manifest SHA-256: `c7510202a7ed3df8a91d2e406c18c2abe416561f357b06e69b3a352bf6886a55`.
See `execution_validation.json`, `track_status.json`, and ordered ID sidecars
for exact counts, hashes, status rows and validation details.

No weight search, calibration, representation selection, playlist mutation or
production activation was performed. Source identity is hash-linked to retained
validated acquisitions; it is not a claim of owner listening verification for
every recording. Split and source-use feasibility remain separate from this
feature-materialization result.
