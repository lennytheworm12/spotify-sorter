"""Pre-score deterministic Stage 4 query/reserve allocation."""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict

import pandas as pd


class QuerySelectionError(ValueError):
    pass


def normalize_text(value: object) -> str:
    return " ".join(str(value or "unknown").casefold().split()) or "unknown"


def seeded_key(seed: int, corpus: str, track_id: str) -> str:
    return hashlib.sha256(f"{seed}|{corpus}|{track_id}".encode()).hexdigest()


def largest_remainder(sizes: dict[str, int], target: int) -> dict[str, int]:
    total = sum(sizes.values())
    if target > total or total <= 0:
        raise QuerySelectionError("allocation target exceeds eligible population")
    exact = {key: target * count / total for key, count in sizes.items()}
    allocated = {key: min(sizes[key], int(exact[key])) for key in sizes}
    for key in sorted(sizes, key=lambda k: (-(exact[k] - int(exact[k])), k)):
        if sum(allocated.values()) >= target:
            break
        if allocated[key] < sizes[key]:
            allocated[key] += 1
    # Fill residual capacity if capped cells prevented a complete first pass.
    for key in sorted(sizes):
        while sum(allocated.values()) < target and allocated[key] < sizes[key]:
            allocated[key] += 1
    return allocated


def select_queries(frame: pd.DataFrame, seed: int, per_corpus: int = 40, reserves: int = 10) -> dict:
    required = {"corpus", "track_id", "artist", "genre", "duration_sec", "decode_status"}
    if missing := required - set(frame.columns):
        raise QuerySelectionError(f"manifest missing fields: {sorted(missing)}")
    result = {"seed": seed, "selection_algorithm": "largest_remainder_genre_duration_quintile_artist_cap2_v1", "limitation": "official genre and duration strata proxy structural diversity; they are not manual song-form labels", "corpora": {}}
    for corpus in ("musdb18", "medleydb"):
        data = frame[(frame.corpus == corpus) & (frame.decode_status == "ok")].copy()
        if len(data) < per_corpus + reserves:
            raise QuerySelectionError(f"{corpus} has fewer than {per_corpus + reserves} query-eligible tracks")
        data["genre_norm"] = data.genre.map(normalize_text)
        data["duration_quintile"] = pd.qcut(data.duration_sec.rank(method="first"), 5, labels=False) + 1
        data["stratum"] = data.genre_norm + "|q" + data.duration_quintile.astype(str)
        data["order"] = data.track_id.astype(str).map(lambda track: seeded_key(seed, corpus, track))
        quotas = largest_remainder(data.stratum.value_counts().to_dict(), per_corpus)
        artist_counts: Counter[str] = Counter()
        selected = []
        # Pass one respects cap; pass two is the explicitly allowed infeasible fallback.
        for enforce_cap in (True, False):
            for stratum in sorted(quotas):
                need = quotas[stratum] - sum(row["stratum"] == stratum for row in selected)
                if need <= 0:
                    continue
                candidates = data[data.stratum == stratum].sort_values(["order", "track_id"]).to_dict("records")
                for row in candidates:
                    if any(str(x["track_id"]) == str(row["track_id"]) for x in selected):
                        continue
                    artist = normalize_text(row["artist"])
                    if enforce_cap and artist_counts[artist] >= 2:
                        continue
                    selected.append(row); artist_counts[artist] += 1; need -= 1
                    if need == 0:
                        break
        if len(selected) != per_corpus:
            raise QuerySelectionError(f"could not allocate {per_corpus} {corpus} queries")
        selected_ids = {str(row["track_id"]) for row in selected}
        reserve_rows = data[~data.track_id.astype(str).isin(selected_ids)].sort_values(["order", "track_id"]).head(reserves).to_dict("records")
        ordered = sorted(selected, key=lambda row: (row["order"], str(row["track_id"])))
        query_rows = [{"track_id": str(row["track_id"]), "stratum": row["stratum"], "tranche": "INTERIM" if index < 20 else "CONTINUATION", "order": index} for index, row in enumerate(ordered)]
        result["corpora"][corpus] = {"queries": query_rows, "technical_reserves": [{"track_id": str(row["track_id"]), "reserve_order": index} for index, row in enumerate(reserve_rows)]}
    return result
