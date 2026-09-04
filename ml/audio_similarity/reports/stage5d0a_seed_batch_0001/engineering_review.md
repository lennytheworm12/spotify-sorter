# Stage 5D.0A pre-launch engineering review

Reviewed 2026-09-04 against code commit `02d4974`.

## Five axes

- **Correctness:** focused tests cover deterministic recording allocation and batching,
  the 500-track boundary, no Batch 0002 dispatch, all four source/representation cache
  conditions, exact-source freezing, scratch cleanup, stop/resume, randomized pacing,
  bounded retries, nested Retry-After headers, extraction timeouts, and persistent circuits.
- **Readability:** removed the unused prototype with owner approval. Catalog collection,
  allocation, network control, per-track processing, queue orchestration, and reporting
  have separate responsibilities. The old implementation remains recoverable in Git.
- **Architecture:** reuse the current selector-aware resolver, frozen Stage 5B.3 selector,
  Stage 5A materializer, and existing research-media root. No query/selector/encoder tuning.
  Hash-pinned upstream code and representation metadata guard resumed runs.
- **Security:** official Spotify metadata endpoints only for catalog construction;
  credentials are not logged. YouTube uses guest operation without personal cookies or
  proxies. The actual temporary Git-ignore probe passed. Retained media is untracked;
  source paths are constrained to Spotify-ID directories. Active human ratings are excluded
  from these commits.
- **Performance:** serial network jobs, independent 30–60-second random deadlines,
  bounded extraction requests, no bandwidth throttle, and cache-first reuse. Sustained
  provider behavior remains a live Batch 0001 question, not a unit-test conclusion.

## Verification before launch

- Stage 5D plus retained-source focused/regression tests: **46 passed**.
- Full non-heavy audio-similarity suite after upstream approval: **1,134 passed;
  12 heavy tests deselected; 11 existing numerical/audio warnings**, in 98.95 seconds.
  Evidence: local `.research_audio/stage5d0a/prelaunch_with_upstream.xml`.
- The previous run had 1,132 passes and two Stage 2B Git-checkpoint failures because
  no upstream was configured. The owner explicitly approved the push; the branch now
  tracks its actual remote, and both checks pass without bypassing or weakening them.
- Frozen CLAP checkpoint and MuQ weights/config SHA-256 checks passed.
- Both encoders loaded together offline on the GPU, using 3,470,732,800 allocated bytes.
  This preflight performed **zero encoder inference calls**.
- An existing full retained WebM decoded through the canonical Stage 5A path. Its frozen
  24-kHz windows were `[60000,180000)`, `[300000,420000)`, and `[540000,660000)`.
- No Stage 5B artifacts or selection behavior were changed. The actively edited Stage 5C
  human-review CSV is owner work and remains untouched by this implementation.

## Remaining live evidence

Catalog and Batch 0001 hashes are frozen before any YouTube discovery. Acquisition,
materialization, sustained pacing, final cache audit, and the batch health verdict are not
claimed by this pre-launch review. Batch 0002 must remain unstarted.

## Final catalog preflight

All 216 Spotify cells completed with 75 admitted candidates each. Global recording
deduplication yielded 14,502 candidate recordings from 15,535 distinct Spotify IDs.
The final catalog contains **5,400 tracks**, exactly 25 in every year/bucket cell;
no underfill redistribution was required. Batch 0001 contains exactly 500 tracks.

The initial freeze attempt rejected nine hyphen-formatted Spotify ISRC values.
ISRC comparison and output now canonicalize only identifier formatting (NFKC,
uppercase, removal of spaces/hyphens), while preserving `spotify_raw_isrc`.
No YouTube request preceded this repair or the successful freeze. The failed
allocation remains locally at
`.research_audio/stage5d0a/spotify_catalog/preflight_allocation_unformatted_isrc.json`.
The focused ISRC regression passed with the other catalog tests.

Ten of the frozen 500 Spotify tracks have metadata durations below 29.5 seconds.
They remain in the denominator and are not replaced. Valid full audio is retained;
any inability to satisfy the unchanged representation windows is recorded as failure.

## Boundaries

The catalog measures the supplied Spotify search recipe, not an exhaustive commercial
chart history. US market and observed alias-page ranks are explicit construction parameters;
2026 is partial. Recording deduplication is conservative metadata inference, not audio proof.
Valid short full recordings may be retained, but the unchanged materializer still rejects
sources unable to support its frozen windows; no replacement segmentation is introduced.
