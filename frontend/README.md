# Spotify Playlist Organizer — Frontend

React + TypeScript + Vite frontend for the Spotify Sorter app. It talks to the
Express backend in `../backend` and never stores Spotify tokens in the browser;
auth is handled server-side with an HTTP-only JWT cookie.

## Getting started

```bash
pnpm install
pnpm dev
```

The app expects the backend to be running at `http://localhost:3000`. To point
at a different backend, copy `.env.example` to `.env.local` and set
`VITE_API_URL`.

## Scripts

- `pnpm dev` — Vite dev server
- `pnpm build` — TypeScript check + production build
- `pnpm lint` — ESLint
- `pnpm preview` — preview the production build

## Notes

- `listening-room-hero.png` is the generated hero image for the logged-out
  screen. Keep it in `src/assets`.
- All API requests send `credentials: 'include'` so the JWT cookie is
  forwarded. Starting OAuth is a full browser navigation to
  `GET /auth/spotify/login`.
