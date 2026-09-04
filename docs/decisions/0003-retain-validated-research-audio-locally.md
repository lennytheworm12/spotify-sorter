# 0003: Retain Validated Research Audio Locally

## Status

Accepted for research-stage acquisition; retained media remains local-only.

## Date

2026-09-04

## Context

Earlier Stage 5C materialization downloaded bounded audio inputs, derived frozen CLAP and MuQ representations, and deleted source media. That minimized retained media, but it also required another provider request whenever the owner wanted local review playback or a later representation experiment needed the same validated source.

The amended Stage 5C.2 V2 review corpus now freezes 100 Spotify-to-YouTube source mappings, including the two selector-aware recoveries. Those exact mappings are stable research inputs and should not be rediscovered or repeatedly downloaded.

## Decision

Every successfully validated research acquisition will retain its complete compressed source audio in the project-local, Git-ignored `ml/audio_similarity/.research_audio/` cache.

Each source is keyed by Spotify track ID and records the frozen YouTube ID, byte SHA-256, technical media metadata, acquisition provenance, and representation linkage. The existing review server range-streams these local files. Temporary downloads, decode files, PCM/WAV intermediates, failed fragments, and transcoding scratch are deleted.

Retained audio is never committed, pushed, placed in Git LFS, or loaded from a personal browser profile. Exact frozen source IDs remain the authority; a cache miss may reacquire that exact ID but may not invoke discovery, selection, or substitution.

## Alternatives Considered

### Delete source media after every representation run

Rejected because it causes unnecessary repeated network acquisition and prevents dependable local seeking during human review.

### Commit media or use Git LFS

Rejected because the corpus is local research material, not repository source data.

### Retain only a 30-second excerpt

Rejected because future rolling, temporal, and structure-aware representations need the complete validated source.

### Replace original compressed media with browser derivatives

Rejected because a playback derivative is not the original acquired byte identity. Browser-compatible derivatives may coexist locally when needed.

## Consequences

- Future representation work can reuse the same exact source bytes without rediscovery or reacquisition.
- Local disk use increases by the compressed size of validated source media.
- Cache validation must check Spotify ID, YouTube ID, file size, and SHA-256 before treating a source as reusable.
- Review playback no longer depends on YouTube embeds when the local corpus is complete.
- Cleanup logic must distinguish durable validated media from disposable scratch files.
