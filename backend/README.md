# Backend — Spotify Sorter API

Express 5 + TypeScript API that brokers Spotify OAuth, stores tokens, and
orchestrates Spotify reads/writes for the Spotify Sorter SPA. See the
[root README](../README.md) for the full project, architecture, and setup.

## Stack

- Express 5 + TypeScript (CommonJS output via NodeNext)
- MongoDB (Mongoose) — `User` (profile + refresh token), `Artist` (14-day genre cache)
- Redis (ioredis) — access-token cache, 1-hour TTL
- Spotify Web API — playlists, liked songs, artists, playlist writes
- Zod — env validation at startup + `POST /sort` body validation
- Jest + `mongodb-memory-server` — unit/integration tests

## Local setup

Requirements: Node.js 20.19+ or 22.12+, pnpm, and MongoDB + Redis.

```bash
pnpm install
cp .env.example .env    # fill in Spotify credentials + JWT secret
docker compose up -d    # local MongoDB (27017) + Redis (6379)
pnpm dev                # server listening on 0.0.0.0:3000; browser URL http://127.0.0.1:3000
```

## Bind host vs browser URL

The listener address and the browser-facing URL are separate settings:

- `HOST` (default `0.0.0.0`) is the address the Express server binds. Binding
  all interfaces lets traffic arrive through a forwarded address — e.g. when
  the backend runs inside WSL and Windows `netsh portproxy` forwards the
  Windows `127.0.0.1:3000` port to the WSL private IP. A server bound only to
  the WSL loopback would reject that forwarded traffic. Users who want a
  local-interface-only listener can set `HOST=127.0.0.1` in `backend/.env`.
- The browser-facing URL is always the 127.0.0.1 loopback: Spotify's OAuth
  redirect rules reject `localhost`, so `SPOTIFY_REDIRECT_URI` must be the
  exact loopback `http://127.0.0.1:3000/auth/spotify/callback` registered in
  the Spotify app dashboard, and `FRONTEND_URL` defaults to
  `http://127.0.0.1:5173` (the SPA dev server). These are what the browser
  uses; they are unaffected by the bind host.

For WSL with `netsh portproxy`:

```powershell
# On Windows, forward the Windows loopback port to the WSL private IP.
# The service inside WSL binds 0.0.0.0 so this forwarded traffic is accepted.
netsh interface portproxy add v4tov4 listenport=3000 listenaddress=127.0.0.1 connectport=3000 connectaddress=<WSL_PRIVATE_IP>
netsh interface portproxy add v4tov4 listenport=5173 listenaddress=127.0.0.1 connectport=5173 connectaddress=<WSL_PRIVATE_IP>
```

Then open `http://127.0.0.1:3000` / `http://127.0.0.1:5173` in the Windows
browser exactly as before; Spotify auth still redirects to the 127.0.0.1
loopback.

Both `HOST` and the browser-facing defaults live in `backend/.env.example`.

`docker compose` defaults:

- Mongo URI: `mongodb://admin:password@localhost:27017/spotify?authSource=admin`
- Redis URI: `redis://localhost:6379`

See `backend/.env.example` for every supported env var.

## Scripts

| Command | What it does |
|---|---|
| `pnpm dev` | tsx watch on `src/index.ts` |
| `pnpm build` | rimraf + tsc → `dist/` |
| `pnpm start` | node `dist/index.js` |
| `pnpm test` | Jest (all suites) |
| `pnpm test:coverage` | Jest with coverage report |

## Routes

- `GET /` — status message
- `GET /auth/spotify/login` — start OAuth
- `GET /auth/spotify/callback` — OAuth callback; sets JWT cookie; redirects to `FRONTEND_URL`
- `GET /auth/me` — current user (protected)
- `POST /auth/logout` — clears JWT cookie + Redis access token (protected)
- `GET /library/liked` — liked songs (protected)
- `GET /playlists` — user's playlists (protected)
- `GET /playlists/:id/tracks` — playlist tracks (protected)
- `POST /sort` — genre sort orchestration (protected; optional `createBackup`
  for playlist sources; `existingPlaylistWriteMode: 'copy' | 'direct'` for
  `sort-into-existing`)
- `GET /sort/actions/latest` — latest undoable sort action for the current
  user (protected; `204` when none)
- `POST /sort/actions/:actionId/undo` — selectively undo buckets from a sort
  action (protected; body `{ buckets: string[] }`)

## Notes

- Auth boundary: stateless JWT in an HttpOnly cookie; access token in Redis
  (1-hour TTL); refresh token in MongoDB. This is not server-side sessions.
- OAuth consent requests only the scopes the app uses: `playlist-read-private`,
  `playlist-read-collaborative`, `playlist-modify-private`,
  `playlist-modify-public`, and `user-library-read` (no email/profile/image
  scopes).
- Startup is readiness-gated: the HTTP server only listens after MongoDB is
  connected and Redis answers a ping; a startup failure logs once and exits
  nonzero. SIGINT/SIGTERM close the HTTP server, Mongo, and Redis cleanly.
- `POST /sort` validates its body with Zod and returns per-bucket
  success/failure results plus excluded playlists; one bucket failing does not
  roll back others.
- `createBackup: true` (playlist sources only) snapshots the copyable source
  tracks into a new private `"<name> — Spotify Sorter Backup"` playlist before
  any genre output work; backup failure aborts the sort. A playlist source can
  never be used as a sort destination (`sort-into-existing`).
- `sort-into-existing` protects selected playlists by default:
  `existingPlaylistWriteMode` defaults to `copy`, which clones each matched
  destination once as `"<name> — Spotify Sorter Copy"`, copies the original's
  existing tracks into the clone first, then appends the sorted candidates —
  the original is never modified. Set `existingPlaylistWriteMode: "direct"` to
  append candidates to the originals explicitly. Direct mode only writes to
  destinations whose full item list is Web-API-replayable (no local,
  unavailable/null, unplayable, or malformed items); any other destination is
  skipped with a bucket-level failure directing the user to choose
  "Create safe copies" instead, because those items could never be rebuilt by
  undo. The field is rejected for `auto-create`. Copy mode returns a top-level
  `destinationCopies` array with per-clone status (`sourcePlaylistId`,
  `sourcePlaylistName`, `playlistId`, `playlistName`, `tracksCopied`, `status`,
  optional `error`); unmatched selected destinations are not cloned.
- Playlist writes are paced (250ms between 100-track batches) and 429 responses
  are retried up to 3 times, honoring `Retry-After` seconds or bounded
  exponential backoff.
- Each successful sort persists a 24-hour undo action in Redis (keyed by
  Spotify user id) with destination baselines, applied buckets, and the final
  expected Spotify `snapshot_id`. Undo preflights every affected destination's
  current snapshot and aborts with `409` before any write on a mismatch.
  Sorting still succeeds if action persistence fails; the response carries an
  `actionWarning` instead of an `action`.
- The backend never deletes or edits source playlists/tracks — sort is
  copy-only.

## Tests

Unit and integration suites mock external services (Spotify HTTP, Redis, and
Mongo CRUD); Mongo persistence tests use an in-memory MongoDB. The suite does
not run against the real Spotify API, so there is no real Spotify end-to-end
coverage — verify manual login/sort flows against a live account separately.
