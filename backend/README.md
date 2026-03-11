# 🎵 Spotify Sorter — README

# What is this?

A web app that lets you log in with your Spotify account and automatically sort your liked songs or playlists into new playlists organized by genre.

---

# Stack

Node/Express, TypeScript, MongoDB Atlas, Redis, Spotify API

---

# Getting Started

**Prerequisites:** Node.js, pnpm

**Clone and install**

```
git clone https://github.com/lennytheworm12/spotify-sorter.git
cd spotify-sorter/backend
pnpm install
```


**Run**

```
pnpm dev
```

Server starts at `http://localhost:3000`. Health check at `GET /health`.

---

# Roadmap

- **Phase 1** — Spotify login + genre-based playlist sorting
- **Phase 2** — ML/audio microservice for smarter sorting
