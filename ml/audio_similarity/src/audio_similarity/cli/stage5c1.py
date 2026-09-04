"""Stage 5C.1 curated Spotify-library materialization experiment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5c1_manifest import freeze_curated_manifest


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


if __name__ == "__main__":
    main()
