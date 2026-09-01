"""Stage 5A manifest, parity, and bounded real-model smoke commands."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audio_similarity.stage5a_cache import Stage5ACache
from audio_similarity.stage5a_contract import load_contract
from audio_similarity.stage5a_manifest import (
    build_fma_large_manifest,
    deterministic_smoke_tracks,
    load_fma_large_manifest,
)
from audio_similarity.stage5a_materialize import materialize
from audio_similarity.stage5a_parity import verify_fma_small_parity, write_parity_report


def _write(path: str | Path, value: dict) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _manifest(args) -> dict:
    _, summary = build_fma_large_manifest(
        args.audio_root,
        args.metadata,
        args.output,
        corpus_version=args.corpus_version,
    )
    return summary


def _parity(args) -> dict:
    result = verify_fma_small_parity(
        clap_cache=args.clap_cache,
        muq_cache=args.muq_cache,
        frozen_aggregates=args.frozen_aggregates,
        atol=args.atol,
    )
    write_parity_report(result, args.output)
    return result


def _smoke(args) -> dict:
    contract = load_contract(args.contract)
    frame, manifest_summary = load_fma_large_manifest(args.manifest)
    tracks = deterministic_smoke_tracks(
        frame,
        args.audio_root,
        manifest_sha256=manifest_summary["manifest_logical_sha256"],
        count=args.count,
    )
    if len(tracks) != args.count:
        raise ValueError(f"requested {args.count} smoke tracks but only {len(tracks)} are eligible")

    root = Path(args.contract).resolve().parents[2]
    clap_contract = contract.encoder("laion_clap")
    checkpoint = root / clap_contract.provenance["checkpoint"]
    checkpoint_hash = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if checkpoint_hash != clap_contract.provenance["checkpoint_sha256"]:
        raise ValueError("CLAP checkpoint hash does not match Audio Representation v1")
    from audio_similarity.holistic_encoders import LaionClapEncoder, MuQMulanEncoder

    clap = LaionClapEncoder(checkpoint_path=str(checkpoint))
    muq_contract = contract.encoder("muq_mulan_large")
    muq = MuQMulanEncoder(revision=muq_contract.provenance["revision"])
    with Stage5ACache(args.cache) as cache:
        stats = materialize(
            tracks,
            corpus="fma_large",
            corpus_version=manifest_summary["corpus_version"],
            contract=contract,
            cache=cache,
            encoders={clap.encoder_id: clap, muq.encoder_id: muq},
            output_dir=args.output,
            rows_per_shard=args.rows_per_shard,
        )
        cache_manifest = cache.manifest()
    report = {
        "schema_version": "stage5a-fma-large-smoke-v1",
        "full_fma_large_cold_start_run": False,
        "contract": {
            "path": str(args.contract),
            "artifact_sha256": contract.artifact_sha256,
            "vector_contract_sha256": contract.vector_contract_sha256,
        },
        "manifest": manifest_summary,
        "smoke_selection": {
            "requested_tracks": args.count,
            "stable_track_ids": [track.stable_track_id for track in tracks],
        },
        "materialization": stats.as_dict(),
        "cache": cache_manifest,
    }
    _write(args.report, report)
    return report


def parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[3]
    command = argparse.ArgumentParser(description=__doc__)
    subcommands = command.add_subparsers(dest="command", required=True)
    manifest = subcommands.add_parser("manifest", help="build and freeze FMA Large source accounting")
    manifest.add_argument("--audio-root", required=True)
    manifest.add_argument("--metadata", default=str(root / "data/fma/fma_metadata/tracks.csv"))
    manifest.add_argument("--output", default=str(root / "reports/stage5a/fma_large_manifest.parquet"))
    manifest.add_argument("--corpus-version", required=True)
    manifest.set_defaults(function=_manifest)

    parity = subcommands.add_parser("parity", help="run cache-only FMA Small K=3 parity")
    parity.add_argument("--clap-cache", default=str(root / "artifacts/holistic_stage4a/segments.sqlite"))
    parity.add_argument("--muq-cache", default=str(root / "artifacts/holistic_stage4a_dual/muq_segments.sqlite"))
    parity.add_argument("--frozen-aggregates", default=str(root / "artifacts/holistic_stage4a_dual/dual_aggregates.parquet"))
    parity.add_argument("--output", default=str(root / "reports/stage5a/fma_small_parity.json"))
    parity.add_argument("--atol", type=float, default=2e-6)
    parity.set_defaults(function=_parity)

    smoke = subcommands.add_parser("smoke", help="run at most 500 deterministic real FMA Large tracks")
    smoke.add_argument("--manifest", default=str(root / "reports/stage5a/fma_large_manifest.parquet"))
    smoke.add_argument("--audio-root", required=True)
    smoke.add_argument("--contract", default=str(root / "reports/holistic_stage4a_dual/audio_representation_v1.json"))
    smoke.add_argument("--cache", default=str(root / "artifacts/stage5a/fma_large_smoke.sqlite"))
    smoke.add_argument("--output", default=str(root / "artifacts/stage5a/fma_large_smoke_representations"))
    smoke.add_argument("--report", default=str(root / "reports/stage5a/fma_large_smoke.json"))
    smoke.add_argument("--count", type=int, default=100)
    smoke.add_argument("--rows-per-shard", type=int, default=10_000)
    smoke.set_defaults(function=_smoke)
    return command


def main() -> None:
    args = parser().parse_args()
    result = args.function(args)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
