"""Resumable metadata-only Spotify search for the frozen commercial recipe."""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .stage5b1b_artifacts import atomic_json

CATALOG_ID = "POPULAR_COMMERCIAL_2000_2026_SPOTIFY_SEARCH_V1"
ALIASES = {
    "POP": ["pop", "dance pop", "electropop", "synthpop"],
    "HIP_HOP_RAP": ["hip hop", "rap", "trap", "alternative hip hop"],
    "ROCK_ALTERNATIVE": ["rock", "alternative", "indie rock", "pop rock"],
    "RNB_SOUL": ["r&b", "soul", "neo soul", "contemporary r&b"],
    "ELECTRONIC_DANCE": ["electronic", "dance", "edm", "house", "electro"],
    "LATIN": ["latin", "latin pop", "reggaeton", "urbano latino"],
    "COUNTRY": ["country", "contemporary country", "country pop"],
    "GLOBAL_CROSSOVER": ["k-pop", "j-pop", "afrobeats", "amapiano", "world pop"],
}
RECIPE = {
    "catalog_id": CATALOG_ID,
    "years": list(range(2000, 2027)),
    "aliases": ALIASES,
    "target_per_cell": 25,
    "maximum_candidates_per_cell": 75,
    "nominal_slots": 5400,
    "source": "https://api.spotify.com/v1/search",
    "market": "US",
    "page_size": 10,
    "maximum_native_rank_per_alias": 100,
    "collection": "page rounds across all aliases; admit by native rank then alias order",
    "query_template": "year:<year> genre:<alias>",
    "spotify_audio": False,
}


class SpotifyRequestFailed(RuntimeError):
    def __init__(self, status, retry_after=None):
        super().__init__(f"Spotify request failed: HTTP {status}")
        self.status = status
        self.retry_after = retry_after


class SpotifySearch:
    """App credentials never leave the official Spotify token endpoint or memory."""

    def __init__(self, env_path: Path, runtime: Path):
        values = {}
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")
        self.client_id = os.environ.get("SPOTIFY_CLIENT_ID", values.get("SPOTIFY_CLIENT_ID"))
        self.secret = os.environ.get("SPOTIFY_CLIENT_SECRET", values.get("SPOTIFY_CLIENT_SECRET"))
        if not self.client_id or not self.secret:
            raise ValueError("Spotify app credentials are missing")
        self.token = None
        self.expires = 0.0
        self.last_request = 0.0
        self.runtime = runtime

    def _request(self, request):
        wait = max(0, self.last_request + 1.5 - time.monotonic())
        time.sleep(wait)
        self.last_request = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            retry_after = exc.headers.get("Retry-After")
            # Persist the deadline before returning; restarts cannot evade a 429.
            if exc.code == 429:
                try:
                    seconds = max(900.0, float(retry_after or 0))
                except ValueError:
                    seconds = 86400.0
                atomic_json(self.runtime / "spotify_cooldown.json", {
                    "status": 429, "retry_after": retry_after,
                    "not_before_unix": time.time() + seconds,
                })
            raise SpotifyRequestFailed(exc.code, retry_after) from None

    def search(self, query, offset):
        cooldown = self.runtime / "spotify_cooldown.json"
        if cooldown.exists():
            deadline = json.loads(cooldown.read_text())["not_before_unix"]
            if time.time() < deadline:
                raise RuntimeError("Spotify cooldown is active; collection paused")
        if time.monotonic() >= self.expires:
            basic = base64.b64encode(f"{self.client_id}:{self.secret}".encode()).decode()
            token = self._request(urllib.request.Request(
                "https://accounts.spotify.com/api/token",
                data=b"grant_type=client_credentials",
                headers={"Authorization": f"Basic {basic}",
                         "Content-Type": "application/x-www-form-urlencoded"},
            ))
            self.token = token["access_token"]
            self.expires = time.monotonic() + token["expires_in"] - 60
        query_string = urllib.parse.urlencode({
            "q": query, "type": "track", "market": RECIPE["market"],
            "limit": RECIPE["page_size"], "offset": offset,
        })
        return self._request(urllib.request.Request(
            RECIPE["source"] + "?" + query_string,
            headers={"Authorization": f"Bearer {self.token}"},
        ))


def collect_cell(year, bucket, search, directory: Path):
    """Freeze each page before admitting candidates; completed pages are never refetched."""
    directory.mkdir(parents=True, exist_ok=True)
    completed = directory / "cell.json"
    if completed.exists():
        return json.loads(completed.read_text())
    aliases = ALIASES[bucket]
    candidates = {}
    exhausted = set()
    pages = []
    for offset in range(0, RECIPE["maximum_native_rank_per_alias"], 10):
        round_items = []
        for alias_index, alias in enumerate(aliases):
            if alias in exhausted:
                continue
            query = f"year:{year} genre:{alias}"
            page_path = directory / f"alias_{alias_index:02d}_offset_{offset:03d}.json"
            if page_path.exists():
                page = json.loads(page_path.read_text())
                if page["query"] != query or page["offset"] != offset:
                    raise ValueError("Spotify page checkpoint identity changed")
            else:
                payload = search(query, offset)
                if not isinstance(payload.get("tracks", {}).get("items"), list):
                    raise ValueError("Spotify search returned invalid tracks")
                page = {"query": query, "offset": offset, "retrieved_at_unix": time.time(),
                        "response": payload}
                atomic_json(page_path, page)
            pages.append(page_path.name)
            tracks = page["response"]["tracks"]
            items = tracks["items"]
            if not tracks.get("next") or len(items) < 10:
                exhausted.add(alias)
            for position, item in enumerate(items, start=offset + 1):
                if isinstance(item, dict) and item.get("id") and not item.get("is_local"):
                    round_items.append((position, alias_index, item))
        for rank, alias_index, item in sorted(round_items, key=lambda value: value[:2]):
            spotify_id = item["id"]
            if spotify_id not in candidates and len(candidates) < 75:
                candidates[spotify_id] = {"spotify": item, "alias_ranks": {}}
            if spotify_id in candidates:
                ranks = candidates[spotify_id]["alias_ranks"]
                alias = aliases[alias_index]
                ranks[alias] = min(rank, ranks.get(alias, rank))
        if len(candidates) == 75 or len(exhausted) == len(aliases):
            break
    cell = {"catalog_id": CATALOG_ID, "year": year, "bucket": bucket,
            "candidates": candidates, "pages": pages,
            "exhausted_aliases": sorted(exhausted)}
    atomic_json(completed, cell)
    return cell


def collect_catalog(project_root: Path):
    runtime = project_root / ".research_audio/stage5d0a/spotify_catalog"
    runtime.mkdir(parents=True, exist_ok=True)
    config = runtime / "recipe.json"
    if config.exists() and json.loads(config.read_text()) != RECIPE:
        raise ValueError("catalog recipe changed after collection began")
    atomic_json(config, RECIPE)
    api = SpotifySearch(project_root.parents[1] / "backend/.env", runtime)
    cells = []
    for year in RECIPE["years"]:
        for bucket in ALIASES:
            cell = collect_cell(year, bucket, api.search, runtime / f"{year}_{bucket}")
            cells.append(cell)
            print(f"Spotify cells {len(cells)}/216: {year} {bucket}: {len(cell['candidates'])} candidates", flush=True)
    atomic_json(runtime / "collected_cells.json", {"recipe": RECIPE, "cells": cells})
    return cells


if __name__ == "__main__":
    collect_catalog(Path(__file__).resolve().parents[2])
