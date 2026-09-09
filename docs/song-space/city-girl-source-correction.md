# City Girl source correction — 2026-09-09

Corrected the live library map's `City Girl — City Girl` (Neon Impasse,
Spotify `5nEmOAtwk043VtpLQXWAQi`). Its previous retained recording was
Shanti Dope's unrelated song of the same name, confirmed wrong by the owner.

The replacement is the distributor-provided City Girl recording:
https://www.youtube.com/watch?v=euZUF2m_E4k. Artist, title, album, release date
and approximately 210.6-second duration match the intended recording.

Old source SHA-256:
`bdd0c13a83b408568dabf70500b98cf2f598f335bf0ba1d9b153dcc27e58a9b1`.
New source SHA-256:
`024662c1c7093d8033f381f0852ff062e1da107f33a9ab639df7ed2ff7ea19cc`.

Reused the existing frozen centered-30-second processing contract and cached
CLAP/MuQ models, rebuilding three segments per encoder for this one recording.
The map still uses CLAP alone. This is a source repair, not a model change.

Historical sources, batch ledgers, original representation database and map v1
remain unchanged, verified against the pre-execution hash ledger. An explicit
hash-locked correction record overlays the completed library row during export.
Frozen C track corrections are rejected. The frozen C100 map is byte-identical.

Private local evidence, relative to `ml/audio_similarity/`:

- `.research_audio/source_corrections/city_girl_v1/`: candidate metadata,
  checked download, isolated source, original execution, correction and replay.
- `artifacts/source_corrections/city_girl_v1/representations.sqlite`: new cache.
- `.research_audio/library_batches_v1/source_corrections.json`: overlay index.
- `.research_audio/song_space/v2/`: regenerated map, audio index and provenance.

The new export contains 1,257 tracks and 11,312 links. Two consecutive exports
produced identical artifacts. Cache replay loaded no encoders, performed zero
new inference and made zero new network requests. Original execution is retained
in `execution_initial.json`. Chromium verified the full audio response hash,
HTTP 206 byte ranges, playback and seeking. Five focused exporter tests pass.

Launch the corrected map from `frontend/`:

```bash
SONG_SPACE_DATA_DIR="$PWD/../ml/audio_similarity/.research_audio/song_space/v2" pnpm dev
```

Earlier map findings involving this incorrectly sourced node describe v1 and
must not be interpreted as evidence of a CLAP musical-identity failure.
Other source-quality findings remain separate unresolved issues.

Full non-heavy regression verification: **1,308 passed, 12 deselected,
11 warnings** in 126.59 seconds. The suite ran with localhost access for its
HTTP fixtures; the initial sandboxed attempt was interrupted by a localhost
network restriction and is not counted as a passing run.
