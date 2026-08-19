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
