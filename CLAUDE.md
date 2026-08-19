# CLAUDE.md

Guidance for agents working in this repository. The root `README.md` is the
project-facing overview; this file is the working contract for code changes.

## Repository layout

Two independent package roots, each with its own `package.json` and
`pnpm-lock.yaml`:

- `backend/` — Express 5 + TypeScript API (MongoDB + Redis + Spotify Web API)
- `frontend/` — React 19 + TypeScript + Vite SPA

pnpm is the official package manager. Never use npm or yarn, and do not change
dependency versions without updating the matching lockfile.

## Commands

Backend (from `backend/`):

```bash
pnpm dev              # tsx watch, readiness-gated startup
pnpm build            # rimraf dist && tsc -> backend/dist
pnpm start            # node dist/index.js
pnpm test             # Jest (all tests)
pnpm test:coverage    # Jest with coverage
```

Single test file:

```bash
pnpm exec jest src/__tests__/services/Token.service.test.ts
```

Frontend (from `frontend/`):

```bash
pnpm dev       # Vite dev server, http://127.0.0.1:5173
pnpm build     # tsc -b && vite build
pnpm lint      # ESLint
pnpm preview   # preview production build
```

There is no frontend test runner; build + lint are the frontend checks.

## Startup & listeners

- `src/startup.ts` waits for MongoDB to connect and Redis to answer a ping
  before the HTTP server listens, so a request never reaches handlers before
  the stores behind them are ready. Dependencies are injectable for tests.
- `src/index.ts` wires startup and shuts down cleanly on SIGINT/SIGTERM
  (HTTP idle/keep-alive connections, Mongo, Redis).
- `HOST` (default `0.0.0.0`) is the **listener** bind address, for
  WSL/container port-forwarding. It is separate from the browser-facing URLs
  (`SPOTIFY_REDIRECT_URI`, `FRONTEND_URL`, `VITE_API_URL`), which stay on the
  `127.0.0.1` loopback because Spotify rejects `localhost` for local OAuth
  redirects. Root docs mention this distinction generically; backend/frontend
  docs own the details.

## Architecture

Full stack: React SPA → Express API → MongoDB/Redis/Spotify Web API.

### Auth flow

1. SPA navigates to `GET /auth/spotify/login` (full browser navigation); the
   backend sets the `spotify_auth_state` cookie (10 min) and redirects to
   Spotify's authorize endpoint.
2. Spotify redirects to `GET /auth/spotify/callback`; the backend validates the
   state cookie, exchanges the code for tokens, fetches the profile, upserts
   the user in MongoDB, stores the access token in Redis, and issues a signed
   JWT in the HttpOnly `jwt` cookie (14 days).
3. The callback redirects the browser to `FRONTEND_URL` with `?auth=success` /
   `?auth=error&reason=...` markers.
4. Protected routes use `verifyUser`, which reads the `jwt` cookie, verifies the
   signature, and attaches `req.user.spotifyId`.

This is a stateless JWT cookie flow, not server-side sessions.

### Token storage strategy

- **Access tokens** → Redis (`user:{spotifyId}:accessToken`, TTL 3600s) via
  `token.service.ts`.
- **Refresh tokens** → MongoDB (`User` model, `refreshToken` field), rotated
  when Spotify returns a new one.
- `getValidAccessToken()` is the central orchestration: Redis first, then
  refresh-token exchange, re-storing both tokens.
- Logout clears the JWT cookie and deletes the Redis access token.
- Cookie options are centralized in `src/utils/cookies.ts` and controlled by
  `COOKIE_SAME_SITE`, `COOKIE_SECURE`, `COOKIE_DOMAIN` (dev defaults: Lax +
  not Secure; production: None + Secure; `SameSite=None` requires `Secure`).

### Service layer

- `spotify.auth.service.ts` — OAuth token exchange.
- `spotify.user.service.ts` — user profile + refresh-token exchange.
- `spotify.playlist.service.ts` — playlists, liked songs, playlist tracks (all
  reads paginate 50 per page via `next`); `createPlaylist` (private by
  default); `addTracksToPlaylist` writes batches of 100 with 250 ms pacing
  between batches and up to 3 retries on 429 honoring `Retry-After`;
  `replacePlaylistItems` PUTs the first batch (including empty clears) then
  paced POSTs for the remainder; `getPlaylistSnapshot` reads only the
  `snapshot_id`.
- `spotify.artist.service.ts` — `getArtists` batches GET `/v1/artists` in
  groups of 50.
- `artist.cache.service.ts` — MongoDB artist genre cache with 14-day freshness;
  fetches only missing/stale artists (batches of 50 preserved at the cache
  layer).
