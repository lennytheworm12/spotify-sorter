"""Generate the offline Stage 5B.1C-C remaining-tail diagnostic."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audio_similarity.stage5b1a_models import file_sha256
from audio_similarity.stage5b1c_diagnostic import write_remaining_tail_diagnostic


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay the frozen resolver and diagnose its ten unresolved tracks"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/stage5b1b_fresh_challenge.json"),
    )
    parser.add_argument(
        "--tier2a-dir",
        type=Path,
        default=Path("reports/stage5b1c_a"),
    )
    parser.add_argument(
        "--source-neutral-dir",
        type=Path,
        default=Path("reports/stage5b1c_b"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/stage5b1c_c_diagnostic/remaining_tail_diagnostic.json"),
    )
    args = parser.parse_args()
    output = args.output.resolve()
    diagnostic = write_remaining_tail_diagnostic(
        args.config.resolve(),
        tier2a_dir=args.tier2a_dir.resolve(),
        source_neutral_dir=args.source_neutral_dir.resolve(),
        output_path=output,
    )
    print(
        json.dumps(
            {
                "status": diagnostic["status"],
                **diagnostic["summary"],
                "artifact": str(output),
                "artifact_sha256": file_sha256(output),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
