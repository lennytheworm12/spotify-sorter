# Problematic library source corrections — 2026-09-09

Four additional wrong recordings have been replaced in the live library map,
and one unresolved recording is quarantined. City Girl's previous correction
remains active. This changes source identity and the representations derived
from it; it does not tune the models or validate playlist compatibility.

| Intended song | Previous source | Resolution |
| --- | --- | --- |
| Maybe — JO YURI | SIENNA SPIRO — MAYBE. | [Official distributor recording](https://www.youtube.com/watch?v=q0ZEMR7pC18), 221.341 s |
| head over heels — luv, jacob; kate hyun | A television-cast interview | [Artist SoundCloud recording](https://soundcloud.com/luvjacob7/head-over-heels-kate-hyun), 152.625 s |
| I Will Be Just Fine — Park Bird; Mich | A CBS news clip about bird imitation | [Artist upload](https://www.youtube.com/watch?v=9gL1_XJR3GY), 185.641 s |
| Telescope — CRUCiAL STAR; Leellamarz; msftz | MSFTZ — 2080 | [Artist's official audio](https://www.youtube.com/watch?v=bGU-l8oqOx4), 205.981 s |
| Kairi — Playstation Lo-Five | lost son — kairi, about 60 s instead of 78 s | Quarantined; exact replacement not acquired |

Replacement checks lock provider identity, title, uploader, decoded duration
(within three seconds of the frozen Spotify duration), source SHA-256 and
full-file decode. SoundCloud acquisition retains its actual provider identity;
no fabricated YouTube identity or album slicing is used. Historical Spotify
metadata, including the differing guest-credit spelling on Telescope, remains
unchanged.

Kairi's artist SoundCloud entry matches the title, artist and 78-second duration,
but its stream reports access protection. The original YouTube source linked
by a fan edit is unavailable. The fan edit is 101 seconds and is not substituted.
Kairi remains searchable, with an explicit source-verification message, no
player, no representation in the current export, and no similarity edges.
Its audio endpoint returns 404. A verified accessible full recording is needed
to resolve this last case.

## Audit scope

Inspected the previously flagged cases and screened the current 1,257-song
library's retained provenance for title-only fallback and missing artist/title
matches. This found the additional Park Bird and Telescope errors. Literal
metadata differences also arise from translated names, aliases, abbreviated
credits and generic Topic channels; those are not automatic evidence of wrong
audio. This is a targeted source-identity audit, not a listening verification
of every library track.

The Khlaw `Motive Promiscuous - v2 Tt` mashup remains an unverified version-identity
lead: no exact artist match was established from the bounded follow-up search.
It has not been called a confirmed mismatch or silently replaced. Historical
chart-corpus records outside the current library were not rewritten.

## Representation and integrity

Reused the frozen centered30 contract and existing local CLAP/MuQ models.
Four new sources produced **12 CLAP and 12 MuQ segment inferences**. Both pooled
representations are cached under the new source hashes; the map uses CLAP only.
No full-song scientific artifacts, ratings, fusion weights or production
ranking behavior were changed.

The active correction index cumulatively includes City Girl and these four
repairs. Each correction is locked to the previous source hash and the new
completed-record hash. A separate hash-matched quarantine index withholds
unverified sources. Neither mechanism permits changing frozen C100 tracks.

Original media, batch ledgers, original SQLite cache and map snapshots remain
preserved. The prior correction index is archived in the new private run.
The C100 export is byte-for-byte identical to v2. Current v3 has **1,257 song
identities, 1,256 represented tracks, one quarantine and 11,295 graph links**.

Cache replay reused all four tracks, made zero inference calls, and reproduced
identical dataset files without modifying the original execution ledger or
SQLite cache. Two map exports were byte-identical. See
[the machine-readable audit](problem-source-corrections.json) for source hashes,
representation identities, before/after neighbors and artifact hashes.
New neighbor scores are diagnostics, not new human judgments.

## Verification and operation

- Python non-heavy suite: **1,309 passed**, 12 heavy tests deselected.
- Frontend: **6 tests passed**, build and lint passed.
- Chromium: all four audio response hashes match; HTTP Range returns 206;
  playback advances and seeking works; the quarantine explanation appears and
  its player/links are absent; no page errors.

Private evidence is under
`ml/audio_similarity/.research_audio/source_corrections/problem_cases_v1/`.
The new representation cache is
`ml/audio_similarity/artifacts/source_corrections/problem_cases_v1/representations.sqlite`.
Acquisition metadata, immutable inputs, execution/replay records and the previous
index are retained locally. Audio and full library exports are not committed.

From `ml/audio_similarity/`, replay the repair and export:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python .research_audio/source_corrections/problem_cases_v1/materialize.py
PYTHONPATH=src .venv/bin/python -m audio_similarity.song_space_export --output .research_audio/song_space/v3
```

From `frontend/`, launch the current map:

```bash
SONG_SPACE_DATA_DIR="$PWD/../ml/audio_similarity/.research_audio/song_space/v3" pnpm dev
```

Refresh http://127.0.0.1:5173/ to discard an older loaded snapshot. Original v1/v2
exports are historical views and still contain the sources used at those times.
