"""Rekey cached MIR features from content-hash keys to source-file SHA-256 keys.

One-time migration for caches created before the audio_key contract.
Decodes each manifest track once (no feature recomputation) to compute its
content hash, then renames the matching npz.

    python -m audio_similarity.cli.rekey_feature_cache --workers 6
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

_CTX: dict = {}


def _init(cache_dir: str, manifest_path: str, audio_root: str) -> None:
    import pandas as pd

    _CTX["dir"] = Path(cache_dir)
    _CTX["manifest"] = pd.read_parquet(manifest_path).set_index("track_id")
    _CTX["root"] = Path(audio_root)


def content_hash_of(tid: int) -> str | None:
    import hashlib

    from audio_similarity.audio import preprocess_file

    row = _CTX["manifest"].loc[tid]
    path = _CTX["root"] / row["relative_audio_path"]
    if not path.exists():
        return None
    try:
        wav = preprocess_file(path)
    except Exception:
        return None
    arr = np.ascontiguousarray(wav.numpy().astype(np.float32))
    return hashlib.sha256(arr.tobytes()).hexdigest()


def rekey_one(tid: int) -> tuple[int, str]:
    sha = str(_CTX["manifest"].at[tid, "audio_sha256"])
    target = _CTX["dir"] / f"{sha[:24]}_"  # prefix match handled by caller scan
    # find existing npz whose stored audio_hash matches the content hash
    chash = content_hash_of(tid)
    if chash is None:
        return tid, "decode-failed"
    src = _CTX["dir"] / f"{chash[:24]}_"
    matches = list(_CTX["dir"].glob(f"{chash[:24]}_*.npz"))
    if not matches:
        return tid, "no-source"
    dest = _CTX["dir"] / f"{sha[:24]}.npz"
    if dest.exists():
        return tid, "already-rekeyed"
    os.rename(matches[0], dest)
    return tid, "rekeyed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", default="data/phase1b_feature_cache")
    parser.add_argument("--manifest", default="data/manifests/fma_small.parquet")
    parser.add_argument("--audio-root", default="data/fma/fma_small")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    done: dict[str, int] = {}
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init,
                             initargs=(args.cache_dir, args.manifest, args.audio_root)) as pool:
        import pandas as pd

        manifest = pd.read_parquet(args.manifest)
        futures = {pool.submit(rekey_one, int(t)): t for t in manifest["track_id"]}
        for n, fut in enumerate(as_completed(futures), 1):
            _, status = fut.result()
            done[status] = done.get(status, 0) + 1
            if n % 200 == 0:
                print(f"{n}/{len(futures)}", flush=True)
    print("rekey complete:", done)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
