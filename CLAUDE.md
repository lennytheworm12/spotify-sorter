# CLAUDE.md

All commands run from the `backend/` directory:

```bash
pnpm dev              # Start dev server with hot reload (tsx watch)
pnpm build            # Compile TypeScript to dist/
pnpm start            # Run compiled output
pnpm test             # Run all tests
pnpm test:coverage    # Run tests with coverage report
```

Run a single test file:

```bash
pnpm exec jest src/__tests__/services/Token.service.test.ts
```

## Architecture

This is a Node.js/Express/TypeScript backend that acts as a proxy between a client and the Spotify Web API. There is no frontend in the repo yet.

### Auth Flow

1. Client hits `GET /auth/spotify/login` → redirected to Spotify's OAuth screen
2. Spotify redirects to `GET /auth/spotify/callback` with an authorization code
3. Backend exchanges the code for a `SpotifyToken` (`spotify.auth.service.ts`), fetches user profile, upserts the user in MongoDB, and issues a signed JWT stored in an HTTP-only cookie
4. All subsequent protected routes use the `verifyUser` middleware, which reads the JWT cookie and attaches `req.user.spotifyId`

### Token Storage Strategy

- **Access tokens** → Redis (`user:{spotifyId}:accessToken`, TTL 3600s) via `token.service.ts`
- **Refresh tokens** → MongoDB (`User` model, `refreshToken` field)
- `getValidAccessToken()` in `token.service.ts` is the central orchestration method: it checks Redis first, then falls back to calling Spotify's refresh endpoint and re-stores both tokens

### Service Layer

- `spotify.auth.service.ts` — OAuth token exchange with Spotify
- `spotify.user.service.ts` — Spotify API calls (user profile, refresh token)
- `spotify.playlist.service.ts` — Spotify API calls for playlists, liked songs, playlist tracks, create playlist, add tracks (all paginating reads use `while (url)` loop with `next` pointer; writes batch by 100)
- `spotify.artist.service.ts` — `getArtistGenres(accessToken, artistIds)` — batches GET `/v1/artists` in groups of 50 (Spotify limit)
- `spotify.service.ts` — **currently empty, do not add code here without discussion**
- `genre.service.ts` — genre bucketing logic: `assignTrackToBucket`, `buildBucketMap`, `buildPlaylistGenreProfile`, `matchBucketToPlaylist`
- `mongo.user.services.ts` — MongoDB CRUD for the `User` model
- `token.service.ts` — Redis access token read/write/delete, plus `getValidAccessToken` orchestration

### Key Conventions

- **Service purity**: Spotify service functions (`spotify.*.service.ts`) accept `accessToken: string` as a direct parameter. They never call `getValidAccessToken` internally. Token orchestration belongs in the controller layer, not inside services. This keeps services as pure data-fetching functions and makes them independently testable.

- **Environment validation**: `src/env.ts` uses Zod to validate all required env vars at startup — the server won't boot if any are missing. Required vars: `MONGO_URI`, `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`, `JWT_SECRET` (min 32 chars), `REDIS_URI`

- **Types**: Spotify API shapes live in `src/types/spotify.types.ts`. App-specific user types in `src/types/user.types.ts`. Express `req.user` is augmented in `src/types/express.d.ts`

- **Mappers**: `src/utils/mappers.ts` converts Spotify API responses to DB models — edit here when Spotify shapes change rather than throughout the codebase

- **Lockfile**: `pnpm-lock.yaml` is committed and is the source of truth for resolved versions. Do not change dependency versions without updating the lockfile. Do not use `npm` or `yarn`.

- **`lastChecked` field**: Present on the `DatabaseUser` schema but intentionally never set yet. It is reserved for Phase 2 cache invalidation logic. Do not remove it or add writes to it.

### Testing Conventions

- Tests live in `src/__tests__/`, organized by layer (`controllers/`, `services/`, `middleware/`, `utils/`)
- Uses `mongodb-memory-server` for MongoDB; Redis and axios are mocked in unit tests
- Config in `jest.config.ts` with a separate `tsconfig.test.json`
- Use `jest.clearAllMocks()` — not `jest.resetAllMocks()`, which wipes mock return values
- Default import mocks require `{ __esModule: true, default: mockFn }` — plain `jest.fn()` will not work for default imports
- Run all tests and confirm they pass after any change before committing

### Route Structure

- `GET /auth/spotify/login` — initiates OAuth
- `GET /auth/spotify/callback` — OAuth callback, sets JWT cookie
- `GET /auth/me` — returns current user (protected)
- `POST /auth/logout` — clears JWT and Redis token (protected)
- `GET /library/liked` — returns raw Spotify liked songs (protected)
- `GET /playlists` — returns user's playlists (protected)
- `GET /playlists/:id/tracks` — returns tracks for a playlist (protected)
- `POST /sort` — genre sort orchestration (protected, Sprint 6)
