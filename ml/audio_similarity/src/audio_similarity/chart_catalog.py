"""Resumable chart-to-Spotify metadata work; no media or batch execution path."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .chart_seed_pilot import run as collect_charts, write_json
from .stage5b1b_artifacts import atomic_json
from .stage5d0a_catalog import normalize, same_recording
from .stage5d0a_spotify import SpotifySearch

CATALOG_ID = "CHART_ANCHORED_2006_2026_METADATA_V1"


@contextmanager
def metadata_lock(runtime):
    """One metadata worker, with no lock on unrelated Spotify development."""
    with (runtime / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("chart metadata worker is already running") from None
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def sources():
    """Archive candidates, not assertions that each archive exists."""
    result = []
    for year in range(2006, 2026):
        result.append(dict(provider="aria", territory="AU", chart_year=year,
                           url=f"https://www.aria.com.au/charts/{year}/singles-chart"))
        for territory, chart in (("JP", "hot100_year"), ("US", "uhot100_year")):
            result.append(dict(provider="billboard_japan", territory=territory,
                               chart_year=year,
                               url=f"https://www.billboard-japan.com/charts/detail?a={chart}&year={year}"))
    return result


def text_key(value):
    # Only typography; version/featured text is intentionally retained.
    return re.sub(r"[^\w]+", " ", normalize(value), flags=re.UNICODE).strip()


def song_key(entry):
    identity = [text_key(entry["title"]), text_key(entry["artist"])]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def song_candidates(entries):
    songs = {}
    for entry in entries:
        key = song_key(entry)
        song = songs.setdefault(key, {"song_key": key, "title": entry["title"],
                                     "artist": entry["artist"], "appearances": []})
        song["appearances"].append(entry)
    return [songs[key] for key in sorted(songs)]


def match_song(song, tracks):
    """Conservative exact title/credit match; ambiguities remain reviewable."""
    accepted = []
    for track in tracks:
        if not isinstance(track, dict) or not track.get("id") or track.get("is_local"):
            continue
        artists = track.get("artists") or []
        if not artists or type(track.get("duration_ms")) is not int or track["duration_ms"] <= 0:
            continue
        credits = text_key(" ".join(artist.get("name", "") for artist in artists))
        title = text_key(track.get("name", ""))
        if title and credits and title == text_key(song["title"]) and credits == text_key(song["artist"]):
            accepted.append(track)
    accepted = sorted({track["id"]: track for track in accepted}.values(), key=lambda t: t["id"])
    if not accepted:
        return {"status": "NO_EXACT_METADATA_MATCH", "spotify": None}
    # Complete-link rather than allowing duration chains to merge versions.
    if any(not same_recording(a, b) for i, a in enumerate(accepted) for b in accepted[i + 1:]):
        return {"status": "AMBIGUOUS_RECORDINGS", "spotify": None,
                "candidate_ids": [track["id"] for track in accepted]}
    return {"status": "MATCHED_METADATA", "spotify": accepted[0],
            "equivalent_spotify_ids": [track["id"] for track in accepted]}


def resolve_songs(songs, search, runtime, limit, local_tracks=()):
    """One native Top-10 metadata search per literal song; checkpoint before match."""
    runtime.mkdir(parents=True, exist_ok=True)
    requested = 0
    matches = []
    by_title = {}
    for track in local_tracks:
        by_title.setdefault(text_key(track.get("name", "")), []).append(track)
    for song in songs:
        query = f"{song['title']} {song['artist']}"
        path = runtime / f"{song['song_key']}.json"
        if path.exists():
            page = json.loads(path.read_text())
            if page["query"] != query:
                raise ValueError("Spotify checkpoint query mismatch")
        else:
            local = match_song(song, by_title.get(text_key(song["title"]), []))
            if local["status"] == "MATCHED_METADATA":
                matches.append({"song": song, "query": query, "metadata_source": "EXISTING_SPOTIFY_METADATA", **local})
                continue
            if requested >= limit:
                matches.append({"song": song, "status": "PENDING", "spotify": None})
                continue
            # Provider errors propagate: no empty-success checkpoint or retry loop.
            payload = search(query, 0)
            if not isinstance(payload.get("tracks", {}).get("items"), list):
                raise ValueError("invalid Spotify search response")
            page = {"query": query, "response": payload, "market": "US",
                    "retrieved_at": datetime.now(timezone.utc).isoformat()}
            atomic_json(path, page)
            requested += 1
        result = match_song(song, page["response"]["tracks"]["items"])
        matches.append({"song": song, "query": query, "metadata_source": "CHART_SPOTIFY_SEARCH", **result})
    return matches


def deduplicate(matches):
    groups = []
    for match in sorted(matches, key=lambda row: row["song"]["song_key"]):
        track = match.get("spotify")
        if not track:
            continue
        group = next((g for g in groups if all(same_recording(track, t) for t in g["members"])), None)
        if group is None:
            group = {"members": [], "song_keys": [], "appearances": []}
            groups.append(group)
        group["members"].append(track)
        group["song_keys"].append(match["song"]["song_key"])
        group["appearances"].extend(match["song"]["appearances"])
    return [{"spotify": min(g["members"], key=lambda t: t["id"]),
             "spotify_ids": sorted({t["id"] for t in g["members"]}),
             "song_keys": sorted(g["song_keys"]), "appearances": g["appearances"],
             "acquisition_eligible": False} for g in groups]


def coverage(charts, matches, recordings):
    artists = Counter(r["spotify"]["artists"][0]["name"] for r in recordings)
    return {"catalog_id": CATALOG_ID, "status": "PARTIAL_METADATA_CATALOG",
            "chart_appearances": len(charts["entries"]),
            "literal_song_candidates": len(matches), "recordings_matched": len(recordings),
            "matching_outcomes": dict(Counter(m["status"] for m in matches)),
            "matched_metadata_sources": dict(Counter(m.get("metadata_source") for m in matches if m.get("spotify"))),
            "appearances_by_market": dict(Counter(e["territory"] for e in charts["entries"])),
            "appearances_by_year": dict(Counter(str(e["chart_year"]) for e in charts["entries"])),
            "source_failures": [s for s in charts["sources"] if s["status"] != "PARSED"],
            "largest_primary_artist_counts": artists.most_common(20),
            "coverage_gaps": ["2026 dated charts", "Korean domestic charts",
                              "broader regional/style charts", "genre coverage not measured"],
            "media_downloads": 0, "acquisition_enabled": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["collect", "match", "report"])
    parser.add_argument("--max-requests", type=int, default=50)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    if not 0 <= args.max_requests <= 500:
        parser.error("max-requests must be 0..500; explicit bounded invocations only")
    root = args.root
    runtime = root / ".research_audio/chart_catalog_v1"
    runtime.mkdir(parents=True, exist_ok=True)
    with metadata_lock(runtime):
        execute(args, runtime)


def execute(args, runtime):
    root = args.root
    report = root / "reports/stage5d_chart_catalog_v1"
    chart_path = report / "chart_appearances.json"
    if args.command == "collect":
        write_json(report / "source_plan.json", {"catalog_id": CATALOG_ID, "sources": sources()})
        collect_charts(root, sources(), chart_path)
        return
    charts = json.loads(chart_path.read_text())
    songs = song_candidates(charts["entries"])
    def offline_search(query, offset):
        raise RuntimeError("report mode must never issue a request")
    search = offline_search
    limit = 0
    if args.command == "match":
        search = SpotifySearch(root.parents[1] / "backend/.env", runtime).search
        limit = args.max_requests
    existing = root / ".research_audio/stage5d0a/spotify_catalog/collected_cells.json"
    local_tracks = {}
    if existing.exists():
        for cell in json.loads(existing.read_text())["cells"]:
            for candidate in cell["candidates"].values():
                raw = candidate["spotify"]
                local_tracks[raw["id"]] = raw
    matches = resolve_songs(songs, search, runtime / "spotify", limit, local_tracks.values())
    recordings = deduplicate(matches)
    metrics = coverage(charts, matches, recordings)
    snapshot = {"matches": matches, "recordings": recordings, "metrics": metrics,
                "existing_metadata_sha256": hashlib.sha256(existing.read_bytes()).hexdigest() if existing.exists() else None,
                "chart_input_sha256": hashlib.sha256(chart_path.read_bytes()).hexdigest()}
    # Content-addressed reports never overwrite earlier matching evidence.
    identity = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    write_json(report / f"matching_{identity}.json", snapshot)
    atomic_json(runtime / "status.json", metrics)
    print(f"Snapshot: {report.name}/matching_{identity}.json")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
