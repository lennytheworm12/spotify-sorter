"""Run immutable checkpoints of the Stage 5C.2 representative validation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5c2_analysis import analyze_representations
from audio_similarity.stage5c2_closeout import write_closeout
from audio_similarity.stage5c2_discovery import freeze_selected_sources, run_discovery
from audio_similarity.stage5c2_manifest import freeze_representative_manifest
from audio_similarity.stage5c2_pipeline import run_materialization


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "checkpoint",
        choices=("freeze-manifest", "discover", "materialize", "cache-rerun", "analyze", "closeout"),
    )
    args = parser.parse_args()
    if args.checkpoint == "freeze-manifest":
        manifest, digest = freeze_representative_manifest(root)
        result = {"tracks": len(manifest["tracks"]), "sha256": digest}
    elif args.checkpoint == "discover":
        discovery = run_discovery(root)
        selected, digest = freeze_selected_sources(root)
        result = {
            "discovery": discovery["summary"],
            "automated_selections": selected["automated_selection_count"],
            "manual_tail": selected["manual_tail_count"],
            "selected_sources_sha256": digest,
        }
    elif args.checkpoint == "materialize":
        result = run_materialization(root, run_kind="first")
    elif args.checkpoint == "cache-rerun":
        result = run_materialization(root, run_kind="cache_rerun")
    elif args.checkpoint == "analyze":
        result = analyze_representations(root)
    else:
        result = write_closeout(root)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
