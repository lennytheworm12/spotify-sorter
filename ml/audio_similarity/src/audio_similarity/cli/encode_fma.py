"""Resumable FMA batch encoder.

    python -m audio_similarity.cli.encode_fma \
        --config configs/phase1_fma_small.yaml \
        --manifest data/manifests/fma_small.parquet \
        --audio-root data/fma/fma_small \
        --output-dir artifacts/phase1 \
        [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from audio_similarity.batch import run_batch
from audio_similarity.manifest import load_manifest
from audio_similarity.merit_encoder import MeritEncoder
from audio_similarity.storage import EmbeddingStore, FailureStore, analysis_key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--manifest", default=None, help="overrides config dataset.manifest")
    parser.add_argument("--audio-root", default=None)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    with open(args.config) as fh:
        config = yaml.safe_load(fh)

    manifest_path = Path(args.manifest or config["dataset"]["manifest"])
    rows = load_manifest(manifest_path).to_dict("records")
    if args.limit:
        rows = rows[: args.limit]

    audio_root = Path(args.audio_root or "data/fma/fma_small")
    output_dir = Path(args.output_dir)

    print(f"loading frozen MERT + MERIT heads (device={args.device or 'auto'})...")
    encoder = MeritEncoder.from_pretrained(device=args.device)
    key = analysis_key(encoder.provenance.to_dict())
    embedding_store = EmbeddingStore(output_dir / "embeddings.parquet")
    failure_store = FailureStore(output_dir / "failures.parquet")

    already = embedding_store.count(key)
    print(f"analysis_key {key[:12]}... resuming: {already} completed rows found")

    def progress(done: int, ok: int, failed: int) -> None:
        sys.stdout.write(f"\rencoded {done} (ok={ok}, failed={failed})")
        sys.stdout.flush()

    summary = run_batch(
        manifest_rows=rows,
        encoder=encoder,
        embedding_store=embedding_store,
        failure_store=failure_store,
        audio_root=audio_root,
        checkpoint_every=int(config.get("encode", {}).get("checkpoint_every", 10)),
        progress_callback=progress,
    )
    print()

    report_path = output_dir / "batch_summary.json"
    with open(report_path, "w") as fh:
        json.dump({"provenance": encoder.provenance.to_dict(), "summary": summary.to_dict()}, fh, indent=2)
    print(json.dumps(summary.to_dict(), indent=2))
    print(f"summary written to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
