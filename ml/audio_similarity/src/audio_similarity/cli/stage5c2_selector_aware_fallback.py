"""Run the two-track Stage 5C.2 selector-aware fallback supplement."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5c2_selector_aware_fallback_supplement import (
    run_targeted_supplement,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root", default=str(Path(__file__).resolve().parents[3])
    )
    args = parser.parse_args()
    result = run_targeted_supplement(args.project_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
