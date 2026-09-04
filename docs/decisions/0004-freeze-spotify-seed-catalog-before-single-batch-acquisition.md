# 0004: Freeze the Spotify Seed Catalog Before Single-Batch Acquisition

## Status

Accepted for Stage 5D.0A research. Only Batch 0001 is authorized.

## Date

2026-09-04

## Context

The owner supplied `POPULAR_COMMERCIAL_2000_2026_SPOTIFY_SEARCH_V1`:
27 years, eight style buckets, 25 selected recordings per cell, using only
Spotify Web API search metadata. Acquisition must not influence catalog or
batch membership. The first sustained batch is also a provider-safety trial.

## Decision

Collect the literal `year:<year> genre:<alias>` searches with the frozen alias
lists. Use US market, ten results per page, alias-page rounds, native rank then
alias order for candidate admission, and at most 75 distinct Spotify IDs per
cell. Preserve each observed alias/native-rank occurrence and checkpoint every
page locally. Stop collection on Spotify rate limiting and persist its cooldown.
These parameters are pinned before any YouTube work.

Deduplicate recordings before allocation. ISRC is primary; absent matching ISRC,
use normalized title, identical primary artist, credited-artist Jaccard overlap
of at least one half, and duration difference at most three seconds. Complete-link
groups prevent chains of near-duration records from merging distant versions.
Qualified remix/live/acoustic/sped/slowed/rerecording versions remain distinct.
Ownership goes to the strongest alias/rank evidence, then deterministic bucket
and year ties. Backfill from remaining owned candidates, redistributing underfill
within the same year by largest remaining surplus and bucket-name tie.

Freeze the complete catalog and its seeded SHA-256 ordering before constructing
Batch 0001. The command accepts no external catalog or live batch-number argument.
Later batch membership is visible in the global manifest but is not executed.

One worker owns the existing retained-media lock, not a repository-wide lock.
Queue state has one writer. Stop commands write a separate flag and cannot clobber
progress. Random 30–60-second track deadlines, per-request retry deadlines, and
circuit state persist outside Git. Retries are bounded to four attempts total.
The first genuine YouTube 429 imposes at least 15 minutes of cooldown; a second
opens the circuit. Two consecutive unrelated verification failures or three
consecutive tracks exhausting transient retries (or receiving HTTP 403) also stop
the worker. Explicit anti-abuse responses stop immediately. Resume
does not reset an open circuit.

Use the current selector-aware resolver and frozen Stage 5B.3 selector unchanged.
Freeze each chosen video before exact-URL acquisition. Reuse valid retained
sources and existing Stage 5C representations where their identities agree;
otherwise materialize the frozen centered30_v1 representation. Full compressed
sources remain in the shared ignored media root. Seed-specific source linkage
uses its own local index so the amended 100-track review index is not changed.

## Alternatives Considered

- External charts, scraped playlists, and third-party catalogs: excluded by V1.
- Selecting easy tracks for Batch 0001: would bias both corpus and safety evidence.
- Automatically rolling into Batch 0002: outside the authorized operational scope.
- One mutable queue file written by both worker and stop command: risks lost progress.
- Retrying through verification or repeated 429 responses: defeats the safety trial.

## Consequences

Catalog coverage reflects Spotify search, the fixed market, frozen aliases, and
observed metadata, not an exhaustive history of commercially successful music.
2026 is partial at the collection date. Recording equivalence is conservative
metadata deduplication, not an audio identity claim. Legitimate underfills remain
visible. A circuit-stopped batch is a valid safety outcome, not permission to
change queries, add cookies, substitute videos, or start the next batch.

## Commands

From `ml/audio_similarity`, use `.venv/bin/python -m audio_similarity.cli.stage5d0a`:

- `collect`: checkpoint/resume Spotify metadata only.
- `prepare`: require all 216 cells, deduplicate, allocate, and freeze the catalog and Batch 0001.
- `run`: validate frozen hashes and run only Batch 0001.
- `status`: read queue/provider status without disturbing the worker.
- `stop`: request graceful stop; completed source/cache writes are preserved.
- `resume`: resume nonterminal work after a normal stop, retaining pacing deadlines.
- `report`: snapshot non-media metrics and health evidence after stop/completion.

An open circuit requires an owner decision; the CLI intentionally has no reset
or force-continue option. Finished terminal failures are not silently retried by
resuming the batch.
