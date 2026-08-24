"""Stage 1A batch encoding CLI (resumable).

    python -m audio_similarity.cli.encode_holistic \
        --encoder muq_mulan_large --limit 25          # perf gate subset
    python -m audio_similarity.cli.encode_holistic --encoder all      # full run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from audio_similarity.holistic_batch import benchmark_key, run_holistic_batch


def get_encoder(name: str):
    from audio_similarity.holistic_encoders import (
        LaionClapEncoder,
        MuQMulanEncoder,
        mert_5120_encoder,
        mert_generic_encoder,
    )

    if name == "muq_mulan_large":
        return MuQMulanEncoder()
    if name == "mert_5120":
        return mert_5120_encoder()
    if name == "mert_generic":
        return mert_generic_encoder()
    if name == "laion_clap":
        ckpt = Path("models/music_audioset_epoch_15_esc_90.14.pt")
        return LaionClapEncoder(checkpoint_path=str(ckpt) if ckpt.exists() else None)
    raise SystemExit(f"unknown encoder '{name}'")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encoder", required=True,
                        help="muq_mulan_large | mert_5120 | mert_generic | laion_clap | all")
    parser.add_argument("--manifest", default="data/manifests/fma_small.parquet")
    parser.add_argument("--audio-root", default="data/fma/fma_small")
    parser.add_argument("--output-dir", default="artifacts/holistic_stage1a")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    names = ["muq_mulan_large", "mert_5120", "mert_generic", "laion_clap"] \
        if args.encoder == "all" else [args.encoder]

    import pandas as pd

    manifest = pd.read_parquet(args.manifest)
    manifest = manifest[manifest["decode_status"] == "SUCCESS"]
    rows = manifest.to_dict("records")
    if args.limit:
        rows = rows[: args.limit]
    audio_root = Path(args.audio_root)

    for name in names:
        print(f"=== {name}: loading model...")
        t0 = time.perf_counter()
        encoder = get_encoder(name)
        load_sec = time.perf_counter() - t0
        key = benchmark_key(encoder.encoder_id, "", "center5_v1", "pp-v1")

        def progress(done, ok, failed):
            sys.stdout.write(f"\r{name} {done} ok={ok} fail={failed}")
            sys.stdout.flush()

        stats = run_holistic_batch(
            encoder=encoder, encoder_id=encoder.encoder_id,
            revision="", manifest_rows=rows, audio_root=audio_root,
            store_path=Path(args.output_dir) / f"{name}.parquet",
            checkpoint_every=50, progress_callback=progress,
        )
        summary = {"load_sec": round(load_sec, 2), **stats.summary()}
        out = Path(args.output_dir) / f"{name}_batch_summary.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as fh:
            json.dump(summary, fh, indent=1)
        print(f"\n{name}: {json.dumps(summary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
