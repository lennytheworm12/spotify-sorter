# Spotify Sorter

Organize your Spotify library by genre. Log in with Spotify, choose a source — your Liked Songs or an existing playlist — and Spotify Sorter buckets every track into one of 16 fixed genre groups, then writes them into playlists for you: either newly created per-genre playlists or existing playlists you own or collaborate on.

## What it does

Hand-sorting a large library by genre is tedious and inconsistent. Spotify Sorter automates the grunt work:

1. **Authenticate** with Spotify through the OAuth authorization-code flow (the backend handles the token exchange; the browser never sees a Spotify token).
2. **Pick a source** — Liked Songs or any of your playlists.
3. **Choose backup protection** — playlist sources can first be copied into a new private backup playlist (enabled by default).
4. **Pick an output** — auto-create one private playlist per genre bucket, or sort into existing playlists you own or can collaborate on.
5. **Review the ledger** — the UI reports the backup, which buckets were written, how many tracks each one received, and which destination playlists were skipped and why.

The sort is **copy-only**: it never deletes or edits your source playlists or tracks.

## Features

- **Spotify OAuth login** — authorization-code flow with state validation, JWT in an HttpOnly cookie, and logout.
- **Genre organization** — Spotify's granular artist genres are normalized into 16 fixed buckets (Hip Hop, R&B, Metal, Jazz, Classical, Country, Latin, Reggae, Folk, Punk, Electronic, Indie, Alternative, Rock, Pop, Other) using priority-ordered keyword rules.
- **Liked / playlist sources** — sort from your Liked Songs or from any existing playlist.
- **Safety-first playlist backups** — optionally copy every copyable source track into a new private backup before sorting; backup failure aborts all genre writes, and a source playlist can never be selected as a destination.
- **Auto-create or existing destinations** — create a new private playlist per bucket, or append tracks into the best-matching playlists among those you select (empty playlists fall back to name-keyword matching).
- **Pagination** — all Spotify reads follow `next` links, 50 items per page.
- **50/100 batching** — artist lookups are grouped by 50 (Spotify's limit) and playlist writes by 100.
- **MongoDB artist cache** — artist genres are cached for 14 days; only missing or stale artists hit Spotify.
- **Redis token cache** — access tokens are cached for 1 hour with automatic refresh-token fallback.
- **Partial failures** — each genre bucket is written independently and reported as success or failure; excluded playlists are returned with reasons.

## Architecture

```text
Browser (React/Vite SPA)
   │  fetch JSON + HttpOnly JWT cookie (credentials: include)
   │  full-page navigation for OAuth
   ▼
Express API (TypeScript)
   ├── MongoDB ── User (profile, refresh token) · Artist (genre cache, 14-day TTL)
   ├── Redis ──── access-token cache (user:{spotifyId}:accessToken, 1-hour TTL)
   └── Spotify Web API ── playlist/library reads, artist lookups, playlist writes
```

- **React SPA** — login screen, authenticated dashboard, source/output selection, sort action, results ledger, and logout. It talks to the backend with `credentials: 'include'` and reads `VITE_API_URL` (default `http://localhost:3000`).
- **Express API** — owns the OAuth handshake, issues and verifies the JWT cookie, restricts CORS to `FRONTEND_URL`, validates `POST /sort` with Zod, and orchestrates every Spotify call and token refresh.
- **MongoDB** — `User` documents (Spotify profile + long-lived refresh token) and `Artist` documents (genre cache keyed by Spotify artist ID with `lastFetchedAt`).
- **Redis** — ephemeral cache of Spotify access tokens; a cache miss falls back to a refresh-token exchange.
- **Spotify Web API** — the only source and destination for track/playlist data. Reads are paginated, writes are batched, and created playlists are private by default.

## Auth & token boundary

- The backend issues a signed **JWT (14-day expiry) in an HttpOnly cookie** (`jwt`) after the OAuth callback. Every protected request is verified statelessly from that cookie — this is **not** server-side session storage.
- The **OAuth state cookie** (`spotify_auth_state`, 10-minute TTL) protects the callback against state mismatches.
- **Access tokens** live in Redis (`user:{spotifyId}:accessToken`, 1-hour TTL). When missing, `getValidAccessToken` exchanges the stored refresh token and re-caches the result.
- **Refresh tokens** persist in MongoDB (`User.refreshToken`) and are rotated when Spotify returns a new one.
- Cookie behavior is env-controlled: local dev defaults to `SameSite=Lax` + `Secure=false` (works on `localhost`); production defaults to `SameSite=None` + `Secure=true` for a cross-site frontend over HTTPS.

## Local setup

### Prerequisites

- Node.js 20.19+ or 22.12+ (Vite 8 requirement)
- pnpm
- Docker (for local MongoDB + Redis) or your own Mongo/Redis instances

### 1. Create a Spotify app

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create an app.
2. Add this exact Redirect URI:

   ```
   http://localhost:3000/auth/spotify/callback
   ```

3. Copy the **Client ID** and **Client Secret** into `backend/.env`.

Spotify development-mode apps require the app owner to have Spotify Premium.
They support up to five authenticated users, and every test user must be added
under **Settings → Users Management** in the Spotify Developer Dashboard.

Scopes requested at login: `playlist-read-private`, `playlist-read-collaborative`, `playlist-modify-private`, `playlist-modify-public`, `user-library-read`, `user-read-email`, `user-read-private`, `ugc-image-upload`.

### 2. Start local MongoDB and Redis

```bash
cd backend
docker compose up -d
```

This starts MongoDB on `localhost:27017` (dev credentials `admin`/`password`, database `spotify`) and Redis on `localhost:6379`. Adjust `MONGO_URI` / `REDIS_URI` if you use your own instances.

### 3. Backend

```bash
cd backend
pnpm install
cp .env.example .env   # fill in your Spotify credentials + JWT secret
pnpm dev               # http://localhost:3000
```

### 4. Frontend

```bash
cd frontend
pnpm install
pnpm dev               # http://localhost:5173
```

The frontend points at `http://localhost:3000` by default. To override, copy `frontend/.env.example` to `frontend/.env.local` and set `VITE_API_URL`.

### Environment variables

Backend (see [backend/.env.example](backend/.env.example)):

| Variable | Purpose | Local default |
|---|---|---|
| `NODE_ENV` | `development` / `test` / `production` | `development` |
| `PORT` | Backend port | `3000` |
| `MONGO_URI` | MongoDB connection string | `mongodb://admin:password@localhost:27017/spotify?authSource=admin` |
| `REDIS_URI` | Redis connection string | `redis://localhost:6379` |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | Spotify app credentials | placeholder |
| `SPOTIFY_REDIRECT_URI` | Must match the registered callback exactly | `http://localhost:3000/auth/spotify/callback` |
| `JWT_SECRET` | ≥ 32 characters | placeholder (generate with e.g. `openssl rand -hex 32`) |
| `FRONTEND_URL` | Allowed CORS origin + OAuth redirect target | `http://localhost:5173` |
| `COOKIE_SAME_SITE` | `lax` / `strict` / `none` (optional) | dev: `lax`; prod: `none` |
| `COOKIE_SECURE` | `true` / `false` (optional) | dev: `false`; prod: `true` |
| `COOKIE_DOMAIN` | Optional cookie domain | unset |

Frontend:

| Variable | Purpose | Default |
|---|---|---|
| `VITE_API_URL` | Backend base URL | `http://localhost:3000` |

**Production cookie notes:** if the frontend and API are on different origins, use HTTPS with `COOKIE_SAME_SITE=none` and `COOKIE_SECURE=true` (`SameSite=None` requires `Secure`). If both are served from the same site, `COOKIE_SAME_SITE=lax` with `COOKIE_SECURE=true` is fine. Use a real random `JWT_SECRET` and keep both it and the Spotify client secret out of version control.

## Running

```bash
# Terminal 1 — backend
cd backend
pnpm dev      # http://localhost:3000

# Terminal 2 — frontend
cd frontend
pnpm dev      # http://localhost:5173
```

## Build, test, lint

| Root | Command | What it does |
|---|---|---|
| backend | `pnpm build` | Compiles TypeScript to `backend/dist` |
| backend | `pnpm test` | Jest suite (last full run: 18 suites, 170 tests passing) |
| backend | `pnpm test:coverage` | Jest with coverage report |
| backend | `pnpm start` | Runs the compiled `dist` output |
| frontend | `pnpm build` | TypeScript check + Vite production build |
| frontend | `pnpm lint` | ESLint |
| frontend | `pnpm preview` | Previews the production build |

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
| `POST` | `/sort` | JWT | Genre sort orchestration with optional playlist backup (Zod-validated; returns backup, per-bucket results, and excluded playlists) |

## Manual end-to-end checklist

The backend and frontend build and their automated checks pass, but the full OAuth + sort flow has **not yet been validated against a real Spotify account**. Verify manually before considering this release-ready:

- [ ] Spotify app created with callback `http://localhost:3000/auth/spotify/callback`
- [ ] `docker compose up -d`; backend and frontend both running
- [ ] "Connect Spotify" → authorize → browser returns to the frontend and the dashboard shows your account
- [ ] Liked Songs → auto-create → new private playlists appear for every bucket that has tracks, and the ledger shows per-bucket counts
- [ ] Playlist source → sort-into-existing → tracks are appended to the best-matching selected playlists; non-editable playlists appear under "Excluded playlists"
- [ ] With "Create a backup copy first" enabled, a private backup appears before genre outputs; the source is disabled in the destination list and remains unchanged
- [ ] Sign out clears the session and returns to the connect screen
- [ ] Re-run a sort on the same source and confirm the ledger and playlist refresh behave as expected (note: the MVP appends tracks again; it does not deduplicate)

## Roadmap

**Phase 1 — MVP (implemented): genre-based organization.** OAuth, optional pre-sort playlist backups, genre bucketing, auto-create and sort-into-existing modes, paginated reads, batched writes, the MongoDB artist cache, the Redis token cache, and partial-failure reporting.

**Phase 2 — Smarter sorting (not implemented).** ML/audio-feature clustering, improved bucket matching, re-run dedupe/merge, queued background jobs for large libraries, and a dry-run preview. None of these exist yet; the Phase 1 architecture (clean service layer, cache seams) is designed to accommodate them.

## Known limitations

- Re-running a sort appends tracks again; the MVP does not deduplicate destination playlists.
- Genre quality depends on Spotify's artist genre metadata and the static normalization table. Spotify currently marks the bulk artist endpoint and its `genres` field as deprecated, with no direct replacement in scope for this genre-based MVP.
- Spotify development mode is limited to five allowlisted users and requires the app owner to have Premium.
- Sorting is request/response based; very large libraries do not yet run as background jobs.

## Security & privacy notes

- Spotify tokens never reach the browser: access tokens stay in Redis, refresh tokens in MongoDB, and the browser only holds HttpOnly cookies (the JWT plus the short-lived OAuth state).
- CORS is restricted to `FRONTEND_URL` with credentials, and the OAuth callback validates the state cookie.
- The app is **copy-only**: it creates playlists and adds tracks, never deletes, reorders, or edits source tracks or playlists, and rejects a source playlist used as a destination.
- The `admin`/`password` credentials in `backend/docker-compose.yml` are local development defaults only — do not reuse them in production. `.env` files are gitignored.
