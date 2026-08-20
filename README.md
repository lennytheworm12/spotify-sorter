# Spotify Sorter

Organize your Spotify library by genre. Log in with Spotify, choose a source — your Liked Songs or an existing playlist — and Spotify Sorter buckets every track into one of 16 fixed genre groups, then writes them into playlists for you: either newly created per-genre playlists or playlists you own or collaborate on.

## The problem

Hand-sorting a large library by genre is tedious and inconsistent. Spotify Sorter automates the grunt work while keeping safety controls visible:

1. **Authenticate** with Spotify through the OAuth authorization-code flow (the backend handles the token exchange; the browser never sees a Spotify token).
2. **Pick a source** — Liked Songs or any playlist you own or collaborate on.
3. **Back up if you want** — a playlist source can first be copied into a new private backup playlist (enabled by default).
4. **Pick an output** — auto-create one private playlist per genre bucket, or sort into selected existing playlists.
5. **Review the ledger** — the UI reports the backup, per-bucket results with track details, destination copies, and which destinations were skipped or excluded and why.
6. **Undo within 24 hours** — select buckets and the backend rebuilds the affected playlists, but only after confirming each playlist's Spotify snapshot is unchanged since the sort.

## Features

- **Spotify OAuth login** — authorization-code flow with a state cookie, JWT in an HttpOnly cookie, a current-user endpoint, and logout that clears the cookie and the Redis access token.
- **Genre organization** — Spotify's granular artist genres are normalized into 16 fixed buckets (Hip Hop, R&B, Metal, Jazz, Classical, Country, Latin, Reggae, Folk, Punk, Electronic, Indie, Alternative, Rock, Pop, Other) using priority-ordered keyword rules.
- **Liked / playlist sources** — sort from Liked Songs or from an owned/collaborative playlist; source playlists are never modified or deleted and can never be selected as a destination.
- **Safety-first backups** — optionally copy every replayable source track into a new private backup before any genre write; a backup failure aborts the sort before destinations are touched.
- **Auto-create destinations** — one new private playlist per genre bucket.
- **Existing destinations with safe defaults** — append tracks to the best-matching selected playlists (genre-profile matching with a name-keyword fallback). The default mode creates safe private copies of the selected playlists — each copy can be given a custom trimmed, nonblank name up to 100 characters, defaulting to `"<Original playlist name> — Spotify Sorter Copy"` — and leaves the originals untouched. An explicit direct mode appends to the originals, and only when every original item is Web-API replayable so undo can rebuild them exactly.
- **Selective undo** — Redis stores the latest user-scoped sort action for 24 hours with per-destination baselines, timestamps, and expected Spotify snapshot IDs. In the UI every bucket is shown as Applied by default; checking a row only selects it for undo, and Spotify is not changed until the user presses Undo (select-all-applied and clear are available). Undo reconstructs baseline + remaining buckets and preflights every affected destination's snapshot first; any mismatch aborts with a 409 before a single write. Playlists are never deleted or unfollowed — undoing everything on an empty baseline leaves the playlist present but empty.
- **Resilient frontend networking** — transport-level failures are normalized so the browser's raw `Failed to fetch` never reaches the UI; the `/auth/me` session check retries only network failures twice with short backoff, and reconnect plus a manual Retry remain available.
- **Pagination** — all Spotify reads follow `next` links, 50 items per page.
- **Batching and pacing** — artist lookups are grouped by 50 (Spotify's limit) and playlist writes by 100, with 250 ms pacing between write batches and up to 3 retries on 429 responses honoring `Retry-After`.
- **MongoDB artist cache** — artist genres are cached for 14 days; only missing or stale artists hit Spotify.
- **Redis token cache** — access tokens are cached for 1 hour with automatic refresh-token fallback.
- **Partial-failure independence** — each genre bucket is attempted and reported independently with track details; a destination clone failure fails only the buckets assigned to that destination.

## Architecture

```text
Browser (React 19 + TypeScript + Vite SPA)
   │  fetch JSON + HttpOnly JWT cookie (credentials: include)
   │  full-page navigation for OAuth
   ▼
Express API (TypeScript)
   ├── MongoDB ── User (profile, refresh token) · Artist (genre cache, 14-day freshness)
   ├── Redis ──── access-token cache (1-hour TTL) · latest undo action (24-hour TTL)
   └── Spotify Web API ── playlist/library reads, artist lookups, playlist writes
```

- **React SPA** — login screen, authenticated dashboard with in-page Setup/Results/Undo navigation, source/output/safety selection, sort run, results ledger, undo panel, and logout. It talks to the backend with `credentials: 'include'` and reads `VITE_API_URL` (default `http://127.0.0.1:3000`).
- **Express API** — owns the OAuth handshake, issues and verifies the JWT cookie, restricts CORS to `FRONTEND_URL`, validates sort and undo bodies with Zod, and orchestrates every Spotify call, token refresh, and undo preflight/rebuild.
- **MongoDB** — `User` documents (Spotify profile + long-lived refresh token) and `Artist` documents (genre cache keyed by Spotify artist ID with `lastFetchedAt`).
- **Redis** — ephemeral cache of Spotify access tokens plus the user-scoped undo action records.
- **Spotify Web API** — the only source and destination for track/playlist data. Reads are paginated, writes are batched and paced, and created playlists are private by default.

## Auth & token boundary

- The backend issues a signed **JWT (14-day expiry) in an HttpOnly cookie** (`jwt`) after the OAuth callback. Every protected request is verified statelessly from that cookie — this is **not** server-side session storage.
- The **OAuth state cookie** (`spotify_auth_state`, 10-minute TTL) protects the callback against state mismatches; it is cleared after use.
- **Access tokens** live in Redis (`user:{spotifyId}:accessToken`, 1-hour TTL). When missing, `getValidAccessToken` exchanges the stored refresh token and re-caches the result.
- **Refresh tokens** persist in MongoDB (`User.refreshToken`) and are rotated when Spotify returns a new one.
- **Logout** clears the JWT cookie and deletes the Redis access token.
- Cookie behavior is env-controlled: local dev defaults to `SameSite=Lax` + `Secure=false`; production defaults to `SameSite=None` + `Secure=true` for a cross-site frontend over HTTPS.

## Local setup

### Prerequisites

- Node.js 20.19+ or 22.12+ (Vite 8 requirement)
- pnpm
- Docker (for local MongoDB + Redis) or your own/managed Mongo and Redis instances

### 1. Create a Spotify app

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create an app.
2. Add this exact Redirect URI (Spotify rejects `localhost` for local OAuth redirects, so the loopback IP is required):

   ```
   http://127.0.0.1:3000/auth/spotify/callback
   ```

3. Copy the **Client ID** and **Client Secret** into `backend/.env`.

Spotify development-mode apps require the app owner to have Spotify Premium. They support up to five authenticated users, and every test user must be added under **Settings → Users Management** in the Spotify Developer Dashboard.

Scopes requested at login: `playlist-read-private`, `playlist-read-collaborative`, `playlist-modify-private`, `playlist-modify-public`, and `user-library-read`.

### 2. Start local MongoDB and Redis

```bash
cd backend
docker compose up -d
```

This starts MongoDB on `127.0.0.1:27017` (dev credentials `admin`/`password`, database `spotify`) and Redis on `127.0.0.1:6379`. Adjust `MONGO_URI` / `REDIS_URI` if you use your own or managed instances.

### 3. Backend

```bash
cd backend
pnpm install
cp .env.example .env   # fill in your Spotify credentials + JWT secret
pnpm dev
```

The browser-facing API URL is `http://127.0.0.1:3000`. The listener itself binds `HOST` (default `0.0.0.0` so WSL/container port-forwarding works) — the bind host and the browser URLs are separate settings.

Backend environment variables (see [backend/.env.example](backend/.env.example)):

| Variable | Purpose | Local default |
|---|---|---|
| `NODE_ENV` | `development` / `test` / `production` | `development` |
| `PORT` | Backend port | `3000` |
| `HOST` | Listener bind address (not the browser URL); `0.0.0.0` accepts WSL/container forwarding | `0.0.0.0` |
| `MONGO_URI` | MongoDB connection string | `mongodb://admin:password@localhost:27017/spotify?authSource=admin` |
| `REDIS_URI` | Redis connection string | `redis://localhost:6379` |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | Spotify app credentials | placeholder |
| `SPOTIFY_REDIRECT_URI` | Must exactly match the registered callback; keep on `127.0.0.1` | `http://127.0.0.1:3000/auth/spotify/callback` |
| `JWT_SECRET` | ≥ 32 characters | placeholder (generate with e.g. `openssl rand -hex 32`) |
| `FRONTEND_URL` | Allowed CORS origin + OAuth redirect target; keep on `127.0.0.1` | `http://127.0.0.1:5173` |
| `COOKIE_SAME_SITE` | `lax` / `strict` / `none` (optional) | dev: `lax`; prod: `none` |
| `COOKIE_SECURE` | `true` / `false` (optional) | dev: `false`; prod: `true` |
| `COOKIE_DOMAIN` | Optional cookie domain | unset |

### 4. Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

The SPA runs at `http://127.0.0.1:5173`. To override the API base, copy `frontend/.env.example` to `frontend/.env.local` and set `VITE_API_URL` (keep it on `127.0.0.1`):

| Variable | Purpose | Default |
|---|---|---|
| `VITE_API_URL` | Backend base URL used by the browser | `http://127.0.0.1:3000` |

**Production cookie notes:** if the frontend and API are on different origins, use HTTPS with `COOKIE_SAME_SITE=none` and `COOKIE_SECURE=true` (`SameSite=None` requires `Secure`). If both are served from the same site, `COOKIE_SAME_SITE=lax` with `COOKIE_SECURE=true` is fine. Use a real random `JWT_SECRET` and keep it, the Spotify client secret, and all `.env` files out of version control.

### WSL (Windows Subsystem for Linux)

When the repo lives inside WSL, the services bind `0.0.0.0` (backend `HOST` default; the Vite dev server also binds `0.0.0.0`) so traffic forwarded from Windows is accepted instead of being rejected as non-loopback. The browser and Spotify always use the `127.0.0.1` loopback URLs — Spotify's OAuth redirect rules reject `localhost`, so the registered callback stays `http://127.0.0.1:3000/auth/spotify/callback` and the frontend stays `http://127.0.0.1:5173`.

If a Windows browser cannot reach the WSL services, add portproxy entries on Windows (run as Administrator):

```powershell
netsh interface portproxy add v4tov4 listenport=3000 listenaddress=127.0.0.1 connectport=3000 connectaddress=<WSL_PRIVATE_IP>
netsh interface portproxy add v4tov4 listenport=5173 listenaddress=127.0.0.1 connectport=5173 connectaddress=<WSL_PRIVATE_IP>
```

Find the WSL private IP with `wsl hostname -I`. The entries point at that IP, so they must be refreshed whenever it changes (for example after a WSL restart or IP renewal): delete the stale entries (`netsh interface portproxy delete v4tov4 listenport=... listenaddress=127.0.0.1`) and re-add them with the current IP.

## Running

```bash
# Terminal 1 — backend
cd backend
pnpm dev      # browser API URL http://127.0.0.1:3000

# Terminal 2 — frontend
cd frontend
pnpm dev      # http://127.0.0.1:5173
```

Open `http://127.0.0.1:5173` in the browser.

## Build, test, lint

| Root | Command | What it does |
|---|---|---|
| backend | `pnpm build` | Compiles TypeScript to `backend/dist` |
| backend | `pnpm test` | Jest suite |
| backend | `pnpm test:scale` | Jest, in-band, running only the synthetic scale profile |
| backend | `pnpm test:coverage` | Jest with coverage report |
| backend | `pnpm start` | Runs the compiled `dist` output |
| frontend | `pnpm build` | TypeScript check + Vite production build |
| frontend | `pnpm lint` | ESLint |
| frontend | `pnpm preview` | Previews the production build |

**Current automated baseline:** backend 24 suites / 258 tests passing; frontend build and lint pass. Backend tests use `mongodb-memory-server` with Redis and axios mocked, so no real Spotify credentials are needed to run them. Update these numbers after future runs instead of treating them as permanent.

`pnpm test:scale` is a deterministic, fully mocked synthetic scale profile: it
drives the production read → filter → artist-cache → bucket → write pipeline
with 1,000 / 5,000 / 10,000 unique tracks and verifies pagination (50/page),
artist batching (50/request, every artist exactly once), cache bulk upserts,
bucketing, write batching (100/request), order preservation, and the 10,000
case's single deterministic 429 retry with `Retry-After`. This is mocked
validation of the pipeline's batching/pagination/retry code — not a live
Spotify benchmark, not load testing, and not a claim that Spotify currently
caps playlists at 10,000 tracks (Spotify currently documents a maximum of
[50 items per playlist read](https://developer.spotify.com/documentation/web-api/reference/get-playlists-items)
and [100 items per write request](https://developer.spotify.com/documentation/web-api/reference/add-items-to-playlist)).

CI (GitHub Actions) runs the backend build and Jest suite plus the frontend lint and build on every pull request to `main` and push to `main`.

## API routes

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/` | — | Simple status message |
| `GET` | `/auth/spotify/login` | — | Starts OAuth; sets state cookie and redirects to Spotify |
| `GET` | `/auth/spotify/callback` | — | Exchanges the code, upserts the user, sets the JWT cookie, redirects to `FRONTEND_URL` |
| `GET` | `/auth/me` | JWT | Returns the current user |
| `POST` | `/auth/logout` | JWT | Clears the JWT cookie + Redis access token |
| `GET` | `/library/liked` | JWT | Liked songs (paginated) |
| `GET` | `/playlists` | JWT | User's playlists (paginated) |
| `GET` | `/playlists/:id/tracks` | JWT | Tracks for a playlist (paginated) |
| `POST` | `/sort` | JWT | Genre sort orchestration with optional playlist backup and per-destination safe-copy names (Zod-validated; returns backup, per-bucket results, destination copies, and excluded playlists) |
| `GET` | `/sort/actions/latest` | JWT | Latest undoable sort action for the user, or `204` when none |
| `POST` | `/sort/actions/:actionId/undo` | JWT | Selective bucket undo; preflights all affected Spotify snapshots and returns `409` on any conflict before writing |

## Manual end-to-end checklist

The automated checks pass (see above), and the app has been exercised against a real Spotify account: the user reported a successful local OAuth return, dashboard load, and a playlist-source sort that wrote 13 tracks to destinations. The latest tracked action also shows three buckets successfully undone with one bucket still applied. This is useful integration evidence, but the newest connectivity copy, custom safe-copy-name editor, select-all undo UI, and fully-undone state have not yet had a user real-account smoke test.

The **current release still needs a short real Spotify smoke test after restart**. Do not mark the current release complete until these pass:

- [ ] Spotify app created with callback `http://127.0.0.1:3000/auth/spotify/callback`
- [ ] `docker compose up -d`; backend and frontend both running; open `http://127.0.0.1:5173`
- [ ] "Connect Spotify" → authorize → browser returns to the frontend and the dashboard shows your account
- [ ] Liked Songs → auto-create → new private playlists appear for every bucket that has tracks, and the ledger shows per-bucket counts and track details
- [ ] Playlist source → sort into existing playlists with **Create safe copies**: private copies appear with the chosen custom names (blank or >100-character names are rejected), originals are unchanged, the source playlist is disabled as a destination, and non-editable playlists appear under "Excluded playlists"
- [ ] Playlist source → **Add directly to originals** on a fully replay-safe playlist: tracks are appended to the originals and the undo panel becomes available
- [ ] With "Create a backup copy first" enabled, a private backup appears before genre outputs; the source remains unchanged
- [ ] Undo: checking rows changes nothing on Spotify until Undo is pressed; select-all-applied and clear behave, and undoing one bucket rebuilds the affected playlist to baseline + remaining buckets
- [ ] Undo conflict: edit a destination playlist after the sort, then attempt undo → the operation is rejected with a 409 and no writes
- [ ] Sign out clears the session and returns to the connect screen
- [ ] Re-run a sort on the same source and confirm the ledger and playlist refresh behave as expected (note: the MVP appends tracks again; it does not deduplicate)

## Roadmap

**Phase 1 — MVP genre sorting (implemented).** OAuth, optional pre-sort playlist backups, genre bucketing, auto-create plus safe-copy/direct existing-destination modes, paginated reads, batched and paced writes, the MongoDB artist cache, the Redis token cache, partial-failure reporting, and 24-hour selective undo with snapshot preflight.

**Phase 2 — Smarter sorting (not implemented).** ML/audio-feature clustering, improved bucket matching, re-run dedupe/merge, queued background jobs for large libraries, and a dry-run preview. None of these exist yet; the Phase 1 architecture (clean service layer, cache seams) is designed to accommodate them.

## Known limitations & platform risks

- Re-running a sort appends tracks again; the MVP does not deduplicate destination playlists.
- Genre quality depends on Spotify's artist genre metadata and the static normalization table.
- Spotify currently marks the "Get Several Artists" endpoint and its artist `genres` field as deprecated. They are still documented and available for this existing MVP, but this is a platform risk to track rather than a Phase 2 feature.
- Spotify development mode is limited to five allowlisted users and requires the app owner to have Premium.
- Sorting is request/response based; very large libraries do not yet run as background jobs.
- Undo is available for 24 hours, only when action tracking succeeded, and only for writes whose destinations can be rebuilt exactly (direct mode additionally requires a fully Web-API-replayable baseline).

## Security & privacy notes

- Spotify tokens never reach the browser: access tokens stay in Redis, refresh tokens in MongoDB, and the browser only holds HttpOnly cookies (the JWT plus the short-lived OAuth state).
- CORS is restricted to `FRONTEND_URL` with credentials, and the OAuth callback validates the state cookie.
- Source playlists are never modified or deleted, and a source playlist can never be a destination. Destination writes default to safe private copies; the explicit direct mode modifies originals only when their entire baseline is Web-API replayable.
- The `admin`/`password` credentials in `backend/docker-compose.yml` are local development defaults only — do not reuse them in production. `.env` files are gitignored, and automated tests run without real credentials.
