"""Freeze the Stage 5B.2 raw YouTube ranking benchmark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b2_youtube_prior import freeze_youtube_prior_manifest


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze-manifest",))
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=root / "reports/stage5b_representative_library_v1/library_snapshot.private.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "reports/stage5b_youtube_prior_v1",
    )
    args = parser.parse_args(argv)
    result = freeze_youtube_prior_manifest(root, args.snapshot, args.output_dir)
    print(json.dumps({
        "status": "STAGE5B2_MANIFEST_FROZEN",
        "track_count": result["manifest"]["sampled_track_count"],
        "manifest_sha256": result["manifest_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
