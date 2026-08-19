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
pnpm dev                # http://localhost:3000
```

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
  for playlist sources)

## Notes

- Auth boundary: stateless JWT in an HttpOnly cookie; access token in Redis
  (1-hour TTL); refresh token in MongoDB. This is not server-side sessions.
- `POST /sort` validates its body with Zod and returns per-bucket
  success/failure results plus excluded playlists; one bucket failing does not
  roll back others.
- `createBackup: true` (playlist sources only) snapshots the copyable source
  tracks into a new private `"<name> — Spotify Sorter Backup"` playlist before
  any genre output work; backup failure aborts the sort. A playlist source can
  never be used as a sort destination (`sort-into-existing`).
- The backend never deletes or edits source playlists/tracks — sort is
  copy-only.
