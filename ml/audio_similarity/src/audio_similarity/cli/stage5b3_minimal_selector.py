"""Run the frozen Stage 5B.3 minimal YouTube-prior selector experiment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b3_minimal_selector import run_minimal_selector


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prior-dir", type=Path,
        default=root / "reports/stage5b_youtube_prior_v1",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=root / "reports/stage5b3_minimal_selector",
    )
    args = parser.parse_args(argv)
    result = run_minimal_selector(args.prior_dir, args.output_dir)
    print(json.dumps({"status": result["status"], **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
