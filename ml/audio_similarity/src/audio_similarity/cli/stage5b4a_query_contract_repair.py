"""Generate and evaluate the bounded Stage 5B.4A query-contract supplement."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b4a_query_contract_repair import (
    OUTPUT_DIRECTORY,
    run_repaired_discovery,
    write_artifact_manifest,
    write_human_review,
    write_offline_artifacts,
    write_report,
)


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("offline", "discover", "build-review", "finalize")
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / OUTPUT_DIRECTORY,
    )
    args = parser.parse_args(argv)
    if args.action == "offline":
        output = write_offline_artifacts(project_root, args.output_dir)
    elif args.action == "discover":
        output = run_repaired_discovery(project_root, args.output_dir)["summary"]
    elif args.action == "build-review":
        output = {"human_review": str(write_human_review(args.output_dir))}
    else:
        output = write_report(args.output_dir)
        manifest = write_artifact_manifest(project_root, args.output_dir)
        output["artifact_manifest"] = str(args.output_dir / "artifact_manifest.json")
        output["status"] = manifest["status"]
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
