# Song space

The default React/Vite view explores a read-only similarity graph. Search or click a song for its supplied Top-k neighbors, audio and community. Bridges expose cross-community edges with shared-neighbor counts; they are inspection leads, not inferred bad matches. The existing Spotify organizer remains at `#/organize`.

## Local library

From `ml/audio_similarity`, reuse the processed-library and frozen C caches:

```bash
PYTHONPATH=src .venv/bin/python -m audio_similarity.song_space_export
```

From `frontend`, start the optional local bridge:

```bash
SONG_SPACE_DATA_DIR="$PWD/../ml/audio_similarity/.research_audio/song_space/v1" pnpm dev
```

Open `http://127.0.0.1:5173/`. The bridge forces loopback binding and only reads explicitly configured snapshots and retained audio. It supports HTTP byte ranges for playback/seeking. No backend, Spotify session, inference or Spotify writes are needed to explore it. Library JSON, source audio and receipts remain in ignored `.research_audio/`; none are production build assets or Git inputs.

The 1,257-track library currently uses cached centered-excerpt CLAP, **not full-song CLAP C**. A separate 100-track map uses exact frozen C scores. The selector and representation descriptions distinguish these. Do not compare scores across maps as calibrated probabilities. Missing cache rows fail the exporter; it never silently shrinks the library.

The exporter sorts identities and scores with stable-ID tie breaking, verifies vector blobs and emits the union of directional Top-12 lists. Rerunning verifies frozen outputs rather than overwriting them. Use a new `--output .research_audio/song_space/v2` directory for changed inputs or export code. `provenance.json` records input/code hashes; `vector-receipts.json` records cache analysis identities and vector hashes. No model inference occurs.

## Replaceable inputs

`SongSpaceProvider` exposes `catalog(signal)` and `load(source, signal)`. Supply a provider to `SongSpace`, set `VITE_SONG_SPACE_CATALOG_URL` to a catalog endpoint, or use **Open map** to import a local JSON file. The default endpoint is `/__song-space/catalog`. Deployed builds need a provider or file import: the local bridge is development-only. Authenticate remote providers at the server; the UI sends cookies but owns no credentials.

Catalog format:

```json
[{"id":"my-map","label":"My map","url":"/maps/my-map.json"}]
```

Snapshot example (synthetic):

```json
{
  "schemaVersion":"song-space-v1",
  "id":"example-v1",
  "name":"Example",
  "description":"An exported similarity snapshot",
  "scorer":{"id":"example-cosine","label":"Example cosine","description":"Frozen audio embeddings","scoreRange":[-1,1],"higherIsCloser":true},
  "neighborhoodSize":12,
  "songs":[
    {"id":"a","title":"First song","artists":["One"]},
    {"id":"b","title":"Second song","artists":["Two"]}
  ],
  "links":[{"source":"a","target":"b","score":0.7,"sourceRank":1,"targetRank":1}]
}
```

Songs optionally supply `album`, `durationMs`, `audioUrl` (http/https or relative), paired finite `x/y`, and `community`. Complete community assignments require `communities:[{id,label}]`. Positions are used if supplied for every song, then uniformly centered/scaled. Supplied community IDs/labels are preserved. Missing positions/communities are computed independently. Ranks are directional: null means outside that endpoint's Top-k, not a negative label. At least one rank per link must exist. IDs, unordered pairs and per-song ranks must be unique. The parser rejects invalid endpoints, self-edges, nonfinite/out-of-range scores and unsafe URLs. Import limit: 25 MB, 20,000 songs, 500,000 links; smaller maps give better browser responsiveness.

## Layout decisions

Sigma 3 renders the graph with WebGL. Graphology supplies graph operations; seeded Louvain finds neighborhoods and fixed-iteration ForceAtlas2 arranges them in a dedicated Vite worker. This avoids blocking the interface during layout. D3 density contours trace actual point density beneath the graph. No genre rules or model training enter the display.

Canonical node/edge ordering and seed 17531 make layout reproducible in the same environment. Layout weights are `max(0.01, closeness²)`, with closeness a linear transformation of the declared score range/direction. Original scores/ranks remain unchanged. Louvain resolution is 1. ForceAtlas2 uses 1,600 iterations (800 above 3,000 songs), Barnes–Hut theta .5, gravity .7, scaling 2, slowdown 1 and lin-log mode. Positions are uniformly scaled into a 1,000-square coordinate system. Contours use bandwidth 30 and seven thresholds. Artist names on areas are navigation labels selected by frequency, never predictive features or genre assertions.

A bridge crosses community assignments. Shared-neighbor count uses the undirected union graph. The bridge list orders by ascending shared count then closeness and shows the first 80; all map edges remain inspectable. Song search reaches every identity, while the list initially renders 200 matches and offers a Show more control. The map is an approximation: physical distance is not the raw similarity function. Communities are unstable under changed data/scorers and must not be treated as production playlist membership.

## Checks

From `frontend`: `pnpm test`, `pnpm build`, `pnpm lint`.

From `ml/audio_similarity`: `.venv/bin/python -m pytest tests/test_song_space_export.py -q`.

Browser validation covers the real 1,257-song map, frozen C selection, search/selection, graph controls, community/bridge inspection, audio/Range seeking, file import, empty/error states, mobile layout and console errors. Browser tests use an isolated profile and never write review labels or call Spotify mutations.

Run the browser checks from the repository root while the configured Vite server is running:

```bash
ml/audio_similarity/.venv/bin/python frontend/tests/browser_song_space.py --output /tmp/song-space-browser
```

This uses an isolated Chromium profile and writes private screenshots/results only to the chosen directory. It expects the complete local library and frozen C exports; imports and failure fixtures are isolated in browser memory. See [verification.json](verification.json) for the recorded run.
