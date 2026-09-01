"""Encode and analyze the frozen GLAP Stage 2B challenger experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.glap_stage2b import encode_historical_evidence
from audio_similarity.glap_stage2b_analysis import analyze_glap_challenger


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    encode = sub.add_parser("encode")
    encode.add_argument("--root", default=".")
    encode.add_argument("--contract", default="reports/glap_stage2b_challenger_v1/experiment_contract.json")
    encode.add_argument("--model-dir", default="models/glap_stage2b_challenger_v1/hf")
    encode.add_argument("--cache", default="artifacts/glap_stage2b_challenger_v1/embeddings.sqlite")
    encode.add_argument("--device", default="cuda")
    encode.add_argument("--batch-size", type=int, default=1)
    encode.add_argument("--limit", type=int)
    encode.add_argument("--track-id", action="append", type=int, dest="track_ids")
    encode.add_argument("--summary-output")

    analyze = sub.add_parser("analyze")
    analyze.add_argument("--root", default=".")
    analyze.add_argument("--contract", default="reports/glap_stage2b_challenger_v1/experiment_contract.json")
    analyze.add_argument("--cache", default="artifacts/glap_stage2b_challenger_v1/embeddings.sqlite")
    analyze.add_argument("--output-dir", default="reports/glap_stage2b_challenger_v1")
    return parser


def main() -> None:
    args = _parser().parse_args()
    root = Path(args.root).resolve()
    if args.command == "encode":
        result = encode_historical_evidence(
            contract_path=root / args.contract,
            root=root,
            model_dir=root / args.model_dir,
            cache_path=root / args.cache,
            device=args.device,
            batch_size=args.batch_size,
            limit=args.limit,
            track_ids=args.track_ids,
        )
        if args.summary_output:
            output = root / args.summary_output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        result = analyze_glap_challenger(
            contract_path=root / args.contract,
            root=root,
            cache_path=root / args.cache,
            output_dir=root / args.output_dir,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
