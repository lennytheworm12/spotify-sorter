# Stage 5B.1D Targeted Rediscovery Diagnostic

## Outcome

Targeted rediscovery did **not** increase automated candidate-resolution coverage.
The unchanged resolver remains at **42/50 AUTO_MATCH (84%)** and **8/50
MATCH_UNCERTAIN (16%)**. None of the four new candidate pools produced an
existing-resolver `AUTO_MATCH`; therefore the diagnostic 45/50 (90%) milestone
was not reached and there are no new selections requiring human review.

This result does not validate the query strategy as a production fallback.
Three targets remain candidate-set failures. One target gained more explicit
modified-version metadata, but the candidate still lacked sufficient
duration/release identity for safe selection.

## Frozen scope and regression

- Branch: `ml/stage5b1d-targeted-rediscovery`
- Starting commit: `83ab23118f2d258fdc849df3e3653e1d70f1b497`
- Pre-search query checkpoint: `014553b`
- Frozen first-pass challenge discovery SHA-256:
  `95bb1ca905a05fcc4167da10e3dfd6cf267600a4dfb1898b491d28ba855e6fb4`
- Frozen Stage 5B.1C-C decisions SHA-256:
  `740b085b2061935b1d66586534ed4bc418c4ed2562f0cd96efeb4b596748793c`
- Frozen remaining-tail diagnostic SHA-256:
  `9968f84d5dbd4825f88dd0fdc329971d93db87e0b2cd9f2b89364f2cbf145ebf`
- Targeted query artifact SHA-256:
  `2064db61cf6d87af346fd0e126d588b29a4a0216acad56b1bb6e9a0f51454b77`

The deterministic pre-run replay reproduced the frozen resolver stack exactly:

| Layer | Incremental selections | Combined |
| --- | ---: | ---: |
| Balanced V1 | 29 | 29/50 |
| Stage 5B.1C-A | +6, same IDs | 35/50 |
| Stage 5B.1C-B | +5, same IDs | 40/50 |
| Stage 5B.1C-C | +2, same IDs | 42/50 |

All prior candidate IDs remain unchanged. No resolver, duration, version,
source-neutral, or conflict rule was modified.

The rediscovery scope was derived from the frozen diagnostic's
`CANDIDATE_SET_FAILURE` rows and contained only:

- `s5b1c_021` — Bad Habits - FISHER Remix
- `s5b1c_029` — The Night We Met - Live at the Ryman
- `s5b1c_032` — Landslide - 2015 Remaster
- `s5b1c_040` — Another Love - Slowed Down

Tracks `030`, `033`, `034`, and `041` were not searched.

## Query design

Each target received the same three deterministic formulations, derived from
structured target metadata rather than track-specific code:

1. quoted primary artist + core title + exact version phrase;
2. quoted core title + exact version phrase + all credited artists;
3. quoted primary artist + combined title/version + `official audio`.

The builder retains named remix artists, live venue/year, remaster year, and
modified-version descriptors while excluding presentation noise. Query count
is hard-bounded at three per track.

## Live discovery execution

- Provider: `yt-dlp` Python API `2026.08.19`
- Search: `ytsearch5`
- Requests: sequential, metadata only
- `download=False`, `simulate=True`, `skip_download=True`
- Pacing: 2 seconds between query variants; 3 seconds between tracks
- Tracks attempted: 4
- Queries attempted: 12
- Queries with candidates: 9
- Query failures: 0
- Provider warnings: 0
- Unique candidate video IDs returned across queries: 27
- Newly introduced IDs after deduplication against the original top five: 21
- Elapsed wall time: 38.17 seconds
- Audio downloads: 0
- Video downloads: 0
- Stage 5A / CLAP / MuQ calls: 0

The combined-title/`official audio` formulation returned zero candidates for
the remix, live-at-Ryman, and remaster targets. It returned five candidates for
the slowed target. The other two formulations returned five candidates for
each track.

## Per-track results

| Target | New IDs | Strongest new evidence | Existing-resolver blockers | Classification |
| --- | ---: | --- | --- | --- |
| `021` Bad Habits - FISHER Remix | 6 | No result combined the requested song with the FISHER remix. The closest artist-bearing result was a different Ed Sheeran song and AgentTabak remix. | Wrong core title, wrong named remix, mashup/mix conflicts, extreme durations | `STILL_CANDIDATE_SET_FAILURE` |
| `029` The Night We Met - Live at the Ryman | 5 | Searches found unrelated Ryman performances, a different Lord Huron cover, and a different artist/song with similar wording. | Wrong title and/or performer; absent requested performance; wrong venue/version; large duration deltas | `STILL_CANDIDATE_SET_FAILURE` |
| `032` Landslide - 2015 Remaster | 5 | A generic `Fleetwood Mac- landslide` result had close duration but no 2015-remaster evidence. `Storms (2015 Remaster)` had the requested remaster year but the wrong song. | Requested remaster evidence absent on Landslide candidates; explicit live conflicts; wrong core title on the only 2015-remaster result | `STILL_CANDIDATE_SET_FAILURE` |
| `040` Another Love - Slowed Down | 5 | Search found slowed variants, including distributor/Topic evidence, but the most plausible full candidate was 14 seconds shorter than the 299-second target and tied to a separate `sped up + slowed` release identity. A 25-second result was only a fragment. | Duration gate; incomplete release identity; several alternatives add explicit reverb or extreme/one-hour modifications | `METADATA_INSUFFICIENT_AFTER_REDISCOVERY` |

