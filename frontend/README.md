# Spotify Playlist Organizer — Frontend

React + TypeScript + Vite frontend for the Spotify Sorter app. It talks to the
Express backend in `../backend` and never stores Spotify tokens in the browser;
auth is handled server-side with an HTTP-only JWT cookie.

## Getting started

```bash
pnpm install
pnpm dev
```

The app expects the backend to be running at `http://127.0.0.1:3000`. To point
at a different backend, copy `.env.example` to `.env.local` and set
`VITE_API_URL`. `VITE_API_URL` is browser-facing and stays on the 127.0.0.1
loopback because Spotify rejects `localhost` for local OAuth redirects.

The Vite dev server binds `0.0.0.0:5173` (all interfaces) so forwarded traffic
can reach it — e.g. when the frontend runs inside WSL and Windows `netsh
portproxy` forwards the Windows `127.0.0.1:5173` port to the WSL private IP.
That bind address is not a browser URL: open the app at
`http://127.0.0.1:5173` in the Windows browser, which the portproxy routes to
the WSL dev server.

## Scripts

- `pnpm dev` — Vite dev server bound to `0.0.0.0:5173`, browsed at `http://127.0.0.1:5173`
- `pnpm build` — TypeScript check + production build
- `pnpm lint` — ESLint
- `pnpm preview` — preview the production build

## Notes

- `listening-room-hero.png` is the generated hero image for the logged-out
  screen. Keep it in `src/assets`.
- All API requests send `credentials: 'include'` so the JWT cookie is
  forwarded. Starting OAuth is a full browser navigation to
  `GET /auth/spotify/login`.
- Transport failures are normalized: raw `Failed to fetch` network errors are
  replaced with a friendly backend-unreachable message. The `/auth/me` session
  check retries only network failures (twice, with short backoff) and
  auto-refetches when the browser reconnects; a manual Retry remains.
- The authenticated dashboard has in-page Setup / Results / Undo navigation.
- In safe-copy mode, each selected destination copy can be given a custom
  trimmed, nonblank name up to 100 characters (default
  `"<Original playlist name> — Spotify Sorter Copy"`); originals are unchanged.
- Undo UI: all buckets are shown as Applied by default; checking a row only
  selects it for undo and Spotify is not changed until the user presses Undo.
  Select-all-applied and clear-selection are available. Undo is snapshot-safe
  and rebuilds each destination as its baseline plus still-applied buckets;
  undoing everything on an empty baseline leaves the playlist present but
  empty — undo never deletes or unfollows playlists.
