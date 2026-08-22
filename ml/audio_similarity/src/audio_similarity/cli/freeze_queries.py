"""Freeze the 24-query human-evaluation set BEFORE inspecting any neighbors.

Phase 1 doc section 15: 24 queries = 3 x 8 FMA Small top-level genres,
selected with a fixed seed from the frozen manifest. Query ids are written
once and never re-rolled.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def freeze_queries(
    manifest_path: str | Path,
    output_csv: str | Path,
    seed: int = 20260822,
    per_genre: int = 3,
) -> pd.DataFrame:
    manifest = pd.read_parquet(manifest_path)
    ok = manifest[manifest["decode_status"] == "SUCCESS"]

    rng = np.random.default_rng(seed)
    picks: list[dict] = []
    genres = sorted(ok["top_genre"].dropna().unique())
    assert len(genres) == 8, f"expected 8 top-level genres, found {len(genres)}"

    for genre in genres:
        pool = ok[ok["top_genre"] == genre]
        chosen = pool.sample(n=min(per_genre, len(pool)), random_state=int(rng.integers(2**31)))
        for _, row in chosen.iterrows():
            picks.append(
                {
                    "track_id": int(row["track_id"]),
                    "top_genre": genre,
                    "artist": row["artist"],
                    "title": row["title"],
                    "seed_used": seed,
                }
            )

    frame = pd.DataFrame(picks).sort_values(["top_genre", "track_id"]).reset_index(drop=True)
    output = Path(output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="data/manifests/fma_small.parquet")
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=20260822)
    args = parser.parse_args()

    frame = freeze_queries(args.manifest, args.output, seed=args.seed)
    print(f"froze {len(frame)} queries ({frame['top_genre'].nunique()} genres x up to 3)")
    print(f"written to {args.output}")
    print("DO NOT regenerate after inspecting retrieval results.")


if __name__ == "__main__":
    main()
