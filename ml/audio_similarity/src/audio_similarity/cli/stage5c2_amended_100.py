"""Materialize and analyze the versioned Stage 5C.2 amended 100-track set."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5c2_amended_100 import run_amendment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root", default=str(Path(__file__).resolve().parents[3])
    )
    args = parser.parse_args()
    print(
        json.dumps(
            run_amendment(args.project_root), ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