### Safety observations

- Specific query terms did not become correctness evidence. Every candidate
  still passed through the unchanged feature and resolver cascade.
- Explicit wrong remixes, covers, live performances, reverb variants, mashups,
  and wrong performers remained rejected.
- The resolver correctly refused to infer that `Landslide` was the 2015
  remaster merely because duration and performer matched.
- The resolver correctly refused to accept slowed uploads merely because the
  target also requested a slowed version; exact release/duration ambiguity
  remained material.

## Search-leverage analysis

| Target attribute | Observed leverage |
| --- | --- |
| Explicit remix artist | None. FISHER tokens attracted unrelated mixes and mashups, not the requested remix. |
| Live venue | Negative/insufficient. `Ryman` retrieved unrelated artists and performances. |
| Live year | Not available in the target metadata beyond the release context; no requested performance surfaced. |
| Remaster year | Insufficient. `2015 Remaster` surfaced the wrong Fleetwood Mac song while Landslide results lacked remaster evidence. |
| Modified-version phrase | Partial. `Slowed Down` surfaced more explicit slowed candidates but not enough release/duration identity for selection. |
| Quoted exact version | Over-constrained some variants: three combined quoted/official-audio searches returned zero results. |
| Artist inclusion | Did not prevent unrelated results when combined with venue/remix terms. |

The experiment exposed a retrieval problem with literal quoted formulations:
YouTube search often matched isolated distinguishing tokens rather than the
complete recording identity. This is evidence for a future discovery-design
iteration, not permission to loosen the resolver.

## Measurement and review state

| Metric | Result |
| --- | ---: |
| Baseline automated coverage | 42/50 = 84% |
| Rediscovery AUTO_MATCH | 0/4 |
| Resulting automated coverage | 42/50 = 84% |
| Absolute coverage gain | 0 percentage points |
| Diagnostic 90% target reached | No |
| Materially stronger but unresolved pool | 1/4 |
| Still candidate-set failures | 3/4 |
| New selections requiring review | 0 |

The human-audit queue and CSV are intentionally empty apart from their schema
because no candidate became an `AUTO_MATCH`. No human or Sol labels were
fabricated, and Sol was not rerun.

## Recommendation

Do **not** productionize this exact three-query fallback. It added request cost
without increasing safe automated coverage on the four intended failures.

The next bounded experiment should either test a different discovery strategy
on a new/frozen basis (especially avoiding over-constrained quoted YouTube
queries) or move the remaining plausible-candidate cases to Tier-3 audio
comparison. The three still-missing exact recordings require better retrieval,
not a weaker metadata resolver. The slowed-version case is a reasonable audio-
comparison candidate because metadata exposes the correct family but cannot
establish exact recording equivalence safely.

Audio comparison is therefore still needed for at least part of the unresolved
tail. This diagnostic does not implement it and does not activate any fallback
in production.

## Validation

- Focused Stage 5B.1D query/discovery tests: 21 passed.
- Focused Stage 5B resolver regressions: 107 passed.
- Full non-heavy `ml/audio_similarity` suite: 738 passed, 12 deselected.
- The first sandboxed full-suite attempt had 17 loopback HTTP failures because
  the sandbox proxy returned HTTP 403 for `127.0.0.1`; rerunning the identical
  suite outside that proxy boundary passed all 738 selected tests.
- Existing librosa short-fixture warnings remained unchanged.

## Artifacts

- `targeted_queries.json`: frozen query contract and four-track scope
- `targeted_discovery.json`: raw normalized yt-dlp outcomes and provenance
- `rediscovery_candidate_features.json`: original/new combined feature layers
- `rediscovery_decisions.json`: unchanged-cascade decisions and classifications
- `rediscovery_human_audit_queue.json`: empty review queue
- `rediscovery_human_review.csv`: header-only review artifact
- `artifact_manifest.json`: final paths, hashes, and media-activity guard

## Reproduction

From `ml/audio_similarity`:

```bash
uv run python -m audio_similarity.stage5b1d_rediscovery prepare
uv run python -m audio_similarity.stage5b1d_rediscovery discover
uv run python -m audio_similarity.stage5b1d_rediscovery evaluate
uv run python -m audio_similarity.stage5b1d_rediscovery manifest
```

Only `discover` uses the network. Re-running it would create a new operational
observation and is not required to replay the frozen evaluation.
