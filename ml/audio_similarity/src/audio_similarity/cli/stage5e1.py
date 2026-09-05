"""Prepare and run the Stage 5E.1 four-arm representation comparison."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5e1_contract import prepare_stage5e1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare",))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    if args.command == "prepare":
        print(json.dumps(prepare_stage5e1(root), indent=2))


if __name__ == "__main__":
    main()
