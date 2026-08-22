"""Build blinded human-evaluation sheets (Phase 1 doc, section 15).

Outputs (under --output-dir, e.g. reports/human_eval/):
- judgments_factor.csv     360 rows: query x factor x 5 neighbors, blinded
- judgments_ab.csv         MERIT-factor vs general-MERT pairwise trials,
                           randomized side assignment, blinded
- key_factor.csv           rater->track reveal key (NOT shown to the rater)
- key_ab.csv               A/B side mapping (NOT shown to the rater)

Rating rubric (per target factor):
0 unrelated | 1 weak/incidental | 2 clearly useful | 3 strongly similar | X cannot judge
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import pandas as pd

from audio_similarity.manifest import load_manifest
from audio_similarity.retrieval import FACTOR_REPRESENTATIONS, RetrievalIndex

FACTORS = ("melody", "rhythm", "timbre")
NEIGHBORS_PER_FACTOR = 5


def build_sheets(
    embeddings_parquet: str | Path,
    manifest_path: str | Path,
    queries_csv: str | Path,
    output_dir: str | Path,
    seed: int = 20260822,
) -> None:
    manifest = load_manifest(manifest_path)
    queries = pd.read_csv(queries_csv)
    index = RetrievalIndex(embeddings_parquet, manifest)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    judgment_rows: list[dict] = []
    key_rows: list[dict] = []
    ab_rows: list[dict] = []
    ab_key_rows: list[dict] = []

    for _, q in queries.iterrows():
        query_id = int(q["track_id"])
        for factor in FACTORS:
            merit_neighbors = index.search(factor, query_id, k=NEIGHBERS_PER_FACTOR)
            general_neighbors = index.search("mert_general", query_id, k=NEIGHBORS_PER_FACTOR)

            # ---- direct utility sheet (blinded: no representation names) ----
            for n in merit_neighbors:
                cell = f"{query_id}:{factor}:{n.rank}"
                meta = manifest.set_index("track_id").loc[n.track_id]
                judgment_rows.append(
                    {
                        "cell_id": cell,
                        "query_track_id": query_id,
                        "target_factor": factor,
                        "neighbor_rank": n.rank,
                        "rating": "",
                        # rater-visible context only; hides model + genre
                        "neighbor_title": meta["title"],
                        "neighbor_artist": meta["artist"],
                    }
                )
                key_rows.append(
                    {
                        "cell_id": cell,
                        "representation": f"merit_{factor}",
                        "neighbor_track_id": int(n.track_id),
                    }
                )

            # ---- A/B sheet: MERIT target factor vs general MERT ----
            for rank in range(1, NEIGHBORS_PER_FACTOR + 1):
                merit_pick = next(n for n in merit_neighbors if n.rank == rank)
                general_pick = next(n for n in general_neighbors if n.rank == rank)
                if merit_pick.track_id == general_pick.track_id:
                    continue  # identical candidate cannot discriminate
                merit_cell = f"{query_id}:{factor}:{rank}:merit_{merit_pick.track_id}"
                general_cell = f"{query_id}:{factor}:{rank}:gen_{general_pick.track_id}"
                side_a_is_merit = rng.random() < 0.5
                cell_a = merit_cell if side_a_is_merit else general_cell
                cell_b = general_cell if side_a_is_merit else merit_cell

                m_meta = manifest.set_index("track_id")
                a_tid = merit_pick.track_id if side_a_is_merit else general_pick.track_id
                b_tid = general_pick.track_id if side_a_is_merit else merit_pick.track_id
                ab_rows.append(
                    {
                        "ab_id": f"{query_id}:{factor}:{rank}",
                        "question": (
                            f"Which clip is MORE similar to the query specifically in {factor.upper()}?"
                        ),
                        "a_title": m_meta.loc[a_tid, "title"],
                        "a_artist": m_meta.loc[a_tid, "artist"],
                        "b_title": m_meta.loc[b_tid, "title"],
                        "b_artist": m_meta.loc[b_tid, "artist"],
                        "choice": "",  # A / B / Tie / Neither
                    }
                )
                ab_key_rows.append(
                    {
                        "ab_id": ab_rows[-1]["ab_id"],
                        "a_representation": f"merit_{factor}" if side_a_is_merit else "mert_general",
                        "b_representation": "mert_general" if side_a_is_merit else f"merit_{factor}",
                        "a_track_id": int(a_tid),
                        "b_track_id": int(b_tid),
                    }
                )

    pd.DataFrame(judgment_rows).to_csv(out / "judgments_factor.csv", index=False)
    pd.DataFrame(key_rows).to_csv(out / "key_factor.csv", index=False)
    pd.DataFrame(ab_rows).to_csv(out / "judgments_ab.csv", index=False)
    pd.DataFrame(ab_key_rows).to_csv(out / "key_ab.csv", index=False)

    print(f"factor judgment cells: {len(judgment_rows)}")
    print(f"A/B trials: {len(ab_rows)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", required=True)
    parser.add_argument("--manifest", default="data/manifests/fma_small.parquet")
    parser.add_argument("--queries", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=20260822)
    args = parser.parse_args()

    build_sheets(args.embeddings, args.manifest, args.queries, args.output_dir, seed=args.seed)


if __name__ == "__main__":
    main()
