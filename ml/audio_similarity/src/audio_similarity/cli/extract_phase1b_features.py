"""Extract+cache MIR features for every track in the frozen Phase 1B cases.

Resumable: the feature cache skips completed audio automatically.

    python -m audio_similarity.cli.extract_phase1b_features
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from audio_similarity.mir_features import FeatureCache, cache_stats, feature_config_hash


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="reports/phase1b/frozen_cases.json")
    parser.add_argument("--manifest", default="data/manifests/fma_small.parquet")
    parser.add_argument("--audio-root", default="data/fma/fma_small")
    parser.add_argument("--cache-dir", default="data/phase1b_feature_cache")
    parser.add_argument("--background-pairs", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    from audio_similarity.audio import preprocess_file, AudioDecodeError
    from audio_similarity.manifest import load_manifest
    from audio_similarity.phase1b_freeze import sha256_file

    manifest = load_manifest(args.manifest).set_index("track_id")

    data = json.loads(Path(args.cases).read_text())
    ids: set[int] = set()
    for c in data["cases"]:
        ids.add(c["query_id"])
        ids.update(c["merit_target_neighbors"])
        for lst in c["merit_other_neighbors"].values():
            ids.update(lst)
        ids.update(c["mert_general_neighbors"])
        ids.update(c["conventional_neighbors"])
        ids.update(c["random_negatives"])
        ids.update(c["hard_negatives"])

    # background pairs also need features: deterministic sample of the corpus
    bg_rng = np.random.default_rng(424242)
    all_ids = manifest.index.to_numpy()
    bg_ids = set(int(t) for t in bg_rng.choice(all_ids, size=min(args.background_pairs * 2, len(all_ids)), replace=False))
    todo = sorted(ids | bg_ids)

    print(f"unique tracks: {len(todo)} (cases: {len(ids)}, +background: {len(bg_ids)})")
    cache = FeatureCache(args.cache_dir)

    failures = []
    t_start = time.perf_counter()
    done_before = len(list(Path(args.cache_dir).glob("*.npz"))) if Path(args.cache_dir).exists() else 0

    workers = max(1, args.workers)
    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        _WORKER_CTX: dict = {}

        def _init_worker(cache_dir: str, audio_root: str, manifest_path: str) -> None:
            import pandas as pd

            _WORKER_CTX["cache"] = FeatureCache(cache_dir)
            _WORKER_CTX["manifest"] = pd.read_parquet(manifest_path).set_index("track_id")
            _WORKER_CTX["audio_root"] = audio_root
            extract_features  # warm reference

        def _work(tid: int):
            from audio_similarity.audio import preprocess_file

            row = _WORKER_CTX["manifest"].loc[tid]
            path = Path(_WORKER_CTX["audio_root"]) / row["relative_audio_path"]
            wav = preprocess_file(path)
            _WORKER_CTX["cache"].get_or_extract(wav.numpy().astype(np.float64), 24000)

        done = 0
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                                 initargs=(args.cache_dir, args.audio_root, args.manifest)) as pool:
            futures = {pool.submit(_work, tid): tid for tid in todo}
            for fut in as_completed(futures):
                tid = futures[fut]
                done += 1
                try:
                    fut.result()
                except Exception as exc:
                    failures.append({"track_id": int(tid), "error": str(exc)[:200]})
                if done % 50 == 0:
                    rate = done / max(time.perf_counter() - t_start, 1e-9)
                    print(f"\r[{done}/{len(todo)}] {rate:.2f} clips/s ETA "
                          f"{(len(todo)-done)/max(rate,1e-9)/60:.0f} min", end="", flush=True)
        print()
    else:
        for n, tid in enumerate(todo, 1):
            row = manifest.loc[tid]
            path = Path(args.audio_root) / row["relative_audio_path"]
            try:
                wav = preprocess_file(path)
                feats = cache.get_or_extract(wav.numpy().astype(np.float64), 24000)
            except Exception as exc:
                failures.append({"track_id": int(tid), "error": str(exc)[:200]})
                print(f"\nFAIL {tid}: {str(exc)[:100]}", end="")
                continue
            if n % 25 == 0:
                rate = (n) / max(time.perf_counter() - t_start, 1e-9)
                eta_min = (len(todo) - n) / max(rate, 1e-9) / 60
                print(f"\r[{n}/{len(todo)}] {rate:.2f} clips/s ETA {eta_min:.0f} min", end="", flush=True)
        print()
        stats = cache_stats(args.cache_dir)
        print(json.dumps({"cache": stats, "failures": len(failures),
                          "wall_min": round((time.perf_counter()-t_start)/60, 1),
                          "config_hash": feature_config_hash()}, indent=1))
        if failures:
            Path(out_dir(args.output_dir, "extraction_failures.json")).write_text(json.dumps(failures, indent=1))
        return 0


    def out_dir(base: str, name: str) -> str:
        return str(Path(base).parent / name)


    if __name__ == "__main__":
        raise SystemExit(main())
