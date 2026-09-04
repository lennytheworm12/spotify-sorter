"""Stage 5C.1 curated Spotify-library materialization experiment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5c1_manifest import freeze_curated_manifest
from audio_similarity.stage5c1_pipeline import run_materialization_attempt
from audio_similarity.stage5c1_analysis import analyze_representations
from audio_similarity.stage5c1_closeout import finalize_stage5c1


def parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[3]
    command = argparse.ArgumentParser(description=__doc__)
    subcommands = command.add_subparsers(dest="command", required=True)
    freeze = subcommands.add_parser("freeze", help="freeze the deterministic curated manifest")
    freeze.add_argument("--project-root", default=str(root))
    freeze.add_argument("--plan", default="configs/stage5c1_curated_25.json")
    freeze.add_argument(
        "--output",
        default="reports/stage5c1_curated_25_materialization/curated_manifest.json",
    )
    materialize = subcommands.add_parser(
        "materialize", help="run exact-ID acquisition and frozen Stage 5A materialization"
    )
    materialize.add_argument("--project-root", default=str(root))
    materialize.add_argument("--run-kind", choices=("first", "cache_rerun"), required=True)
    analyze = subcommands.add_parser(
        "analyze", help="compute frozen CLAP, MuQ, and combined similarity diagnostics"
    )
    analyze.add_argument("--project-root", default=str(root))
    finalize = subcommands.add_parser(
        "finalize", help="write reliability metrics, closeout report, and artifact manifest"
    )
    finalize.add_argument("--project-root", default=str(root))
    return command


def main() -> None:
    args = parser().parse_args()
    if args.command == "freeze":
        manifest, digest = freeze_curated_manifest(
            args.project_root,
            plan_path=args.plan,
            output_path=args.output,
        )
        print(json.dumps({"tracks": len(manifest["tracks"]), "sha256": digest}, indent=2))
    elif args.command == "materialize":
        result = run_materialization_attempt(args.project_root, run_kind=args.run_kind)
        print(json.dumps(result, indent=2, sort_keys=True))
    elif args.command == "analyze":
        result = analyze_representations(args.project_root)
        print(json.dumps(result, indent=2, sort_keys=True))
    elif args.command == "finalize":
        result = finalize_stage5c1(args.project_root)
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
