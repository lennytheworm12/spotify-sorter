"""Finalize a completed Stage 5C.2 amended-100 owner review export."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5c2_review_finalize import finalize_review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    print(json.dumps(finalize_review(root, args.export), indent=2))


if __name__ == "__main__":
    main()