- `genre.service.ts` — bucket assignment (`assignTrackToBucket`,
  `buildBucketMap`), playlist genre profiles, best-fit matching with
  name-keyword fallback, and editable-playlist validation.
- `sort.action.service.ts` — Redis undo records under
  `sort:action:<spotifyId>:<actionId>` plus a per-user latest pointer; 24-hour
  TTL; updates preserve the original expiry.
- `mongo.user.services.ts` — MongoDB CRUD for the `User` model.
- `token.service.ts` — Redis access-token read/write/delete +
  `getValidAccessToken` orchestration.

### Validation layer

- `src/env.ts` — Zod-validated env at startup; the server refuses to boot with
  missing or invalid required vars.
- `src/schemas/sort.schema.ts` — Zod schema for `POST /sort` (source type,
  output mode, conditional `playlistId` / `editablePlaylistIds`); existing-mode
  writes default to `copy`; a source playlist can never be a destination.
- `src/schemas/sort.action.schema.ts` — Zod schema for undo (`buckets`:
  non-empty, unique bucket names).

### Sort & undo invariants

- Source playlists are never modified or deleted; the source playlist can never
  be a destination.
- Existing-destination mode defaults to **copy**: clone each matched original
  (private, `"<name> — Spotify Sorter Copy"`), copy its replayable base items,
  then add candidates. Originals are never written in copy mode.
- **Direct mode** appends candidates to originals only when the destination's
  entire baseline is Web-API replayable (`playlistTracksToCopyableUris` length
  equals the original item count); unsafe destinations fail their buckets with
  zero writes.
- Optional playlist-source backup is created and filled before any artist
  lookup or genre write; a backup failure aborts the whole sort.
- Per-bucket writes are independent; results carry track details and per-bucket
  success/failure; excluded playlists are reported with reasons.
- Undo fetches strictly under the authenticated user's key, preflights every
  affected destination's expected snapshot ID, and returns `409` with zero
  writes on any mismatch. Success rebuilds `baselineUris` + still-applied
  buckets per destination and marks selected buckets `undone`.

### Key conventions

- **Service purity**: Spotify service functions accept `accessToken: string`
  directly and never call `getValidAccessToken` internally. Token orchestration
  belongs in the controller layer. This keeps services pure and unit-testable.
- **Types**: Spotify shapes in `src/types/spotify.types.ts`; app user types in
  `src/types/user.types.ts`; `req.user` is augmented in
  `src/types/express.d.ts`.
- **Mappers**: `src/utils/mappers.ts` converts Spotify API responses to DB
  models — update here when Spotify shapes change.
- **Lockfiles**: `pnpm-lock.yaml` in each root is the source of truth. No
  npm/yarn; no stray `package-lock.json`.
- **`lastChecked` field**: present on `DatabaseUser` but intentionally never
  written; reserved for Phase 2 cache invalidation. Do not remove it or write
  to it.
- **Build output**: `backend/dist` and `frontend/dist` are gitignored; coverage
  artifacts (including `backend/src/coverage`) must not be committed.
- **No real credentials in tests**: backend tests use `mongodb-memory-server`;
  Redis and axios are mocked; startup tests inject dependencies.

### Testing conventions

- Backend tests live in `src/__tests__/`, organized by layer (`controllers/`,
  `services/`, `middleware/`, `utils/`, `integration/`, `routes/`).
- Use `jest.clearAllMocks()` — not `jest.resetAllMocks()`, which wipes mock
  return values.
- Default-import mocks require `{ __esModule: true, default: mockFn }`.
- Run `pnpm test` after backend changes. The root README's Testing section
  records the latest verified suite/test counts; do not hard-code counts in
  this file.

### Route structure

- `GET /` — simple status message (no DB checks)
- `GET /auth/spotify/login` — starts OAuth
- `GET /auth/spotify/callback` — OAuth callback; sets JWT cookie; redirects to
  the frontend
- `GET /auth/me` — current user (protected)
- `POST /auth/logout` — clears JWT cookie + Redis access token (protected)
- `GET /library/liked` — liked songs (protected)
- `GET /playlists` — user's playlists (protected)
- `GET /playlists/:id/tracks` — playlist tracks (protected)
- `POST /sort` — genre sort orchestration (protected; Zod-validated; returns
  backup, per-bucket results, destination copies, and excluded playlists)
- `GET /sort/actions/latest` — latest undoable sort action (protected; `204`
  when none)
- `POST /sort/actions/:actionId/undo` — selective bucket undo (protected;
  `409` on snapshot conflict before any write)
