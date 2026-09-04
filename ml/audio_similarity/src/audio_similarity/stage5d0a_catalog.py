"""Recording identity and deterministic allocation of Spotify seed candidates."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict

from .stage5d0a_spotify import CATALOG_ID, RECIPE

_EDITION = re.compile(r"\s*(?:[-–—]\s*|[([])(?:explicit(?: version)?|clean(?: version)?|radio clean|album version|single version|deluxe(?: edition)?|bonus track(?: version)?)[)\]]?\s*$", re.I)
_VERSION = re.compile(r"\b(?:remix|mix|rmx|live|acoustic|sped\s*up|speed\s*up|slowed|rerecord(?:ed|ing)?|re.record(?:ed|ing)?|version|instrumental|remaster(?:ed)?|demo|edit)\b", re.I)


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value or "").casefold().split())


def canonical_isrc(value):
    compact = re.sub(r"[-\s]", "", unicodedata.normalize("NFKC", value or "")).upper()
    return compact if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}", compact) else None


def recording_title(value):
    value = normalize(value)
    while True:
        stripped = _EDITION.sub("", value).strip()
        if stripped == value:
            return value
        value = stripped


def version_signature(title):
    """Preserve qualified versions, including distinct named remix variants."""
    normalized = recording_title(title)
    if not _VERSION.search(normalized):
        return ""
    # Full qualified display title is conservative for materially different versions.
    return normalized


def same_recording(left, right):
    if version_signature(left["name"]) != version_signature(right["name"]):
        return False
    a = canonical_isrc((left.get("external_ids") or {}).get("isrc"))
    b = canonical_isrc((right.get("external_ids") or {}).get("isrc"))
    if a and a == b:
        return True
    la = [normalize(artist["name"]) for artist in left["artists"]]
    ra = [normalize(artist["name"]) for artist in right["artists"]]
    return (
        recording_title(left["name"]) == recording_title(right["name"])
        and bool(la and ra) and la[0] == ra[0]
        and len(set(la) & set(ra)) / len(set(la) | set(ra)) >= 0.5
        and isinstance(left.get("duration_ms"), int)
        and isinstance(right.get("duration_ms"), int)
        and abs(left["duration_ms"] - right["duration_ms"]) <= 3000
    )


def evidence_key(alias_ranks, spotify):
    ranks = list(alias_ranks.values())
    popularity = spotify.get("popularity")
    return (-len(ranks), min(ranks), sum(ranks) / len(ranks),
            -(popularity if isinstance(popularity, (int, float)) else 0), spotify["id"])


def allocate_catalog(cells):
    """Resolve recording ownership globally, backfill, then redistribute within year."""
    entries = {}
    occurrences = defaultdict(list)
    for cell in sorted(cells, key=lambda row: (row["year"], row["bucket"])):
        for spotify_id, candidate in cell["candidates"].items():
            raw = candidate["spotify"]
            if not raw.get("artists") or not raw.get("name") or not raw.get("duration_ms"):
                continue
            entries.setdefault(spotify_id, raw)
            occurrences[spotify_id].append((cell["year"], cell["bucket"], candidate))

    groups = []
    indexes = defaultdict(set)
    for spotify_id in sorted(entries):
        raw = entries[spotify_id]
        isrc = canonical_isrc((raw.get("external_ids") or {}).get("isrc"))
        fallback = (recording_title(raw["name"]), normalize(raw["artists"][0]["name"]))
        keys = [("title", fallback)] + ([("isrc", isrc)] if isrc else [])
        possible = set().union(*(indexes[key] for key in keys))
        group_index = next((index for index in sorted(possible)
                            if all(same_recording(raw, entries[item]) for item in groups[index])), None)
        if group_index is None:
            group_index = len(groups)
            groups.append([])
        groups[group_index].append(spotify_id)
        for key in keys:
            indexes[key].add(group_index)

    owned = defaultdict(list)
    ownership = []
    for ids in groups:
        by_cell = defaultdict(list)
        for spotify_id in ids:
            for year, bucket, occurrence in occurrences[spotify_id]:
                by_cell[(year, bucket)].append(occurrence)
        options = []
        for (year, bucket), cell_entries in by_cell.items():
            ranks = {}
            for entry in cell_entries:
                for alias, rank in entry["alias_ranks"].items():
                    ranks[alias] = min(ranks.get(alias, rank), rank)
            representative = min(cell_entries, key=lambda row: evidence_key(row["alias_ranks"], row["spotify"]))["spotify"]
            options.append((evidence_key(ranks, representative), bucket, year, ranks, representative))
        key, bucket, year, ranks, raw = min(options, key=lambda option: option[:3])
        recording_id = hashlib.sha256("|".join(ids).encode()).hexdigest()
        row = {
            "recording_id": recording_id,
            "spotify_track_id": raw["id"], "title": raw["name"],
            "artists": [artist["name"] for artist in raw["artists"]],
            "album": raw.get("album", {}).get("name"),
            "release_year": year,
            "spotify_release_date": raw.get("album", {}).get("release_date"),
            "spotify_popularity": raw.get("popularity"),
            "duration_ms": raw["duration_ms"],
            "isrc": canonical_isrc((raw.get("external_ids") or {}).get("isrc")),
            "spotify_raw_isrc": (raw.get("external_ids") or {}).get("isrc"),
            "source_memberships": sorted(f"{y}:{b}" for y, b in by_cell),
            "assigned_bucket": bucket, "assigned_year": year,
            "alias_ranks": ranks, "ranking_key": list(key),
            "collapsed_spotify_ids": ids,
            "all_occurrences": [
                {"year": y, "bucket": b, "spotify_track_id": occurrence["spotify"]["id"],
                 "alias_ranks": occurrence["alias_ranks"]}
                for (y, b), values in sorted(by_cell.items()) for occurrence in values
            ],
        }
        owned[(year, bucket)].append(row)
        ownership.append({"recording_id": recording_id, "spotify_ids": ids,
                          "assigned_year": year, "assigned_bucket": bucket})

    selected = []
    audit = []
    for year in RECIPE["years"]:
        pools = {bucket: sorted(owned[(year, bucket)], key=lambda row: row["ranking_key"])
                 for bucket in RECIPE["aliases"]}
        allocations = {bucket: min(25, len(pool)) for bucket, pool in pools.items()}
        missing = 200 - sum(allocations.values())
        transfers = []
        while missing:
            available = [bucket for bucket in pools if len(pools[bucket]) > allocations[bucket]]
            if not available:
                break
            bucket = min(available, key=lambda name: (-(len(pools[name]) - allocations[name]), name))
            allocations[bucket] += 1
            missing -= 1
            transfers.append(bucket)
        for bucket in pools:
            selected.extend(pools[bucket][:allocations[bucket]])
            audit.append({"year": year, "bucket": bucket, "unique_owned_candidates": len(pools[bucket]),
                          "selected": allocations[bucket], "redistributed_slots_received": transfers.count(bucket)})
    return {
        "schema_version": "stage5d0a-commercial-seed-catalog-input-v1",
        "catalog_design": {"design_id": CATALOG_ID, **RECIPE,
                           "credited_artist_overlap": "Jaccard >= 0.5 with equal primary artist",
                           "duration_tolerance_ms": 3000,
                           "isrc_normalization": "NFKC uppercase; remove spaces/hyphens; invalid identifiers use recording fallback",
                           "dedupe_group_rule": "complete-link; no duration-chain merging",
                           "ownership_ties": "ranking evidence then bucket name then year",
                           "missing_popularity": "zero; does not create popularity evidence"},
        "tracks": selected,
        "allocation_audit": audit,
        "recording_ownership": ownership,
        "unique_spotify_candidates": len(entries),
        "unique_recording_candidates": len(groups),
    }
