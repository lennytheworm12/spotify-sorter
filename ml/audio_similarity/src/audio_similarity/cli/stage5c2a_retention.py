"""Prepare, run, or audit Stage 5C.2A persistent exact-source retention."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5c2a_browser import validate_browser_playback
from audio_similarity.stage5c2a_closeout import write_stage5c2a_closeout
from audio_similarity.stage5c2a_retention import (
    closeout_retention,
    prepare_retention,
    run_retention,
    validate_local_playback,
)


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "checkpoint",
        choices=("prepare", "run", "audit", "playback", "browser", "closeout"),
    )
    args = parser.parse_args()
    if args.checkpoint == "prepare":
        result = prepare_retention(root)
    elif args.checkpoint == "run":
        result = run_retention(root)
    elif args.checkpoint == "audit":
        result = closeout_retention(root)
    elif args.checkpoint == "playback":
        result = validate_local_playback(root)
    elif args.checkpoint == "browser":
        result = validate_browser_playback(root)
    else:
        result = write_stage5c2a_closeout(root)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
